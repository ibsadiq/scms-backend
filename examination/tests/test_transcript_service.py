from django_tenants.test.cases import TenantTestCase as TestCase
from django.contrib.auth import get_user_model
from administration.models import AcademicYear, Term
from academic.models import Student, ClassRoom, GradeLevel, Subject, StudentClassEnrollment, ClassLevel, Teacher
from examination.models import (
    GradingScheme, AssessmentComponent, GradeRule, PromotionRule,
    AssessmentEntry, TermResult, SubjectResult, CumulativeResult
)
from examination.services.term_result_service import TermResultService
from examination.services.annual_result_service import AnnualResultService
from examination.services.cumulative_result_service import CumulativeResultService
from examination.services.transcript_service import TranscriptService

User = get_user_model()

class TranscriptServiceTestCase(TestCase):
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
        GradeRule.objects.create(scheme=self.scheme, min_score=0, max_score=39, grade="F", grade_point=0.0)
        
        PromotionRule.objects.create(
            scheme=self.scheme,
            minimum_average=40,
            minimum_subject_pass=40
        )

    def test_transcript_generation(self):
        # 100%
        AssessmentEntry.objects.create(student=self.enrollment, subject=self.subject, component=self.ca_component, score=30, entered_by=self.teacher)
        AssessmentEntry.objects.create(student=self.enrollment, subject=self.subject, component=self.exam_component, score=70, entered_by=self.teacher)
        term_res = TermResultService.compute_student_term_result(self.student, self.term1, self.academic_year, self.user, skip_ranking=True)
        term_res.is_published = True
        term_res.save()
        
        annual_res = AnnualResultService.compute_annual_result(self.student, self.academic_year, self.user)
        annual_res.is_published = True
        annual_res.save()
        
        cum_res = CumulativeResultService.compute_cumulative_result(self.student, self.academic_year, self.user)
        cum_res.lifecycle_state = "PUBLISHED"
        cum_res.save()
        
        transcript = TranscriptService.generate_transcript(self.student, self.user)
        
        self.assertIsNotNone(transcript)
        self.assertIsNotNone(transcript.history_snapshot)
        self.assertEqual(transcript.student, self.student)
        
        # Verify JSON payload structure
        snapshot = transcript.history_snapshot
        self.assertEqual(snapshot['admission_number'], "STD001")
        self.assertIn("records", snapshot)
        
        # Verify we can extract the annual result from the snapshot
        year_data = snapshot['records'][0]
        self.assertEqual(year_data['academic_year'], "2024/2025")
        

