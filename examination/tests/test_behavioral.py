from school.testcases import TenantTestCase as TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from examination.models import (
    BehavioralDomain, BehavioralTrait, StudentBehavioralRating, TermResult, LifecycleState, GradingScheme
)
from examination.services.behavioral_rating_service import BehavioralRatingService
from academic.models import ClassRoom, GradeLevel, Student, Teacher
from administration.models import AcademicYear, Term

User = get_user_model()

class BehavioralRatingTests(TestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        tenant.auto_create_schema = True
        return super().setup_tenant(tenant)

    def setUp(self):
        self.user = User.objects.create_user(password="password", email="teacher1@example.com", first_name="John", last_name="Doe")
        self.admin = User.objects.create_superuser(password="password", email="admin@example.com", first_name="Admin", last_name="User")
        self.teacher = Teacher.objects.create(user=self.user, empId="T001", short_name="JD")

        self.academic_year = AcademicYear.objects.create(name="2023/2024", start_date="2023-09-01", end_date="2024-07-01", active_year=True)
        self.term = Term.objects.create(name="First Term", academic_year=self.academic_year, start_date="2023-09-01", end_date="2023-12-15")
        self.grade_level = GradeLevel.objects.create(system_code="JSS_1", default_name="JSS 1", section="JSS", sequence_order=1)
        self.classroom = ClassRoom.objects.create(name="JSS 1A", grade_level=self.grade_level, class_teacher=self.teacher)
        
        self.student = Student.objects.create(first_name="Test", last_name="Student", classroom=self.classroom, admission_number="STD-001")
        
        self.scheme = GradingScheme.objects.create(name="Standard", academic_year=self.academic_year, grade_level=self.grade_level)
        self.term_result = TermResult.objects.create(
            student=self.student, term=self.term, academic_year=self.academic_year, classroom=self.classroom,
            lifecycle_state=LifecycleState.COMPUTED, grading_scheme=self.scheme, scheme_name="Standard",
            total_marks=50, average_percentage=50.0, grade="C", gpa=2.5
        )
        
        self.trait_affective = BehavioralTrait.objects.create(domain=BehavioralDomain.AFFECTIVE, name="Punctuality", order=1)
        self.trait_psychomotor = BehavioralTrait.objects.create(domain=BehavioralDomain.PSYCHOMOTOR, name="Handwriting", order=2)
        self.trait_jss = BehavioralTrait.objects.create(domain=BehavioralDomain.AFFECTIVE, name="Leadership", section="JSS", order=3)
        self.trait_primary = BehavioralTrait.objects.create(domain=BehavioralDomain.AFFECTIVE, name="Playfulness", section="PRIMARY", order=4)

    def test_create_valid_rating(self):
        rating = BehavioralRatingService.record_rating(self.term_result, self.trait_affective, 5, self.user)
        self.assertEqual(rating.rating, 5)

    def test_rating_out_of_bounds_rejected(self):
        with self.assertRaises(ValidationError):
            BehavioralRatingService.record_rating(self.term_result, self.trait_affective, 6, self.user)
        
        with self.assertRaises(ValidationError):
            BehavioralRatingService.record_rating(self.term_result, self.trait_affective, 0, self.user)

    def test_applicable_traits(self):
        traits = BehavioralRatingService.get_applicable_traits(student_section="JSS")
        names = [t.name for t in traits]
        self.assertIn("Punctuality", names)
        self.assertIn("Leadership", names)
        self.assertNotIn("Playfulness", names)

    def test_invalid_section_trait_rejected(self):
        with self.assertRaises(ValidationError):
            BehavioralRatingService.record_rating(self.term_result, self.trait_primary, 4, self.user)

    def test_unauthorized_teacher_rejected(self):
        other_user = User.objects.create_user(password="password", email="teacher2@example.com")
        with self.assertRaises(ValidationError):
            BehavioralRatingService.record_rating(self.term_result, self.trait_affective, 4, other_user)

    def test_locked_result_rejected(self):
        for state in [LifecycleState.LOCKED, LifecycleState.PUBLISHED, LifecycleState.HOMEROOM_APPROVED, LifecycleState.ADMIN_APPROVED]:
            self.term_result.lifecycle_state = state
            self.term_result.save()
            with self.assertRaises(ValidationError):
                BehavioralRatingService.record_rating(
                    term_result=self.term_result,
                    trait=self.trait_affective,
                    rating=4,
                    user=self.teacher.user
                )

    def test_bulk_record_ratings(self):
        data = [
            {"trait_id": self.trait_affective.id, "rating": 5},
            {"trait_id": self.trait_psychomotor.id, "rating": 3}
        ]
        BehavioralRatingService.bulk_record_ratings(self.term_result, data, self.user)
        self.assertEqual(StudentBehavioralRating.objects.count(), 2)
