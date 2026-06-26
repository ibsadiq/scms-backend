"""
Django Management Command: Generate Nigerian School Sample Data for SCMS

This comprehensive script generates realistic sample data for a Nigerian school system including:
- Nigerian names, locations, occupations
- Academic structure (JSS/SSS system)
- Teachers, parents, and students with relationships
- Fee structures
- Student class enrollments and dormitories
- Attendance records
- Financial transactions

Usage:
    python manage.py generate_sample_data
    python manage.py generate_sample_data --students 200
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import Group
from django.utils import timezone
from datetime import datetime, timedelta, date
from decimal import Decimal
import random

try:
    from django_tenants.utils import schema_context
except ImportError:
    schema_context = None

from users.models import CustomUser
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


class Command(BaseCommand):
    help = 'Generate comprehensive Nigerian school sample data for the SCMS'

    def add_arguments(self, parser):
        parser.add_argument(
            '--students',
            type=int,
            default=150,
            help='Number of students to generate (default: 150)'
        )
        parser.add_argument(
            '--teachers',
            type=int,
            default=20,
            help='Number of teachers to generate (default: 20)'
        )
        parser.add_argument(
            '--schema',
            type=str,
            help='Tenant schema name to run this command within',
        )

    def handle(self, *args, **options):
        self.teachers = []
        self.parents = []
        self.students = []
        self.classrooms = []
        self.subjects = []
        self.academic_year = None
        self.current_term = None
        self.accountants = []
        self.num_students = options['students']
        self.num_teachers = options['teachers']

        schema_name = options.get('schema')
        if schema_name:
            if schema_context is None:
                raise CommandError(
                    'django-tenants is required to use --schema. Install django-tenants or run without --schema in an active tenant context.'
                )
            self.stdout.write(self.style.WARNING(
                f"Running sample data generation inside tenant schema '{schema_name}'"
            ))
            with schema_context(schema_name):
                self._run_generation()
        else:
            self._run_generation()

    def _run_generation(self):
        self.stdout.write("=" * 80)
        self.stdout.write(self.style.SUCCESS("🎓 NIGERIAN SCHOOL MANAGEMENT SYSTEM - DATA GENERATOR"))
        self.stdout.write("=" * 80)

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
        self.create_articles()

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("DATA GENERATION COMPLETE!"))
        self.stdout.write("=" * 60)
        self.print_summary()

    def create_groups(self):
        """Create user groups if they don't exist"""
        self.stdout.write("\n[1/17] Creating user groups...")
        groups = ['teacher', 'parent', 'accountant', 'family']
        for group_name in groups:
            Group.objects.get_or_create(name=group_name)
        self.stdout.write(self.style.SUCCESS(f"  ✓ Created/verified {len(groups)} user groups"))

    def create_school_info(self):
        """Create Nigerian school information if not already set"""
        self.stdout.write("\n[2/17] Creating school information...")
        
        # Only create school if none exists
        school = School.objects.filter(active=True).first()
        if school:
            self.stdout.write(self.style.SUCCESS(f"  ✓ Using existing school: {school.name}"))
        else:
            school = School.objects.create(
                active=True,
                name='Pinnacle Excellence Academy',
                address='123 Awolowo Road, Ikoyi, Lagos, Nigeria',
                school_type='Secondary School',
                students_gender='Mixed',
                ownership='Private',
                mission='To provide quality education that nurtures academic excellence, moral character, and leadership development in the Nigerian context.',
                vision='To be Nigeria\'s leading school producing globally competitive yet culturally rooted citizens.',
                telephone='+234-803-456-7890',
                school_email='info@pinnacleacademy.edu.ng'
            )
            self.stdout.write(self.style.SUCCESS(f"  ✓ Created school: {school.name}"))

        days = [
            (1, 'Monday'), (2, 'Tuesday'), (3, 'Wednesday'),
            (4, 'Thursday'), (5, 'Friday'), (6, 'Saturday'), (7, 'Sunday')
        ]
        for day_num, day_name in days:
            Day.objects.get_or_create(day=day_num)
        self.stdout.write(self.style.SUCCESS(f"  ✓ Created days of the week"))

    def create_academic_calendar(self):
        """Create Nigerian academic year and terms if not already set"""
        self.stdout.write("\n[3/17] Creating academic calendar (Nigerian system)...")

        current_year = datetime.now().year
        
        # Check if academic year already exists (created during tenant setup)
        self.academic_year = AcademicYear.objects.filter(active_year=True).first()
        if self.academic_year:
            self.stdout.write(self.style.SUCCESS(f"  ✓ Using existing academic year: {self.academic_year.name}"))
        else:
            self.academic_year = AcademicYear.objects.create(
                name=f"{current_year}",
                start_date=date(current_year, 1, 15),
                end_date=date(current_year, 12, 15),
                active_year=True
            )
            self.stdout.write(self.style.SUCCESS(f"  ✓ Created academic year: {self.academic_year.name}"))

        # Check if terms already exist
        existing_terms = Term.objects.filter(academic_year=self.academic_year).count()
        if existing_terms > 0:
            self.stdout.write(self.style.SUCCESS(f"  ✓ Using existing {existing_terms} terms"))
            self.current_term = Term.objects.filter(academic_year=self.academic_year).first()
        else:
            # Nigerian Terms
            terms_data = [
                ('First Term', date(current_year, 1, 15), date(current_year, 4, 1), Decimal('150000')),
                ('Second Term', date(current_year, 4, 15), date(current_year, 7, 31), Decimal('150000')),
                ('Third Term', date(current_year, 9, 1), date(current_year, 12, 15), Decimal('150000')),
            ]

            for term_name, start, end, fee in terms_data:
                term, _ = Term.objects.get_or_create(
                    name=term_name,
                    academic_year=self.academic_year,
                    defaults={
                        'start_date': start,
                        'end_date': end
                    }
                )
                if term_name == 'First Term':
                    self.current_term = term

            self.stdout.write(self.style.SUCCESS(f"  ✓ Created {len(terms_data)} terms"))

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
        self.stdout.write(self.style.SUCCESS(f"  ✓ Created school events"))

    def create_departments_and_subjects(self):
        """Create Nigerian curriculum subjects"""
        self.stdout.write("\n[4/17] Creating departments and subjects (Nigerian curriculum)...")

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

        for dept_name, subjects in departments_subjects.items():
            dept, _ = Department.objects.get_or_create(
                name=dept_name.lower()
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

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {dept_count} departments and {subj_count} subjects"))

    def create_grade_levels(self):
        """Create Nigerian grade and class levels"""
        self.stdout.write("\n[5/17] Creating grade and class levels (Nigerian system)...")

        # Nigerian grade levels
        grade_levels_data = [
            'JSS 1', 'JSS 2', 'JSS 3',
            'SS 1', 'SS 2', 'SS 3'
        ]

        grade_levels = {}
        for i, gl_name in enumerate(grade_levels_data):
            section = 'JSS' if 'JSS' in gl_name else 'SSS'
            gl, _ = GradeLevel.objects.get_or_create(
                system_code=gl_name.replace(' ', ''),
                defaults={
                    'section': section,
                    'default_name': gl_name,
                    'sequence_order': i + 1,
                    'min_age': 0,
                    'max_age': 18
                }
            )
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
        for cl_name, gl_name in class_levels_data:
            ClassLevel.objects.get_or_create(
                name=cl_name,
                defaults={
                    'grade_level': grade_levels[gl_name]
                }
            )
            class_count += 1

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {len(grade_levels_data)} grade levels and {class_count} class levels"))

        current_year = datetime.now().year
        for i in range(-2, 5):
            year = current_year + i
            ClassYear.objects.get_or_create(year=year)
        self.stdout.write(self.style.SUCCESS(f"  ✓ Created class years"))

    def create_accountants(self):
        """Create accountant users"""
        self.stdout.write("\n[6/17] Creating accountants...")

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

        group, _ = Group.objects.get_or_create(name='accountant')

        for acc_data in accountants_data:
            user, created = CustomUser.objects.get_or_create(
                email=acc_data['email'],
                defaults={
                    'first_name': acc_data['first_name'],
                    'last_name': acc_data['last_name'],
                    'is_active': True,
                    'is_accountant': True,
                }
            )
            if created:
                user.set_password('password')
                user.save()

            if not user.is_accountant:
                user.is_accountant = True
                user.save()

            user.groups.add(group)
            self.accountants.append(user)

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {len(self.accountants)} accountants"))

    def create_teachers(self):
        """Create Nigerian teachers"""
        self.stdout.write("\n[7/17] Creating teachers...")

        designations = ['Head Teacher', 'Senior Teacher', 'Teacher']

        group, _ = Group.objects.get_or_create(name='teacher')

        for i in range(self.num_teachers):
            first_name = random.choice(NIGERIAN_FIRST_NAMES_MALE + NIGERIAN_FIRST_NAMES_FEMALE)
            last_name = random.choice(NIGERIAN_LAST_NAMES)
            gender = 'Male' if first_name in NIGERIAN_FIRST_NAMES_MALE else 'Female'

            email = f"{first_name.lower()}.{last_name.lower()}{i}@pinnacleacademy.edu.ng"[:50]

            specializations = random.sample(self.subjects, k=random.randint(2, 4))

            # Create user first
            user, user_created = CustomUser.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': first_name,
                    'last_name': last_name,
                    'is_active': True,
                    'is_teacher': True,
                    'phone_number': f"+234701{i:06d}",
                }
            )
            if user_created:
                user.set_password('password')
                user.save()

            if not user.is_teacher:
                user.is_teacher = True
                user.save()

            user.groups.add(group)

            # Create teacher with user
            teacher, created = Teacher.objects.get_or_create(
                user=user,
                defaults={
                    'empId': f'TCH{i+1:04d}',
                    'short_name': f"{chr(65 + (i % 26))}{i % 100:02d}"[:3],
                    'salary': Decimal(random.randint(100000, 500000)),
                    'designation': random.choice(designations),
                }
            )

            if created:
                teacher.subject_specialization.set(specializations)

            self.teachers.append(teacher)

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {len(self.teachers)} teachers"))

    def create_classrooms(self):
        """Create classrooms with teachers"""
        self.stdout.write("\n[8/17] Creating classrooms...")

        class_levels = ClassLevel.objects.filter(
            id__in=[4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
        )

        streams = ['A', 'B', 'C']
        teacher_idx = 0

        for class_level in class_levels:
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

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {len(self.classrooms)} classrooms"))

    def create_parents(self):
        """Create Nigerian parents"""
        self.stdout.write("\n[9/17] Creating parents...")

        num_parents = max(100, int(self.num_students * 0.7))

        for i in range(num_parents):
            gender = random.choice(['Male', 'Female'])
            first_name = random.choice(NIGERIAN_FIRST_NAMES_MALE if gender == 'Male' else NIGERIAN_FIRST_NAMES_FEMALE)
            last_name = random.choice(NIGERIAN_LAST_NAMES)
            state = random.choice(NIGERIAN_STATES)

            # Nigerian phone format: max 15 chars
            phone = f"+234701{i:07d}"[:15]
            email = f"{first_name.lower()}.{last_name.lower()}{i}@email.com"[:50]

            parent, created = Parent.objects.get_or_create(
                phone_number=phone,
                defaults={
                    'first_name': first_name,
                    'last_name': last_name,
                    'gender': gender,
                    'email': email,
                    'parent_type': random.choice(['Father', 'Mother', 'Guardian']),
                    'occupation': random.choice(NIGERIAN_OCCUPATIONS),
                    'monthly_income': float(random.randint(50000, 500000)) * 100,
                    'single_parent': random.choice([True, False, False]),
                    'address': f"{random.randint(1, 500)} Street, {state}, Nigeria",
                }
            )
            self.parents.append(parent)

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {len(self.parents)} parents"))

    def create_students(self):
        """Create Nigerian students and enroll them in classrooms"""
        self.stdout.write("\n[10/17] Creating students...")

        religions = NIGERIAN_RELIGIONS
        blood_groups = ['O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-']

        current_year = datetime.now().year
        class_year = ClassYear.objects.get(year=current_year + 4)

        students_per_classroom = int(self.num_students / len(self.classrooms))
        student_count = 0

        for classroom in self.classrooms:
            # Refresh classroom from DB to get current occupancy
            classroom.refresh_from_db()

            # Calculate how many students we can add
            available_space = classroom.capacity - classroom.occupied_sits
            num_students_to_create = min(students_per_classroom, available_space)

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
                first_name = random.choice(NIGERIAN_FIRST_NAMES_MALE if gender == 'Male' else NIGERIAN_FIRST_NAMES_FEMALE)
                parent = random.choice(self.parents)

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
                    phone_number=parent.phone_number[:20],
                    date_of_birth=date(current_year - random.randint(13, 18), random.randint(1, 12), random.randint(1, 28)),
                    region=random.choice(NIGERIAN_STATES),
                    city=random.choice(['Lagos', 'Abuja', 'Port Harcourt', 'Kano', 'Ibadan']),
                )

                StudentClassEnrollment.objects.create(
                    student=student,
                    classroom=classroom,
                    academic_year=self.academic_year
                )

                self.students.append(student)
                student_count += 1

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {student_count} new students (total: {len(self.students)} students)"))

    def create_dormitories(self):
        """Create dormitories"""
        self.stdout.write("\n[11/17] Creating dormitories...")

        dorm_data = [
            ('Boys Dormitory A', 80, 'Male'),
            ('Boys Dormitory B', 80, 'Male'),
            ('Girls Dormitory A', 70, 'Female'),
            ('Girls Dormitory B', 70, 'Female'),
        ]

        for dorm_name, capacity, gender in dorm_data:
            captains = [s for s in self.students if s.gender == gender]
            captain = random.choice(captains) if captains else None

            Dormitory.objects.get_or_create(
                name=dorm_name,
                defaults={
                    'capacity': capacity,
                    'occupied_beds': 0,
                    'captain': captain
                }
            )

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {len(dorm_data)} dormitories"))

    def create_fee_structures(self):
        """Create fee structures and assign to students"""
        self.stdout.write("\n[12/17] Creating fee structures and assignments...")

        primary = GradeLevel.objects.get(default_name='Primary')
        o_level = GradeLevel.objects.get(default_name='O-Level')
        a_level = GradeLevel.objects.get(default_name='A-Level')

        fee_structures_data = [
            ('Primary Tuition Fee', 'Tuition', Decimal('400000'), primary, True),
            ('O-Level Tuition Fee', 'Tuition', Decimal('500000'), o_level, True),
            ('A-Level Tuition Fee', 'Tuition', Decimal('600000'), a_level, True),
            ('Transport Fee', 'Transport', Decimal('150000'), None, False),
            ('Meals Fee', 'Meals', Decimal('200000'), None, True),
            ('Books and Stationery', 'Books', Decimal('80000'), None, True),
            ('School Uniform', 'Uniform', Decimal('120000'), None, False),
        ]

        fee_structures = []
        for name, fee_type, amount, grade_level, mandatory in fee_structures_data:
            fs, _ = FeeStructure.objects.get_or_create(
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
            if grade_level:
                fs.grade_levels.add(grade_level)
            fee_structures.append(fs)

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {len(fee_structures)} fee structures"))

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

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {assignment_count} fee assignments to students"))

    def create_receipts_and_payments(self):
        """Create receipts and payment allocations"""
        self.stdout.write("\n[13/17] Creating receipts and payments...")

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

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {receipt_count} receipts with {allocation_count} allocations"))

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

        salary_cat = PaymentCategory.objects.get(name='Salaries')
        utilities_cat = PaymentCategory.objects.get(name='Utilities')

        payment_count = 0

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

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {payment_count} expense payments"))

    def create_attendance_statuses(self):
        """Create attendance status types"""
        self.stdout.write("\n[14/17] Creating attendance statuses...")

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

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {len(statuses)} attendance status types"))

    def create_attendance_records(self):
        """Create sample attendance records"""
        self.stdout.write("\n[15/17] Creating attendance records...")

        present = AttendanceStatus.objects.get(code='P')
        absent = AttendanceStatus.objects.get(code='A')
        sick = AttendanceStatus.objects.get(code='S')
        late = AttendanceStatus.objects.get(code='L')

        student_attendance_count = 0
        for days_ago in range(1, 31):
            attendance_date = timezone.now().date() - timedelta(days=days_ago)

            if attendance_date.weekday() >= 5:
                continue

            for student in random.sample(self.students, min(50, len(self.students))):
                status = random.choices(
                    [present, absent, sick, late],
                    weights=[90, 5, 3, 2]
                )[0]

                if status != present:
                    StudentAttendance.objects.get_or_create(
                        student=student,
                        date=attendance_date,
                        status=status,
                        defaults={'ClassRoom': student.student_classes.first().classroom}
                    )
                    student_attendance_count += 1

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {student_attendance_count} student attendance records"))

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

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {teacher_attendance_count} teacher attendance records"))

    def create_grade_scale(self):
        """Create grading scale system"""
        self.stdout.write("\n[16/17] Creating grade scale...")

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

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created grade scale with {len(rules)} rules"))

    def create_examinations(self):
        """Create examinations and marks"""
        self.stdout.write("\n[17/17] Creating examinations and marks...")

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

            exam.classrooms.set(random.sample(self.classrooms, min(5, len(self.classrooms))))
            exams.append(exam)

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {len(exams)} examinations"))

        marks_count = 0
        for exam in exams:
            for classroom in exam.classrooms.all():
                enrollments = StudentClassEnrollment.objects.filter(
                    classroom=classroom,
                    academic_year=self.academic_year
                )

                exam_subjects = random.sample(self.subjects, k=random.randint(3, 5))

                for enrollment in enrollments[:20]:
                    for subject in exam_subjects:
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

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {marks_count} exam marks"))

    def create_allocated_subjects(self):
        """Allocate subjects to teachers and classrooms"""
        self.stdout.write("\n[Bonus] Creating subject allocations...")

        allocation_count = 0

        for classroom in self.classrooms:
            classroom_subjects = random.sample(self.subjects, k=random.randint(6, 8))

            for subject in classroom_subjects:
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

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {allocation_count} subject allocations"))

    def create_articles(self):
        """Create sample articles/news"""
        self.stdout.write("\n[Bonus] Creating articles...")

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

        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {len(articles_data)} articles"))

    def print_summary(self):
        """Print summary of generated data"""
        self.stdout.write("\n📊 DATA SUMMARY:")
        self.stdout.write(f"   • School: {School.objects.filter(active=True).first().name}")
        self.stdout.write(f"   • Academic Year: {self.academic_year.name}")
        self.stdout.write(f"   • Current Term: {self.current_term.name}")
        self.stdout.write(f"   • Departments: {Department.objects.count()}")
        self.stdout.write(f"   • Subjects: {Subject.objects.count()}")
        self.stdout.write(f"   • Classrooms: {ClassRoom.objects.count()}")
        self.stdout.write(f"   • Teachers: {Teacher.objects.count()}")
        self.stdout.write(f"   • Accountants: {CustomUser.objects.filter(is_accountant=True).count()}")
        self.stdout.write(f"   • Parents: {Parent.objects.count()}")
        self.stdout.write(f"   • Students: {Student.objects.count()}")
        self.stdout.write(f"   • Fee Structures: {FeeStructure.objects.count()}")
        self.stdout.write(f"   • Receipts: {Receipt.objects.count()}")
        self.stdout.write(f"   • Payments (Expenses): {Payment.objects.count()}")
        self.stdout.write(f"   • Examinations: {ExaminationListHandler.objects.count()}")
        self.stdout.write(f"   • Exam Marks: {MarksManagement.objects.count()}")
        self.stdout.write(f"   • Subject Allocations: {AllocatedSubject.objects.count()}")
        self.stdout.write(f"   • Timetable Periods: {Period.objects.count()}")

        self.stdout.write(self.style.SUCCESS("\n🔑 SAMPLE LOGIN CREDENTIALS:"))
        self.stdout.write("   Teachers: teacher001@hillcrest.edu.ug (password: password)")
        self.stdout.write("   Accountants: sarah.nakato@hillcrest.edu.ug (password: password)")
        self.stdout.write("   Parents: Use phone number as username (password: password)")

        self.stdout.write(self.style.SUCCESS("\n💡 NEXT STEPS:"))
        self.stdout.write("   1. Create a superuser: python manage.py createsuperuser")
        self.stdout.write("   2. Run development server: python manage.py runserver")
        self.stdout.write("   3. Access admin: http://localhost:8000/admin/")
        self.stdout.write("   4. Generate timetable: python manage.py generate_timetable")
