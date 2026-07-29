import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

from django_tenants.utils import schema_context
from users.models import CustomUser
from academic.models import Student, ClassRoom, Parent

schema_name = 'green_valley_academy'

with schema_context(schema_name):
    # 1. Create or get CustomUser account
    user, _ = CustomUser.objects.get_or_create(
        email='student@demo.com',
        defaults={
            'first_name': 'Lara',
            'last_name': 'Parent',
            'is_active': True,
            'is_student': True,
        }
    )
    user.set_password('password123')
    user.is_active = True
    user.is_student = True
    user.first_name = 'Lara'
    user.last_name = 'Parent'
    user.save()

    # 2. Check if student record exists for user or admission_number ADM-2026-0001
    existing_student = Student.objects.filter(user=user).first()
    if not existing_student:
        existing_student = Student.objects.filter(admission_number='ADM-2026-0001').first()

    parent = Parent.objects.first()
    parent_contact = parent.phone_number if (parent and parent.phone_number) else "+2348010000000"
    classroom = ClassRoom.objects.first()

    if existing_student:
        existing_student.user = user
        if not existing_student.parent_contact:
            existing_student.parent_contact = parent_contact
        existing_student.save()
        print(f"✓ Linked student@demo.com to existing Student: {existing_student.first_name} {existing_student.last_name} ({existing_student.admission_number})")
    else:
        Student.objects.create(
            user=user,
            first_name='Lara',
            last_name='Parent',
            admission_number='ADM-2026-0001',
            classroom=classroom,
            parent_guardian=parent,
            parent_contact=parent_contact
        )
        print("✓ Created new Demo Student ADM-2026-0001")

    print("\n🎉 DEMO STUDENT ACCOUNT ACTIVATED!")
    print("Login Email: student@demo.com")
    print("Password: password123")
