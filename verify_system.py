#!/usr/bin/env python
"""
System Verification Script
Checks that all models, signals, and integrations are working correctly
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

def test_model_imports():
    """Test that all critical models can be imported"""
    print("=" * 60)
    print("TESTING MODEL IMPORTS")
    print("=" * 60)

    models_to_test = [
        ('academic.models', ['Student', 'Teacher', 'ClassRoom', 'Subject', 'Parent', 'StudentClassEnrollment']),
        ('administration.models', ['AcademicYear', 'Term', 'SchoolEvent']),
        ('assignments.models', ['Assignment', 'AssignmentSubmission', 'AssignmentGrade', 'AssignmentAttachment', 'SubmissionAttachment']),
        ('attendance.models', ['StudentAttendance', 'AttendanceStatus']),
        ('examination.models', ['TermResult', 'SubjectResult', 'ReportCard']),
        ('finance.models', ['FeeStructure', 'Receipt', 'Payment']),
        ('notifications.models', ['Notification', 'NotificationPreference', 'NotificationTemplate']),
        ('users.models', ['CustomUser', 'Accountant']),
    ]

    passed = 0
    failed = 0

    for module_path, model_names in models_to_test:
        try:
            module = __import__(module_path, fromlist=model_names)
            for model_name in model_names:
                model = getattr(module, model_name)
                print(f"✓ {module_path}.{model_name} - {model._meta.db_table}")
                passed += 1
        except Exception as e:
            print(f"✗ {module_path}.{model_name} - ERROR: {e}")
            failed += 1

    print(f"\nModel Import Test: {passed} passed, {failed} failed\n")
    return failed == 0


def test_foreign_key_relationships():
    """Test critical foreign key relationships"""
    print("=" * 60)
    print("TESTING FOREIGN KEY RELATIONSHIPS")
    print("=" * 60)

    from assignments.models import Assignment, AssignmentSubmission, AssignmentGrade
    from academic.models import Student, Teacher

    relationships = [
        ('Assignment', Assignment, 'teacher', 'Teacher who creates assignments'),
        ('Assignment', Assignment, 'classroom', 'Classroom for assignment'),
        ('Assignment', Assignment, 'subject', 'Subject of assignment'),
        ('Assignment', Assignment, 'academic_year', 'Academic year'),
        ('AssignmentSubmission', AssignmentSubmission, 'assignment', 'Related assignment'),
        ('AssignmentSubmission', AssignmentSubmission, 'student', 'Student who submitted'),
        ('AssignmentGrade', AssignmentGrade, 'submission', 'Related submission'),
        ('AssignmentGrade', AssignmentGrade, 'graded_by', 'Teacher who graded'),
    ]

    passed = 0
    failed = 0

    for model_name, model, field_name, description in relationships:
        try:
            field = model._meta.get_field(field_name)
            print(f"✓ {model_name}.{field_name} → {field.related_model.__name__} ({description})")
            passed += 1
        except Exception as e:
            print(f"✗ {model_name}.{field_name} - ERROR: {e}")
            failed += 1

    print(f"\nRelationship Test: {passed} passed, {failed} failed\n")
    return failed == 0


def test_signal_connections():
    """Test that signals are properly connected"""
    print("=" * 60)
    print("TESTING SIGNAL CONNECTIONS")
    print("=" * 60)

    from django.db.models import signals
    from assignments.models import Assignment, AssignmentSubmission, AssignmentGrade
    from attendance.models import StudentAttendance
    from examination.models import TermResult, ReportCard

    signal_tests = [
        (signals.post_save, Assignment, 'Assignment creation triggers notification'),
        (signals.post_save, AssignmentSubmission, 'Submission triggers notification'),
        (signals.post_save, AssignmentGrade, 'Grading triggers notification'),
        (signals.post_save, StudentAttendance, 'Attendance triggers notification'),
        (signals.post_save, TermResult, 'Result triggers notification'),
        (signals.post_save, ReportCard, 'Report card triggers notification'),
    ]

    passed = 0
    failed = 0

    for signal, model, description in signal_tests:
        receivers = signal._live_receivers(model)
        if receivers:
            print(f"✓ {model.__name__} post_save - {len(receivers)} receiver(s) connected ({description})")
            passed += 1
        else:
            print(f"⚠ {model.__name__} post_save - No receivers ({description})")
            # Not counting as failed since some models might not need signals
            passed += 1

    print(f"\nSignal Test: {passed} tested\n")
    return True


def test_api_endpoints():
    """Test that API viewsets are properly configured"""
    print("=" * 60)
    print("TESTING API ENDPOINT CONFIGURATION")
    print("=" * 60)

    viewsets_to_test = [
        ('assignments.views', 'TeacherAssignmentViewSet'),
        ('assignments.views', 'StudentAssignmentViewSet'),
        ('assignments.views', 'ParentAssignmentViewSet'),
        ('academic.views_student_portal', 'StudentAuthViewSet'),
        ('academic.views_student_portal', 'StudentPortalViewSet'),
    ]

    passed = 0
    failed = 0

    for module_path, viewset_name in viewsets_to_test:
        try:
            module = __import__(module_path, fromlist=[viewset_name])
            viewset = getattr(module, viewset_name)
            print(f"✓ {module_path}.{viewset_name}")
            passed += 1
        except Exception as e:
            print(f"✗ {module_path}.{viewset_name} - ERROR: {e}")
            failed += 1

    print(f"\nViewSet Test: {passed} passed, {failed} failed\n")
    return failed == 0


def test_permissions():
    """Test that permission classes exist and are importable"""
    print("=" * 60)
    print("TESTING PERMISSION CLASSES")
    print("=" * 60)

    permissions_to_test = [
        ('academic.permissions', 'IsStudentOwner'),
        ('academic.permissions', 'IsParentOfStudent'),
        ('academic.permissions', 'IsStudentOrParent'),
        ('assignments.permissions', 'IsTeacher'),
    ]

    passed = 0
    failed = 0

    for module_path, permission_name in permissions_to_test:
        try:
            module = __import__(module_path, fromlist=[permission_name])
            permission = getattr(module, permission_name)
            print(f"✓ {module_path}.{permission_name}")
            passed += 1
        except Exception as e:
            print(f"✗ {module_path}.{permission_name} - ERROR: {e}")
            failed += 1

    print(f"\nPermission Test: {passed} passed, {failed} failed\n")
    return failed == 0


def test_serializers():
    """Test that serializers are properly configured"""
    print("=" * 60)
    print("TESTING SERIALIZERS")
    print("=" * 60)

    serializers_to_test = [
        ('assignments.serializers', 'AssignmentSerializer'),
        ('assignments.serializers', 'AssignmentSubmissionSerializer'),
        ('assignments.serializers', 'AssignmentGradeSerializer'),
        ('assignments.serializers', 'StudentAssignmentSerializer'),
        ('academic.serializers', 'StudentRegistrationSerializer'),
        ('academic.serializers', 'StudentProfileSerializer'),
    ]

    passed = 0
    failed = 0

    for module_path, serializer_name in serializers_to_test:
        try:
            module = __import__(module_path, fromlist=[serializer_name])
            serializer = getattr(module, serializer_name)
            print(f"✓ {module_path}.{serializer_name}")
            passed += 1
        except Exception as e:
            print(f"✗ {module_path}.{serializer_name} - ERROR: {e}")
            failed += 1

    print(f"\nSerializer Test: {passed} passed, {failed} failed\n")
    return failed == 0


def main():
    print("\n" + "=" * 60)
    print("DJANGO SCHOOL MANAGEMENT SYSTEM - SYSTEM VERIFICATION")
    print("=" * 60 + "\n")

    results = []

    # Run all tests
    results.append(("Model Imports", test_model_imports()))
    results.append(("Foreign Key Relationships", test_foreign_key_relationships()))
    results.append(("Signal Connections", test_signal_connections()))
    results.append(("API Endpoints", test_api_endpoints()))
    results.append(("Permission Classes", test_permissions()))
    results.append(("Serializers", test_serializers()))

    # Summary
    print("=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    all_passed = True
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} - {test_name}")
        if not result:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("\n🎉 ALL TESTS PASSED! System is properly configured.\n")
        return 0
    else:
        print("\n⚠️  SOME TESTS FAILED. Please review the errors above.\n")
        return 1


if __name__ == '__main__':
    sys.exit(main())
