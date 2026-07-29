"""
Django Management Command: Generate Nigerian School Sample Data for SCMS
"""
import os
import random
from datetime import datetime, timedelta, date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import Group
from django.utils import timezone
from django.conf import settings
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
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
    FeeStructure, StudentFeeAssignment, Receipt, FeePaymentAllocation
)
from attendance.models import AttendanceStatus, StudentAttendance, TeachersAttendance

from examination.models import (
    GradingScheme, AssessmentComponent, GradeRule,
    AssessmentSession, AssessmentEntry, AssessmentType
)
from schedule.models import PeriodSlot, TimetableEntry

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

NIGERIAN_RELIGIONS = ['Christianity', 'Islam', 'Traditional Religion', 'Other']
NIGERIAN_OCCUPATIONS = [
    'Civil Servant', 'Business Owner', 'Trader', 'Teacher', 'Nurse', 'Doctor',
    'Engineer', 'Lawyer', 'Accountant', 'Banker', 'Farmer', 'Artisan',
    'Transporter', 'Tailor', 'Welder', 'Mechanic', 'Administrator', 'Electrician',
    'Contractor', 'Manager', 'Supervisor', 'Driver', 'Security Officer',
    'Beautician', 'Hairdresser', 'Barber', 'Cleaner', 'Laborer'
]

AVATAR_PATHS = [
    f"avatars/avatar_{i}.png" for i in range(5)
]

