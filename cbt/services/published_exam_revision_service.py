import hashlib
import json
from pathlib import PurePath

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from academic.models import AcademicWorkflow
from academic.services.academic_authority_service import AcademicAuthorityService

from cbt.models import (
    CBTExam,
    CBTExamStatus,
    PublishedExamRevision,
    PublishedExamQuestion,
    PublishedExamChoice,
    PublishedExamBlank,
    PublishedExamMatchingItem,
    PublishedQuestionGradingDefinition,
    PublishedExamMedia,
    QuestionType,
)
from .cbt_actor_service import CBTActorService


class PublishedExamRevisionService:
    SCHEMA_VERSION = 1

    @staticmethod
    def get_current_for_exam(exam):
        revision = (
            PublishedExamRevision.objects.filter(
                exam=exam,
                status=PublishedExamRevision.Status.FINALIZED,
            )
            .order_by("-revision_number")
            .first()
        )
        if revision is None:
            raise ValidationError("This published CBT exam has no finalized revision.")
        return revision

    @staticmethod
    def ensure_current_for_exam(exam):
        revision = (
            PublishedExamRevision.objects.filter(
                exam=exam,
                status=PublishedExamRevision.Status.FINALIZED,
            ).order_by("-revision_number").first()
        )
        if revision is not None:
            return revision
        return PublishedExamRevisionService.publish(
            exam=exam,
            actor=None,
            _backfill=True,
        )

    @staticmethod
    @transaction.atomic
    def publish(*, exam, actor, _backfill=False):
        exam = (
            CBTExam.objects.select_for_update()
            .get(pk=exam.pk)
        )
        if exam.status == CBTExamStatus.PUBLISHED:
            current = PublishedExamRevision.objects.filter(
                exam=exam,
                status=PublishedExamRevision.Status.FINALIZED,
            ).order_by("-revision_number").first()
            if current is not None:
                return current
            if not _backfill:
                raise ValidationError(
                    "Published exam revision is missing; run the CBT revision backfill."
                )

        if _backfill:
            if exam.status != CBTExamStatus.PUBLISHED or exam.created_by_id is None:
                raise ValidationError("Only complete published exams can be backfilled.")
            if not exam.exam_questions.exists():
                raise ValidationError("Published exam has no generated questions to freeze.")
            publisher = exam.created_by
        else:
            from .cbt_exam_service import CBTExamService
            CBTExamService.validate_for_publish(exam)
            section = exam.classroom.grade_level.section if exam.classroom_id else None
            AcademicAuthorityService.require_approval_authority(
                actor=actor,
                workflow=AcademicWorkflow.CBT_PUBLISH,
                subject=exam.subject,
                section=section,
                academic_year=exam.session.academic_year,
                creator=exam.created_by,
            )
            try:
                publisher = CBTActorService.resolve_teacher(actor)
            except ValidationError:
                # Administrative users can hold publication authority without a
                # tenant Teacher profile; retain the exam's accountable creator.
                publisher = exam.created_by
            if publisher is None:
                raise ValidationError("A publisher identity is required.")
        next_number = (
            PublishedExamRevision.objects.filter(exam=exam)
            .aggregate(value=Max("revision_number"))["value"]
            or 0
        ) + 1
        revision = PublishedExamRevision.objects.create(
            exam=exam,
            revision_number=next_number,
            schema_version=PublishedExamRevisionService.SCHEMA_VERSION,
            title=exam.title,
            instructions=exam.instructions,
            duration_minutes=exam.duration_minutes,
            shuffle_questions=exam.shuffle_questions,
            shuffle_options=exam.shuffle_options,
            allow_back_navigation=exam.allow_back_navigation,
            auto_submit=exam.auto_submit,
            published_by=publisher,
        )

        exam_questions = (
            exam.exam_questions.select_related("question_version")
            .prefetch_related(
                "question_version__options",
                "question_version__attachments",
                "question_version__short_answer_definition__accepted_answers",
                "question_version__fill_blank_definition__blanks__accepted_answers",
                "question_version__matching_definition__pairs",
            )
            .order_by("order")
        )
        canonical_questions = [
            PublishedExamRevisionService._freeze_question(revision, item)
            for item in exam_questions
        ]
        canonical = {
            "schema_version": revision.schema_version,
            "exam": {
                "title": revision.title,
                "instructions": revision.instructions,
                "duration_minutes": revision.duration_minutes,
                "shuffle_questions": revision.shuffle_questions,
                "shuffle_options": revision.shuffle_options,
                "allow_back_navigation": revision.allow_back_navigation,
                "auto_submit": revision.auto_submit,
            },
            "questions": canonical_questions,
        }
        content_hash = hashlib.sha256(
            json.dumps(
                canonical,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        published_at = timezone.now()
        PublishedExamRevision.objects.filter(pk=revision.pk).update(
            status=PublishedExamRevision.Status.FINALIZED,
            content_hash=content_hash,
            published_at=published_at,
        )
        CBTExam.objects.filter(pk=exam.pk).update(
            status=CBTExamStatus.PUBLISHED,
            updated_at=published_at,
        )
        revision.refresh_from_db()
        return revision

    @staticmethod
    def _freeze_question(revision, exam_question):
        version = exam_question.question_version
        question = PublishedExamQuestion.objects.create(
            revision=revision,
            source_exam_question=exam_question,
            source_question_version=version,
            question_type=version.question_type,
            question_text=version.text,
            instructions=version.instructions,
            marks=exam_question.marks,
            order=exam_question.order,
        )
        interaction = {}
        grading = {}

        if version.question_type in {
            QuestionType.SINGLE_CHOICE,
            QuestionType.MULTIPLE_CHOICE,
            QuestionType.TRUE_FALSE,
        }:
            choice_rows = []
            correct_keys = []
            for index, option in enumerate(version.options.all().order_by("order"), 1):
                key = f"choice-{index}"
                PublishedExamChoice.objects.create(
                    published_question=question,
                    source_option=option,
                    key=key,
                    text=option.text,
                    order=index,
                )
                choice_rows.append({"key": key, "text": option.text, "order": index})
                if option.is_correct:
                    correct_keys.append(key)
            interaction["choices"] = choice_rows
            grading["correct_choice_keys"] = correct_keys

        elif version.question_type == QuestionType.SHORT_ANSWER:
            definition = version.short_answer_definition
            grading = {
                "case_sensitive": definition.case_sensitive,
                "trim_whitespace": definition.trim_whitespace,
                "accepted_answers": list(
                    definition.accepted_answers.order_by("id").values_list("answer", flat=True)
                ),
            }

        elif version.question_type == QuestionType.NUMERIC:
            definition = version.numeric_answer_definition
            grading = {
                "expected_value": str(definition.expected_value),
                "tolerance": str(definition.tolerance),
            }

        elif version.question_type == QuestionType.FILL_BLANK:
            definition = version.fill_blank_definition
            blanks = []
            grading_blanks = []
            for index, blank in enumerate(definition.blanks.all().order_by("position"), 1):
                key = f"blank-{index}"
                PublishedExamBlank.objects.create(
                    published_question=question,
                    source_blank=blank,
                    key=key,
                    position=blank.position,
                )
                blanks.append({"key": key, "position": blank.position})
                grading_blanks.append({
                    "key": key,
                    "accepted_answers": list(
                        blank.accepted_answers.order_by("id").values_list("answer", flat=True)
                    ),
                })
            interaction["blanks"] = blanks
            grading = {
                "case_sensitive": definition.case_sensitive,
                "blanks": grading_blanks,
            }

        elif version.question_type == QuestionType.MATCHING:
            definition = version.matching_definition
            left = []
            right = []
            mapping = {}
            for index, pair in enumerate(definition.pairs.all().order_by("order"), 1):
                left_key, right_key = f"left-{index}", f"right-{index}"
                PublishedExamMatchingItem.objects.create(
                    published_question=question,
                    source_pair=pair,
                    key=left_key,
                    side=PublishedExamMatchingItem.Side.LEFT,
                    text=pair.left_text,
                    order=index,
                )
                PublishedExamMatchingItem.objects.create(
                    published_question=question,
                    source_pair=pair,
                    key=right_key,
                    side=PublishedExamMatchingItem.Side.RIGHT,
                    text=pair.right_text,
                    order=index,
                )
                left.append({"key": left_key, "text": pair.left_text, "order": index})
                right.append({"key": right_key, "text": pair.right_text, "order": index})
                mapping[left_key] = right_key
            interaction = {
                "left": left,
                "right": right,
                "shuffle_right_items": definition.shuffle_right_items,
            }
            grading["correct_matches"] = mapping

        elif version.question_type == QuestionType.ESSAY:
            definition = version.essay_definition
            interaction = {
                "minimum_words": definition.minimum_words,
                "maximum_words": definition.maximum_words,
            }
            grading = {
                "marking_guide": definition.marking_guide,
                "model_answer": definition.model_answer,
                "minimum_words": definition.minimum_words,
                "maximum_words": definition.maximum_words,
            }

        question.interaction_config = interaction
        question.save(update_fields=["interaction_config"])
        PublishedQuestionGradingDefinition.objects.create(
            published_question=question,
            definition=grading,
        )
        media_rows = []
        for attachment in version.attachments.all().order_by("order", "id"):
            digest = hashlib.sha256()
            size = 0
            try:
                attachment.file.open("rb")
                for chunk in attachment.file.chunks():
                    digest.update(chunk)
                    size += len(chunk)
            except Exception as exc:
                raise ValidationError(
                    f"Unable to freeze media for question version {version.pk}."
                ) from exc
            finally:
                try:
                    attachment.file.close()
                except Exception:
                    pass
            filename = PurePath(attachment.file.name).name
            PublishedExamMedia.objects.create(
                published_question=question,
                source_attachment=attachment,
                filename=filename,
                caption=attachment.caption,
                order=attachment.order,
                storage_reference=attachment.file.name,
                content_sha256=digest.hexdigest(),
                size_bytes=size,
            )
            media_rows.append({
                "filename": filename,
                "caption": attachment.caption,
                "order": attachment.order,
                "content_sha256": digest.hexdigest(),
                "size_bytes": size,
            })
        return {
            "order": exam_question.order,
            "question_type": version.question_type,
            "question_text": version.text,
            "instructions": version.instructions,
            "marks": str(exam_question.marks),
            "interaction": interaction,
            "grading": grading,
            "media": media_rows,
        }
