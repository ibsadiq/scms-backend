from django.core.exceptions import ValidationError
from rest_framework import status
from unittest.mock import patch

from examination.models import AssessmentComponent

from cbt.models import (
    CBTExam,
    CBTExamStatus,
    ExamQuestion,
    PublishedExamRevision,
    QuestionOption,
    QuestionType,
)
from cbt.services import PublishedExamRevisionService, QuestionBankService
from cbt.tests.base import CBTAPITestBase


class PublishedExamRevisionTests(CBTAPITestBase):
    def setUp(self):
        super().setUp()
        self.exam = CBTExam.objects.create(
            session=self.session,
            component=self.component,
            subject=self.subj_math,
            classroom=self.classroom_jss1,
            title="Immutable delivery exam",
            duration_minutes=37,
            instructions="Frozen instructions",
            status=CBTExamStatus.PUBLISHED,
            created_by=self.teacher_1,
        )
        self.question = QuestionBankService.create_question(
            subject=self.subj_math,
            grade_levels=[self.grade_jss1],
            question_type=QuestionType.SINGLE_CHOICE,
            text="Frozen question text",
            created_by=self.teacher_1,
            options=[
                {"text": "Correct", "is_correct": True},
                {"text": "Distractor", "is_correct": False},
            ],
        )
        ExamQuestion.objects.create(
            cbt_exam=self.exam,
            question_version=self.question.current_version,
            order=1,
            marks=10,
        )

    def test_legacy_publish_backfill_is_idempotent_and_finalized(self):
        first = PublishedExamRevisionService.ensure_current_for_exam(self.exam)
        second = PublishedExamRevisionService.ensure_current_for_exam(self.exam)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.status, PublishedExamRevision.Status.FINALIZED)
        self.assertEqual(first.revision_number, 1)
        self.assertEqual(len(first.content_hash), 64)
        self.assertEqual(first.questions.count(), 1)

    def test_finalized_revision_and_children_are_immutable(self):
        revision = PublishedExamRevisionService.ensure_current_for_exam(self.exam)
        revision.title = "Changed"
        with self.assertRaises(ValidationError):
            revision.save()
        frozen_question = revision.questions.get()
        frozen_question.question_text = "Changed"
        with self.assertRaises(ValidationError):
            frozen_question.save()
        with self.assertRaises(ValidationError):
            frozen_question.delete()

    def test_attempt_delivery_and_grading_use_only_frozen_content(self):
        revision = PublishedExamRevisionService.ensure_current_for_exam(self.exam)
        frozen_question = revision.questions.get()
        correct = frozen_question.choices.get(text="Correct")

        # Simulate legacy/admin bulk mutation after publication; published data
        # must remain the sole delivery and grading authority.
        QuestionOption.objects.filter(
            question_version=self.question.current_version
        ).update(is_correct=False, text="MUTATED SOURCE")

        self.client.force_authenticate(user=self.student_user)
        started = self.client.post(f"/api/cbt/student/exams/{self.exam.pk}/start/")
        self.assertEqual(started.status_code, status.HTTP_201_CREATED, started.data)
        self.assertEqual(started.data["published_revision_id"], str(revision.public_id))
        delivered = started.data["questions"][0]
        self.assertEqual(delivered["question_text"], "Frozen question text")
        self.assertEqual(
            {option["text"] for option in delivered["options"]},
            {"Correct", "Distractor"},
        )
        self.assertNotIn("grading_definition", delivered)
        self.assertNotIn("correct_choice_keys", str(delivered))

        saved = self.client.put(
            f"/api/cbt/attempt-questions/{delivered['id']}/answer/",
            {"option_ids": [str(correct.public_id)]},
            format="json",
        )
        self.assertEqual(saved.status_code, status.HTTP_200_OK, saved.data)
        submitted = self.client.post(
            f"/api/cbt/student/attempts/{started.data['id']}/submit/",
            {},
            format="json",
        )
        self.assertEqual(submitted.status_code, status.HTTP_200_OK, submitted.data)
        attempt = self.exam.attempts.get()
        self.assertEqual(attempt.published_revision_id, revision.pk)
        self.assertEqual(attempt.attempt_questions.get().grade.awarded_marks, 10)

    def test_student_payload_exposes_public_not_source_option_identity(self):
        revision = PublishedExamRevisionService.ensure_current_for_exam(self.exam)
        source_ids = {
            str(value) for value in self.question.current_version.options.values_list("pk", flat=True)
        }
        self.client.force_authenticate(user=self.student_user)
        response = self.client.post(f"/api/cbt/student/exams/{self.exam.pk}/start/")
        option_ids = {
            option["option_id"] for option in response.data["questions"][0]["options"]
        }
        self.assertTrue(option_ids.isdisjoint(source_ids))
        self.assertEqual(response.data["published_revision_hash"], revision.content_hash)

    def test_all_supported_question_types_are_frozen_with_private_grading(self):
        component = AssessmentComponent.objects.create(
            scheme=self.grading_scheme,
            name="Phase 3 all types",
            max_score=100,
            weight=0,
            order=99,
        )
        exam = CBTExam.objects.create(
            session=self.session,
            component=component,
            subject=self.subj_math,
            classroom=self.classroom_jss1,
            title="Phase 3 all types",
            duration_minutes=30,
            status=CBTExamStatus.PUBLISHED,
            created_by=self.teacher_1,
        )
        definitions = [
            (QuestionType.SINGLE_CHOICE, [{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}], None),
            (QuestionType.MULTIPLE_CHOICE, [{"text": "A", "is_correct": True}, {"text": "B", "is_correct": True}], None),
            (QuestionType.TRUE_FALSE, [{"text": "True", "is_correct": True}, {"text": "False", "is_correct": False}], None),
            (QuestionType.SHORT_ANSWER, None, {"accepted_answers": ["short"]}),
            (QuestionType.NUMERIC, None, {"expected_value": "12", "tolerance": "0.5"}),
            (QuestionType.FILL_BLANK, None, {"blanks": [{"accepted_answers": ["blank"]}]}),
            (QuestionType.MATCHING, None, {"pairs": [{"left_text": "L", "right_text": "R"}]}),
            (QuestionType.ESSAY, None, {"model_answer": "private", "marking_guide": "private guide"}),
        ]
        for order, (question_type, options, answer_definition) in enumerate(definitions, 1):
            question = QuestionBankService.create_question(
                subject=self.subj_math,
                grade_levels=[self.grade_jss1],
                question_type=question_type,
                text=f"Frozen {question_type}",
                created_by=self.teacher_1,
                options=options,
                answer_definition=answer_definition,
            )
            ExamQuestion.objects.create(
                cbt_exam=exam,
                question_version=question.current_version,
                order=order,
                marks=1,
            )

        revision = PublishedExamRevisionService.ensure_current_for_exam(exam)
        self.assertEqual(
            set(revision.questions.values_list("question_type", flat=True)),
            {item[0] for item in definitions},
        )
        self.assertTrue(all(
            hasattr(question, "grading_definition")
            for question in revision.questions.all()
        ))

    def test_failed_build_rolls_back_partial_revision(self):
        with patch.object(
            PublishedExamRevisionService,
            "_freeze_question",
            side_effect=ValidationError("forced publication failure"),
        ):
            with self.assertRaises(ValidationError):
                PublishedExamRevisionService.ensure_current_for_exam(self.exam)
        self.assertFalse(self.exam.published_revisions.exists())
