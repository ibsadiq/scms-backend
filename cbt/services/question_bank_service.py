from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max

from ..models import (
    Question,
    QuestionVersion,
    QuestionLearningObjective,
    QuestionOption,
    QuestionStatus,
    QuestionType,
    ShortAnswerDefinition,
    ShortAnswerVariant,
    NumericAnswerDefinition,
    FillBlankDefinition,
    FillBlankItem,
    FillBlankAcceptedAnswer,
    EssayDefinition,
    MatchingDefinition,
    MatchingPair,
    QuestionReview,
)
from .question_curriculum_service import QuestionCurriculumService


class QuestionBankService:

    @staticmethod
    @transaction.atomic
    def create_question(
        *,
        subject,
        grade_levels,
        question_type,
        text,
        created_by,
        bank=None,
        topic=None,
        subtopic=None,
        difficulty=None,
        default_marks=1,
        instructions="",
        explanation="",
        options=None,
        answer_definition=None,
    ):
        """
        Creates the stable Question record and Version 1.

        `options` is used for:
            SINGLE_CHOICE
            MULTIPLE_CHOICE
            TRUE_FALSE

        `answer_definition` is used for:
            SHORT_ANSWER
            NUMERIC
            FILL_BLANK
            ESSAY
            MATCHING
        """

        grade_levels = list(grade_levels)

        if not grade_levels:
            raise ValidationError(
                "Question must apply to at least one grade level."
            )

        question = Question(
            bank=bank,
            subject=subject,
            topic=topic,
            subtopic=subtopic,
            question_type=question_type,
            default_marks=default_marks,
            created_by=created_by,
        )

        if difficulty:
            question.difficulty = difficulty

        question.full_clean()
        question.save()

        question.grade_levels.set(grade_levels)

        QuestionCurriculumService.validate_question_grade_scope(
            question=question,
            grade_levels=grade_levels,
        )

        QuestionCurriculumService.validate_bank_grade_scope(
            question=question,
            grade_levels=grade_levels,
        )

        version = QuestionBankService._create_version(
            question=question,
            text=text,
            instructions=instructions,
            explanation=explanation,
            created_by=created_by,
            options=options or [],
            answer_definition=answer_definition or {},
        )

        question.current_version = version

        question.save(
            update_fields=[
                "current_version",
                "updated_at",
            ]
        )

        return question

    @staticmethod
    @transaction.atomic
    def create_new_version(
        *,
        question,
        text,
        created_by,
        instructions="",
        explanation="",
        options=None,
        answer_definition=None,
    ):
        """
        Creates a new immutable version of an existing question.

        Existing versions are never modified.
        """

        if question.status == QuestionStatus.ARCHIVED:
            raise ValidationError(
                "Archived questions cannot be edited."
            )

        version = QuestionBankService._create_version(
            question=question,
            text=text,
            instructions=instructions,
            explanation=explanation,
            created_by=created_by,
            options=options or [],
            answer_definition=answer_definition or {},
        )

        question.current_version = version

        # Any modification to an approved question must go
        # through review again.
        if question.status == QuestionStatus.APPROVED:
            question.status = QuestionStatus.DRAFT

        question.save(
            update_fields=[
                "current_version",
                "status",
                "updated_at",
            ]
        )

        return version

    @staticmethod
    @transaction.atomic
    def _create_version(
        *,
        question,
        text,
        instructions,
        explanation,
        created_by,
        options,
        answer_definition,
    ):
        """
        Creates an immutable question version.

        select_for_update() prevents two concurrent requests
        from generating the same version number.
        """

        locked_question = (
            Question.objects
            .select_for_update()
            .get(pk=question.pk)
        )

        if not text or not text.strip():    
            raise ValidationError(
                {
                    "text": "Question text is required."
                }
            )

        latest_version = (
            QuestionVersion.objects
            .filter(question=locked_question)
            .aggregate(
                max_version=Max("version")
            )["max_version"]
            or 0
        )

        version = QuestionVersion.objects.create(
            question=locked_question,
            version=latest_version + 1,

            # Historical snapshots
            question_type=locked_question.question_type,
            default_marks=locked_question.default_marks,

            text=text.strip(),
            instructions=instructions.strip() if instructions else "",
            explanation=explanation.strip() if explanation else "",
            created_by=created_by,
        )

        QuestionBankService._create_answer_structure(
            version=version,
            question_type=version.question_type,
            options=options,
            answer_definition=answer_definition,
        )

        return version

    @staticmethod
    def _create_answer_structure(
        *,
        version,
        question_type,
        options,
        answer_definition,
    ):
        """
        Creates the correct answer-definition structure
        for the question type.
        """

        objective_types = {
            QuestionType.SINGLE_CHOICE,
            QuestionType.MULTIPLE_CHOICE,
            QuestionType.TRUE_FALSE,
        }

        if question_type in objective_types:
            QuestionBankService._create_options(
                version=version,
                question_type=question_type,
                options=options,
            )
            return

        if options:
            raise ValidationError(
                "Options are not supported for this question type."
            )

        if question_type == QuestionType.SHORT_ANSWER:
            QuestionBankService._create_short_answer(
                version=version,
                definition=answer_definition,
            )

        elif question_type == QuestionType.NUMERIC:
            QuestionBankService._create_numeric_answer(
                version=version,
                definition=answer_definition,
            )

        elif question_type == QuestionType.FILL_BLANK:
            QuestionBankService._create_fill_blank(
                version=version,
                definition=answer_definition,
            )

        elif question_type == QuestionType.ESSAY:
            QuestionBankService._create_essay_definition(
                version=version,
                definition=answer_definition,
            )

        elif question_type == QuestionType.MATCHING:
            QuestionBankService._create_matching_definition(
                version=version,
                definition=answer_definition,
            )

        else:
            raise ValidationError(
                f"Unsupported question type: {question_type}"
            )
        
    @staticmethod
    def _create_options(
        *,
        version,
        question_type,
        options,
    ):
        if not options:
            raise ValidationError(
                "This question type requires answer options."
            )

        if (
            question_type == QuestionType.TRUE_FALSE
            and len(options) != 2
        ):
            raise ValidationError(
                "True/False questions require exactly two options."
            )

        option_objects = []

        for index, option in enumerate(options, start=1):
            text = str(
                option.get("text", "")
            ).strip()

            if not text:
                raise ValidationError(
                    f"Option {index} cannot be empty."
                )

            option_objects.append(
                QuestionOption(
                    question_version=version,
                    text=text,
                    is_correct=bool(
                        option.get(
                            "is_correct",
                            False,
                        )
                    ),
                    feedback=str(
                        option.get(
                            "feedback",
                            "",
                        )
                    ).strip(),
                    order=index,
                )
            )

        QuestionOption.objects.bulk_create(
            option_objects
        )

    @staticmethod
    def _create_short_answer(
        *,
        version,
        definition,
    ):
        accepted_answers = definition.get(
            "accepted_answers",
            [],
        )

        short_definition = (
            ShortAnswerDefinition.objects.create(
                question_version=version,
                case_sensitive=definition.get(
                    "case_sensitive",
                    False,
                ),
                trim_whitespace=definition.get(
                    "trim_whitespace",
                    True,
                ),
            )
        )

        variants = []

        for raw_answer in accepted_answers:
            answer = str(raw_answer).strip()

            if not answer:
                continue

            variants.append(
                ShortAnswerVariant(
                    definition=short_definition,
                    answer=answer,
                )
            )

        if variants:
            ShortAnswerVariant.objects.bulk_create(
                variants
            )

    @staticmethod
    def _create_numeric_answer(
        *,
        version,
        definition,
    ):
        if "expected_value" not in definition:
            return

        numeric_definition = NumericAnswerDefinition(
            question_version=version,
            expected_value=definition[
                "expected_value"
            ],
            tolerance=definition.get(
                "tolerance",
                0,
            ),
        )

        numeric_definition.full_clean()
        numeric_definition.save()

    @staticmethod
    def _create_fill_blank(
        *,
        version,
        definition,
    ):
        fill_definition = (
            FillBlankDefinition.objects.create(
                question_version=version,
                case_sensitive=definition.get(
                    "case_sensitive",
                    False,
                ),
            )
        )

        blanks = definition.get(
            "blanks",
            [],
        )

        for index, blank_data in enumerate(
            blanks,
            start=1,
        ):
            position = blank_data.get(
                "position",
                index,
            )

            blank = FillBlankItem.objects.create(
                definition=fill_definition,
                position=position,
            )

            accepted_answers = blank_data.get(
                "accepted_answers",
                [],
            )

            answers = []

            for raw_answer in accepted_answers:
                answer = str(raw_answer).strip()

                if not answer:
                    continue

                answers.append(
                    FillBlankAcceptedAnswer(
                        blank=blank,
                        answer=answer,
                    )
                )

            if answers:
                FillBlankAcceptedAnswer.objects.bulk_create(
                    answers
                )

    @staticmethod
    def _create_essay_definition(
        *,
        version,
        definition,
    ):
        essay_definition = EssayDefinition(
            question_version=version,
            marking_guide=definition.get(
                "marking_guide",
                "",
            ),
            model_answer=definition.get(
                "model_answer",
                "",
            ),
            minimum_words=definition.get(
                "minimum_words",
            ),
            maximum_words=definition.get(
                "maximum_words",
            ),
        )

        essay_definition.full_clean()
        essay_definition.save()


    @staticmethod
    def _create_matching_definition(
        *,
        version,
        definition,
    ):
        matching_definition = (
            MatchingDefinition.objects.create(
                question_version=version,
                shuffle_right_items=definition.get(
                    "shuffle_right_items",
                    True,
                ),
            )
        )

        pairs = definition.get(
            "pairs",
            [],
        )

        pair_objects = []

        for index, pair in enumerate(
            pairs,
            start=1,
        ):
            left_text = str(
                pair.get(
                    "left_text",
                    "",
                )
            ).strip()

            right_text = str(
                pair.get(
                    "right_text",
                    "",
                )
            ).strip()

            if not left_text or not right_text:
                continue

            pair_objects.append(
                MatchingPair(
                    definition=matching_definition,
                    left_text=left_text,
                    right_text=right_text,
                    order=index,
                )
            )

        if pair_objects:
            MatchingPair.objects.bulk_create(
                pair_objects
            )

    
    @staticmethod
    def validate_question(question):
        """
        Performs complete validation before a question
        can enter review or become approved.
        """

        version = question.current_version

        if not version:
            raise ValidationError(
                "Question has no active version."
            )

        if not version.text or not version.text.strip():
            raise ValidationError(
                "Question text cannot be empty."
            )

        if not question.grade_levels.exists():
            raise ValidationError(
                "Question must apply to at least one grade level."
            )

        # Topic must belong to the same subject.
        if (
            question.topic
            and question.topic.subject_id
            != question.subject_id
        ):
            raise ValidationError(
                "Topic does not belong to the question subject."
            )

        # Topic grade must be represented by the question.
        if question.topic:
            if not question.grade_levels.filter(
                pk=question.topic.grade_level_id
            ).exists():
                raise ValidationError(
                    "The topic's grade level must be included "
                    "in the question's applicable grade levels."
                )

        # Subtopic must belong to selected topic.
        if question.subtopic:
            if not question.topic:
                raise ValidationError(
                    "Subtopic requires a topic."
                )

            if (
                question.subtopic.topic_id
                != question.topic_id
            ):
                raise ValidationError(
                    "Subtopic does not belong to the selected topic."
                )

        # Validate bank scope.
        if question.bank:
            if (
                question.bank.subject_id
                != question.subject_id
            ):
                raise ValidationError(
                    "Question bank subject must match "
                    "the question subject."
                )

            bank_grade_ids = set(
                question.bank.grade_levels.values_list(
                    "id",
                    flat=True,
                )
            )

            question_grade_ids = set(
                question.grade_levels.values_list(
                    "id",
                    flat=True,
                )
            )

            if (
                bank_grade_ids
                and not question_grade_ids.issubset(
                    bank_grade_ids
                )
            ):
                raise ValidationError(
                    "Question grade levels must fall "
                    "within the question bank's "
                    "grade-level scope."
                )

        QuestionBankService._validate_answer_structure(
            question
        )

        return True

    @staticmethod
    def _validate_answer_structure(question):
        version = question.current_version

        question_type = version.question_type

        if question_type in {
            QuestionType.SINGLE_CHOICE,
            QuestionType.MULTIPLE_CHOICE,
            QuestionType.TRUE_FALSE,
        }:
            options = list(
                version.options.all()
            )

            correct_options = [
                option
                for option in options
                if option.is_correct
            ]

            if question_type == QuestionType.SINGLE_CHOICE:
                if len(options) < 2:
                    raise ValidationError(
                        "Single-choice questions require "
                        "at least two options."
                    )

                if len(correct_options) != 1:
                    raise ValidationError(
                        "Single-choice questions must have "
                        "exactly one correct answer."
                    )

            elif question_type == QuestionType.MULTIPLE_CHOICE:
                if len(options) < 2:
                    raise ValidationError(
                        "Multiple-choice questions require "
                        "at least two options."
                    )

                if len(correct_options) < 1:
                    raise ValidationError(
                        "Multiple-choice questions require "
                        "at least one correct answer."
                    )

            elif question_type == QuestionType.TRUE_FALSE:
                if len(options) != 2:
                    raise ValidationError(
                        "True/False questions must have "
                        "exactly two options."
                    )

                if len(correct_options) != 1:
                    raise ValidationError(
                        "True/False questions must have "
                        "exactly one correct answer."
                    )

            return

        if question_type == QuestionType.SHORT_ANSWER:
            definition = getattr(
                version,
                "short_answer_definition",
                None,
            )

            if (
                not definition
                or not definition.accepted_answers.exists()
            ):
                raise ValidationError(
                    "Short-answer questions require "
                    "at least one accepted answer."
                )

            return

        if question_type == QuestionType.NUMERIC:
            definition = getattr(
                version,
                "numeric_answer_definition",
                None,
            )

            if not definition:
                raise ValidationError(
                    "Numeric questions require "
                    "a numeric answer definition."
                )

            definition.full_clean()
            return

        if question_type == QuestionType.FILL_BLANK:
            definition = getattr(
                version,
                "fill_blank_definition",
                None,
            )

            if (
                not definition
                or not definition.blanks.exists()
            ):
                raise ValidationError(
                    "Fill-in-the-blank questions require "
                    "at least one blank."
                )

            for blank in definition.blanks.all():
                if not blank.accepted_answers.exists():
                    raise ValidationError(
                        f"Blank {blank.position} "
                        "has no accepted answer."
                    )

            return

        if question_type == QuestionType.ESSAY:
            definition = getattr(
                version,
                "essay_definition",
                None,
            )

            if not definition:
                raise ValidationError(
                    "Essay questions require "
                    "an essay definition."
                )

            definition.full_clean()
            return

        if question_type == QuestionType.MATCHING:
            definition = getattr(
                version,
                "matching_definition",
                None,
            )

            if (
                not definition
                or definition.pairs.count() < 2
            ):
                raise ValidationError(
                    "Matching questions require "
                    "at least two matching pairs."
                )

            return

        raise ValidationError(
            f"Unsupported question type: {question_type}"
        )
    @staticmethod
    @transaction.atomic
    def submit_for_review(
        question,
        user,
    ):
        if question.status != QuestionStatus.DRAFT:
            raise ValidationError(
                "Only draft questions can be submitted for review."
            )

        QuestionBankService.validate_question(
            question
        )

        question.status = QuestionStatus.IN_REVIEW

        question.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        return question

        
    @staticmethod
    @transaction.atomic
    def approve_question(
        question,
        user,
        comments="",
    ):
        if not user:
            raise ValidationError("Actor is required to approve a question.")

        if question.status != QuestionStatus.IN_REVIEW:
            raise ValidationError(
                "Only questions under review can be approved."
            )

        from academic.models import AcademicWorkflow
        from academic.services.academic_authority_service import AcademicAuthorityService

        AcademicAuthorityService.require_approval_authority(
            actor=user,
            workflow=AcademicWorkflow.QUESTION_BANK,
            subject=question.subject,
            creator=question.created_by,
        )

        QuestionBankService.validate_question(
            question
        )

        version = question.current_version
        reviewer = AcademicAuthorityService.get_teacher(user)

        QuestionReview.objects.create(
            question_version=version,
            reviewed_by=reviewer,
            decision=QuestionReview.Decision.APPROVED,
            comments=comments,
        )

        question.status = QuestionStatus.APPROVED

        question.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        return question

    @staticmethod
    @transaction.atomic
    def reject_question(
        question,
        user,
        comments="",
    ):
        if not user:
            raise ValidationError("Actor is required to reject a question.")

        if question.status != QuestionStatus.IN_REVIEW:
            raise ValidationError(
                "Only questions under review can be rejected."
            )

        from academic.models import AcademicWorkflow
        from academic.services.academic_authority_service import AcademicAuthorityService

        AcademicAuthorityService.require_approval_authority(
            actor=user,
            workflow=AcademicWorkflow.QUESTION_BANK,
            subject=question.subject,
            creator=question.created_by,
        )

        version = question.current_version

        if not version:
            raise ValidationError(
                "Question has no active version."
            )

        reviewer = AcademicAuthorityService.get_teacher(user)

        QuestionReview.objects.create(
            question_version=version,
            reviewed_by=reviewer,
            decision=QuestionReview.Decision.REJECTED,
            comments=comments,
        )

        question.status = QuestionStatus.DRAFT

        question.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        return question


    @staticmethod
    @transaction.atomic
    def archive_question(question, user):
        if question.status == QuestionStatus.ARCHIVED:
            raise ValidationError(
                "Question is already archived."
            )

        question.status = QuestionStatus.ARCHIVED
        question.is_active = False

        question.save(
            update_fields=[
                "status",
                "is_active",
                "updated_at",
            ]
        )

        return question

    @staticmethod
    @transaction.atomic
    def align_learning_objective(
        *,
        question_version=None,
        version=None,
        learning_objective,
        is_primary=False,
    ):
        """
        Aligns a QuestionVersion with a LearningObjective, validating curriculum scope.
        Safely unsets any existing primary alignment if is_primary is True.
        """
        target_version = question_version or version
        if not target_version:
            raise ValidationError("A question version is required for objective alignment.")

        QuestionCurriculumService.validate_objective(
            question_version=target_version,
            learning_objective=learning_objective,
        )

        if is_primary:
            target_version.objective_alignments.filter(
                is_primary=True
            ).update(is_primary=False)

        alignment, _ = (
            QuestionLearningObjective.objects
            .update_or_create(
                question_version=target_version,
                learning_objective=learning_objective,
                defaults={
                    "is_primary": is_primary,
                },
            )
        )

        return alignment

    @staticmethod
    @transaction.atomic
    def remove_learning_objective(
        *,
        question_version=None,
        version=None,
        learning_objective,
    ):
        """
        Removes a learning objective alignment from a QuestionVersion.
        """
        target_version = question_version or version
        if not target_version:
            raise ValidationError("A question version is required.")

        return QuestionLearningObjective.objects.filter(
            question_version=target_version,
            learning_objective=learning_objective,
        ).delete()