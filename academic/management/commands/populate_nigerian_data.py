"""
Django Management Command: Generate Nigerian School Sample Data for SCMS

This comprehensive script generates realistic sample data for a Nigerian school system including:
- Nigerian names, locations, occupations
- Academic structure (JSS/SSS system)
- Teachers, parents, and students with relationships
- Admission sessions and fee structures
- Student class enrollments and dormitories
- Attendance records
- Financial transactions

Usage:
    python manage.py populate_nigerian_data
    python manage.py populate_nigerian_data --students 150 --teachers 25
    python manage.py populate_nigerian_data --clear --students 200
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group
from django.utils import timezone
from django.db import transaction
from datetime import datetime, timedelta, date
from decimal import Decimal
import random
import logging

from users.models import CustomUser
from academic.models import (
    Department, Subject, GradeLevel, ClassLevel, ClassYear,
    ClassRoom, Teacher, Parent, Student, StudentClassEnrollment,
    AllocatedSubject, Stream, ReasonLeft, Dormitory, DormitoryAllocation,
    AdmissionSession, AdmissionFeeStructure, AdmissionApplication, AdmissionStatus,
    AssessmentType
)
from administration.models import (
    School, Day, AcademicYear, Term, SchoolEvent
)
from finance.models import FeeStructure
from attendance.models import AttendanceStatus, StudentAttendance, TeachersAttendance

logger = logging.getLogger(__name__)

# Nigerian Names Data
NIGERIAN_FIRST_NAMES_MALE = [
    'Chioma', 'Emeka', 'Tunde', 'Adebayo', 'Oluwaseun', 'Chidi', 'Babatunde',
    'Obinna', 'Kunle', 'Segun', 'Karim', 'Ahmed', 'Ibrahim', 'Ali', 'Yusuf',
    'Chibuzor', 'Nkosi', 'Jamal', 'Aminu', 'Rashid', 'Ravi', 'Abasi', 'Azikiwe',
    'Bisi', 'Chiukwu', 'Dare', 'Denzil', 'Ebube', 'Festus', 'Gbenga', 'Kevin',
    'Lanre', 'Mba', 'Nonso', 'Olutayo', 'Pius', 'Samson', 'Tendai', 'Victor'
]

NIGERIAN_FIRST_NAMES_FEMALE = [
    'Zainab', 'Aisha', 'Chioma', 'Ngozi', 'Blessing', 'Folake', 'Kaida',
    'Amina', 'Fatima', 'Hauwa', 'Talia', 'Zara', 'Nneka', 'Ifunanya', 'Ifeoma',
    'Justina', 'Kamara', 'Lara', 'Mopelola', 'Oyinbo', 'Priscilla', 'Quddus',
    'Ranyinudo', 'Stella', 'Tinuade', 'Uchenna', 'Victoria', 'Wanise', 'Yetunde',
    'Zoe', 'Ada', 'Bola', 'Chinyere', 'Deborah'
]

NIGERIAN_LAST_NAMES = [
    'Okafor', 'Oyewole', 'Ibrahim', 'Adeyemi', 'Ogundimu', 'Ezeh', 'Nwosu',
    'Eze', 'Chukwu', 'Okonkwo', 'Ezeoke', 'Abubakar', 'Salihu', 'Hassan', 'Balogun',
    'Olajide', 'Adebisi', 'Babajide', 'Oluwanmi', 'Owolabi', 'Adenuga', 'Ejiro',
    'Umoh', 'Obi', 'Adeleke', 'Ajibade', 'Osei', 'Mensah', 'Amadi', 'Adeniyi'
]

NIGERIAN_STATES = [
    'Lagos', 'Ogun', 'Osun', 'Oyo', 'Ekiti', 'Kwara', 'Kogi', 'Benue',
    'Nasarawa', 'Plateau', 'Kaduna', 'Kebbi', 'Sokoto', 'Kano', 'Katsina',
    'Zamfara', 'Yobe', 'Borno', 'Adamawa', 'Taraba', 'Bauchi', 'Gombe', 'Jigawa',
    'Niger', 'Ondo', 'Edo', 'Delta', 'Rivers', 'Bayelsa', 'Cross River', 'Akwa Ibom',
    'Abia', 'Imo', 'Enugu', 'Ebonyi', 'Anambra', 'Federal Capital Territory'
]

NIGERIAN_RELIGIONS = [
    'Christianity',
    'Islam',
    'Traditional Religion',
    'Other'
]

NIGERIAN_OCCUPATIONS = [
    'Civil Servant', 'Business Owner', 'Trader', 'Teacher', 'Nurse', 'Doctor',
    'Engineer', 'Lawyer', 'Accountant', 'Banker', 'Farmer', 'Artisan',
    'Transporter', 'Tailor', 'Welder', 'Mechanic', 'Administrator', 'Electrician',
    'Contractor', 'Manager', 'Supervisor', 'Driver', 'Security Officer',
    'Beautician', 'Hairdresser', 'Barber', 'Cleaner', 'Laborer'
]

BLOOD_GROUPS = ['O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-']


class Command(BaseCommand):
    help = 'Generate comprehensive Nigerian school sample data for the SCMS'

    def add_arguments(self, parser):
        parser.add_argument(
            '--students',
            type=int,
            default=200,
            help='Number of students to generate (default: 200)'
        )
        parser.add_argument(
            '--teachers',
            type=int,
            default=30,
            help='Number of teachers to generate (default: 30)'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before generating'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS("🎓 NIGERIAN SCHOOL MANAGEMENT SYSTEM - DATA GENERATOR"))
        self.stdout.write("=" * 80 + "\n")

        self.num_students = options['students']
        self.num_teachers = options['teachers']
        self.should_clear = options['clear']

        if self.should_clear:
            self.clear_data()

        self.stdout.write(self.style.WARNING(f"📊 Generating data for {self.num_students} students and {self.num_teachers} teachers\n"))

        try:
            self.create_groups()
            self.create_school_info()
            self.create_academic_calendar()
            self.create_departments_and_subjects()
            self.create_grade_and_class_levels()
            self.create_streams()
            self.create_accountants()
            self.create_teachers()
            self.create_classrooms()
            self.create_parents()
            self.create_students()
            self.create_student_enrollments()
            self.create_dormitories()
            self.create_fee_structures()
            self.create_admission_system()
            self.create_attendance_statuses()
            self.create_attendance_records()
            self.create_allocated_subjects()

            self.stdout.write("\n" + "=" * 80)
            self.stdout.write(self.style.SUCCESS("✅ DATA GENERATION COMPLETE!"))
            self.stdout.write("=" * 80 + "\n")
            self.print_summary()

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ ERROR: {str(e)}"))
            logger.exception("Error during data generation")
            raise

    def clear_data(self):
        """Clear existing data"""
        self.stdout.write(self.style.WARNING("🗑️  Clearing existing data..."))
        try:
            Student.objects.all().delete()
            Parent.objects.all().delete()
            Teacher.objects.all().delete()
            CustomUser.objects.filter(is_staff=False, is_superuser=False).delete()
            self.stdout.write(self.style.SUCCESS("  ✓ Data cleared\n"))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  ⚠️  Could not clear all data: {e}"))

    def create_groups(self):
        """Create user groups"""
        self.stdout.write("[1/15] Creating user groups...")
        groups = ['teacher', 'parent', 'accountant', 'family']
        for group_name in groups:
            Group.objects.get_or_create(name=group_name)
        self.stdout.write(self.style.SUCCESS(f"  ✓ Created/verified {len(groups)} user groups\n"))

    def create_school_info(self):
        """Create Nigerian school information"""
        self.stdout.write("[2/15] Creating school information...")
        
        school, created = School.objects.get_or_create(
            active=True,
            defaults={
                'name': 'Pinnacle Excellence Academy',
                'address': '123 Awolowo Road, Ikoyi, Lagos, Nigeria',
                'school_type': 'Secondary School',
                'students_gender': 'Mixed',
                'ownership': 'Private',
                'mission': 'To provide quality education that nurtures academic excellence, moral character, and leadership development in the Nigerian context.',
                'vision': 'To be Nigeria\'s leading school producing globally competitive yet culturally rooted citizens.',
                'telephone': '+234-803-456-7890',
                'school_email': 'info@pinnacleacademy.edu.ng'
            }
        )
        action = "Created" if created else "Already exists"
        self.stdout.write(self.style.SUCCESS(f"  ✓ {action}: {school.name}"))

        # Create days
        days = [
            (1, 'Monday'), (2, 'Tuesday'), (3, 'Wednesday'),
            (4, 'Thursday'), (5, 'Friday'), (6, 'Saturday'), (7, 'Sunday')
        ]
        for day_num, day_name in days:
            Day.objects.get_or_create(day=day_num)
        self.stdout.write(self.style.SUCCESS(f"  ✓ Created days of the week\n"))

    def create_academic_calendar(self):
        """Create Nigerian academic year and terms"""
        self.stdout.write("[3/15] Creating academic calendar (Nigerian system)...")
        
        current_year = datetime.now().year
        
        # Nigerian academic year: Jan-Dec with 3 terms
        academic_year, created = AcademicYear.objects.get_or_create(
            name=f"{current_year}",
            defaults={
                'start_date': date(current_year, 1, 15),
                'end_date': date(current_year, 12, 15),
                'active_year': True
            }
        )

        # Nigerian Terms
        terms_data = [
            ('First Term', date(current_year, 1, 15), date(current_year, 4, 1), Decimal('150000')),
            ('Second Term', date(current_year, 4, 15), date(current_year, 7, 31), Decimal('150000')),
            ('Third Term', date(current_year, 9, 1), date(current_year, 12, 15), Decimal('150000')),
        ]

        self.academic_year = academic_year
        self.current_term = None

        for term_name, start, end, fee in terms_data:
            term, _ = Term.objects.get_or_create(
                name=term_name,
                academic_year=academic_year,
                defaults={
                    'start_date': start,
                    'end_date': end,
                    'default_term_fee': fee
                }
            )
            if term_name == 'First Term':
                self.current_term = term

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created academic year {academic_year.name} with 3 terms\n"))

    def create_departments_and_subjects(self):
        """Create Nigerian curriculum subjects"""
        self.stdout.write("[4/15] Creating departments and subjects (Nigerian curriculum)...")

        departments_subjects = {
            'Languages': [
                ('English Language', 'ENG', True, True),
                ('Hausa Language', 'HAS', True, True),
                ('Igbo Language', 'IGO', True, True),
                ('Yoruba Language', 'YOR', True, True),
                ('French', 'FRE', True, True),
            ],
            'Mathematics': [
                ('Mathematics', 'MATH', False, True),
                ('Further Mathematics', 'FMATH', True, True),
            ],
            'Sciences': [
                ('Physics', 'PHY', False, True),
                ('Chemistry', 'CHEM', False, True),
                ('Biology', 'BIO', False, True),
                ('Integrated Science', 'INTSC', False, True),
            ],
            'Social Sciences': [
                ('History', 'HIST', True, True),
                ('Geography', 'GEO', True, True),
                ('Government', 'GOVT', True, True),
                ('Economics', 'ECON', True, True),
                ('Civic Education', 'CIVIC', True, True),
            ],
            'Vocational Studies': [
                ('Computer Science', 'CS', True, True),
                ('Information Technology', 'IT', True, True),
                ('Accounting', 'ACC', True, True),
                ('Commerce', 'COM', True, True),
            ],
            'Arts': [
                ('Fine Arts', 'ART', True, True),
                ('Music', 'MUS', True, True),
                ('Home Economics', 'HOME', True, True),
                ('Agricultural Science', 'AGRIC', True, True),
            ],
            'Religion & Ethics': [
                ('Christian Religious Studies', 'CRS', True, True),
                ('Islamic Religious Studies', 'IRS', True, True),
            ],
            'Physical Education': [
                ('Physical Education', 'PE', False, False),
            ],
        }

        dept_count = 0
        subj_count = 0
        self.subjects = []

        for dept_name, subjects in departments_subjects.items():
            dept, _ = Department.objects.get_or_create(name=dept_name.lower())
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

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {dept_count} departments and {subj_count} subjects\n"))

    def create_grade_and_class_levels(self):
        """Create Nigerian grade and class levels"""
        self.stdout.write("[5/15] Creating grade and class levels (Nigerian system)...")

        # Nigerian grade levels
        grade_levels_data = [
            'JSS 1', 'JSS 2', 'JSS 3',
            'SS 1', 'SS 2', 'SS 3'
        ]

        grade_levels = {}
        for gl_name in grade_levels_data:
            gl, _ = GradeLevel.objects.get_or_create(name=gl_name)
            grade_levels[gl_name] = gl

        # Class levels with subdivisions
        class_levels_data = [
            ('JSS 1A', 'JSS 1'), ('JSS 1B', 'JSS 1'), ('JSS 1C', 'JSS 1'),
            ('JSS 2A', 'JSS 2'), ('JSS 2B', 'JSS 2'), ('JSS 2C', 'JSS 2'),
            ('JSS 3A', 'JSS 3'), ('JSS 3B', 'JSS 3'), ('JSS 3C', 'JSS 3'),
            ('SS 1A', 'SS 1'), ('SS 1B', 'SS 1'), ('SS 1C', 'SS 1'),
            ('SS 2A', 'SS 2'), ('SS 2B', 'SS 2'), ('SS 2C', 'SS 2'),
            ('SS 3A', 'SS 3'), ('SS 3B', 'SS 3'), ('SS 3C', 'SS 3'),
        ]

        class_count = 0
        self.class_levels = {}
        for cl_name, gl_name in class_levels_data:
            cl, _ = ClassLevel.objects.get_or_create(
                name=cl_name,
                defaults={'grade_level': grade_levels[gl_name]}
            )
            self.class_levels[cl_name] = cl
            class_count += 1

        # Class years
        current_year = datetime.now().year
        for i in range(-3, 4):
            year = current_year + i
            ClassYear.objects.get_or_create(year=str(year))

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {len(grade_levels_data)} grade levels and {class_count} class levels\n"))

    def create_streams(self):
        """Create Nigerian academic streams"""
        self.stdout.write("[6/15] Creating academic streams...")
        
        streams_data = ['A', 'B', 'C']
        for stream_name in streams_data:
            Stream.objects.get_or_create(name=stream_name)
        
        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {len(streams_data)} streams\n"))

    def create_accountants(self):
        """Create accountant users"""
        self.stdout.write("[7/15] Creating accountants...")

        accountants_data = [
            {
                'email': 'chukwu@pinnacleacademy.edu.ng',
                'first_name': 'Chukwu',
                'last_name': 'Okafor',
            },
            {
                'email': 'fatima@pinnacleacademy.edu.ng',
                'first_name': 'Fatima',
                'last_name': 'Hassan',
            },
        ]

        acc_count = 0
        group, _ = Group.objects.get_or_create(name='accountant')
        for i, acc_data in enumerate(accountants_data):
            user, created = CustomUser.objects.get_or_create(
                email=acc_data['email'],
                defaults={
                    'first_name': acc_data['first_name'],
                    'last_name': acc_data['last_name'],
                    'is_staff': True,
                    'is_active': True,
                    'is_accountant': True,
                }
            )
            if created:
                user.set_password('Complex.0000')
                user.save()

            if not user.is_accountant:
                user.is_accountant = True
                user.save()

            user.groups.add(group)
            acc_count += 1

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {acc_count} accountants\n"))

    def create_teachers(self):
        """Create Nigerian teachers"""
        self.stdout.write("[8/15] Creating teachers...")

        self.teachers = []
        teachers_created = 0

        for i in range(self.num_teachers):
            first_name = random.choice(NIGERIAN_FIRST_NAMES_MALE + NIGERIAN_FIRST_NAMES_FEMALE)
            last_name = random.choice(NIGERIAN_LAST_NAMES)
            gender = 'Male' if first_name in NIGERIAN_FIRST_NAMES_MALE else 'Female'

            email = f"{first_name.lower()}.{last_name.lower()}{i}@pinnacleacademy.edu.ng"[:50]

            try:
                user, created = CustomUser.objects.get_or_create(
                    email=email,
                    defaults={
                        'first_name': first_name,
                        'last_name': last_name,
                        'is_teacher': True,
                        'is_staff': True,
                        'phone_number': f"+234701{i:06d}",  # ✅ Fixed: max 15 chars
                    }
                )

                if created:
                    user.set_password('Complex.0000')
                    user.save()
                    group, _ = Group.objects.get_or_create(name='teacher')
                    user.groups.add(group)

                teacher, _ = Teacher.objects.get_or_create(
                    user=user,
                    defaults={
                        'empId': f'TCH-{i+1:04d}',
                        'short_name': f"{chr(65 + (i % 26))}{i % 100:02d}"[:3],  # ✅ Fixed: A00-Z99 format, unique
                        'salary': Decimal(random.randint(100000, 500000)),
                        'designation': random.choice(['Head Teacher', 'Senior Teacher', 'Teacher']),
                        'national_id': f"{random.randint(10000000, 99999999)}{random.randint(10, 99)}",
                    }
                )
                
                # Assign 2-4 subjects
                if self.subjects:
                    teacher.subject_specialization.set(random.sample(self.subjects, k=random.randint(2, 4)))
                
                self.teachers.append(teacher)
                teachers_created += 1

            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  ⚠️  Error creating teacher {i}: {str(e)[:50]}"))

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {teachers_created} teachers\n"))

    def create_classrooms(self):
        """Create classrooms with teachers"""
        self.stdout.write("[Creating classrooms...")

        self.classrooms = []  # ✅ Initialize immediately

        if not self.teachers or not self.class_levels:
            self.stdout.write(self.style.WARNING("  ⚠️  Not enough teachers or class levels"))
            return

        classrooms_created = 0

        for cl_name, class_level in list(self.class_levels.items()):
            for _ in range(2):  # 2 classrooms per class level
                teacher = random.choice(self.teachers)
                try:
                    classroom, created = ClassRoom.objects.get_or_create(
                        name=class_level,
                        defaults={
                            'class_teacher': teacher,
                            'capacity': random.randint(40, 55),
                            'occupied_sits': 0,
                        }
                    )
                    if created:
                        self.classrooms.append(classroom)
                        classrooms_created += 1
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"  ⚠️  Error creating classroom: {str(e)[:50]}"))

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {classrooms_created} classrooms\n"))

    def create_parents(self):
        """Create Nigerian parents"""
        self.stdout.write("[9/15] Creating parents...")

        self.parents = []
        parents_created = 0
        num_parents = int(self.num_students * 0.7)

        for i in range(num_parents):
            gender = random.choice(['Male', 'Female'])
            first_name = random.choice(NIGERIAN_FIRST_NAMES_MALE if gender == 'Male' else NIGERIAN_FIRST_NAMES_FEMALE)
            last_name = random.choice(NIGERIAN_LAST_NAMES)
            state = random.choice(NIGERIAN_STATES)

            # ✅ Fixed phone format: max 15 chars, unique
            phone = f"+234701{i:07d}"[:15]
            email = f"{first_name.lower()}.{last_name.lower()}{i}@email.com"[:50]

            try:
                parent, created = Parent.objects.get_or_create(
                    phone_number=phone,
                    defaults={
                        'first_name': first_name,
                        'last_name': last_name,
                        'gender': gender,
                        'email': email,
                        'parent_type': random.choice(['Father', 'Mother', 'Guardian']),
                        'occupation': random.choice(NIGERIAN_OCCUPATIONS),
                        'monthly_income': float(random.randint(50000, 500000)) * 100,  # 5M - 50M NGN
                        'single_parent': random.choice([True, False, False]),
                        'address': f"{random.randint(1, 500)} Street, {state}, Nigeria",
                        'national_id': f"{random.randint(10000000, 99999999)}{random.randint(10, 99)}",
                    }
                )
                if created:
                    self.parents.append(parent)
                    parents_created += 1
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  ⚠️  Error creating parent {i}: {str(e)[:50]}"))

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {parents_created} parents\n"))

    def create_students(self):
        """Create Nigerian students"""
        self.stdout.write("[10/15] Creating students...")

        self.students = []
        current_year = datetime.now().year
        class_year = ClassYear.objects.filter(year=str(current_year)).first() or ClassYear.objects.create(year=str(current_year))

        students_created = 0
        for i in range(self.num_students):
            gender = random.choice(['Male', 'Female'])
            first_name = random.choice(NIGERIAN_FIRST_NAMES_MALE if gender == 'Male' else NIGERIAN_FIRST_NAMES_FEMALE)
            parent = random.choice(self.parents) if self.parents else None

            try:
                # ✅ Fixed phone format: max 20 chars
                student_phone = parent.phone_number if parent else f"+234701{i:06d}"

                student = Student.objects.create(
                    first_name=first_name,
                    middle_name=random.choice([random.choice(NIGERIAN_FIRST_NAMES_MALE), '', '']),
                    last_name=parent.last_name if parent else random.choice(NIGERIAN_LAST_NAMES),
                    gender=gender,
                    religion=random.choice(NIGERIAN_RELIGIONS),
                    blood_group=random.choice(BLOOD_GROUPS),
                    class_level=random.choice(list(self.class_levels.values())),
                    class_of_year=class_year,
                    parent_guardian=parent,
                    parent_contact=parent.phone_number if parent else f"+234701{i:06d}",
                    phone_number=student_phone[:20],  # ✅ Truncate to max_length=20
                    date_of_birth=date(current_year - random.randint(13, 18), random.randint(1, 12), random.randint(1, 28)),
                    region=random.choice(NIGERIAN_STATES),
                    city=random.choice(['Lagos', 'Abuja', 'Port Harcourt', 'Kano', 'Ibadan']),
                )
                self.students.append(student)
                students_created += 1

                if students_created % 50 == 0:
                    self.stdout.write(f"    ... created {students_created} students")

            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  ⚠️  Error creating student {i}: {str(e)[:50]}"))

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {students_created} students\n"))

    def create_student_enrollments(self):
        """Enroll students in classrooms"""
        self.stdout.write("[11/15] Enrolling students in classrooms...")

        if not self.classrooms or not self.academic_year:
            self.stdout.write(self.style.WARNING("  ⚠️  Missing classrooms or academic year"))
            return

        enrollments_created = 0
        for student in self.students:
            # Find matching classrooms
            matching_classrooms = [c for c in self.classrooms if c.name == student.class_level]
            if not matching_classrooms:
                matching_classrooms = self.classrooms

            classroom = random.choice(matching_classrooms)

            # Check capacity
            if classroom.occupied_sits >= classroom.capacity:
                continue

            try:
                enrollment, created = StudentClassEnrollment.objects.get_or_create(
                    student=student,
                    classroom=classroom,
                    academic_year=self.academic_year,
                    defaults={'is_active': True}
                )
                if created:
                    enrollments_created += 1
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  ⚠️  Error enrolling student: {str(e)[:50]}"))

        self.stdout.write(self.style.SUCCESS(f"  ✓ Enrolled {enrollments_created} students\n"))

    def create_dormitories(self):
        """Create dormitories"""
        self.stdout.write("[Creating dormitories...")

        dorm_data = [
            ('Boys Dormitory A', 80),
            ('Boys Dormitory B', 80),
            ('Girls Dormitory A', 70),
            ('Girls Dormitory B', 70),
        ]

        dorms_created = 0
        for dorm_name, capacity in dorm_data:
            captain = random.choice(self.students) if self.students else None
            dorm, created = Dormitory.objects.get_or_create(
                name=dorm_name,
                defaults={
                    'capacity': capacity,
                    'occupied_beds': 0,
                    'captain': captain
                }
            )
            if created:
                dorms_created += 1

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {dorms_created} dormitories\n"))

    def create_fee_structures(self):
        """Create Nigerian fee structures"""
        self.stdout.write("[Creating fee structures...")

        fees_created = 0

        # Fee structure definitions
        fee_types = [
            ('Tuition', 'tuition', Decimal('100000')),
            ('Development', 'development', Decimal('50000')),
            ('Uniform', 'uniform', Decimal('25000')),
            ('Registration', 'registration', Decimal('10000')),
        ]

        for fee_name, fee_type, amount in fee_types:
            for grade_level in GradeLevel.objects.all():
                try:
                    fee_struct, created = FeeStructure.objects.get_or_create(
                        name=f"{grade_level.alias or grade_level.default_name} {fee_name}",
                        academic_year=self.academic_year,
                        fee_type=fee_type,
                        defaults={
                            'amount': amount,
                            'is_mandatory': True,
                        }
                    )
                    if created:
                        fee_struct.grade_levels.add(grade_level)
                        fees_created += 1
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"  ⚠️  Error: {str(e)[:50]}"))

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {fees_created} fee structures\n"))

    def create_admission_system(self):
        """Create admission sessions and fee structures"""
        self.stdout.write("[12/15] Creating admission system...")

        # Create admission session
        try:
            admission_session, created = AdmissionSession.objects.get_or_create(
                academic_year=self.academic_year,
                defaults={
                    'name': f'{self.academic_year.name} Admission',
                    'start_date': timezone.now().date(),
                    'end_date': timezone.now().date() + timedelta(days=90),
                    'require_acceptance_fee': True,
                    'acceptance_fee_deadline_days': 14,
                    'application_number_prefix': 'ADM',
                    'allow_public_applications': True,
                    'send_confirmation_emails': True,
                    'is_active': True,
                    'application_instructions': 'Please provide accurate information when filling this form.',
                }
            )
            
            # Create fee structures for grade levels
            grade_levels = GradeLevel.objects.all()[:3]  # Just first 3 grade levels
            for grade_level in grade_levels:
                fee_struct, _ = AdmissionFeeStructure.objects.get_or_create(
                    admission_session=admission_session,
                    defaults={
                        'application_fee': Decimal('5000'),
                        'application_fee_required': True,
                        'entrance_exam_required': True,
                        'entrance_exam_fee': Decimal('10000'),
                        'entrance_exam_pass_score': Decimal('50'),
                        'interview_required': False,
                        'acceptance_fee': Decimal('50000'),
                        'acceptance_fee_required': True,
                        'acceptance_fee_is_part_of_tuition': True,
                        'max_applications': 100,
                        'minimum_age': 11,
                        'maximum_age': 18,
                    }
                )
                fee_struct.grade_levels.add(grade_level)

            self.stdout.write(self.style.SUCCESS(f"  ✓ Created admission session and fee structures\n"))

        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  ⚠️  Error creating admission system: {str(e)[:50]}"))

    def create_attendance_statuses(self):
        """Create attendance statuses"""
        self.stdout.write("[13/15] Creating attendance statuses...")

        statuses_data = [
            {'name': 'Present', 'code': 'P', 'absent': False, 'excused': False, 'late': False},
            {'name': 'Absent', 'code': 'A', 'absent': True, 'excused': False, 'late': False},
            {'name': 'Late', 'code': 'L', 'absent': False, 'excused': False, 'late': True},
            {'name': 'Excused', 'code': 'E', 'absent': False, 'excused': True, 'late': False},
        ]
        
        for status_data in statuses_data:
            AttendanceStatus.objects.get_or_create(
                name=status_data['name'],
                defaults={
                    'code': status_data['code'],
                    'absent': status_data['absent'],
                    'excused': status_data['excused'],
                    'late': status_data['late'],
                }
            )

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {len(statuses_data)} attendance statuses\n"))

    def create_attendance_records(self):
        """Create sample attendance records"""
        self.stdout.write("[14/15] Creating attendance records...")

        present = AttendanceStatus.objects.filter(name='Present').first()  # ✅ Changed title to name
        absent = AttendanceStatus.objects.filter(name='Absent').first()    # ✅ Changed title to name

        attendance_count = 0

        # Student attendance for past 20 days
        for days_ago in range(1, 21):
            attendance_date = timezone.now().date() - timedelta(days=days_ago)

            if attendance_date.weekday() >= 5:  # Skip weekends
                continue

            for student in random.sample(self.students, min(30, len(self.students))):
                status = present if random.random() > 0.1 else absent

                # Only create absent records
                if status != present and status:
                    try:
                        StudentAttendance.objects.get_or_create(
                            student=student,
                            date=attendance_date,
                            status=status,
                            defaults={'ClassRoom': student.classroom}
                        )
                        attendance_count += 1
                    except:
                        pass

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {attendance_count} attendance records\n"))

    def create_allocated_subjects(self):
        """Allocate subjects to teachers and classrooms"""
        self.stdout.write("[15/15] Creating subject allocations...")

        allocation_count = 0

        for classroom in self.classrooms:
            if not self.subjects:
                break

            # Allocate 6-8 subjects per classroom
            classroom_subjects = random.sample(self.subjects, k=min(random.randint(6, 8), len(self.subjects)))

            for subject in classroom_subjects:
                # Find teacher specializing in subject
                suitable_teachers = [
                    t for t in self.teachers
                    if subject in t.subject_specialization.all()
                ]

                if not suitable_teachers:
                    suitable_teachers = self.teachers

                if suitable_teachers:
                    teacher = random.choice(suitable_teachers)

                    try:
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
                    except Exception as e:
                        pass

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {allocation_count} subject allocations\n"))

    def print_summary(self):
        """Print summary of created data"""
        self.stdout.write(self.style.SUCCESS("\n�� DATA SUMMARY:\n"))

        print(f"  👨‍🎓 Students:            {Student.objects.count():>6}")
        print(f"  👥 Parents:             {Parent.objects.count():>6}")
        print(f"  👨‍🏫 Teachers:            {Teacher.objects.count():>6}")
        print(f"  🏫 Classrooms:          {ClassRoom.objects.count():>6}")
        print(f"  📚 Subjects:            {Subject.objects.count():>6}")
        print(f"  📝 Grade Levels:        {GradeLevel.objects.count():>6}")
        print(f"  🎓 Class Levels:        {ClassLevel.objects.count():>6}")
        print(f"  👨‍💼 Total Users:         {CustomUser.objects.count():>6}")
        print(f"  📧 Admission Sessions:  {AdmissionSession.objects.count():>6}\n")

        print(self.style.SUCCESS("🚀 Your Django SCMS is ready with Nigerian data!"))
        print(self.style.SUCCESS("📍 Default credentials: username/password: Complex.0000"))
        print(self.style.SUCCESS("🌐 Access admin: http://localhost:8000/admin/\n"))
