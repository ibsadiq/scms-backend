from school.testcases import TenantTestCase as TestCase
from django.contrib.auth import get_user_model
from administration.models import AcademicYear, Term
from academic.models import Student, ClassRoom, GradeLevel, Subject, StudentClassEnrollment, ClassLevel, Teacher
from examination.models import (
    GradingScheme, AssessmentComponent, GradeRule, PromotionRule,
    AssessmentEntry, TermResult, SubjectResult
)
from examination.services.term_result_service import TermResultService
from examination.services.annual_result_service import AnnualResultService
from examination.services.promotion_service import PromotionService

User = get_user_model()

class PromotionServiceTestCase(TestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        return super().setup_tenant(tenant)

    def setUp(self):
        self.user = User.objects.create_user(email="test@admin.com", password="password")
        self.teacher = Teacher.objects.create(user=self.user, empId="T001", short_name="TS")
        
        self.academic_year = AcademicYear.objects.create(name="2024/2025", start_date="2024-09-01", end_date="2025-07-01", active_year=True)
        self.term1 = Term.objects.create(academic_year=self.academic_year, name="Term 1", start_date="2024-09-01", end_date="2024-12-15")
        
        self.grade_level = GradeLevel.objects.create(system_code="JSS_1", default_name="JSS 1", section="JSS", sequence_order=1)
        self.class_level = ClassLevel.objects.create(name="JSS 1A", grade_level=self.grade_level)
        self.classroom = ClassRoom.objects.create(name=self.class_level)
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

    def test_promotion_override(self):
        # Student gets 20% (Fails)
        AssessmentEntry.objects.create(student=self.enrollment, subject=self.subject, component=self.ca_component, score=5, entered_by=self.teacher)
        AssessmentEntry.objects.create(student=self.enrollment, subject=self.subject, component=self.exam_component, score=15, entered_by=self.teacher)
        term_res = TermResultService.compute_student_term_result(self.student, self.term1, self.academic_year, self.user, skip_ranking=True)
        term_res.is_published = True
        term_res.save()
        
        annual_res = AnnualResultService.compute_annual_result(self.student, self.academic_year, self.user)
        
        # Verify student is initially failed
        self.assertEqual(annual_res.promotion_decision.status, "NOT_PROMOTED")
        
        # Override promotion
        overridden_res = PromotionService.override_promotion(
            annual_result=annual_res,
            new_status="CONDITIONAL_PROMOTION",
            reason="Improved over terms",
            user=self.user
        )
        
        self.assertTrue(overridden_res.is_overridden)
        self.assertEqual(overridden_res.status, "CONDITIONAL_PROMOTION")
        self.assertEqual(overridden_res.override_reason, "Improved over terms")
