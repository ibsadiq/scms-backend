"""
Django School Management System - Sample Data Generator

This script generates comprehensive sample data for the SCMS including:
- School information and academic calendar
- Users (teachers, parents, accountants)
- Academic structure (departments, subjects, classes)
- Students with families
- Fee structures and payments
- Attendance records
- Exam results
- Timetable

Usage:
    python manage.py shell < generate_sample_data.py
    OR
    python generate_sample_data.py
"""

import os
import sys
import django
from datetime import datetime, timedelta, date
from decimal import Decimal
import random

# Setup Django environment
if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
    django.setup()

from django.contrib.auth.models import Group
from django.utils import timezone
from users.models import CustomUser, Accountant
from academic.models import (
    Department, Subject, GradeLevel, ClassLevel, ClassYear,
    ClassRoom, Teacher, Parent, Student, StudentClassEnrollment,
    AllocatedSubject, Dormitory, ReasonLeft
)
from administration.models import (
    School, Day, AcademicYear, Term, SchoolEvent, Article
)
from finance.models import (
    FeeStructure, StudentFeeAssignment, Receipt, Payment,
    PaymentCategory, FeePaymentAllocation
)
from attendance.models import AttendanceStatus, StudentAttendance, TeachersAttendance
from examination.models import GradeScale, GradeScaleRule, ExaminationListHandler, MarksManagement
from schedule.models import Period


