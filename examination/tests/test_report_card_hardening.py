from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from school.testcases import TenantTestCase as TestCase
from examination.models import (
    BehavioralDomain, BehavioralTrait, StudentBehavioralRating,
    TermResult, LifecycleState, GradingScheme, GradeRule,
    SubjectResult, AssessmentComponent, AssessmentSession, AssessmentType,
    AssessmentEntry
)
from examination.services.behavioral_rating_service import BehavioralRatingService
from examination.services.report_card_generator import ReportCardGenerator
from examination.services.term_result_service import TermResultService
from examination.views.behavioral import _is_authorized_for_classroom
from academic.models import ClassRoom, GradeLevel, Student, Teacher, Subject, StudentClassEnrollment
from administration.models import AcademicYear, Term
from tenants.models import TenantStatus

User = get_user_model()


class ReportCardHardeningTests(TestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        super().setup_tenant(tenant)
        tenant.auto_create_schema = True
        tenant.status = TenantStatus.ACTIVE
        return tenant

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            password="password", email="homeroom@example.com", first_name="Homeroom", last_name="Teacher", is_teacher=True
        )
        self.other_user = User.objects.create_user(
            password="password", email="subject_teacher@example.com", first_name="Subject", last_name="Teacher", is_teacher=True
        )
        self.admin_user = User.objects.create_superuser(
            password="password", email="admin@example.com", first_name="Admin", last_name="User"
        )

        self.teacher = Teacher.objects.create(user=self.user, empId="T001", short_name="HT")
        self.other_teacher = Teacher.objects.create(user=self.other_user, empId="T002", short_name="ST")

        self.academic_year = AcademicYear.objects.create(name="2023/2024", start_date="2023-09-01", end_date="2024-07-01", active_year=True)
        self.term = Term.objects.create(name="First Term", academic_year=self.academic_year, start_date="2023-09-01", end_date="2023-12-15")
        self.grade_level = GradeLevel.objects.create(system_code="JSS_1", default_name="JSS 1", section="JSS", sequence_order=1)
        self.classroom = ClassRoom.objects.create(name="JSS 1A", grade_level=self.grade_level, class_teacher=self.teacher)
        self.other_classroom = ClassRoom.objects.create(name="JSS 1B", grade_level=self.grade_level, class_teacher=self.other_teacher)

        self.student = Student.objects.create(first_name="Emeka", last_name="Okonkwo", classroom=self.classroom, admission_number="STD-001")
        self.enrollment = StudentClassEnrollment.objects.create(student=self.student, classroom=self.classroom, academic_year=self.academic_year)

        self.scheme = GradingScheme.objects.create(name="Standard Secondary", academic_year=self.academic_year, grade_level=self.grade_level)
        self.rule_a = GradeRule.objects.create(scheme=self.scheme, grade="A", min_score=70, max_score=100, remark="Distinction", grade_point=Decimal("5.00"))
        self.rule_b = GradeRule.objects.create(scheme=self.scheme, grade="B", min_score=60, max_score=69.99, remark="Very Good", grade_point=Decimal("4.00"))
        self.rule_c = GradeRule.objects.create(scheme=self.scheme, grade="C", min_score=50, max_score=59.99, remark="Credit", grade_point=Decimal("3.00"))
        self.rule_d = GradeRule.objects.create(scheme=self.scheme, grade="D", min_score=40, max_score=49.99, remark="Pass", grade_point=Decimal("2.00"))
        self.rule_f = GradeRule.objects.create(scheme=self.scheme, grade="F", min_score=0, max_score=39.99, remark="Fail", grade_point=Decimal("0.00"))

        self.comp_ca = AssessmentComponent.objects.create(scheme=self.scheme, name="Continuous Assessment", max_score=40, weight=40, order=1)
        self.comp_exam = AssessmentComponent.objects.create(scheme=self.scheme, name="Term Exam", max_score=60, weight=60, order=2)

        self.subject_math = Subject.objects.create(name="Mathematics", subject_code="MTH")
        self.subject_eng = Subject.objects.create(name="English Language", subject_code="ENG")

        # Snapshot of full grade scale
        self.scale_snapshot = [
            {"grade": "A", "min_score": "70.00", "max_score": "100.00", "remark": "Distinction", "grade_point": "5.00"},
            {"grade": "B", "min_score": "60.00", "max_score": "69.99", "remark": "Very Good", "grade_point": "4.00"},
            {"grade": "C", "min_score": "50.00", "max_score": "59.99", "remark": "Credit", "grade_point": "3.00"},
            {"grade": "D", "min_score": "40.00", "max_score": "49.99", "remark": "Pass", "grade_point": "2.00"},
            {"grade": "F", "min_score": "0.00", "max_score": "39.99", "remark": "Fail", "grade_point": "0.00"},
        ]

        self.term_result = TermResult.objects.create(
            student=self.student, term=self.term, academic_year=self.academic_year, classroom=self.classroom,
            lifecycle_state=LifecycleState.COMPUTED, grading_scheme=self.scheme, scheme_name=self.scheme.name,
            grading_scale_snapshot=self.scale_snapshot,
            total_marks=Decimal("170.00"), average_percentage=Decimal("85.00"), grade="A", gpa=Decimal("5.00"),
            position_in_class=1, total_students=25
        )

        self.sr1 = SubjectResult.objects.create(
            term_result=self.term_result, subject=self.subject_math, total_score=Decimal("90.00"), percentage=Decimal("90.00"),
            grade="A", grade_point=Decimal("5.00"), is_pass=True,
            grading_rule_snapshot={'min_score': '70.00', 'max_score': '100.00', 'remark': 'Distinction'}
        )
        self.sr2 = SubjectResult.objects.create(
            term_result=self.term_result, subject=self.subject_eng, total_score=Decimal("80.00"), percentage=Decimal("80.00"),
            grade="A", grade_point=Decimal("5.00"), is_pass=True,
            grading_rule_snapshot={'min_score': '70.00', 'max_score': '100.00', 'remark': 'Distinction'}
        )

        self.trait_affective = BehavioralTrait.objects.create(domain=BehavioralDomain.AFFECTIVE, name="Punctuality", order=1, is_active=True)
        self.trait_psychomotor = BehavioralTrait.objects.create(domain=BehavioralDomain.PSYCHOMOTOR, name="Handwriting", order=2, is_active=True)
        self.trait_inactive = BehavioralTrait.objects.create(domain=BehavioralDomain.AFFECTIVE, name="Old Trait", order=3, is_active=False)

    # ── 1. Historical Grade Scale & Snapshot Tests ─────────────────────────

    def test_complete_grading_scale_snapshot_stored_on_term_result(self):
        """Student has only 'A' grades, but TermResult snapshot contains full scale A-F."""
        generator = ReportCardGenerator(term_result=self.term_result)
        context = generator._prepare_context()

        legend = context.get('grade_legend', [])
        letters = [item['letter'] for item in legend]
        self.assertEqual(letters, ['A', 'B', 'C', 'D', 'F'])
        self.assertEqual(context.get('grade_scale_source'), 'snapshot')

    def test_modifying_live_grade_rule_does_not_affect_snapshot_report_legend(self):
        """Historical report cards must be immune to changes in live GradeRule."""
        self.rule_a.min_score = 80
        self.rule_a.save()

        generator = ReportCardGenerator(term_result=self.term_result)
        context = generator._prepare_context()

        legend = context.get('grade_legend', [])
        # Snapshot still has min_score 70 for A
        self.assertEqual(legend[0]['letter'], 'A')
        self.assertEqual(legend[0]['range'], '70-100')

    def test_grade_scale_deterministic_ordering(self):
        """Legend rules are ordered descending by min_score."""
        generator = ReportCardGenerator(term_result=self.term_result)
        context = generator._prepare_context()

        legend = context.get('grade_legend', [])
        self.assertEqual(legend[0]['letter'], 'A')
        self.assertEqual(legend[1]['letter'], 'B')
        self.assertEqual(legend[2]['letter'], 'C')
        self.assertEqual(legend[3]['letter'], 'D')
        self.assertEqual(legend[4]['letter'], 'F')

    def test_legacy_term_result_without_snapshot_uses_live_fallback(self):
        """Legacy results with empty grading_scale_snapshot safely fallback to live scheme rules."""
        legacy_student = Student.objects.create(
            first_name="Legacy", last_name="Student", classroom=self.classroom, admission_number="STD-LEGACY"
        )
        legacy_result = TermResult.objects.create(
            student=legacy_student, term=self.term, academic_year=self.academic_year, classroom=self.classroom,
            lifecycle_state=LifecycleState.COMPUTED, grading_scheme=self.scheme, scheme_name=self.scheme.name,
            grading_scale_snapshot=[],
            total_marks=Decimal("90.00"), average_percentage=Decimal("90.00"), grade="A", gpa=Decimal("5.00")
        )
        generator = ReportCardGenerator(term_result=legacy_result)
        context = generator._prepare_context()

        self.assertEqual(context.get('grade_scale_source'), 'legacy_live_fallback')
        legend = context.get('grade_legend', [])
        self.assertEqual(len(legend), 5)

    def test_grade_analysis_follows_scale_order(self):
        """Grade analysis counts are presented in grading scale rank order."""
        # Add a 'C' and an 'F' result
        sub_bio = Subject.objects.create(name="Biology", subject_code="BIO")
        sub_phy = Subject.objects.create(name="Physics", subject_code="PHY")
        SubjectResult.objects.create(
            term_result=self.term_result, subject=sub_bio, total_score=Decimal("55.00"), percentage=Decimal("55.00"),
            grade="C", grade_point=Decimal("3.00"), is_pass=True
        )
        SubjectResult.objects.create(
            term_result=self.term_result, subject=sub_phy, total_score=Decimal("30.00"), percentage=Decimal("30.00"),
            grade="F", grade_point=Decimal("0.00"), is_pass=False
        )

        generator = ReportCardGenerator(term_result=self.term_result)
        context = generator._prepare_context()

        grade_analysis = context.get('grade_analysis', [])
        grades_in_analysis = [ga['grade'] for ga in grade_analysis]
        # Mathematics=A, English=A, Biology=C, Physics=F -> Ordered A, C, F
        self.assertEqual(grades_in_analysis, ['A', 'C', 'F'])
        self.assertEqual(grade_analysis[0]['count'], 2)  # A
        self.assertEqual(grade_analysis[1]['count'], 1)  # C
        self.assertEqual(grade_analysis[2]['count'], 1)  # F

    def test_subject_level_grading_rule_snapshot_preserved(self):
        """SubjectResult.grading_rule_snapshot supplies subject-level remark evidence."""
        generator = ReportCardGenerator(term_result=self.term_result)
        context = generator._prepare_context()

        rows = context.get('subject_rows', [])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['remark'], 'Distinction')

    # ── 2. Report Card Performance & Assessment Components ─────────────────

    def test_dynamic_components_context_no_crash(self):
        """AssessmentComponent instances are passed into context['components'] without NameError."""
        generator = ReportCardGenerator(term_result=self.term_result)
        context = generator._prepare_context()

        components = context.get('components', [])
        self.assertEqual(len(components), 2)
        self.assertEqual(components[0].name, "Continuous Assessment")
        self.assertEqual(components[1].name, "Term Exam")

    def test_performance_summary_metrics(self):
        """Performance summary accurately derives totals, passed, failed, highest, lowest."""
        generator = ReportCardGenerator(term_result=self.term_result)
        context = generator._prepare_context()

        summary = context.get('performance_summary', {})
        self.assertIsNotNone(summary)
        self.assertEqual(summary['total_subjects'], 2)
        self.assertEqual(summary['passed_subjects'], 2)
        self.assertEqual(summary['failed_subjects'], 0)
        self.assertEqual(summary['highest_score'], 90.0)
        self.assertEqual(summary['lowest_score'], 80.0)
        self.assertEqual(summary['grade'], 'A')

    def test_highest_lowest_preserves_zero_score(self):
        """A legitimate score of 0.00 is preserved in lowest_score, not converted to None."""
        sub_zero = Subject.objects.create(name="Music", subject_code="MUS")
        SubjectResult.objects.create(
            term_result=self.term_result, subject=sub_zero, total_score=Decimal("0.00"), percentage=Decimal("0.00"),
            grade="F", grade_point=Decimal("0.00"), is_pass=False
        )

        generator = ReportCardGenerator(term_result=self.term_result)
        context = generator._prepare_context()

        summary = context.get('performance_summary', {})
        self.assertEqual(summary['lowest_score'], 0.0)
        self.assertEqual(summary['highest_score'], 90.0)

    def test_zero_subject_result_produces_no_performance_summary(self):
        """When student has zero subject results, performance_summary is None."""
        empty_student = Student.objects.create(first_name="Empty", last_name="Student", classroom=self.classroom, admission_number="STD-EMPTY")
        empty_term_result = TermResult.objects.create(
            student=empty_student, term=self.term, academic_year=self.academic_year, classroom=self.classroom,
            lifecycle_state=LifecycleState.COMPUTED, grading_scheme=self.scheme, scheme_name=self.scheme.name,
            total_marks=0, average_percentage=0, grade="N/A", gpa=0.0
        )
        generator = ReportCardGenerator(term_result=empty_term_result)
        context = generator._prepare_context()

        self.assertIsNone(context.get('performance_summary'))

    def test_attendance_missing_returns_none(self):
        """When no attendance records exist, attendance context is None and section is omitted."""
        generator = ReportCardGenerator(term_result=self.term_result)
        context = generator._prepare_context()

        self.assertIsNone(context.get('attendance'))

    # ── 3. Behavioral Ratings Report Context ───────────────────────────────

    def test_behavioral_legend_is_authoritative(self):
        """Authoritative rating legend (1-5) is passed to report context."""
        generator = ReportCardGenerator(term_result=self.term_result)
        context = generator._prepare_context()

        legend = context.get('behavioral_rating_legend', [])
        self.assertEqual(len(legend), 5)
        self.assertEqual(legend[0]['value'], 5)
        self.assertEqual(legend[0]['label'], 'Excellent')
        self.assertEqual(legend[4]['value'], 1)
        self.assertEqual(legend[4]['label'], 'Needs Improvement')

    def test_behavioral_conditional_domains_and_inactive_retention(self):
        """Historical ratings on inactive traits still render, and domains separate cleanly."""
        StudentBehavioralRating.objects.create(
            term_result=self.term_result, trait=self.trait_affective, rating=5, entered_by=self.user
        )
        StudentBehavioralRating.objects.create(
            term_result=self.term_result, trait=self.trait_psychomotor, rating=4, entered_by=self.user
        )
        StudentBehavioralRating.objects.create(
            term_result=self.term_result, trait=self.trait_inactive, rating=3, entered_by=self.user
        )

        generator = ReportCardGenerator(term_result=self.term_result)
        context = generator._prepare_context()

        affective = context.get('affective_traits', [])
        psychomotor = context.get('psychomotor_traits', [])

        affective_names = [a['name'] for a in affective]
        psychomotor_names = [p['name'] for p in psychomotor]

        self.assertIn("Punctuality", affective_names)
        self.assertIn("Old Trait", affective_names)  # Inactive trait is preserved
        self.assertIn("Handwriting", psychomotor_names)

    # ── 4. Unit & API Authorization Tests ──────────────────────────────────

    def test_homeroom_teacher_authorization_unit(self):
        """Homeroom teacher is authorized, other teacher is rejected, admin is authorized."""
        self.assertTrue(_is_authorized_for_classroom(self.user, self.classroom))
        self.assertFalse(_is_authorized_for_classroom(self.other_user, self.classroom))
        self.assertTrue(_is_authorized_for_classroom(self.admin_user, self.classroom))
        self.assertFalse(_is_authorized_for_classroom(None, self.classroom))
        self.assertFalse(_is_authorized_for_classroom(self.user, None))

    def test_locked_term_result_rejects_rating_mutation(self):
        """Mutations to ratings are rejected when result is in approved or locked state."""
        for state in [LifecycleState.HOMEROOM_APPROVED, LifecycleState.ADMIN_APPROVED, LifecycleState.LOCKED, LifecycleState.PUBLISHED]:
            self.term_result.lifecycle_state = state
            self.term_result.save()
            with self.assertRaises(ValidationError):
                BehavioralRatingService.record_rating(
                    term_result=self.term_result,
                    trait=self.trait_affective,
                    rating=5,
                    user=self.user
                )

    def test_api_class_ratings_authorization(self):
        """Homeroom teacher can retrieve class ratings; other teacher gets 403."""
        client = APIClient(HTTP_HOST=self.domain.domain)

        # Homeroom teacher
        client.force_authenticate(user=self.user)
        response = client.get(f"/api/examination/behavioral-ratings/class_ratings/?term_id={self.term.id}&classroom_id={self.classroom.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("rating_index", response.data)
        self.assertIn("students", response.data)

        # Unauthorized teacher
        client.force_authenticate(user=self.other_user)
        forbidden_response = client.get(f"/api/examination/behavioral-ratings/class_ratings/?term_id={self.term.id}&classroom_id={self.classroom.id}")
        self.assertEqual(forbidden_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_api_retrieve_ratings_authorization(self):
        """Homeroom teacher can retrieve single result ratings; other teacher gets 403."""
        client = APIClient(HTTP_HOST=self.domain.domain)

        # Homeroom teacher
        client.force_authenticate(user=self.user)
        response = client.get(f"/api/examination/behavioral-ratings/{self.term_result.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Unauthorized teacher
        client.force_authenticate(user=self.other_user)
        forbidden_response = client.get(f"/api/examination/behavioral-ratings/{self.term_result.id}/")
        self.assertEqual(forbidden_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_api_bulk_record_authorization_and_lifecycle(self):
        """Homeroom teacher can bulk record ratings; unauthorized teacher gets 403; locked result gets 400."""
        client = APIClient(HTTP_HOST=self.domain.domain)
        payload = {
            "term_result": self.term_result.id,
            "ratings": [
                {"trait_id": self.trait_affective.id, "rating": 5},
                {"trait_id": self.trait_psychomotor.id, "rating": 4}
            ]
        }

        # Unauthorized teacher
        client.force_authenticate(user=self.other_user)
        forbidden_response = client.post("/api/examination/behavioral-ratings/bulk-record/", payload, format="json")
        self.assertEqual(forbidden_response.status_code, status.HTTP_403_FORBIDDEN)

        # Homeroom teacher
        client.force_authenticate(user=self.user)
        ok_response = client.post("/api/examination/behavioral-ratings/bulk-record/", payload, format="json")
        self.assertEqual(ok_response.status_code, status.HTTP_200_OK)
        self.assertEqual(StudentBehavioralRating.objects.filter(term_result=self.term_result).count(), 2)

        # Locked result
        self.term_result.lifecycle_state = LifecycleState.HOMEROOM_APPROVED
        self.term_result.save()
        locked_response = client.post("/api/examination/behavioral-ratings/bulk-record/", payload, format="json")
        self.assertEqual(locked_response.status_code, status.HTTP_400_BAD_REQUEST)
