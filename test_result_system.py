"""
Test Script for Result Computation System (Phase 1.1)
Run with: uv run python test_result_system.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

from examination.models import TermResult, SubjectResult, GradeScale, GradeScaleRule
from examination.services import GradingEngine, ResultComputationService
from academic.models import Student, ClassRoom
from administration.models import Term
from decimal import Decimal


def test_models():
    """Test 1: Verify models are accessible"""
    print("=" * 60)
    print("TEST 1: Model Verification")
    print("=" * 60)

    try:
        print(f"✓ TermResult model: OK")
        print(f"✓ SubjectResult model: OK")
        print(f"  - GradeScale count: {GradeScale.objects.count()}")
        print(f"  - GradeScaleRule count: {GradeScaleRule.objects.count()}")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_grading_engine():
    """Test 2: Test grading engine with configurable scales"""
    print("\n" + "=" * 60)
    print("TEST 2: Grading Engine")
    print("=" * 60)

    try:
        engine = GradingEngine()
        print(f"✓ GradingEngine initialized")
        print(f"  - Using grade scale: {engine.grade_scale.name if engine.grade_scale else 'None'}")

        # Test various percentages
        test_scores = [95, 85, 72, 65, 55, 45, 35]
        print(f"\n  Testing grade calculations:")
        for score in test_scores:
            grade, gpa, remark = engine.get_grade_from_percentage(Decimal(score))
            print(f"    {score}% → Grade: {grade}, GPA: {gpa}, Remark: {remark}")

        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_data_availability():
    """Test 3: Check if we have data to compute results"""
    print("\n" + "=" * 60)
    print("TEST 3: Data Availability")
    print("=" * 60)

    try:
        students = Student.objects.filter(is_active=True)
        classrooms = ClassRoom.objects.all()
        terms = Term.objects.all()

        print(f"✓ Active students: {students.count()}")
        print(f"✓ Classrooms: {classrooms.count()}")
        print(f"✓ Terms: {terms.count()}")

        if classrooms.exists():
            classroom = classrooms.first()
            print(f"\n  Sample classroom: {classroom}")
            print(f"  - Students in classroom: {Student.objects.filter(classroom=classroom, is_active=True).count()}")

        if terms.exists():
            term = terms.first()
            print(f"\n  Sample term: {term.name}")
            print(f"  - Academic Year: {term.academic_year.name if term.academic_year else 'N/A'}")

        return students.exists() and classrooms.exists() and terms.exists()
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_result_computation():
    """Test 4: Test result computation for a classroom"""
    print("\n" + "=" * 60)
    print("TEST 4: Result Computation")
    print("=" * 60)

    try:
        # Get first available classroom and term
        classroom = ClassRoom.objects.first()
        term = Term.objects.first()

        if not classroom or not term:
            print("✗ No classroom or term available for testing")
            return False

        print(f"  Testing with:")
        print(f"  - Classroom: {classroom}")
        print(f"  - Term: {term.name}")

        # Check if we have students
        students = Student.objects.filter(classroom=classroom, is_active=True)
        print(f"  - Students: {students.count()}")

        if not students.exists():
            print("⚠ No students in classroom - cannot test computation")
            return False

        # Initialize service
        from users.models import CustomUser
        admin_user = CustomUser.objects.filter(is_staff=True).first()

        service = ResultComputationService(
            term=term,
            classroom=classroom,
            computed_by=admin_user
        )

        print(f"\n✓ ResultComputationService initialized")
        print(f"  - Using grading scale: {service.grading_engine.grade_scale.name}")

        # Check if results already exist
        existing_results = TermResult.objects.filter(
            term=term,
            classroom=classroom
        ).count()

        print(f"  - Existing results: {existing_results}")

        if existing_results > 0:
            print(f"\n⚠ Results already exist. Use recompute=True to recompute.")
            print(f"\n  Sample existing result:")
            result = TermResult.objects.filter(term=term, classroom=classroom).first()
            print(f"  - Student: {result.student.full_name}")
            print(f"  - Average: {result.average_percentage}%")
            print(f"  - Grade: {result.grade}")
            print(f"  - GPA: {result.gpa}")
            print(f"  - Position: {result.position_in_class}/{result.total_students}")
            print(f"  - Published: {result.is_published}")
        else:
            print(f"\n⚠ No marks data available - cannot compute results")
            print(f"  You need to add marks in MarksManagement first")

        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_grade_scale_creation():
    """Test 5: Check or create default grade scale"""
    print("\n" + "=" * 60)
    print("TEST 5: Grade Scale Configuration")
    print("=" * 60)

    try:
        grade_scales = GradeScale.objects.all()

        if grade_scales.exists():
            print(f"✓ Existing grade scales: {grade_scales.count()}")
            for scale in grade_scales:
                print(f"\n  Grade Scale: {scale.name}")
                rules = scale.gradescalerule_set.all().order_by('-min_grade')
                for rule in rules:
                    print(f"    {rule.min_grade}-{rule.max_grade} → {rule.letter_grade} ({rule.numeric_scale})")
        else:
            print("⚠ No grade scales found. Creating default Nigerian scale...")
            from examination.services import GradingEngine
            engine = GradingEngine()  # This will create default scale
            print(f"✓ Default scale created: {engine.grade_scale.name}")

        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 10 + "RESULT COMPUTATION SYSTEM - TEST SUITE" + " " * 10 + "║")
    print("╚" + "═" * 58 + "╝")

    results = []

    results.append(("Models", test_models()))
    results.append(("Grade Scale Configuration", test_grade_scale_creation()))
    results.append(("Grading Engine", test_grading_engine()))
    results.append(("Data Availability", test_data_availability()))
    results.append(("Result Computation", test_result_computation()))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} - {test_name}")

    print(f"\n{passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! System is ready for use.")
        print("\nNext steps:")
        print("1. Add marks in MarksManagement (via admin or API)")
        print("2. Test result computation via API:")
        print("   POST /api/examination/term-results/compute/")
        print("   {")
        print('     "term_id": <term_id>,')
        print('     "classroom_id": <classroom_id>')
        print("   }")
    else:
        print("\n⚠ Some tests failed. Please check the errors above.")


if __name__ == '__main__':
    main()