class Command(BaseCommand):
    help = 'Generate comprehensive Nigerian school sample data for the SCMS demo'

    def add_arguments(self, parser):
        parser.add_argument('--students', type=int, default=300)
        parser.add_argument('--teachers', type=int, default=20)
        parser.add_argument('--schema', type=str)

    def handle(self, *args, **options):
        self.num_students = options['students']
        self.num_teachers = options['teachers']
        self.teachers = []
        self.parents = []
        self.students = []
        self.classrooms = []
        self.subjects = []
        self.accountants = []
        self.grading_schemes = []
        
        schema_name = options.get('schema')
        if schema_name:
            if schema_context is None:
                raise CommandError("django_tenants is not installed")
            
            from tenants.models import Client
            try:
                self.tenant_client = Client.objects.get(schema_name=schema_name)
            except Client.DoesNotExist:
                raise CommandError(f"No tenant found with schema_name='{schema_name}'")

            self.school_domain = self.tenant_client.schema_name
            with schema_context(schema_name):
                self._run_generation()
        else:
            self.school_domain = "demo"
            self._run_generation()

    def get_avatar_file(self, prefix="avatar"):
        try:
            from io import BytesIO
            from PIL import Image
            color = (random.randint(40, 200), random.randint(40, 200), random.randint(40, 200))
            img = Image.new('RGB', (200, 200), color=color)
            buf = BytesIO()
            img.save(buf, format='PNG')
            return ContentFile(buf.getvalue(), name=f"{prefix}_{random.randint(10000, 99999)}.png")
        except Exception:
            VALID_PNG = (
                b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00d\x00\x00\x00d\x08\x02\x00\x00\x00'
                b'\xff\x80\x02\x03\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xdc'
                b'\xcc\x59\x00\x00\x00\x00IEND\xaeB`\x82'
            )
            return ContentFile(VALID_PNG, name=f"{prefix}_{random.randint(10000, 99999)}.png")

    def get_gender_avatar_file(self, gender):
        """
        Loads male.png / female.png from the project root (same directory as
        manage.py) for student avatars. Falls back to a generated placeholder
        if the file is missing, so a bad path doesn't abort the whole run.
        """
        filename = 'male.png' if gender == 'Male' else 'female.png'
        path = os.path.join(settings.BASE_DIR, filename)
        try:
            with open(path, 'rb') as f:
                data = f.read()
            return ContentFile(data, name=filename)
        except FileNotFoundError:
            self.stdout.write(self.style.WARNING(
                f"  Warning: {filename} not found at {path} — using a generated placeholder instead."
            ))
            return self.get_avatar_file(gender.lower())


    def get_avatar(self, gender=None):
        return self.get_avatar_file("avatar")

    def _run_generation(self):
        self.stdout.write(self.style.SUCCESS("🎓 GENERATING DEMO DATA (2025/2026 Session)"))
        self.create_groups()
        self.create_academic_calendar()
        self.create_departments_and_subjects()
        self.create_grade_levels()
        self.create_grading_schemes()
        self.create_demo_admin()
        self.create_accountants()
        self.create_teachers()
        self.create_classrooms()
        self.create_parents()
        self.create_students()
        self.create_fee_structures()
        self.create_receipts_and_payments()
        self.create_attendance()
        self.create_examinations_and_scores()
        self.create_timetable()
        self.create_school_events()
        
        self.stdout.write(self.style.SUCCESS("DATA GENERATION COMPLETE!"))
        
        # Print demo accounts
        print("\n--- DEMO ACCOUNTS ---")
        print("Admin: admin@demo.com / password123")
        print("Teacher: teacher@demo.com / password123")
        print("Parent: parent@demo.com / password123")
        print("Accountant: accountant@demo.com / password123")

    def create_groups(self):
        for g in ['teacher', 'parent', 'accountant', 'family', 'student']:
            Group.objects.get_or_create(name=g)

    def create_academic_calendar(self):
        self.stdout.write("1. Creating Academic Calendar 2025/2026...")
        # Force the 2025/2026 academic year
        self.academic_year, _ = AcademicYear.objects.update_or_create(
            name="2025/2026",
            defaults={
                'start_date': date(2025, 9, 1),
                'end_date': date(2026, 7, 30),
                'active_year': True
            }
        )
        # Deactivate others
        AcademicYear.objects.exclude(id=self.academic_year.id).update(active_year=False)

        # Create terms
        terms_data = [
            ('First Term', date(2025, 9, 1), date(2025, 12, 15)),
            ('Second Term', date(2026, 1, 5), date(2026, 4, 15)),
            ('Third Term', date(2026, 4, 20), date(2026, 7, 30)),
        ]
        self.terms = []
        for name, start, end in terms_data:
            term, _ = Term.objects.update_or_create(
                name=name,
                academic_year=self.academic_year,
                defaults={'start_date': start, 'end_date': end}
            )
            self.terms.append(term)
        
        # Current term is Third Term for demo purposes
        self.current_term = self.terms[2]
        
        # Create days
        for day_num, day_name in enumerate(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'], 1):
            Day.objects.get_or_create(day=day_num)

    def create_departments_and_subjects(self):
        self.stdout.write("2. Creating Departments and Subjects...")
        departments_subjects = {
            'Languages': [('English Language', 'ENG'), ('French', 'FRE')],
            'Mathematics': [('Mathematics', 'MATH')],
            'Sciences': [('Physics', 'PHY'), ('Chemistry', 'CHEM'), ('Biology', 'BIO'), ('Basic Science', 'BSC')],
            'Social Sciences': [('Geography', 'GEO'), ('Economics', 'ECON')],
            'Vocational': [('Computer Science', 'CS'), ('Accounting', 'ACC')]
        }

        for dept_name, subjects in departments_subjects.items():
            dept, _ = Department.objects.get_or_create(name=dept_name.lower())
            for subj_name, code in subjects:
                subject, _ = Subject.objects.get_or_create(
                    subject_code=code,
                    defaults={'name': subj_name, 'is_selectable': False, 'graded': True, 'department': dept}
                )
                self.subjects.append(subject)

    def create_grade_levels(self):
        self.stdout.write("3. Fetching Grade Levels and creating Class Levels...")
        # Assume GradeLevel.initialize_defaults() ran, fetch them
        jss1 = GradeLevel.objects.get(system_code='JSS_1')
        jss2 = GradeLevel.objects.get(system_code='JSS_2')
        jss3 = GradeLevel.objects.get(system_code='JSS_3')
        ss1 = GradeLevel.objects.get(system_code='SS_1')
        ss2 = GradeLevel.objects.get(system_code='SS_2')
        ss3 = GradeLevel.objects.get(system_code='SS_3')
        
        classes = [
            ('JSS 1A', jss1), ('JSS 1B', jss1), ('JSS 2A', jss2),
            ('JSS 3A', jss3), ('SS 1A', ss1), ('SS 2A', ss2), ('SS 3A', ss3)
        ]
        
        for cl_name, gl in classes:
            ClassLevel.objects.get_or_create(name=cl_name, defaults={'grade_level': gl})

        # Class years
        current_year = datetime.now().year
        for i in range(-1, 6):
            ClassYear.objects.get_or_create(year=current_year + i)

    def create_grading_schemes(self):
        self.stdout.write("4. Creating Grading Schemes...")
        for gl in GradeLevel.objects.all():
            scheme, _ = GradingScheme.objects.update_or_create(
                name=f"Standard WAEC Scheme ({gl.default_name})",
                academic_year=self.academic_year,
                grade_level=gl,
                defaults={'description': 'Standard secondary school grading scheme'}
            )
            
            AssessmentComponent.objects.update_or_create(
                scheme=scheme, name="1st CA", defaults={'max_score': 20, 'weight': 20, 'order': 1}
            )
            AssessmentComponent.objects.update_or_create(
                scheme=scheme, name="2nd CA", defaults={'max_score': 20, 'weight': 20, 'order': 2}
            )
            AssessmentComponent.objects.update_or_create(
                scheme=scheme, name="Examination", defaults={'max_score': 60, 'weight': 60, 'order': 3}
            )
            
            rules = [
                (75, 100, 'A1', 'Excellent'),
                (70, 74.99, 'B2', 'Very Good'),
                (65, 69.99, 'B3', 'Good'),
                (60, 64.99, 'C4', 'Credit'),
                (55, 59.99, 'C5', 'Credit'),
                (50, 54.99, 'C6', 'Credit'),
                (45, 49.99, 'D7', 'Pass'),
                (40, 44.99, 'E8', 'Pass'),
                (0,  39.99, 'F9', 'Fail'),
            ]
            for min_s, max_s, grade, remark in rules:
                GradeRule.objects.update_or_create(
                    scheme=scheme,
                    min_score=min_s,
                    defaults={'max_score': max_s, 'grade': grade, 'remark': remark}
                )
            
            self.grading_schemes.append(scheme)

    def create_demo_admin(self):
        admin, _ = CustomUser.objects.get_or_create(
            email='admin@demo.com',
            defaults={
                'first_name': 'Demo',
                'last_name': 'Admin',
                'is_active': True,
                'is_admin': True,
            }
        )
        admin.set_password('password123')
        admin.save()

    def create_accountants(self):
        acc, _ = CustomUser.objects.get_or_create(
            email='accountant@demo.com',
            defaults={
                'first_name': 'Demo',
                'last_name': 'Accountant',
                'is_active': True,
                'is_accountant': True,
            }
        )
        acc.set_password('password123')
        acc.save()
        self.accountants.append(acc)

    def create_teachers(self):
        self.stdout.write("5. Creating Teachers...")
        demo_t, _ = CustomUser.objects.get_or_create(
            email='teacher@demo.com',
            defaults={
                'first_name': 'Demo',
                'last_name': 'Teacher',
                'is_active': True,
                'is_teacher': True,
            }
        )
        demo_t.set_password('password123')
        demo_t.save()
        
        dt, _ = Teacher.objects.get_or_create(user=demo_t, defaults={'empId': 'TCH001'})
        dt.subject_specialization.set(random.sample(self.subjects, 2))
        self.teachers.append(dt)
        
        for i in range(1, self.num_teachers):
            fname = NIGERIAN_FIRST_NAMES_MALE[i % len(NIGERIAN_FIRST_NAMES_MALE)]
            lname = NIGERIAN_LAST_NAMES[i % len(NIGERIAN_LAST_NAMES)]
            email = f"teacher_{i:02d}@school.com"
            user, _ = CustomUser.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': fname,
                    'last_name': lname,
                    'is_active': True,
                    'is_teacher': True,
                }
            )
            user.first_name = fname
            user.last_name = lname
            user.set_password('password123')
            user.save()
            t, _ = Teacher.objects.get_or_create(
                user=user,
                defaults={'empId': f'TCH{i:04d}'}
            )
            t.subject_specialization.set(random.sample(self.subjects, 2))
            self.teachers.append(t)

    def create_classrooms(self):
        self.stdout.write("6. Creating Classrooms...")
        class_levels = list(ClassLevel.objects.all())
        t_idx = 0
        for cl in class_levels:
            classroom, _ = ClassRoom.objects.get_or_create(
                name=cl,
                defaults={'class_teacher': self.teachers[t_idx % len(self.teachers)], 'capacity': 50}
            )
            self.classrooms.append(classroom)
            t_idx += 1

    def create_parents(self):
        self.stdout.write("7. Creating Parents...")
        demo_p, _ = CustomUser.objects.get_or_create(
            email='parent@demo.com',
            defaults={
                'first_name': 'Ngozi',
                'last_name': 'Okafor',
                'is_active': True,
                'is_parent': True,
                'phone_number': '+2348000000000',
            }
        )
        demo_p.first_name = 'Ngozi'
        demo_p.last_name = 'Okafor'
        demo_p.set_password('password123')
        demo_p.save()

        dp, _ = Parent.objects.get_or_create(
            user=demo_p, 
            defaults={'phone_number': demo_p.phone_number, 'first_name': 'Ngozi', 'last_name': 'Okafor', 'email': demo_p.email}
        )
        dp.first_name = 'Ngozi'
        dp.last_name = 'Okafor'
        dp.email = demo_p.email
        if not dp.image:
            try:
                dp.image.save("parent_demo.png", self.get_avatar_file("parent_demo"), save=False)
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  Warning: Could not upload demo parent image ({e})"))
        dp.save()
        self.parents.append(dp)
        
        num_p = max(50, int(self.num_students * 0.7))
        for i in range(num_p):
            fname = random.choice(NIGERIAN_FIRST_NAMES_MALE + NIGERIAN_FIRST_NAMES_FEMALE)
            lname = random.choice(NIGERIAN_LAST_NAMES)
            phone_num = f"701{i+1:07d}"
            phone = f"+234{phone_num}"[:15]
            email = f"parent_{phone_num}@school.com"
            gender = 'Male' if fname in NIGERIAN_FIRST_NAMES_MALE else 'Female'

            user, _ = CustomUser.objects.get_or_create(
                email=email,
                defaults={
                    'phone_number': phone,
                    'first_name': fname,
                    'last_name': lname,
                    'is_active': True,
                    'is_parent': True,
                }
            )
            user.first_name = fname
            user.last_name = lname
            if not user.phone_number:
                user.phone_number = phone
            user.set_password('password')
            user.save()

            p, _ = Parent.objects.get_or_create(
                user=user,
                defaults={'phone_number': phone, 'first_name': fname, 'last_name': lname, 'email': email, 'gender': gender}
            )
            p.first_name = fname
            p.last_name = lname
            p.email = email
            p.gender = gender
            p.phone_number = phone
            if not p.image:
                try:
                    p.image.save(f"parent_{user.id}.png", self.get_avatar_file("parent"), save=False)
                except Exception:
                    pass
            p.save()
            self.parents.append(p)

    def create_students(self):
        self.stdout.write("8. Creating Students...")
        class_year = ClassYear.objects.get(year=2028)
        
        # Create Demo Student Account
        demo_st_user, _ = CustomUser.objects.get_or_create(
            email='student@demo.com',
            defaults={
                'first_name': 'Lara',
                'last_name': 'Okafor',
                'is_active': True,
                'is_student': True,
            }
        )
        demo_st_user.set_password('password123')
        demo_st_user.save()
        
        parent = self.parents[0] if self.parents else None
        parent_contact = parent.phone_number if (parent and parent.phone_number) else "+2348010000000"

        demo_st, _ = Student.objects.get_or_create(
            user=demo_st_user,
            defaults={
                'first_name': 'Lara',
                'last_name': 'Okafor',
                'admission_number': 'ADM-2026-0001',
                'classroom': self.classrooms[0] if self.classrooms else None,
                'parent_guardian': parent,
                'parent_contact': parent_contact,
                'gender': 'Female',
            }
        )
        if parent:
            demo_st.parent_guardian = parent
            demo_st.parent_contact = parent_contact
            demo_st.save()
        self.students.append(demo_st)
        
        newly_enrolled_count = int(self.num_students * 0.18)  # ~18% new enrollments
        first_term_new_count = int(newly_enrolled_count * 0.88) # ~88% in First Term

        for i in range(self.num_students):
            fname = random.choice(NIGERIAN_FIRST_NAMES_MALE + NIGERIAN_FIRST_NAMES_FEMALE)
            parent = self.parents[0] if i < 3 else random.choice(self.parents)
            lname = parent.last_name
            classroom = self.classrooms[i % len(self.classrooms)]
            gender = 'Male' if fname in NIGERIAN_FIRST_NAMES_MALE else 'Female'

            if i < first_term_new_count:
                d_val = date(2025, 9, random.randint(1, 20))
            elif i < newly_enrolled_count:
                d_val = date(2026, 1, random.randint(5, 20))
            else:
                d_val = date(random.choice([2023, 2024]), 9, random.randint(1, 20))
            admission_date = timezone.make_aware(datetime.combine(d_val, datetime.min.time()))
            
            phone_num = f"801{i+1:07d}"
            phone = f"+234{phone_num}"[:15]
            email = f"student_{phone_num}@school.com"

            user, _ = CustomUser.objects.get_or_create(
                email=email,
                defaults={
                    'phone_number': phone,
                    'first_name': fname,
                    'last_name': lname,
                    'is_active': True,
                    'is_student': True,
                }
            )
            user.first_name = fname
            user.last_name = lname
            if not user.phone_number:
                user.phone_number = phone
            user.set_password('password')
            user.save()
            
            student, _ = Student.objects.get_or_create(
                user=user,
                defaults={
                    'first_name': fname,
                    'last_name': lname,
                    'gender': gender,
                    'class_level': classroom.name,
                    'class_of_year': class_year,
                    'parent_guardian': parent,
                    'parent_contact': parent.phone_number,
                    'phone_number': user.phone_number,
                    'admission_date': admission_date,
                }
            )
            student.first_name = fname
            student.last_name = lname
            student.gender = gender
            student.parent_guardian = parent
            if not student.image:
                try:
                    student.image.save(
                        f"student_{user.id}_{gender.lower()}.png",
                        self.get_gender_avatar_file(gender),
                        save=False,
                    )
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"  Warning: Could not set student avatar ({e})"))
            student.save()

            StudentClassEnrollment.objects.get_or_create(student=student, classroom=classroom, academic_year=self.academic_year)
            self.students.append(student)
            
            # Allocate subjects per classroom evenly across all teachers
        t_assign_idx = 0
        for cr in self.classrooms:
            for sub in self.subjects:
                assigned_teacher = self.teachers[t_assign_idx % len(self.teachers)]
                t_assign_idx += 1
                alloc, created = AllocatedSubject.objects.get_or_create(
                    class_room=cr, 
                    subject=sub, 
                    academic_year=self.academic_year, 
                    defaults={'teacher_name': assigned_teacher, 'weekly_periods': 3, 'term': None}
                )
                if not created:
                    alloc.teacher_name = assigned_teacher
                    alloc.save(update_fields=['teacher_name'])

    def create_fee_structures(self):
        self.stdout.write("9. Creating Fees (Mostly Paid)...")
        fees_data = [
            ('Tuition Fee', 'Tuition', Decimal('150000'), True),
            ('Transport', 'Transport', Decimal('50000'), False),
            ('ICT Levy', 'Others', Decimal('15000'), True),
        ]
        
        for term in self.terms:
            structures = []
            for name, fee_type, amount, is_mandatory in fees_data:
                fs, _ = FeeStructure.objects.get_or_create(
                    name=f"{name} ({term.name})",
                    academic_year=self.academic_year,
                    term=term,
                    defaults={'fee_type': fee_type, 'amount': amount, 'is_mandatory': is_mandatory, 'due_date': term.end_date}
                )
                structures.append(fs)
                # Auto-assign if mandatory
                if is_mandatory:
                    fs.auto_assign_to_students(term=term)
                else:
                    # Manually assign to ~30% of students
                    for student in self.students:
                        if random.random() < 0.3:
                            StudentFeeAssignment.objects.get_or_create(
                                student=student, fee_structure=fs, term=term,
                                defaults={'amount_owed': fs.amount, 'amount_paid': Decimal('0')}
                            )

    def create_receipts_and_payments(self):
        # Pay fees (mostly paid)
        for term in self.terms:
            assignments = StudentFeeAssignment.objects.filter(term=term)
            for assignment in assignments:
                # 92% fully paid, 5% partial, 3% unpaid
                r = random.random()
                if r < 0.92:
                    payment = assignment.amount_owed
                elif r < 0.97:
                    payment = assignment.amount_owed * Decimal('0.5')
                else:
                    payment = Decimal('0')
                
                if payment > 0:
                    assignment.amount_paid = payment
                    assignment.save()
                    
                    # Create receipt
                    pg = assignment.student.parent_guardian
                    if pg:
                        payer_name = f"{pg.first_name or ''} {pg.last_name or ''}".strip() or "Parent"
                    else:
                        payer_name = "Parent"
                    methods = ['Bank Transfer', 'Cash', 'Online', 'Mobile Money']
                    
                    Receipt.objects.create(
                        date=timezone.now().date(),
                        student=assignment.student,
                        amount=payment,
                        payer=payer_name,
                        paid_through=random.choice(methods),
                        term=term,
                        status='Completed'
                    )

    def create_attendance(self):
        self.stdout.write("10. Creating Attendance...")
        present, _ = AttendanceStatus.objects.get_or_create(name='Present', defaults={'code': 'P'})
        absent, _ = AttendanceStatus.objects.get_or_create(name='Absent', defaults={'code': 'A'})
        late, _ = AttendanceStatus.objects.get_or_create(name='Late', defaults={'code': 'L'})
        
        # Generate attendance for 30 weekdays (~6 full school weeks) of current term
        today = date.today()
        raw_dates = [today - timedelta(days=i) for i in range(45)]
        dates = [d for d in raw_dates if d.weekday() < 5][:30] # 30 weekdays
        
        for d in dates:
            for student in self.students:
                r = random.random()
                if r < 0.9:
                    status = present
                elif r < 0.95:
                    status = late
                else:
                    status = absent
                    
                StudentAttendance.objects.get_or_create(
                    student=student,
                    date=d,
                    term=self.current_term,
                    defaults={'status': status}
                )

    def create_examinations_and_scores(self):
        self.stdout.write("11. Creating Examinations & Scores (Term-end Nightmare Demo)...")
        for term in self.terms[:2]:
            session, _ = AssessmentSession.objects.get_or_create(
                name=f"{term.name} Examination {self.academic_year.name}",
                defaults={
                    'assessment_type': 'EXAM',
                    'start_date': term.start_date,
                    'ends_date': term.end_date,
                    'out_of': 100,
                    'created_by': self.teachers[0] if self.teachers else None
                }
            )
            session.classrooms.set(self.classrooms)
            self._fill_scores(session)
            
        # For Term 3 (current), create active session, partially fill
        session, _ = AssessmentSession.objects.get_or_create(
            name=f"{self.current_term.name} Examination {self.academic_year.name}",
            defaults={
                'assessment_type': 'EXAM',
                'start_date': self.current_term.start_date,
                'ends_date': self.current_term.end_date,
                'out_of': 100,
                'created_by': self.teachers[0] if self.teachers else None
            }
        )
        session.classrooms.set(self.classrooms)
        self._fill_scores(session, partial=True)
        
    def _fill_scores(self, session, partial=False):
        for classroom in self.classrooms:
            gl = classroom.name.grade_level
            scheme = GradingScheme.objects.filter(grade_level=gl, academic_year=self.academic_year).first()
            if not scheme:
                continue
            comps = AssessmentComponent.objects.filter(scheme=scheme)
            enrollments = StudentClassEnrollment.objects.filter(classroom=classroom, academic_year=self.academic_year)
            teacher_obj = classroom.class_teacher or (self.teachers[0] if self.teachers else None)
            
            for enrollment in enrollments:
                for subject in self.subjects:
                    for comp in comps:
                        # If partial, maybe skip exams
                        if partial and comp.name == 'Examination' and random.random() < 0.8:
                            continue
                        
                        max_score = float(comp.max_score)
                        score = random.randint(int(max_score * 0.4), int(max_score))
                        AssessmentEntry.objects.get_or_create(
                            student=enrollment,
                            subject=subject,
                            component=comp,
                            defaults={'score': Decimal(str(score)), 'entered_by': teacher_obj}
                        )

    def create_timetable(self):
        self.stdout.write("12. Creating Timetable (Smart Clash-free)...")
        
        times = [
            ("08:00:00", "08:40:00"),
            ("08:40:00", "09:20:00"),
            ("09:20:00", "10:00:00"),
            ("10:00:00", "10:40:00"),
            ("11:00:00", "11:40:00"),
            ("11:40:00", "12:20:00"),
            ("12:20:00", "13:00:00"),
            ("13:00:00", "13:40:00"),
        ]
        slots = []
        for d in PeriodSlot.DAYS_OF_WEEK[:5]:
            for i, (start, end) in enumerate(times, 1):
                slot, _ = PeriodSlot.objects.get_or_create(
                    term=self.current_term,
                    day_of_week=d[0],
                    period_number=i,
                    defaults={'start_time': start, 'end_time': end, 'label': f'Period {i}'}
                )
                slots.append(slot)
                
        # Track which (teacher_id, slot_id) pairs are already used
        busy_teacher_slots = set()
                
        for classroom in self.classrooms[:3]:
            allocations = AllocatedSubject.objects.filter(class_room=classroom, academic_year=self.academic_year)
            if not allocations.exists():
                continue
            
            pool = []
            for alloc in allocations:
                subject_name = alloc.subject.name.lower()
                if 'english' in subject_name or 'math' in subject_name:
                    pool.extend([alloc] * 5)
                else:
                    pool.extend([alloc] * 2)
            
            random.shuffle(pool)
            while len(pool) < len(slots):
                pool.extend(pool)
            
            for i, slot in enumerate(slots):
                allocated = pool[i]
                teacher = allocated.teacher_name
                
                # Skip if this teacher is already teaching another class during this slot
                if (teacher.id, slot.id) in busy_teacher_slots:
                    continue
                    
                try:
                    TimetableEntry.objects.get_or_create(
                        term=self.current_term,
                        slot=slot,
                        classroom=classroom,
                        defaults={
                            'subject': allocated,
                            'teacher': teacher
                        }
                    )
                    busy_teacher_slots.add((teacher.id, slot.id))
                except ValidationError:
                    # Teacher conflict slipped through — skip this slot for this classroom
                    pass
    def create_school_events(self):
        self.stdout.write("13. Creating School Events and Holidays...")
        today = date.today()
        friday_last_week = date(2026, 7, 24)
        sept_resumption = date(2026, 9, 7)
        events_data = [
            ("End-of-Session Long Vacation", "holiday", friday_last_week, sept_resumption, "School closed for long vacation. Resumption for 2026/2027 Academic Session on Sept 7, 2026"),
            ("2026/2027 First Term Resumption & Orientation", "other", sept_resumption, sept_resumption + timedelta(days=1), "Resumption of all students for the new 2026/2027 academic session"),
            ("1st Term Parent-Teacher Alignment Forum", "other", date(2026, 9, 18), date(2026, 9, 18), "First term parent-teacher meeting for 2026/2027 academic session"),
            ("1st Term Continuous Assessment (CA 1)", "exam", date(2026, 10, 19), date(2026, 10, 23), "First assessment test for 2026/2027 1st Term"),
        ]
        for name, etype, sdate, edate, desc in events_data:
            SchoolEvent.objects.get_or_create(
                name=name,
                academic_year=self.academic_year,
                term=self.current_term,
                defaults={
                    'event_type': etype,
                    'start_date': sdate,
                    'end_date': edate,
                    'description': desc
                }
            )
