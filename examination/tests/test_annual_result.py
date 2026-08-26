from decimal import Decimal
from school.testcases import TenantTestCase as TestCase
from django.contrib.auth import get_user_model
from administration.models import AcademicYear, Term
from academic.models import Student, ClassRoom, GradeLevel, Subject, StudentClassEnrollment, Teacher
from examination.models import (
    GradingScheme, AssessmentComponent, GradeRule, PromotionRule,
    AssessmentEntry, TermResult, SubjectResult
)
from examination.services.term_result_service import TermResultService
from examination.services.annual_result_service import AnnualResultService

User = get_user_model()

class AnnualResultServiceTestCase(TestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        return super().setup_tenant(tenant)

    def setUp(self):
        self.user = User.objects.create_user(email="test@admin.com", password="password")
        self.teacher = Teacher.objects.create(user=self.user, empId="T001", short_name="TS")
        
        self.academic_year = AcademicYear.objects.create(name="2024/2025", start_date="2024-09-01", end_date="2025-07-01", active_year=True)
        self.term1 = Term.objects.create(academic_year=self.academic_year, name="Term 1", start_date="2024-09-01", end_date="2024-12-15")
        self.term2 = Term.objects.create(academic_year=self.academic_year, name="Term 2", start_date="2025-01-10", end_date="2025-04-15")
        
        self.grade_level = GradeLevel.objects.create(system_code="JSS_1", default_name="JSS 1", section="JSS", sequence_order=1)
        self.classroom = ClassRoom.objects.create(name="A", grade_level=self.grade_level)
        self.subject = Subject.objects.create(name="Mathematics", subject_code="MTH")
        
        self.student = Student.objects.create(first_name="John", last_name="Doe", admission_number="STD001", parent_contact="+2348012345678")
        self.enrollment = StudentClassEnrollment.objects.create(
            student=self.student, classroom=self.classroom, academic_year=self.academic_year
        )
        
        self.scheme = GradingScheme.objects.create(
            name="Standard JSS Scheme",
            academic_year=self.academic_year,
            grade_level=self.grade_level,
            is_active=True
        )
        
        self.ca_component = AssessmentComponent.objects.create(scheme=self.scheme, name="CA", max_score=30, weight=30, order=1)
        self.exam_component = AssessmentComponent.objects.create(scheme=self.scheme, name="Exam", max_score=70, weight=70, order=2)
        
        GradeRule.objects.create(scheme=self.scheme, min_score=70, max_score=100, grade="A", remark="Excellent", grade_point=4.0)
        GradeRule.objects.create(scheme=self.scheme, min_score=0, max_score=69.99, grade="F", remark="Fail", grade_point=0.0)
        
        PromotionRule.objects.create(
            scheme=self.scheme, minimum_average=50, minimum_subject_pass=50, max_failed_subjects=2
        )

    def test_annual_result_computation(self):
        # Create term-specific components to avoid unique constraint
        ca_t1 = AssessmentComponent.objects.create(scheme=self.scheme, name="CA T1", max_score=30, weight=30, order=3)
        exam_t1 = AssessmentComponent.objects.create(scheme=self.scheme, name="Exam T1", max_score=70, weight=70, order=4)
        
        ca_t2 = AssessmentComponent.objects.create(scheme=self.scheme, name="CA T2", max_score=30, weight=30, order=5)
        exam_t2 = AssessmentComponent.objects.create(scheme=self.scheme, name="Exam T2", max_score=70, weight=70, order=6)
        
        # Term 1: 50%
        e1 = AssessmentEntry.objects.create(student=self.enrollment, term=self.term1, subject=self.subject, component=ca_t1, score=15, entered_by=self.teacher)
        e2 = AssessmentEntry.objects.create(student=self.enrollment, term=self.term1, subject=self.subject, component=exam_t1, score=35, entered_by=self.teacher)
        term1_res = TermResultService.compute_student_term_result(self.student, self.term1, self.academic_year, self.user, skip_ranking=True, pre_fetched_entries=[e1, e2])
        term1_res.is_published = True
        term1_res.save()
        
        # Term 2: 90%
        e3 = AssessmentEntry.objects.create(student=self.enrollment, term=self.term2, subject=self.subject, component=ca_t2, score=30, entered_by=self.teacher)
        e4 = AssessmentEntry.objects.create(student=self.enrollment, term=self.term2, subject=self.subject, component=exam_t2, score=60, entered_by=self.teacher)
        term2_res = TermResultService.compute_student_term_result(self.student, self.term2, self.academic_year, self.user, skip_ranking=True, pre_fetched_entries=[e3, e4])
        term2_res.is_published = True
        term2_res.save()
        
        # Compute Annual Result
        annual_res = AnnualResultService.compute_annual_result(self.student, self.academic_year, self.user)
        
        self.assertIsNotNone(annual_res)
        
        # Average of 50 and 90 is 70
        annual_sub = annual_res.subjects.get(subject=self.subject)
        self.assertEqual(annual_sub.annual_average, Decimal("70.00"))
        self.assertEqual(annual_sub.grade, "A")
        
        self.assertEqual(annual_res.average_percentage, Decimal("70.00"))
        self.assertEqual(annual_res.grade, "A")
        self.assertEqual(annual_res.promotion_decision.status, "PROMOTED")
