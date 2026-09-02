import threading
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection, transaction
from django.utils import timezone

from school.testcases import TenantTransactionTestCase
from academic.models import (
    ClassRoom,
    Department,
    GradeLevel,
    SectionType,
    Student,
    StudentClassEnrollment,
    Subject,
    Teacher,
)
from administration.models import AcademicYear, Term
from examination.models import (
    AssessmentComponent,
    AssessmentSession,
    AssessmentType,
    GradingScheme,
)
from cbt.models import CBTExam, CBTExamStatus, ExamAttempt, ExamQuestion, QuestionType
from cbt.services import (
    ExamAttemptService,
    PublishedExamRevisionService,
    AttemptGrantService,
    QuestionBankService,
    StudentAnswerService,
)


User = get_user_model()


class PhaseTwoConcurrencyTests(TenantTransactionTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.status = "active"
        return super().setup_tenant(tenant)

    def setUp(self):
        connection.set_tenant(self.tenant)
        self.user = User.objects.create_user(
            email="phase2-student@test.local",
            password="password123",
            is_student=True,
        )
        teacher_user = User.objects.create_user(
            email="phase2-teacher@test.local",
            password="password123",
            is_teacher=True,
        )
        self.teacher = Teacher.objects.create(user=teacher_user)
        department = Department.objects.create(name="Phase 2 Department")
        self.subject = Subject.objects.create(
            name="Phase 2 Subject",
            subject_code="P2",
            department=department,
        )
        grade = GradeLevel.objects.create(
            system_code="P2_GRADE",
            default_name="Phase 2 Grade",
            section=SectionType.JUNIOR_SECONDARY,
            sequence_order=91,
        )
        self.classroom = ClassRoom.objects.create(name="P2", grade_level=grade)
        year = AcademicYear.objects.create(
            name="Phase 2 Year",
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timezone.timedelta(days=365),
            active_year=True,
        )
        term = Term.objects.create(
            name="Phase 2 Term",
            academic_year=year,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timezone.timedelta(days=90),
        )
        self.student = Student.objects.create(
            user=self.user,
            student_id="P2-STUDENT",
            admission_number="P2-ADM",
            first_name="Phase",
            last_name="Two",
            classroom=self.classroom,
        )
        StudentClassEnrollment.objects.create(
            student=self.student,
            classroom=self.classroom,
            academic_year=year,
            is_active=True,
        )
        session = AssessmentSession.objects.create(
            assessment_type=AssessmentType.EXAMINATION,
            name="Phase 2 Session",
            academic_year=year,
            term=term,
            start_date=timezone.now().date(),
            ends_date=timezone.now().date() + timezone.timedelta(days=7),
            out_of=100,
        )
        scheme = GradingScheme.objects.create(
            name="Phase 2 Scheme",
            academic_year=year,
            grade_level=grade,
        )
        component = AssessmentComponent.objects.create(
            scheme=scheme,
            name="Phase 2 CBT",
            max_score=100,
            weight=100,
            order=1,
        )
        self.exam = CBTExam.objects.create(
            session=session,
            component=component,
            subject=self.subject,
            classroom=self.classroom,
            title="Phase 2 Concurrency",
            duration_minutes=30,
            status=CBTExamStatus.PUBLISHED,
            created_by=self.teacher,
        )
        question = QuestionBankService.create_question(
            subject=self.subject,
            grade_levels=[grade],
            question_type=QuestionType.SINGLE_CHOICE,
            text="Concurrent answer",
            created_by=self.teacher,
            options=[
                {"text": "A", "is_correct": True},
                {"text": "B", "is_correct": False},
            ],
        )
        ExamQuestion.objects.create(
            cbt_exam=self.exam,
            question_version=question.current_version,
            order=1,
            marks=10,
        )

    def run_threads(self, functions):
        barrier = threading.Barrier(len(functions))
        results = []
        errors = []

        def runner(function):
            close_old_connections()
            try:
                connection.set_tenant(self.tenant)
                barrier.wait()
                results.append(function())
            except Exception as exc:  # assertions inspect expected domain failures
                errors.append(exc)
            finally:
                close_old_connections()

        threads = [threading.Thread(target=runner, args=(fn,)) for fn in functions]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        return results, errors

    def test_simultaneous_start_returns_one_attempt(self):
        def start():
            return ExamAttemptService.start_attempt(
                exam=CBTExam.objects.get(pk=self.exam.pk),
                student=Student.objects.get(pk=self.student.pk),
            ).pk

        results, errors = self.run_threads([start, start])
        self.assertEqual(errors, [])
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(ExamAttempt.objects.count(), 1)
        self.assertEqual(self.exam.attempt_grants.count(), 1)
        attempt = ExamAttempt.objects.get()
        self.assertIsNotNone(attempt.attempt_grant_id)
        self.assertEqual(
            attempt.attempt_grant.published_revision_id,
            attempt.published_revision_id,
        )

    def test_simultaneous_grant_issuance_returns_one_grant(self):
        PublishedExamRevisionService.ensure_current_for_exam(self.exam)

        def issue():
            return AttemptGrantService.issue(
                student=Student.objects.get(pk=self.student.pk),
                exam=CBTExam.objects.get(pk=self.exam.pk),
            ).pk

        results, errors = self.run_threads([issue, issue])
        self.assertEqual(errors, [])
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(self.exam.attempt_grants.count(), 1)

    def test_revoke_versus_start_never_creates_duplicate_authorization(self):
        revision = PublishedExamRevisionService.ensure_current_for_exam(self.exam)
        grant = AttemptGrantService.issue(
            student=self.student, exam=self.exam, revision=revision
        )

        def start():
            return ExamAttemptService.start_attempt(
                exam=CBTExam.objects.get(pk=self.exam.pk),
                student=Student.objects.get(pk=self.student.pk),
            ).pk

        def revoke():
            return AttemptGrantService.revoke(
                grant=grant.__class__.objects.get(pk=grant.pk),
                actor=Teacher.objects.get(pk=self.teacher.pk),
                reason="Concurrent revocation",
            ).pk

        results, errors = self.run_threads([start, revoke])
        self.assertTrue(all(isinstance(error, ValidationError) for error in errors))
        grant.refresh_from_db()
        self.assertEqual(grant.status, "REVOKED")
        self.assertLessEqual(ExamAttempt.objects.count(), 1)
        self.assertEqual(self.exam.attempt_grants.count(), 1)

    def test_close_boundary_start_is_decided_under_exam_lock(self):
        PublishedExamRevisionService.ensure_current_for_exam(self.exam)
        CBTExam.objects.filter(pk=self.exam.pk).update(
            available_from=timezone.now() - timezone.timedelta(minutes=1),
            available_until=timezone.now() + timezone.timedelta(minutes=5),
        )

        def start():
            return ExamAttemptService.start_attempt(
                exam=CBTExam.objects.get(pk=self.exam.pk),
                student=Student.objects.get(pk=self.student.pk),
            ).pk

        def close_window():
            with transaction.atomic():
                exam = CBTExam.objects.select_for_update().get(pk=self.exam.pk)
                exam.available_until = timezone.now()
                exam.save(update_fields=["available_until", "updated_at"])
                return exam.pk

        results, errors = self.run_threads([start, close_window])
        self.assertTrue(all(isinstance(error, ValidationError) for error in errors))
        self.assertLessEqual(ExamAttempt.objects.count(), 1)
        self.assertLessEqual(self.exam.attempt_grants.count(), 1)

    def test_concurrent_revision_resolution_creates_one_revision(self):
        def resolve():
            exam = CBTExam.objects.get(pk=self.exam.pk)
            return PublishedExamRevisionService.ensure_current_for_exam(exam).pk

        results, errors = self.run_threads([resolve, resolve])
        self.assertEqual(errors, [])
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(self.exam.published_revisions.count(), 1)

    def test_simultaneous_saves_preserve_revision_and_highest_sequence(self):
        attempt = ExamAttemptService.start_attempt(exam=self.exam, student=self.student)
        attempt_question = attempt.attempt_questions.get()
        options = list(
            attempt_question.published_question.choices.order_by("order")
        )
        client_id = uuid.uuid4()

        def save(sequence, option):
            return lambda: StudentAnswerService.apply_answer_event(
                attempt_question=attempt_question.__class__.objects.get(pk=attempt_question.pk),
                event_id=uuid.uuid4(),
                client_id=client_id,
                client_sequence=sequence,
                base_revision=0,
                operation="SET",
                payload={"option_ids": [str(option.public_id)]},
            ).outcome

        results, errors = self.run_threads([save(1, options[0]), save(2, options[1])])
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        attempt.refresh_from_db()
        self.assertIn(attempt.revision, {1, 2})
        selected = attempt_question.__class__.objects.get(
            pk=attempt_question.pk
        ).answer.selected_options.get().published_choice_id
        self.assertEqual(selected, options[1].pk)

    def test_concurrent_duplicate_event_advances_revision_once(self):
        attempt = ExamAttemptService.start_attempt(exam=self.exam, student=self.student)
        attempt_question = attempt.attempt_questions.get()
        option = attempt_question.published_question.choices.first()
        event_id = uuid.uuid4()
        client_id = uuid.uuid4()

        def save():
            return StudentAnswerService.apply_answer_event(
                attempt_question=attempt_question.__class__.objects.get(pk=attempt_question.pk),
                event_id=event_id,
                client_id=client_id,
                client_sequence=1,
                base_revision=0,
                operation="SET",
                payload={"option_ids": [str(option.public_id)]},
            ).outcome

        results, errors = self.run_threads([save, save])
        self.assertEqual(errors, [])
        self.assertCountEqual(results, ["ACCEPTED", "DUPLICATE"])
        attempt.refresh_from_db()
        self.assertEqual(attempt.revision, 1)

    def test_save_versus_submit_has_one_serialized_winner(self):
        attempt = ExamAttemptService.start_attempt(exam=self.exam, student=self.student)
        attempt_question = attempt.attempt_questions.get()
        option = attempt_question.published_question.choices.first()

        def save():
            return StudentAnswerService.apply_answer_event(
                attempt_question=attempt_question.__class__.objects.get(pk=attempt_question.pk),
                event_id=uuid.uuid4(),
                client_id=uuid.uuid4(),
                client_sequence=1,
                operation="SET",
                payload={"option_ids": [str(option.public_id)]},
            ).outcome

        def submit():
            return ExamAttemptService.submit(
                attempt=ExamAttempt.objects.get(pk=attempt.pk),
                submission_id=uuid.uuid4(),
            ).outcome

        results, errors = self.run_threads([save, submit])
        self.assertTrue(all(isinstance(error, ValidationError) for error in errors))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "SUBMITTED")
        accepted_events = attempt.answer_events.filter(outcome="ACCEPTED").count()
        self.assertIn(accepted_events, {0, 1})
        if accepted_events:
            self.assertEqual(attempt.submitted_revision, 1)
        else:
            self.assertEqual(attempt.submitted_revision, 0)
