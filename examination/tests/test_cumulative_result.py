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
from examination.services.cumulative_result_service import CumulativeResultService

User = get_user_model()

class CumulativeResultServiceTestCase(TestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        return super().setup_tenant(tenant)

    def setUp(self):
        self.user = User.objects.create_user(email="test@admin.com", password="password")
        self.teacher = Teacher.objects.create(user=self.user, empId="T001", short_name="TS")
        
        self.academic_year_1 = AcademicYear.objects.create(name="2023/2024", start_date="2023-09-01", end_date="2024-07-01", active_year=False)
        self.academic_year_2 = AcademicYear.objects.create(name="2024/2025", start_date="2024-09-01", end_date="2025-07-01", active_year=True)
        
        self.term_y1_1 = Term.objects.create(academic_year=self.academic_year_1, name="Term 1", start_date="2023-09-01", end_date="2023-12-15")
        self.term_y2_1 = Term.objects.create(academic_year=self.academic_year_2, name="Term 1", start_date="2024-09-01", end_date="2024-12-15")
        
        self.grade_level = GradeLevel.objects.create(system_code="JSS_1", default_name="JSS 1", section="JSS", sequence_order=1)
        self.grade_level_2 = GradeLevel.objects.create(system_code="JSS_2", default_name="JSS 2", section="JSS", sequence_order=2)
        self.classroom = ClassRoom.objects.create(name="A", grade_level=self.grade_level)
        self.classroom_2 = ClassRoom.objects.create(name="A", grade_level=self.grade_level_2)
        self.subject = Subject.objects.create(name="Mathematics", subject_code="MTH")
        
        self.student = Student.objects.create(first_name="John", last_name="Doe", admission_number="STD001", parent_contact="+2348012345678")
        
        self.enrollment_y1 = StudentClassEnrollment.objects.create(
            student=self.student, classroom=self.classroom, academic_year=self.academic_year_1
        )
        self.enrollment_y2 = StudentClassEnrollment.objects.create(
            student=self.student, classroom=self.classroom_2, academic_year=self.academic_year_2
        )
        
        self.scheme = GradingScheme.objects.create(
            name="Standard JSS Scheme",
            academic_year=self.academic_year_1,
            grade_level=self.grade_level,
            is_active=True
        )
        
        self.ca_component = AssessmentComponent.objects.create(scheme=self.scheme, name="CA", max_score=30, weight=30, order=1)
        self.exam_component = AssessmentComponent.objects.create(scheme=self.scheme, name="Exam", max_score=70, weight=70, order=2)
        
        GradeRule.objects.create(scheme=self.scheme, min_score=70, max_score=100, grade="A", remark="Excellent", grade_point=4.0)
        GradeRule.objects.create(scheme=self.scheme, min_score=60, max_score=69.99, grade="B", remark="Good", grade_point=3.0)
        GradeRule.objects.create(scheme=self.scheme, min_score=0, max_score=59.99, grade="F", remark="Fail", grade_point=0.0)

        PromotionRule.objects.create(
            scheme=self.scheme, minimum_average=50, minimum_subject_pass=50
        )

        self.scheme2 = GradingScheme.objects.create(
            name="Standard JSS Scheme 2",
            academic_year=self.academic_year_2,
            grade_level=self.grade_level_2,
            is_active=True
        )
        
        self.ca_component2 = AssessmentComponent.objects.create(scheme=self.scheme2, name="CA", max_score=30, weight=30, order=1)
        self.exam_component2 = AssessmentComponent.objects.create(scheme=self.scheme2, name="Exam", max_score=70, weight=70, order=2)
        
        GradeRule.objects.create(scheme=self.scheme2, min_score=70, max_score=100, grade="A", remark="Excellent", grade_point=4.0)
        GradeRule.objects.create(scheme=self.scheme2, min_score=60, max_score=69.99, grade="B", remark="Good", grade_point=3.0)
        GradeRule.objects.create(scheme=self.scheme2, min_score=0, max_score=59.99, grade="F", remark="Fail", grade_point=0.0)

        PromotionRule.objects.create(
            scheme=self.scheme2, minimum_average=50, minimum_subject_pass=50
        )

    def test_cumulative_result_computation(self):
        # Year 1 Term 1: 80% (A, 4.0 GP)
        AssessmentEntry.objects.create(student=self.enrollment_y1, subject=self.subject, component=self.ca_component, score=20, entered_by=self.teacher, term=self.term_y1_1)
        AssessmentEntry.objects.create(student=self.enrollment_y1, subject=self.subject, component=self.exam_component, score=60, entered_by=self.teacher, term=self.term_y1_1)
        term_res1 = TermResultService.compute_student_term_result(self.student, self.term_y1_1, self.academic_year_1, self.user, skip_ranking=True)
        term_res1.is_published = True
        term_res1.save()
        
        annual_res1 = AnnualResultService.compute_annual_result(self.student, self.academic_year_1, self.user)
        annual_res1.is_published = True
        annual_res1.lifecycle_state = "PUBLISHED"
        annual_res1.save()
        
        # Year 2 Term 1: 65% (B, 3.0 GP)
        AssessmentEntry.objects.create(student=self.enrollment_y2, subject=self.subject, component=self.ca_component2, score=25, entered_by=self.teacher, term=self.term_y2_1)
        AssessmentEntry.objects.create(student=self.enrollment_y2, subject=self.subject, component=self.exam_component2, score=40, entered_by=self.teacher, term=self.term_y2_1)
        term_res2 = TermResultService.compute_student_term_result(self.student, self.term_y2_1, self.academic_year_2, self.user, skip_ranking=True)
        term_res2.is_published = True
        term_res2.save()
        
        annual_res2 = AnnualResultService.compute_annual_result(self.student, self.academic_year_2, self.user)
        annual_res2.is_published = True
        annual_res2.lifecycle_state = "PUBLISHED"
        annual_res2.save()
        
        # Compute cumulative
        cum_res = CumulativeResultService.compute_cumulative_result(self.student, self.academic_year_2, self.user)
        
        self.assertIsNotNone(cum_res)
        
        # Average of 80 and 65 is 72.5
        self.assertEqual(cum_res.cumulative_average, Decimal("72.50"))
        
        # Grade point resolved for 72.50% on GradeRule (70-100 => 4.0)
        self.assertEqual(cum_res.cumulative_gpa, Decimal("4.00"))