class DataGenerator:
    """Generate sample data for the school management system"""

    def __init__(self):
        self.teachers = []
        self.parents = []
        self.students = []
        self.classrooms = []
        self.subjects = []
        self.academic_year = None
        self.current_term = None
        self.accountants = []

    def generate_all(self):
        """Generate all sample data"""
        print("=" * 60)
        print("DJANGO SCMS - Sample Data Generator")
        print("=" * 60)

        self.create_groups()
        self.create_school_info()
        self.create_academic_calendar()
        self.create_departments_and_subjects()
        self.create_grade_levels()
        self.create_accountants()
        self.create_teachers()
        self.create_classrooms()
        self.create_parents()
        self.create_students()
        self.create_dormitories()
        self.create_fee_structures()
        self.create_receipts_and_payments()
        self.create_attendance_statuses()
        self.create_attendance_records()
        self.create_grade_scale()
        self.create_examinations()
        self.create_allocated_subjects()
        self.create_timetable()
        self.create_articles()

        print("\n" + "=" * 60)
        print("DATA GENERATION COMPLETE!")
        print("=" * 60)
        self.print_summary()

    def create_groups(self):
        """Create user groups if they don't exist"""
        print("\n[1/18] Creating user groups...")
        groups = ['teacher', 'parent', 'accountant', 'family']
        for group_name in groups:
            Group.objects.get_or_create(name=group_name)
        print(f"  ✓ Created/verified {len(groups)} user groups")

    def create_school_info(self):
        """Create school information"""
        print("\n[2/18] Creating school information...")
        school, created = School.objects.get_or_create(
            active=True,
            defaults={
                'name': 'Hillcrest International School',
                'address': 'Plot 123, Kampala Road, Kampala, Uganda',
                'school_type': 'Boarding-day school',
                'students_gender': 'Mixed',
                'ownership': 'Private',
                'mission': 'To provide quality education that nurtures academic excellence and character development',
                'vision': 'To be the leading educational institution producing future leaders',
                'telephone': '+256-700-123456',
                'school_email': 'info@hillcrest.edu.ug'
            }
        )
        action = "Created" if created else "Found existing"
        print(f"  ✓ {action} school: {school.name}")

        # Create days of week
        days = [
            (1, 'Monday'), (2, 'Tuesday'), (3, 'Wednesday'),
            (4, 'Thursday'), (5, 'Friday'), (6, 'Saturday'), (7, 'Sunday')
        ]
        for day_num, day_name in days:
            Day.objects.get_or_create(day=day_num)
        print(f"  ✓ Created days of the week")

    def create_academic_calendar(self):
        """Create academic year and terms"""
        print("\n[3/18] Creating academic calendar...")

        # Current academic year
        current_year = datetime.now().year
        self.academic_year, created = AcademicYear.objects.get_or_create(
            name=f"{current_year}/{current_year + 1}",
            defaults={
                'start_date': date(current_year, 1, 15),
                'end_date': date(current_year, 12, 15),
                'active_year': True
            }
        )
        print(f"  ✓ Academic Year: {self.academic_year.name}")

        # Create terms
        terms_data = [
            ('One', date(current_year, 1, 15), date(current_year, 4, 5), Decimal('500000')),
            ('Two', date(current_year, 5, 1), date(current_year, 8, 10), Decimal('500000')),
            ('Three', date(current_year, 9, 1), date(current_year, 12, 15), Decimal('500000')),
        ]

        for term_name, start, end, fee in terms_data:
            term, _ = Term.objects.get_or_create(
                name=term_name,
                academic_year=self.academic_year,
                defaults={
                    'start_date': start,
                    'end_date': end,
                    'default_term_fee': fee
                }
            )
            if term_name == 'Two':  # Set current term
                self.current_term = term

        print(f"  ✓ Created {len(terms_data)} terms")

        # Create school events
        events_data = [
            ('Mid-term Break', 'holiday', 30, 7),
            ('End of Term Exams', 'exam', -14, 7),
            ('Graduation Ceremony', 'graduation', -7, 1),
        ]

        for event_name, event_type, days_offset, duration in events_data:
            event_date = self.current_term.end_date + timedelta(days=days_offset)
            SchoolEvent.objects.get_or_create(
                term=self.current_term,
                name=event_name,
                defaults={
                    'event_type': event_type,
                    'start_date': event_date,
                    'end_date': event_date + timedelta(days=duration),
                    'description': f'{event_name} for Term {self.current_term.name}'
                }
            )
        print(f"  ✓ Created school events")

    def create_departments_and_subjects(self):
        """Create academic departments and subjects for Nigerian curriculum"""
        print("\n[4/18] Creating departments and subjects...")

        # Nigerian curriculum subjects organized by department
        departments_subjects = {
            'Languages': [
                ('English Studies', 'ENG001', False, True),
                ('English Language', 'ENG101', False, True),
                ('Literature in English', 'LIT101', True, True),
                ('Nigerian Language', 'NGL101', True, True),
                ('French', 'FRE101', True, True),
            ],
            'Mathematics': [
                ('Mathematics', 'MATH101', False, True),
                ('Further Mathematics', 'MATH201', True, True),
            ],
            'Sciences': [
                ('Basic Science', 'BSC001', False, True),
                ('Physics', 'PHY101', True, True),
                ('Chemistry', 'CHE101', True, True),
                ('Biology', 'BIO101', True, True),
                ('Agricultural Science', 'AGR101', True, True),
            ],
            'Social Studies': [
                ('Social Studies', 'SST001', False, True),
                ('Government', 'GOV101', True, True),
                ('History', 'HIS101', True, True),
                ('Geography', 'GEO101', True, True),
                ('Economics', 'ECO101', True, True),
                ('Civic Education', 'CIV001', False, True),
            ],
            'Religious Studies': [
                ('Christian Religious Studies', 'CRS101', True, True),
                ('Islamic Religious Studies', 'IRS101', True, True),
                ('Moral Instruction', 'MOR001', False, False),
            ],
            'Vocational Studies': [
                ('Basic Technology', 'TEC001', False, True),
                ('Home Economics', 'HEC101', True, True),
                ('Agriculture', 'AGR001', False, True),
                ('Vocational Studies', 'VOC001', False, True),
                ('Technical Drawing', 'TDR101', True, True),
            ],
            'Business Studies': [
                ('Business Studies', 'BUS001', True, True),
                ('Commerce', 'COM101', True, True),
                ('Financial Accounting', 'ACC101', True, True),
                ('Office Practice', 'OFP101', True, True),
                ('Marketing', 'MKT101', True, True),
                ('Data Processing', 'DAT101', True, True),
            ],
            'Arts and Culture': [
                ('Cultural and Creative Arts', 'CCA001', False, True),
                ('Music', 'MUS101', True, True),
                ('Visual Arts', 'VAR101', True, True),
            ],
            'Physical and Health Education': [
                ('Physical and Health Education', 'PHE001', False, False),
                ('Physical Education', 'PHE101', False, False),
            ],
            'Computer Studies': [
                ('Computer Studies', 'COM001', False, True),
            ],
        }

        dept_count = 0
        subj_count = 0

        for dept_name, subjects in departments_subjects.items():
            dept, _ = Department.objects.get_or_create(
                name=dept_name.lower(),
                defaults={'order_rank': dept_count + 1}
            )
            dept_count += 1

            for subj_name, code, selectable, graded in subjects:
                subject, _ = Subject.objects.get_or_create(
                    subject_code=code,
                    defaults={
                        'name': subj_name,
                        'is_selectable': selectable,
                        'graded': graded,
                        'department': dept
                    }
                )
                self.subjects.append(subject)
                subj_count += 1

        print(f"  ✓ Created {dept_count} departments and {subj_count} subjects")

    def create_grade_levels(self):
        """Create grade levels and class levels for Nigerian education system"""
        print("\n[5/18] Creating grade levels and class levels...")

        # Create grade levels (Nigerian system)
        grade_levels_data = [
            (1, 'Nursery'),
            (2, 'Primary'),
            (3, 'Junior Secondary (JSS)'),
            (4, 'Senior Secondary (SSS)'),
        ]

        grade_levels = {}
        for gl_id, gl_name in grade_levels_data:
            gl, _ = GradeLevel.objects.get_or_create(id=gl_id, defaults={'name': gl_name})
            grade_levels[gl_name] = gl

        # Create class levels (Nigerian curriculum)
        class_levels_data = [
            ('Nursery 1', 'Nursery'),
            ('Nursery 2', 'Nursery'),
            ('Nursery 3', 'Nursery'),
            ('Primary 1', 'Primary'),
            ('Primary 2', 'Primary'),
            ('Primary 3', 'Primary'),
            ('Primary 4', 'Primary'),
            ('Primary 5', 'Primary'),
            ('Primary 6', 'Primary'),
            ('JSS 1', 'Junior Secondary (JSS)'),
            ('JSS 2', 'Junior Secondary (JSS)'),
            ('JSS 3', 'Junior Secondary (JSS)'),
            ('SSS 1', 'Senior Secondary (SSS)'),
            ('SSS 2', 'Senior Secondary (SSS)'),
            ('SSS 3', 'Senior Secondary (SSS)'),
        ]

        class_count = 0
        for cl_name, gl_name in class_levels_data:
            cl_id = class_count + 1
            ClassLevel.objects.get_or_create(
                id=cl_id,
                defaults={
                    'name': cl_name,
                    'grade_level': grade_levels[gl_name]
                }
            )
            class_count += 1

        print(f"  ✓ Created {len(grade_levels_data)} grade levels and {class_count} class levels")

        # Create class years
        current_year = datetime.now().year
        for i in range(-2, 5):  # Create from 2 years ago to 4 years ahead
            year = current_year + i
            ClassYear.objects.get_or_create(year=year)
        print(f"  ✓ Created class years")

    def create_accountants(self):
        """Create accountant users"""
        print("\n[6/18] Creating accountants...")

        accountants_data = [
            {
                'username': 'acc001',
                'first_name': 'Sarah',
                'last_name': 'Nakato',
                'gender': 'Female',
                'email': 'sarah.nakato@hillcrest.edu.ug',
                'empId': 'EMP-ACC-001',
                'salary': Decimal('1500000'),
            },
            {
                'username': 'acc002',
                'first_name': 'James',
                'last_name': 'Okello',
                'gender': 'Male',
                'email': 'james.okello@hillcrest.edu.ug',
                'empId': 'EMP-ACC-002',
                'salary': Decimal('1200000'),
            },
        ]

        for acc_data in accountants_data:
            acc, created = Accountant.objects.get_or_create(
                username=acc_data['username'],
                defaults=acc_data
            )
            self.accountants.append(acc)

        print(f"  ✓ Created {len(self.accountants)} accountants")

    def create_teachers(self):
        """Create teacher users"""
        print("\n[7/18] Creating teachers...")

        first_names = ['John', 'Mary', 'David', 'Susan', 'Peter', 'Grace',
                      'Michael', 'Alice', 'Robert', 'Jane', 'Daniel', 'Ruth']
        last_names = ['Mugisha', 'Kamau', 'Ochieng', 'Musoke', 'Asiimwe',
                     'Wanjiru', 'Okoth', 'Namukasa', 'Kibet', 'Atim']

        designations = ['Head Teacher', 'Senior Teacher', 'Teacher', 'Teacher', 'Teacher']

        for i in range(20):
            first_name = random.choice(first_names)
            last_name = random.choice(last_names)
            email = f'teacher{i+1:03d}@hillcrest.edu.ug'
            phone_number = f'+256-70{random.randint(0, 9)}-{random.randint(100000, 999999)}'
            empId = f'EMP-TCH-{i+1:03d}'

            # Assign 1-3 subjects to each teacher
            specializations = random.sample(self.subjects, k=random.randint(1, 3))

            # First, create or get CustomUser
            user, user_created = CustomUser.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': first_name,
                    'last_name': last_name,
                    'phone_number': phone_number,
                    'is_teacher': True,
                }
            )

            if user_created:
                # Set a default password
                default_password = f"Complex.{empId[-4:]}"
                user.set_password(default_password)
                user.save()

                # Add user to "teacher" group
                from django.contrib.auth.models import Group
                group, _ = Group.objects.get_or_create(name="teacher")
                user.groups.add(group)

            # Then create Teacher profile linked to the user
            teacher, created = Teacher.objects.get_or_create(
                user=user,
                defaults={
                    'empId': empId,
                    'short_name': f'{first_name[0]}.{last_name}{i+1}',
                    'salary': Decimal(random.randint(800, 1500) * 1000),
                    'designation': random.choice(designations),
                    'address': f'{random.randint(1, 500)} {random.choice(["Lagos", "Abuja", "Kano", "Ibadan", "Port Harcourt", "Benin City"])}',
                }
            )

            if created:
                teacher.subject_specialization.set(specializations)

            self.teachers.append(teacher)

        print(f"  ✓ Created {len(self.teachers)} teachers")

    def create_classrooms(self):
        """Create classrooms with teachers"""
        print("\n[8/18] Creating classrooms...")

        # Get primary and secondary class levels (Primary 1 to SSS 3)
        class_levels = ClassLevel.objects.filter(
            id__in=[4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]  # Primary 1 to SSS 3
        )

        streams = ['A', 'B', 'C']
        teacher_idx = 0

        for class_level in class_levels:
            # Determine number of streams based on class level
            num_streams = 2 if 'Primary' in class_level.name else 3

            for stream in streams[:num_streams]:
                classroom, created = ClassRoom.objects.get_or_create(
                    name=class_level,
                    defaults={
                        'class_teacher': self.teachers[teacher_idx % len(self.teachers)],
                        'capacity': random.randint(35, 50),
                        'occupied_sits': 0
                    }
                )
                self.classrooms.append(classroom)
                teacher_idx += 1

        print(f"  ✓ Created {len(self.classrooms)} classrooms")

    def create_parents(self):
        """Create parent users"""
        print("\n[9/18] Creating parents...")

        # Nigerian names
        first_names_male = ['Chukwudi', 'Emeka', 'Oluwaseun', 'Musa', 'Ibrahim',
                           'Joseph', 'Samuel', 'Patrick', 'Emmanuel', 'Tunde']
        first_names_female = ['Ngozi', 'Amina', 'Funmilayo', 'Blessing', 'Fatima',
                             'Grace', 'Chioma', 'Aisha', 'Oluchi', 'Halima']
        last_names = ['Okafor', 'Adeleke', 'Bello', 'Okoro', 'Adeyemi',
                     'Mohammed', 'Nwankwo', 'Okonkwo', 'Ibrahim', 'Eze']

        occupations = ['Teacher', 'Doctor', 'Engineer', 'Businessman', 'Farmer',
                      'Nurse', 'Accountant', 'Lawyer', 'Civil Servant', 'Trader']

        nigerian_cities = ['Lagos', 'Abuja', 'Kano', 'Ibadan', 'Port Harcourt',
                          'Benin City', 'Kaduna', 'Enugu', 'Jos', 'Owerri']

        # Create 100 parents (will create families later)
        for i in range(100):
            parent_type = random.choice(['Father', 'Mother', 'Guardian'])
            gender = 'Male' if parent_type == 'Father' else 'Female'

            first_name = random.choice(first_names_male if gender == 'Male' else first_names_female)
            last_name = random.choice(last_names)

            # Generate unique phone number using index (Nigerian format)
            phone = f'+234-80{i//1000}-{i%1000000:06d}'
            email = f'parent{i+1:04d}@email.com'

            parent, created = Parent.objects.get_or_create(
                phone_number=phone,
                defaults={
                    'first_name': first_name,
                    'last_name': last_name,
                    'gender': gender,
                    'email': email,
                    'parent_type': parent_type,
                    'occupation': random.choice(occupations),
                    'monthly_income': Decimal(random.randint(50, 500) * 1000),  # Nigerian Naira
                    'single_parent': random.choice([True, False]) if parent_type == 'Guardian' else False,
                    'address': f'{random.randint(1, 500)} {random.choice(nigerian_cities)}',
                }
            )

            self.parents.append(parent)

        print(f"  ✓ Created {len(self.parents)} parents")

    def create_students(self):
        """Create students and enroll them in classrooms"""
        print("\n[10/18] Creating students...")

        # Nigerian student names
        first_names_male = ['Chinedu', 'Kayode', 'Abubakar', 'Chidera', 'Tunde', 'Uche',
                           'Samuel', 'Emmanuel', 'Ibrahim', 'Nnamdi', 'Oluwaseun', 'David']
        first_names_female = ['Chiamaka', 'Folake', 'Hauwa', 'Adaeze', 'Blessing', 'Precious',
                             'Faith', 'Hope', 'Mercy', 'Joy', 'Ifunanya', 'Zainab']
        religions = ['Christian', 'Islam', 'Other']
        blood_groups = ['A+', 'A-', 'B+', 'B-', 'O+', 'O-', 'AB+', 'AB-']

        current_year = datetime.now().year
        class_year = ClassYear.objects.get(year=current_year + 4)  # Graduating in 4 years

        student_count = 0

        # Create students for each classroom
        for classroom in self.classrooms:
            # Refresh classroom from DB to get current occupancy
            classroom.refresh_from_db()

            # Calculate how many students we can add
            available_space = classroom.capacity - classroom.occupied_sits
            num_students_to_create = min(random.randint(30, classroom.capacity), available_space)

            if num_students_to_create <= 0:
                # Classroom is full, just get existing students
                existing_students = StudentClassEnrollment.objects.filter(
                    classroom=classroom,
                    academic_year=self.academic_year
                ).select_related('student')

                for enrollment in existing_students:
                    if enrollment.student not in self.students:
                        self.students.append(enrollment.student)
                continue

            for _ in range(num_students_to_create):
                gender = random.choice(['Male', 'Female'])
                first_name = random.choice(first_names_male if gender == 'Male' else first_names_female)
                parent = random.choice(self.parents)

                # Create student
                student = Student.objects.create(
                    first_name=first_name,
                    last_name=parent.last_name,
                    gender=gender,
                    religion=random.choice(religions),
                    blood_group=random.choice(blood_groups),
                    class_level=classroom.name,
                    class_of_year=class_year,
                    parent_guardian=parent,
                    parent_contact=parent.phone_number,
                    is_active=True,
                    region='Central',
                    city=random.choice(['Kampala', 'Entebbe', 'Wakiso', 'Mukono']),
                )

                # Enroll in classroom
                StudentClassEnrollment.objects.create(
                    student=student,
                    classroom=classroom,
                    academic_year=self.academic_year
                )

                self.students.append(student)
                student_count += 1

        print(f"  ✓ Created {student_count} new students (total: {len(self.students)} students)")

    def create_dormitories(self):
        """Create dormitories and allocate students"""
        print("\n[11/18] Creating dormitories...")

        dorm_data = [
            ('Boys Dormitory A', 80, 'Male'),
            ('Boys Dormitory B', 80, 'Male'),
            ('Girls Dormitory A', 70, 'Female'),
            ('Girls Dormitory B', 70, 'Female'),
        ]

        for dorm_name, capacity, gender in dorm_data:
            # Get a random student captain of matching gender
            captains = [s for s in self.students if s.gender == gender]
            captain = random.choice(captains) if captains else None

            dormitory, _ = Dormitory.objects.get_or_create(
                name=dorm_name,
                defaults={
                    'capacity': capacity,
                    'occupied_beds': 0,
                    'captain': captain
                }
            )

        print(f"  ✓ Created {len(dorm_data)} dormitories")

    def create_fee_structures(self):
        """Create fee structures and assign to students"""
        print("\n[12/18] Creating fee structures and assignments...")

        # Get primary and secondary grade levels (Nigerian system)
        primary = GradeLevel.objects.get(name='Primary')
        jss = GradeLevel.objects.get(name='Junior Secondary (JSS)')
        sss = GradeLevel.objects.get(name='Senior Secondary (SSS)')

        fee_structures_data = [
            ('Primary Tuition Fee', 'Tuition', Decimal('150000'), primary, True),  # NGN
            ('JSS Tuition Fee', 'Tuition', Decimal('200000'), jss, True),  # NGN
            ('SSS Tuition Fee', 'Tuition', Decimal('250000'), sss, True),  # NGN
            ('Transport Fee', 'Transport', Decimal('50000'), None, False),
            ('Meals Fee', 'Meals', Decimal('80000'), None, True),
            ('Books and Stationery', 'Books', Decimal('30000'), None, True),
            ('School Uniform', 'Uniform', Decimal('40000'), None, False),
        ]

        fee_structures = []
        for name, fee_type, amount, grade_level, mandatory in fee_structures_data:
            fs, created = FeeStructure.objects.get_or_create(
                name=name,
                academic_year=self.academic_year,
                term=self.current_term,
                defaults={
                    'fee_type': fee_type,
                    'amount': amount,
                    'is_mandatory': mandatory,
                    'due_date': self.current_term.end_date - timedelta(days=30)
                }
            )
            if created and grade_level:
                # Add grade level to ManyToMany field
                fs.grade_levels.add(grade_level)
            fee_structures.append(fs)

        print(f"  ✓ Created {len(fee_structures)} fee structures")

        # Assign fees to students
        assignment_count = 0
        for student in self.students:
            applicable_fees = [fs for fs in fee_structures if fs.applies_to_student(student)]

            for fee_structure in applicable_fees:
                amount_owed = fee_structure.amount

                # Create fee assignment without payment (payment will be added via allocations)
                StudentFeeAssignment.objects.get_or_create(
                    student=student,
                    fee_structure=fee_structure,
                    term=self.current_term,
                    defaults={
                        'amount_owed': amount_owed,
                        'amount_paid': Decimal('0')
                    }
                )
                assignment_count += 1

        print(f"  ✓ Created {assignment_count} fee assignments to students")

    def create_receipts_and_payments(self):
        """Create receipts and payment allocations"""
        print("\n[13/18] Creating receipts and payments...")

        # Create receipts for students
        receipt_count = 0
        allocation_count = 0

        # Create receipts for a random sample of students
        for student in random.sample(self.students, min(100, len(self.students))):
            # Get unpaid or partially paid fee assignments
            all_assignments = StudentFeeAssignment.objects.filter(
                student=student,
                term=self.current_term,
                is_waived=False
            )

            # Filter out fully paid assignments (balance > 0)
            fee_assignments = [fa for fa in all_assignments if fa.balance > 0]

            if not fee_assignments:
                continue

            # Randomly decide payment status: full (50%), partial (30%), or skip (20%)
            payment_status = random.choices(
                ['full', 'partial', 'skip'],
                weights=[50, 30, 20]
            )[0]

            if payment_status == 'skip':
                continue

            # Calculate payment amount
            total_owed = sum(fa.balance for fa in fee_assignments)

            if payment_status == 'full':
                payment_amount = total_owed
            else:  # partial
                payment_amount = total_owed * Decimal(random.uniform(0.3, 0.9))

            # Round payment amount to 2 decimal places
            payment_amount = Decimal(str(round(float(payment_amount), 2)))

            # Create receipt
            receipt = Receipt.objects.create(
                date=timezone.now().date() - timedelta(days=random.randint(1, 60)),
                payer=f"{student.parent_guardian.first_name} {student.parent_guardian.last_name}",
                student=student,
                amount=payment_amount,
                paid_through=random.choice(['Cash', 'Bank Transfer', 'Mobile Money']),
                term=self.current_term,
                payment_date=timezone.now().date() - timedelta(days=random.randint(1, 60)),
                status='Completed',
                received_by=random.choice(self.accountants) if self.accountants else None
            )
            receipt_count += 1

            # Allocate payment to fee assignments
            remaining = payment_amount
            for fee_assignment in fee_assignments:
                if remaining <= 0:
                    break

                # Allocate up to the balance or remaining amount
                # Round to 2 decimal places to avoid precision issues
                allocation_amount = min(fee_assignment.balance, remaining)
                allocation_amount = Decimal(str(round(float(allocation_amount), 2)))

                FeePaymentAllocation.objects.create(
                    receipt=receipt,
                    fee_assignment=fee_assignment,
                    amount=allocation_amount
                )
                allocation_count += 1
                remaining -= allocation_amount

        print(f"  ✓ Created {receipt_count} receipts with {allocation_count} allocations")

        # Create payment categories and payments (expenses)
        categories_data = [
            ('Salaries', 'SAL'),
            ('Utilities', 'UTL'),
            ('Maintenance', 'MNT'),
            ('Supplies', 'SUP'),
        ]

        for cat_name, abbr in categories_data:
            PaymentCategory.objects.get_or_create(
                name=cat_name,
                defaults={'abbr': abbr}
            )

        # Create sample payments
        salary_cat = PaymentCategory.objects.get(name='Salaries')
        utilities_cat = PaymentCategory.objects.get(name='Utilities')

        payment_count = 0

        # Teacher salaries
        for teacher in random.sample(self.teachers, min(10, len(self.teachers))):
            Payment.objects.create(
                date=timezone.now().date() - timedelta(days=random.randint(1, 30)),
                paid_to=f"{teacher.first_name} {teacher.last_name}",
                user=teacher.user,
                category=salary_cat,
                paid_through='Bank Transfer',
                amount=teacher.salary,
                description=f'Monthly salary for {teacher.first_name} {teacher.last_name}',
                status='Completed',
                paid_by=random.choice(self.accountants) if self.accountants else None
            )
            payment_count += 1

        # Utility payments
        Payment.objects.create(
            date=timezone.now().date() - timedelta(days=15),
            paid_to='Electricity Company',
            category=utilities_cat,
            paid_through='Bank Transfer',
            amount=Decimal('5000000'),
            description='Electricity bill for the month',
            status='Completed',
            paid_by=random.choice(self.accountants) if self.accountants else None
        )
        payment_count += 1

        print(f"  ✓ Created {payment_count} expense payments")

    def create_attendance_statuses(self):
        """Create attendance status types"""
        print("\n[14/18] Creating attendance statuses...")

        statuses = [
            ('Present', 'P', False, False, False, False),
            ('Absent', 'A', False, True, False, False),
            ('Sick', 'S', True, True, False, False),
            ('Late', 'L', False, False, True, False),
            ('Holiday', 'H', True, False, False, False),
            ('Half Day', 'HD', True, False, False, True),
        ]

        for name, code, excused, absent, late, half in statuses:
            AttendanceStatus.objects.get_or_create(
                code=code,
                defaults={
                    'name': name,
                    'excused': excused,
                    'absent': absent,
                    'late': late,
                    'half': half
                }
            )

        print(f"  ✓ Created {len(statuses)} attendance status types")

    def create_attendance_records(self):
        """Create sample attendance records"""
        print("\n[15/18] Creating attendance records...")

        present = AttendanceStatus.objects.get(code='P')
        absent = AttendanceStatus.objects.get(code='A')
        sick = AttendanceStatus.objects.get(code='S')
        late = AttendanceStatus.objects.get(code='L')

        # Student attendance for past 30 days
        student_attendance_count = 0
        for days_ago in range(1, 31):
            attendance_date = timezone.now().date() - timedelta(days=days_ago)

            # Skip weekends
            if attendance_date.weekday() >= 5:
                continue

            for student in random.sample(self.students, min(50, len(self.students))):
                # 90% present, 5% absent, 3% sick, 2% late
                status = random.choices(
                    [present, absent, sick, late],
                    weights=[90, 5, 3, 2]
                )[0]

                # Only create records for non-present status
                if status != present:
                    StudentAttendance.objects.get_or_create(
                        student=student,
                        date=attendance_date,
                        status=status,
                        defaults={'ClassRoom': student.student_classes.first().classroom}
                    )
                    student_attendance_count += 1

        print(f"  ✓ Created {student_attendance_count} student attendance records")

        # Teacher attendance
        teacher_attendance_count = 0
        for days_ago in range(1, 31):
            attendance_date = timezone.now().date() - timedelta(days=days_ago)

            if attendance_date.weekday() >= 5:
                continue

            for teacher in random.sample(self.teachers, min(15, len(self.teachers))):
                status = random.choices(
                    [present, absent, sick],
                    weights=[95, 3, 2]
                )[0]

                time_in = timezone.now().replace(
                    hour=random.randint(7, 8),
                    minute=random.randint(0, 59)
                ).time()
                time_out = timezone.now().replace(
                    hour=random.randint(16, 18),
                    minute=random.randint(0, 59)
                ).time()

                TeachersAttendance.objects.get_or_create(
                    teacher=teacher,
                    date=attendance_date,
                    status=status,
                    defaults={
                        'time_in': time_in,
                        'time_out': time_out
                    }
                )
                teacher_attendance_count += 1

        print(f"  ✓ Created {teacher_attendance_count} teacher attendance records")

    def create_grade_scale(self):
        """Create grading scale system"""
        print("\n[16/18] Creating grade scale...")

        scale, _ = GradeScale.objects.get_or_create(name='Standard Grade Scale')

        rules = [
            (90, 100, 'A', Decimal('4.0')),
            (80, 89, 'B', Decimal('3.5')),
            (70, 79, 'C', Decimal('3.0')),
            (60, 69, 'D', Decimal('2.5')),
            (50, 59, 'E', Decimal('2.0')),
            (0, 49, 'F', Decimal('1.0')),
        ]

        for min_g, max_g, letter, numeric in rules:
            GradeScaleRule.objects.get_or_create(
                grade_scale=scale,
                min_grade=min_g,
                max_grade=max_g,
                defaults={
                    'letter_grade': letter,
                    'numeric_scale': numeric
                }
            )

        print(f"  ✓ Created grade scale with {len(rules)} rules")

    def create_examinations(self):
        """Create examinations and marks"""
        print("\n[17/18] Creating examinations and marks...")

        # Create examinations
        exams_data = [
            ('Mid-Term Test', -45, 5, 50),
            ('End of Term Exam', -14, 7, 100),
        ]

        exams = []
        for exam_name, start_offset, duration, out_of in exams_data:
            start_date = self.current_term.end_date + timedelta(days=start_offset)

            exam, _ = ExaminationListHandler.objects.get_or_create(
                name=f"{exam_name} - Term {self.current_term.name}",
                defaults={
                    'start_date': start_date,
                    'ends_date': start_date + timedelta(days=duration),
                    'out_of': out_of,
                    'created_by': random.choice(self.teachers),
                    'created_on': timezone.now()
                }
            )

            # Add classrooms
            exam.classrooms.set(random.sample(self.classrooms, min(5, len(self.classrooms))))
            exams.append(exam)

        print(f"  ✓ Created {len(exams)} examinations")

        # Create marks for students
        marks_count = 0
        for exam in exams:
            for classroom in exam.classrooms.all():
                enrollments = StudentClassEnrollment.objects.filter(
                    classroom=classroom,
                    academic_year=self.academic_year
                )

                # Random subjects for this exam (3-5 subjects)
                exam_subjects = random.sample(self.subjects, k=random.randint(3, 5))

                for enrollment in enrollments[:20]:  # Limit to 20 students per class
                    for subject in exam_subjects:
                        # Generate random marks (normally distributed around 65%)
                        mean_score = exam.out_of * 0.65
                        std_dev = exam.out_of * 0.15
                        score = max(0, min(exam.out_of, random.gauss(mean_score, std_dev)))

                        MarksManagement.objects.get_or_create(
                            exam_name=exam,
                            student=enrollment,
                            subject=subject,
                            defaults={
                                'points_scored': round(score, 2),
                                'created_by': random.choice(self.teachers),
                                'date_time': timezone.now()
                            }
                        )
                        marks_count += 1

        print(f"  ✓ Created {marks_count} exam marks")

    def create_allocated_subjects(self):
        """Allocate subjects to teachers and classrooms"""
        print("\n[18/18] Creating subject allocations...")

        allocation_count = 0

        for classroom in self.classrooms:
            # Allocate 6-8 subjects per classroom
            classroom_subjects = random.sample(self.subjects, k=random.randint(6, 8))

            for subject in classroom_subjects:
                # Find a teacher who specializes in this subject
                suitable_teachers = [
                    t for t in self.teachers
                    if subject in t.subject_specialization.all()
                ]

                if not suitable_teachers:
                    suitable_teachers = self.teachers

                teacher = random.choice(suitable_teachers)

                # Note: term is OneToOneField, so we can't use it in get_or_create
                # We'll create allocations per classroom/subject/teacher/academic_year
                AllocatedSubject.objects.get_or_create(
                    teacher_name=teacher,
                    subject=subject,
                    class_room=classroom,
                    academic_year=self.academic_year,
                    defaults={
                        'weekly_periods': random.randint(3, 6),
                        'max_daily_periods': random.randint(1, 2)
                    }
                )
                allocation_count += 1

        print(f"  ✓ Created {allocation_count} subject allocations")

    def create_timetable(self):
        """Create sample timetable periods"""
        print("\n[Bonus] Creating sample timetable...")

        # Use management command if available
        try:
            from django.core.management import call_command
            call_command('generate_timetable')
            print(f"  ✓ Generated timetable using management command")
        except Exception as e:
            print(f"  ⚠ Could not auto-generate timetable: {e}")
            print(f"  → Run: python manage.py generate_timetable")

    def create_articles(self):
        """Create sample articles/news"""
        print("\n[Bonus] Creating articles...")

        articles_data = [
            {
                'title': 'Welcome to the New Academic Year',
                'content': 'We are pleased to welcome all students and parents to the new academic year. This year promises to be exciting with new programs and activities planned.',
            },
            {
                'title': 'Outstanding Performance in National Exams',
                'content': 'Our students have once again excelled in the national examinations with a 95% pass rate. We congratulate all students and teachers for their hard work.',
            },
            {
                'title': 'Sports Day Highlights',
                'content': 'The annual sports day was a great success with students participating in various athletic events. Thank you to all parents who attended.',
            },
        ]

        admin_user = CustomUser.objects.filter(is_staff=True).first()
        if not admin_user and self.teachers:
            admin_user = self.teachers[0].user

        for article_data in articles_data:
            Article.objects.get_or_create(
                title=article_data['title'],
                defaults={
                    'content': article_data['content'],
                    'created_by': admin_user,
                    'created_at': timezone.now() - timedelta(days=random.randint(1, 60))
                }
            )

        print(f"  ✓ Created {len(articles_data)} articles")

    def print_summary(self):
        """Print summary of generated data"""
        print("\n📊 DATA SUMMARY:")
        print(f"   • School: {School.objects.filter(active=True).first().name}")
        print(f"   • Academic Year: {self.academic_year.name}")
        print(f"   • Current Term: {self.current_term.name}")
        print(f"   • Departments: {Department.objects.count()}")
        print(f"   • Subjects: {Subject.objects.count()}")
        print(f"   • Classrooms: {ClassRoom.objects.count()}")
        print(f"   • Teachers: {Teacher.objects.count()}")
        print(f"   • Accountants: {Accountant.objects.count()}")
        print(f"   • Parents: {Parent.objects.count()}")
        print(f"   • Students: {Student.objects.count()}")
        print(f"   • Fee Structures: {FeeStructure.objects.count()}")
        print(f"   • Receipts: {Receipt.objects.count()}")
        print(f"   • Payments (Expenses): {Payment.objects.count()}")
        print(f"   • Examinations: {ExaminationListHandler.objects.count()}")
        print(f"   • Exam Marks: {MarksManagement.objects.count()}")
        print(f"   • Subject Allocations: {AllocatedSubject.objects.count()}")
        print(f"   • Timetable Periods: {Period.objects.count()}")

        print("\n🔑 SAMPLE LOGIN CREDENTIALS:")
        print("   Teachers: teacher001@hillcrest.edu.ug (password: password)")
        print("   Accountants: sarah.nakato@hillcrest.edu.ug (password: password)")
        print("   Parents: Use phone number as username (password: password)")

        print("\n💡 NEXT STEPS:")
        print("   1. Create a superuser: python manage.py createsuperuser")
        print("   2. Run development server: python manage.py runserver")
        print("   3. Access admin: http://localhost:8000/admin/")
        print("   4. Update student debt: python manage.py update_student_debt")
        print("   5. Generate timetable: python manage.py generate_timetable")


def main():
    """Main entry point"""
    print("\n⚠️  WARNING: This will create sample data in your database.")
    print("Make sure you're running this on a development/test database.\n")

    response = input("Continue? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("Aborted.")
        return

    generator = DataGenerator()
    generator.generate_all()


if __name__ == "__main__":
    main()
