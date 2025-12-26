#!/usr/bin/env python
"""
Create Test Users for Frontend Testing
Creates sample student and parent accounts with known credentials
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

from django.contrib.auth import get_user_model
from academic.models import Student, Parent, Teacher, ClassRoom, Subject
from administration.models import AcademicYear, Term
from django.utils import timezone

User = get_user_model()

def create_test_data():
    print("=" * 60)
    print("CREATING TEST USERS FOR LOGIN")
    print("=" * 60)
    print()

    # Get or create academic year and term
    academic_year, _ = AcademicYear.objects.get_or_create(
        name="2024/2025",
        defaults={
            'start_date': '2024-09-01',
            'end_date': '2025-08-31',
            'active_year': True
        }
    )

    term, _ = Term.objects.get_or_create(
        name="First Term",
        academic_year=academic_year,
        defaults={
            'start_date': '2024-09-01',
            'end_date': '2024-12-15',
            'default_term_fee': 50000
        }
    )

    # Get or create a classroom
    classroom = ClassRoom.objects.first()
    if not classroom:
        print("⚠️  No classroom found. Creating one...")
        from academic.models import ClassLevel, GradeLevel

        grade_level, _ = GradeLevel.objects.get_or_create(
            name="Junior Secondary",
            defaults={'description': 'Junior Secondary School'}
        )

        class_level, _ = ClassLevel.objects.get_or_create(
            name="JSS 3",
            defaults={'description': 'Junior Secondary School 3'}
        )

        classroom, _ = ClassRoom.objects.get_or_create(
            name="Form 3A",
            defaults={
                'class_level': class_level,
                'grade_level': grade_level,
                'capacity': 40
            }
        )

    print(f"✓ Academic Year: {academic_year.name}")
    print(f"✓ Term: {term.name}")
    print(f"✓ Classroom: {classroom.name}")
    print()

    # ========================================
    # CREATE PARENT USER
    # ========================================
    print("-" * 60)
    print("CREATING PARENT USER")
    print("-" * 60)

    # Check if parent profile exists (will auto-create user via save method)
    parent = Parent.objects.filter(phone_number='08012345678').first()
    if not parent:
        parent = Parent.objects.create(
            first_name='John',
            middle_name='Paul',
            last_name='Doe',
            email='parent@test.com',
            phone_number='08012345678',
            gender='M',
            address='123 Test Street, Lagos'
        )
        print("✓ Created parent profile and user account")

    # Update password to our known test password
    if parent.user:
        parent.user.set_password('parent123')
        parent.user.save()
        print("✓ Updated parent password to test credentials")

    print()
    print("📧 PARENT CREDENTIALS:")
    print(f"   Email: parent@test.com")
    print(f"   Password: parent123")
    print(f"   Name: {parent.first_name} {parent.last_name}")
    print()

    # ========================================
    # CREATE STUDENT USER
    # ========================================
    print("-" * 60)
    print("CREATING STUDENT USER")
    print("-" * 60)

    # Check if student exists
    student = Student.objects.filter(admission_number='TEST/2024/001').first()

    if student:
        print("Student record already exists. Updating...")
        student.phone_number = '08098765432'
        student.parent_contact = '08012345678'  # Parent's phone number
        student.can_login = True
        student.is_active = True
        student.parent_guardian = parent

        # If student already has a user, update password and phone
        if student.user:
            student.user.phone_number = '08098765432'  # Ensure phone is set
            student.user.set_password('student123')
            student.user.save()
            print("✓ Updated existing student user password and phone")
        else:
            # Create new user for student
            student_user = User.objects.create_user(
                email=f'{student.admission_number}@student.local',
                password='student123',
                first_name=student.first_name,
                last_name=student.last_name,
                phone_number='08098765432',  # Set phone on user for login
                is_student=True
            )
            student.user = student_user
            print("✓ Created student user account")

        student.save()
    else:
        # Create new student
        student = Student.objects.create(
            admission_number='TEST/2024/001',
            first_name='Jane',
            middle_name='Mary',
            last_name='Doe',
            gender='F',
            date_of_birth='2010-05-15',
            phone_number='08098765432',
            parent_contact='08012345678',  # Parent's phone number
            is_active=True,
            can_login=True,
            parent_guardian=parent
        )

        # Create user account for student
        student_user = User.objects.create_user(
            email=f'{student.admission_number}@student.local',
            password='student123',
            first_name=student.first_name,
            last_name=student.last_name,
            phone_number='08098765432',  # Set phone on user for login
            is_student=True
        )

        student.user = student_user
        student.save()
        print("✓ Created student record and user account")

    # Enroll student in classroom
    from academic.models import StudentClassEnrollment
    enrollment, created = StudentClassEnrollment.objects.get_or_create(
        student=student,
        academic_year=academic_year,
        defaults={
            'classroom': classroom,
            'is_active': True
        }
    )
    if created:
        print(f"✓ Enrolled student in {classroom.name}")

    print()
    print("📱 STUDENT CREDENTIALS:")
    print(f"   Phone: 08098765432")
    print(f"   Password: student123")
    print(f"   Admission Number: TEST/2024/001")
    print(f"   Name: {student.full_name}")
    print(f"   Classroom: {classroom.name}")
    print(f"   Parent: {parent.first_name} {parent.last_name}")
    print()

    # ========================================
    # CREATE TEACHER USER (BONUS)
    # ========================================
    print("-" * 60)
    print("CREATING TEACHER USER (BONUS)")
    print("-" * 60)

    teacher_user = User.objects.filter(email='teacher@test.com').first()
    if teacher_user:
        print("Teacher user already exists. Updating password...")
        teacher_user.set_password('teacher123')
        teacher_user.save()
    else:
        teacher_user = User.objects.create_user(
            email='teacher@test.com',
            password='teacher123',
            first_name='Sarah',
            last_name='Smith',
            is_teacher=True
        )
        print("✓ Created teacher user account")

    teacher = Teacher.objects.filter(user=teacher_user).first()
    if not teacher:
        teacher = Teacher.objects.create(
            user=teacher_user,
            empId='TEACH001',
            address='456 Teacher Lane, Lagos'
        )
        print("✓ Created teacher profile")

    print()
    print("👨‍🏫 TEACHER CREDENTIALS:")
    print(f"   Email: teacher@test.com")
    print(f"   Password: teacher123")
    print(f"   Name: {teacher.first_name} {teacher.last_name}")
    print()

    # ========================================
    # SUMMARY
    # ========================================
    print("=" * 60)
    print("✅ TEST USERS CREATED SUCCESSFULLY!")
    print("=" * 60)
    print()
    print("You can now login with these credentials:")
    print()
    print("1️⃣  PARENT LOGIN (Email/Password):")
    print("   URL: POST /api/users/token/")
    print("   Email: parent@test.com")
    print("   Password: parent123")
    print()
    print("2️⃣  STUDENT LOGIN (Phone/Password):")
    print("   URL: POST /api/academic/students/auth/login/")
    print("   Phone: 08098765432")
    print("   Password: student123")
    print()
    print("   OR STUDENT REGISTRATION (if you delete the user):")
    print("   URL: POST /api/academic/students/auth/register/")
    print("   Phone: 08098765432")
    print("   Password: student123")
    print("   Admission Number: TEST/2024/001")
    print()
    print("3️⃣  TEACHER LOGIN (Email/Password):")
    print("   URL: POST /api/users/token/")
    print("   Email: teacher@test.com")
    print("   Password: teacher123")
    print()
    print("=" * 60)
    print()

if __name__ == '__main__':
    try:
        create_test_data()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
