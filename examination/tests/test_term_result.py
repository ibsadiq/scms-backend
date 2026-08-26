from decimal import Decimal
from school.testcases import TenantTestCase as TestCase
from django.contrib.auth import get_user_model
from administration.models import AcademicYear, Term
from academic.models import Student, ClassRoom, GradeLevel, Subject, StudentClassEnrollment, SectionType
from examination.models import (
    GradingScheme, AssessmentComponent, GradeRule, PromotionRule,
    AssessmentEntry, TermResult, SubjectResult
)
from examination.services.term_result_service import TermResultService

User = get_user_model()

class TermResultServiceTestCase(TestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        return super().setup_tenant(tenant)

    def setUp(self):
        self.user = User.objects.create_user(email="test@admin.com", password="password")
        self.academic_year = AcademicYear.objects.create(name="2024/2025", start_date="2024-09-01", end_date="2025-07-01", active_year=True)
        self.term = Term.objects.create(academic_year=self.academic_year, name="Term 1", start_date="2024-09-01", end_date="2024-12-15")
        
        self.grade_level = GradeLevel.objects.create(system_code="JSS_1", default_name="JSS 1", section="JSS", sequence_order=1)
        self.classroom = ClassRoom.objects.create(name="A", grade_level=self.grade_level)
        self.subject = Subject.objects.create(name="Mathematics", subject_code="MTH")
        self.subject2 = Subject.objects.create(name="English", subject_code="ENG")
        
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
        GradeRule.objects.create(scheme=self.scheme, min_score=60, max_score=69.99, grade="B", remark="Good", grade_point=3.0)
        GradeRule.objects.create(scheme=self.scheme, min_score=50, max_score=59.99, grade="C", remark="Average", grade_point=2.0)
        GradeRule.objects.create(scheme=self.scheme, min_score=0, max_score=49.99, grade="F", remark="Fail", grade_point=0.0)
        
        PromotionRule.objects.create(
            scheme=self.scheme, minimum_average=40, minimum_subject_pass=50, max_failed_subjects=2
        )

    def test_term_result_computation(self):
        from academic.models import Teacher
        self.teacher = Teacher.objects.create(user=self.user, empId="T001", short_name="TS")
        
        # Add entries for Math
        AssessmentEntry.objects.create(
            student=self.enrollment, subject=self.subject, component=self.ca_component, score=25,
            entered_by=self.teacher, term=self.term, academic_year=self.academic_year,
        )
        AssessmentEntry.objects.create(
            student=self.enrollment, subject=self.subject, component=self.exam_component, score=50,
            entered_by=self.teacher, term=self.term, academic_year=self.academic_year,
        )
        
        # Add entries for English (Failed)
        AssessmentEntry.objects.create(
            student=self.enrollment, subject=self.subject2, component=self.ca_component, score=10,
            entered_by=self.teacher, term=self.term, academic_year=self.academic_year,
        )
        AssessmentEntry.objects.create(
            student=self.enrollment, subject=self.subject2, component=self.exam_component, score=30,
            entered_by=self.teacher, term=self.term, academic_year=self.academic_year,
        )
        
        result = TermResultService.compute_student_term_result(
            self.student, self.term, self.academic_year, self.user, skip_ranking=True
        )
        
        self.assertIsNotNone(result)
        
        # Math: (25/30)*30 + (50/70)*70 = 25 + 50 = 75 => A
        # Eng: (10/30)*30 + (30/70)*70 = 10 + 30 = 40 => F
        math_res = result.subject_results.get(subject=self.subject)
        eng_res = result.subject_results.get(subject=self.subject2)
        
        self.assertEqual(math_res.percentage, Decimal("75.00"))
        self.assertEqual(math_res.grade, "A")
        self.assertTrue(math_res.is_pass)
        
        self.assertEqual(eng_res.percentage, Decimal("40.00"))
        self.assertEqual(eng_res.grade, "F")
        self.assertFalse(eng_res.is_pass)
        
        self.assertEqual(result.total_marks, Decimal("115.00"))
        self.assertEqual(result.average_percentage, Decimal("57.50")) # 115 / 2
        self.assertEqual(result.grade, "C") # 57.50 is between 50 and 59.99
        self.assertFalse(result.is_pass) # One subject failed, overall pass is false
