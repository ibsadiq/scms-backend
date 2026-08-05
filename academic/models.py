from django.db import models, transaction
from django.db.models import F
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _
from django.utils.crypto import get_random_string
from django.utils import timezone
from users.models import CustomUser
from django.conf import settings

from administration.models import AcademicYear, Term

from .validators import *
from administration.common_objs import *


class Department(models.Model):
    name = models.CharField(max_length=255, unique=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.name = self.name.lower()
        super().save(*args, **kwargs)


class Subject(models.Model):
    name = models.CharField(max_length=255, unique=True)
    subject_code = models.CharField(max_length=10, unique=True)
    is_selectable = models.BooleanField(
        default=False, help_text="Select if subject is optional"
    )
    graded = models.BooleanField(default=True, help_text="Teachers can submit grades")
    description = models.CharField(max_length=255, blank=True)
    department = models.ForeignKey(
        Department, on_delete=models.CASCADE, blank=True, null=True
    )

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["subject_code"]
        verbose_name = "Subject"
        verbose_name_plural = "Subjects"

    def save(self, *args, **kwargs):
        self.description = f"{self.name} - {self.subject_code}"
        super().save(*args, **kwargs)


class Teacher(models.Model):
    teacher_id = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        db_index=True,
        blank=True,
        help_text="Globally unique teacher identifier (e.g., TCH-B3N8Y6P1)"
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="teacher",
        null=True,
        blank=True,
    )
    empId = models.CharField(max_length=8, unique=True, null=True, blank=True)
    tin_number = models.CharField(max_length=9, blank=True, null=True, unique=True)
    short_name = models.CharField(max_length=3, blank=True, null=True, unique=True)
    subject_specialization = models.ManyToManyField(Subject, blank=True)
    national_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    address = models.CharField(max_length=255, blank=True)
    alt_email = models.EmailField(blank=True, null=True)
    designation = models.CharField(max_length=255, blank=True, null=True)
    image = models.ImageField(upload_to="Employee_images", blank=True, null=True)
    inactive = models.BooleanField(default=False)

    class Meta:
        ordering = ("id", "user__first_name", "user__last_name")

    # Properties to access user fields for backward compatibility
    @property
    def username(self):
        return self.user.email if self.user else None

    @property
    def first_name(self):
        return self.user.first_name if self.user else ""

    @property
    def middle_name(self):
        return self.user.middle_name if self.user else ""

    @property
    def last_name(self):
        return self.user.last_name if self.user else ""

    @property
    def email(self):
        return self.user.email if self.user else None

    @property
    def phone_number(self):
        return self.user.phone_number if self.user else ""

    @property
    def gender(self):
        # Gender will be added to CustomUser model in future
        return getattr(self.user, 'gender', None) if self.user else None

    @property
    def date_of_birth(self):
        # Date of birth will be added to CustomUser model in future
        return getattr(self.user, 'date_of_birth', None) if self.user else None

    @property
    def deleted(self):
        return self.inactive

    def save(self, *args, **kwargs):
        """
        When a teacher is created, ensure a CustomUser instance exists for login.
        """
        if not self.user:
            raise ValidationError("Teacher must have an associated user account. Create the CustomUser first.")
        
        if not self.teacher_id:
            from django_tenants.utils import schema_context
            with schema_context('public'):
                from core.models import GlobalIDRegistry
                self.teacher_id = GlobalIDRegistry.generate_unique_id('teacher')

        # Ensure user is marked as teacher
        if not self.user.is_teacher:
            self.user.is_teacher = True
            self.user.save(update_fields=["is_teacher"])

        group, _ = Group.objects.get_or_create(name="teacher")
        self.user.groups.add(group)

        super().save(*args, **kwargs)

        # Sync identity snapshot + current school to public GlobalIDRegistry
        if self.teacher_id:
            from django.db import connection
            from django_tenants.utils import schema_context
            _schema = connection.schema_name
            with schema_context('public'):
                from core.models import GlobalIDRegistry
                GlobalIDRegistry.sync(
                    unique_id=self.teacher_id,
                    first_name=self.first_name or '',
                    last_name=self.last_name or '',
                    date_of_birth=getattr(self, 'date_of_birth', None),
                    current_schema=_schema,
                )

    def __str__(self):
        if self.user:
            return f"{self.user.first_name} {self.user.last_name} ({self.teacher_id})"
        return f"Teacher {self.teacher_id}"


class SectionType(models.TextChoices):
    PRE_PRIMARY = 'PRE_PRIMARY', _('Pre-Primary Education')
    PRIMARY = 'PRIMARY', _('Primary Education')
    JUNIOR_SECONDARY = 'JSS', _('Junior Secondary School')
    SENIOR_SECONDARY = 'SSS', _('Senior Secondary School')

class StandardClassCode(models.TextChoices):
    """
    Hardcoded codes for Data Analysis. 
    These keys (e.g., 'BASIC_1') will NEVER change, ensuring reports stay consistent
    even if the School Administrator changes the alias.
    """
    # 1. Pre-Primary
    CRECHE = 'CRECHE', _('Creche/Playgroup')
    PRE_NURSERY = 'PRE_NURSERY', _('Pre-Nursery')
    NURSERY_1 = 'NURSERY_1', _('Nursery 1')
    NURSERY_2 = 'NURSERY_2', _('Nursery 2')
    
    # 2. Primary (Basic)
    BASIC_1 = 'BASIC_1', _('Basic 1 (Primary 1)')
    BASIC_2 = 'BASIC_2', _('Basic 2 (Primary 2)')
    BASIC_3 = 'BASIC_3', _('Basic 3 (Primary 3)')
    BASIC_4 = 'BASIC_4', _('Basic 4 (Primary 4)')
    BASIC_5 = 'BASIC_5', _('Basic 5 (Primary 5)')
    BASIC_6 = 'BASIC_6', _('Basic 6 (Primary 6)')
    
    # 3. Junior Secondary
    JSS_1 = 'JSS_1', _('JSS 1 (Basic 7)')
    JSS_2 = 'JSS_2', _('JSS 2 (Basic 8)')
    JSS_3 = 'JSS_3', _('JSS 3 (Basic 9)')
    
    # 4. Senior Secondary
    SS_1 = 'SS_1', _('SS 1')
    SS_2 = 'SS_2', _('SS 2')
    SS_3 = 'SS_3', _('SS 3')

class GradeLevel(models.Model):
    """
    The Master Configuration for Classes.
    Contains the standardized structure and the editable aliases.
    """
    system_code = models.CharField(
        max_length=20, 
        choices=StandardClassCode.choices, 
        unique=True,
        help_text="Internal code for data analysis. Cannot be changed."
    )
    section = models.CharField(max_length=20, choices=SectionType.choices)
    
    # Display Fields
    default_name = models.CharField(max_length=100, help_text="Standard Universal Name")
    alias = models.CharField(
        max_length=100, 
        blank=True, 
        help_text="School-specific name (e.g., 'Year 1' instead of 'Basic 1'). Admin editable."
    )
    updated_at = models.DateTimeField(auto_now=True)
    
    # Age & Sequence Logic
    sequence_order = models.PositiveIntegerField(help_text="Order for promotion (1, 2, 3...)")
    min_age = models.PositiveIntegerField(default=0)
    max_age = models.PositiveIntegerField(default=0)
    
    # Certification Notes
    graduation_note = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="E.g., 'Graduates receive FSLC' or 'Graduates take WAEC'"
    )

    class Meta:
        ordering = ("sequence_order",)
        verbose_name = "Grade Configuration"

    def __str__(self):
        # Return the Alias if set, otherwise the Standard Name
        return self.alias if self.alias else self.default_name

    @classmethod
    def initialize_defaults(cls):
        """
        Run this method to populate the database with the hardcoded structure.
        Usage: GradeLevel.initialize_defaults()
        """
        defaults = [
            # Pre-Primary
            {'code': 'CRECHE', 'name': 'Creche/Playgroup', 'section': 'PRE_PRIMARY', 'order': 1, 'min': 0, 'max': 2},
            {'code': 'PRE_NURSERY', 'name': 'Pre-Nursery', 'section': 'PRE_PRIMARY', 'order': 2, 'min': 2, 'max': 3},
            {'code': 'NURSERY_1', 'name': 'Nursery 1', 'section': 'PRE_PRIMARY', 'order': 3, 'min': 3, 'max': 4},
            {'code': 'NURSERY_2', 'name': 'Nursery 2', 'section': 'PRE_PRIMARY', 'order': 4, 'min': 4, 'max': 5},
            
            # Primary
            {'code': 'BASIC_1', 'name': 'Basic 1', 'section': 'PRIMARY', 'order': 5, 'min': 6, 'max': 6},
            {'code': 'BASIC_2', 'name': 'Basic 2', 'section': 'PRIMARY', 'order': 6, 'min': 7, 'max': 7},
            {'code': 'BASIC_3', 'name': 'Basic 3', 'section': 'PRIMARY', 'order': 7, 'min': 8, 'max': 8},
            {'code': 'BASIC_4', 'name': 'Basic 4', 'section': 'PRIMARY', 'order': 8, 'min': 9, 'max': 9},
            {'code': 'BASIC_5', 'name': 'Basic 5', 'section': 'PRIMARY', 'order': 9, 'min': 10, 'max': 10},
            {'code': 'BASIC_6', 'name': 'Basic 6', 'section': 'PRIMARY', 'order': 10, 'min': 11, 'max': 11, 'note': 'First School Leaving Certificate'},
            
            # JSS
            {'code': 'JSS_1', 'name': 'JSS 1', 'section': 'JSS', 'order': 11, 'min': 12, 'max': 12},
            {'code': 'JSS_2', 'name': 'JSS 2', 'section': 'JSS', 'order': 12, 'min': 13, 'max': 13},
            {'code': 'JSS_3', 'name': 'JSS 3', 'section': 'JSS', 'order': 13, 'min': 14, 'max': 14, 'note': 'BECE/JSCE'},
            
            # SSS
            {'code': 'SS_1', 'name': 'SS 1', 'section': 'SSS', 'order': 14, 'min': 15, 'max': 15},
            {'code': 'SS_2', 'name': 'SS 2', 'section': 'SSS', 'order': 15, 'min': 16, 'max': 16},
            {'code': 'SS_3', 'name': 'SS 3', 'section': 'SSS', 'order': 16, 'min': 17, 'max': 17, 'note': 'SSCE (WAEC/NECO)'},
        ]

        for item in defaults:
            obj, created = cls.objects.update_or_create(
                system_code=item['code'],
                defaults={
                    'default_name': item['name'],
                    'section': item['section'],
                    'sequence_order': item['order'],
                    'min_age': item['min'],
                    'max_age': item['max'],
                    'graduation_note': item.get('note', '')
                }
            )
            if created and not obj.alias:
                # Set default alias to name initially
                obj.alias = item['name']
                obj.save()


class ClassLevel(models.Model):
    """
    Represents the active classes in the school linked to the Master Grade.
    Examples: 'JSS 1 Gold', 'Basic 1A'.
    """
    name = models.CharField(max_length=150, help_text="e.g. JSS 1 Gold")
    grade_level = models.ForeignKey(
        GradeLevel, 
        on_delete=models.CASCADE, 
        related_name='classes'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ("grade_level__sequence_order", "name")

    def __str__(self):
        return self.name

    @property
    def section(self):
        return self.grade_level.get_section_display()


class ClassYear(models.Model):
    year = models.CharField(max_length=100, unique=True, help_text="Example 2020")
    full_name = models.CharField(
        max_length=255, help_text="Example Class of 2020", blank=True
    )

    def __str__(self):
        return self.full_name

    def save(self, *args, **kwargs):
        if not self.full_name:
            self.full_name = f"Class of {self.year}"
        super().save(*args, **kwargs)


class ReasonLeft(models.Model):
    reason = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.reason


class Stream(models.Model):
    name = models.CharField(max_length=50, validators=[stream_validator])

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.name = self.name.upper()
        super().save(*args, **kwargs)


class ClassRoom(models.Model):
    name = models.ForeignKey(
        ClassLevel, on_delete=models.CASCADE, related_name="class_level"
    )
    stream = models.ForeignKey(
        Stream, on_delete=models.CASCADE, blank=True, null=True, related_name="class_stream"
    )
    class_teacher = models.ForeignKey(Teacher, on_delete=models.SET_NULL, blank=True, null=True)
    capacity = models.PositiveIntegerField(default=40, blank=True)
    occupied_sits = models.PositiveIntegerField(default=0, blank=True)

    class Meta:
        constraints = [
        models.UniqueConstraint(fields=["name", "stream"], name="unique_classroom_per_stream")
        ]

    def __str__(self):
        if self.stream:
            return f"{self.name} {self.stream}"
        return f"{self.name}"

    @property
    def available_sits(self):
        return self.capacity - self.occupied_sits

    @property
    def class_status(self):
        percentage = (self.occupied_sits / self.capacity) * 100
        return f"{percentage:.2f}%"

    def clean(self):
        if self.occupied_sits > self.capacity:
            raise ValidationError("Occupied sits cannot exceed the capacity.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class Topic(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)
    class_level = models.ForeignKey(
        ClassLevel, on_delete=models.CASCADE, blank=True, null=True
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, blank=True, null=True
    )

    def __str__(self):
        return self.name


class SubTopic(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, blank=True, null=True)

    def __str__(self):
        return self.name


class AllocatedSubject(models.Model):
    teacher_name = models.ForeignKey(Teacher, on_delete=models.CASCADE)
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="allocated_subjects"
    )
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.SET_NULL, blank=True, null=True, related_name="allocated_subjects")
    class_room = models.ForeignKey(
        ClassRoom, on_delete=models.CASCADE, related_name="subjects"
    )
    weekly_periods = models.IntegerField(help_text="Total number of periods per week.")
    max_daily_periods = models.IntegerField(
        default=2,
        help_text="Maximum number of periods allowed per day for this subject.",
    )
    is_mandatory = models.BooleanField(
        default=True,
        help_text="Indicates whether this subject is mandatory (core) or optional (elective) for the class.",
    )

    def __str__(self):
        return f"{self.teacher_name} - {self.subject} ({self.academic_year})"

    def subjects_data(self):
        return list(self.subject.all())


class Parent(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="parent",
        null=True,
        blank=True,
    )
    first_name = models.CharField(
        max_length=300, verbose_name="First Name", blank=True, null=True
    )
    middle_name = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="Middle Name"
    )
    last_name = models.CharField(
        max_length=300, verbose_name="Last Name", blank=True, null=True
    )
    gender = models.CharField(
        max_length=10, choices=GENDER_CHOICE, blank=True, null=True
    )
    email = models.EmailField(blank=True, null=True, unique=True)
    parent_type = models.CharField(
        choices=PARENT_CHOICE, max_length=10, blank=True, null=True
    )
    address = models.CharField(max_length=255, blank=True, null=True)
    phone_number = models.CharField(
        max_length=150, unique=True, help_text="Personal phone number"
    )
    national_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    occupation = models.CharField(
        max_length=255, blank=True, null=True, help_text="Current occupation"
    )
    monthly_income = models.FloatField(
        help_text="Parent's average monthly income", blank=True, null=True
    )
    single_parent = models.BooleanField(
        default=False, blank=True, help_text="Is he/she a single parent"
    )
    alt_email = models.EmailField(blank=True, null=True, help_text="Personal email")
    date = models.DateTimeField(auto_now_add=True)
    image = models.ImageField(upload_to="Parent_images", blank=True)
    inactive = models.BooleanField(default=False)

    class Meta:
        ordering = ["email", "first_name", "last_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"

    def save(self, *args, **kwargs):
        """
        When a parent is created, ensure a user exists or is created
        based on email or phone number. Attach the user to the parent.
        """
        if not self.user:
            from django.db.models import Q
            from django.contrib.auth.models import Group
            from users.models import CustomUser

            query = Q()
            if self.email:
                query |= Q(email__iexact=self.email)
            if self.phone_number:
                clean_phone = self.phone_number.strip().replace(' ', '').replace('-', '')
                query |= Q(phone_number=self.phone_number) | Q(phone_number=clean_phone)
                if clean_phone.startswith('+234'):
                    query |= Q(phone_number='0' + clean_phone[4:])
                elif clean_phone.startswith('234'):
                    query |= Q(phone_number='0' + clean_phone[3:])
                elif clean_phone.startswith('0') and len(clean_phone) == 11:
                    query |= Q(phone_number='+234' + clean_phone[1:])

            user = CustomUser.objects.filter(query).first() if query else None

            if user:
                if not user.is_parent:
                    user.is_parent = True
                    user.save(update_fields=['is_parent'])
                self.user = user
            else:
                user_email = self.email or self.alt_email
                if not user_email:
                    phone_clean = (self.phone_number or 'parent').replace('+', '').replace(' ', '').replace('-', '')
                    user_email = f"parent_{phone_clean}@ssyncportal.local"

                user = CustomUser.objects.create(
                    first_name=self.first_name or '',
                    last_name=self.last_name or '',
                    email=user_email,
                    phone_number=self.phone_number or '',
                    is_parent=True,
                )
                user.set_password("Complex.0000")
                user.save()

                group, _ = Group.objects.get_or_create(name="parent")
                user.groups.add(group)

                self.user = user

        super().save(*args, **kwargs)

        # Optionally send email (integrate email backend here)



class Student(models.Model):
    student_id = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        db_index=True,
        blank=True,
        help_text="Globally unique student identifier (e.g., STU-A7K9X2M4)"
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_profile",
        help_text="Optional: Student's user account for portal access"
    )
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Student's phone number for login/notifications"
    )
    can_login = models.BooleanField(
        default=False,
        help_text="Allow student to access student portal"
    )

    first_name = models.CharField(max_length=150, null=True, verbose_name="First Name")
    middle_name = models.CharField(max_length=150, blank=True, null=True, verbose_name="Middle Name")
    last_name = models.CharField(max_length=150, null=True, verbose_name="Last Name")

    graduation_date = models.DateField(blank=True, null=True)
    date_dismissed = models.DateField(blank=True, null=True)
    reason_left = models.ForeignKey(
        "ReasonLeft", blank=True, null=True, on_delete=models.SET_NULL
    )

    class_level = models.ForeignKey("ClassLevel", blank=True, null=True, on_delete=models.SET_NULL)
    class_of_year = models.ForeignKey("ClassYear", blank=True, null=True, on_delete=models.SET_NULL)
    classroom = models.ForeignKey("ClassRoom", blank=True, null=True, on_delete=models.SET_NULL, related_name="students")

    gender = models.CharField(max_length=10, choices=GENDER_CHOICE, blank=True, null=True)
    religion = models.CharField(max_length=50, choices=RELIGION_CHOICE, blank=True, null=True)
    region = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=255, blank=True, null=True)
    street = models.CharField(max_length=255, blank=True)
    blood_group = models.CharField(max_length=10, blank=True, null=True)

    parent_guardian = models.ForeignKey(
        "Parent", on_delete=models.SET_NULL, blank=True, null=True, related_name="children"
    )
    parent_contact = models.CharField(max_length=15, blank=True, null=True)

    date_of_birth = models.DateField(blank=True, null=True)
    admission_date = models.DateTimeField(blank=True, null=True)
    admission_number = models.CharField(max_length=50, blank=True, unique=True)
    siblings = models.ManyToManyField("self", blank=True)
    image = models.ImageField(upload_to="Student_images", blank=True)
    cache_gpa = models.DecimalField(editable=False, max_digits=5, decimal_places=2, blank=True, null=True)

    is_active = models.BooleanField(default=True, help_text="Indicates whether the student is currently active.")

    # Phase 2.2: Stream Preferences for SS1
    STREAM_CHOICES = [
        ('science', 'Science'),
        ('commercial', 'Commercial'),
        ('arts', 'Arts'),
    ]
    preferred_stream = models.CharField(
        max_length=20,
        choices=STREAM_CHOICES,
        blank=True,
        null=True,
        help_text="Student/Parent preferred stream for SS1 (Science/Commercial/Arts)"
    )
    assigned_stream = models.CharField(
        max_length=20,
        choices=STREAM_CHOICES,
        blank=True,
        null=True,
        help_text="Admin-assigned stream for SS1+ (final decision)"
    )

    class Meta:
        ordering = ["admission_number", "last_name", "first_name"]

 

    # --- PROPERTIES ---

    @property
    def full_name(self):
        parts = filter(None, [self.first_name, self.middle_name, self.last_name])
        return " ".join(part.capitalize() for part in parts)


    @property
    def total_paid(self):
        return self.receipts.filter(status='Completed').aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")

    def unpaid_terms(self):
        return self.debt_records.filter(is_reversed=False).exclude(
            amount_paid__gte=models.F("amount_added")
        )
    
    @property
    def status(self):
        if self.graduation_date:
            return "Graduated"
        if self.date_dismissed:
            return "Withdrawn"
        return "Active" if self.is_active else "Inactive"


    # --- VALIDATION ---

    def clean(self):
        from .models import Teacher  # avoid circular import

        if Teacher.objects.filter(id=self.id).exists():
            raise ValidationError("A person cannot be both a student and a teacher.")
        super().clean()

    # --- SAVE AUTOMATION ---

    def save(self, *args, **kwargs):

        if not self.student_id:
            from django_tenants.utils import schema_context
            with schema_context('public'):
                from core.models import GlobalIDRegistry
                self.student_id = GlobalIDRegistry.generate_unique_id('student')

        # Validate parent contact
        if not self.parent_contact:
            raise ValidationError("Parent contact is required.")

        # Normalize names
        self.first_name = self.first_name.lower() if self.first_name else ""
        self.middle_name = self.middle_name.lower() if self.middle_name else ""
        self.last_name = self.last_name.lower() if self.last_name else ""

        # Auto-create or assign parent
        parent, created = Parent.objects.get_or_create(
            phone_number=self.parent_contact,
            defaults={
                "first_name": self.middle_name or "Unknown",
                "last_name": self.last_name or "Unknown",
                # Use phone number in email to guarantee uniqueness
                "email": f"parent_{self.parent_contact}@hayatul.com",
                "phone_number": self.parent_contact,
            },
        )
        self.parent_guardian = parent

        # ✅ AUTO-GENERATE ADMISSION NUMBER (if blank)
        if not self.admission_number:
            year = timezone.now().year
            last_id = Student.objects.all().count() + 1
            self.admission_number = f"ADM-{year}-{last_id:04d}"

        # ✅ AUTO-SET ADMISSION DATE (if blank)
        if not self.admission_date:
            self.admission_date = timezone.now()

        # ✅ AUTOMATIC ACTIVE STATUS HANDLING
        if self.date_dismissed or self.graduation_date:
            self.is_active = False
        else:
            self.is_active = True

        super().save(*args, **kwargs)

        # Sync identity snapshot + current school to public GlobalIDRegistry
        if self.student_id:
            from django.db import connection
            from django_tenants.utils import schema_context
            _schema = connection.schema_name
            with schema_context('public'):
                from core.models import GlobalIDRegistry
                GlobalIDRegistry.sync(
                    unique_id=self.student_id,
                    first_name=self.first_name or '',
                    last_name=self.last_name or '',
                    date_of_birth=self.date_of_birth,
                    # Clear current_schema when student leaves (transferred / dismissed / graduated)
                    current_schema=_schema if self.is_active else '',
                )

        # Link siblings automatically
        existing_siblings = Student.objects.filter(
            parent_contact=self.parent_contact
        ).exclude(id=self.id)
        for sibling in existing_siblings:
            self.siblings.add(sibling)
            sibling.siblings.add(self)

    # --- FINANCE HELPERS ---

    def update_debt_for_term(self, term):
        from finance.models import DebtRecord
        if not self.debt_records.filter(term=term, is_reversed=False).exists():
            DebtRecord.objects.create(
                student=self, term=term, amount_added=term.default_term_fee
            )

    def reverse_debt_for_term(self, term):
        from finance.models import DebtRecord
        debt_record = self.debt_records.filter(term=term, is_reversed=False).first()
        if debt_record:
            debt_record.reverse()

    def carry_forward_debt_to_new_academic_year(self):
        from .models import AcademicYear, Term

        current_academic_year = AcademicYear.objects.get(current=True)
        next_year = AcademicYear.objects.filter(start_date__gt=current_academic_year.end_date).first()

        if next_year:
            first_term_of_new_year = Term.objects.filter(academic_year=next_year).order_by("start_date").first()
            if first_term_of_new_year:
                self.update_debt_for_term(first_term_of_new_year)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.student_id})"

    

class StudentsMedicalHistory(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    history = models.TextField(blank=True, null=True)
    file = models.FileField(upload_to="students_medical_files", blank=True, null=True)

    def __str__(self):
        return f"Medical History for {self.student}"

    def clean(self):
        # You can add validation if a file is uploaded and ensure it meets the constraints
        if not self.history and not self.file:
            raise ValidationError(
                "At least one of 'history' or 'file' must be provided."
            )


class StudentsPreviousAcademicHistory(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    former_school = models.CharField(max_length=255, help_text="Former school name")
    last_gpa = models.FloatField()
    notes = models.CharField(
        max_length=255,
        blank=True,
        help_text="Indicate student's academic performance according to your observation",
    )
    academic_record = models.FileField(
        upload_to="students_former_academic_files", blank=True
    )

    def __str__(self):
        return f"Previous Academic History for {self.student}"

    def clean(self):
        # You can add validation for the file field if needed
        if not self.former_school:
            raise ValidationError("Former school name is required.")


class Dormitory(models.Model):
    name = models.CharField(max_length=150)
    capacity = models.PositiveIntegerField(blank=True, null=True)
    occupied_beds = models.IntegerField(blank=True, null=True)
    captain = models.ForeignKey(Student, on_delete=models.CASCADE, blank=True)

    def __str__(self):
        return self.name

    def available_beds(self):
        total = self.capacity - self.occupied_beds
        if total <= 0:
            return 0  # Return 0 to indicate no available beds
        return total

    def save(
        self, force_insert=False, force_update=False, using=None, update_fields=None
    ):
        if (
            self.capacity is not None
            and self.occupied_beds is not None
            and self.capacity <= self.occupied_beds
        ):
            raise ValueError(
                f"All beds in {self.name} are occupied. Please add more beds or allocate to another dormitory."
            )
        super(Dormitory, self).save()


class DormitoryAllocation(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    dormitory = models.ForeignKey(Dormitory, on_delete=models.CASCADE)
    date_from = models.DateField(auto_now_add=True)
    date_till = models.DateField(blank=True, null=True)

    def __str__(self):
        return str(self.student.admission_number)

    @transaction.atomic
    def update_dormitory(self):
        """Update the capacity of the selected dormitory."""
        selected_dorm = Dormitory.objects.select_for_update().get(pk=self.dormitory.pk)
        if selected_dorm.available_beds() <= 0:
            raise ValidationError(f"{selected_dorm.name} has no available beds.")
        selected_dorm.occupied_beds += 1
        selected_dorm.save()

    def save(
        self, force_insert=False, force_update=False, using=None, update_fields=None
    ):
        self.update_dormitory()
        super(DormitoryAllocation, self).save()


class StudentFile(models.Model):
    file = models.FileField(
        upload_to="students_files/%(student_id)s/",
        validators=[
            FileExtensionValidator(allowed_extensions=["pdf", "jpg", "png", "docx"])
        ],
    )
    student = models.ForeignKey(Student, on_delete=models.CASCADE)

    def __str__(self):
        return str(self.student)

    def clean(self):
        """Override to validate file size or type if necessary."""
        if self.file.size > 10 * 1024 * 1024:  # Limit to 10MB files
            raise ValidationError("File size must be under 10MB.")
        super().clean()


class StudentHealthRecord(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    record = models.TextField()

    def __str__(self):
        return str(self.student)

    def clean(self):
        """Ensure that the record contains appropriate information."""
        if len(self.record) < 10:  # Ensure some minimal content in the record
            raise ValidationError("Health record must contain more information.")
        super().clean()


class MessageToParent(models.Model):
    """Store a message to be shown to parents for a specific amount of time."""

    message = models.TextField(help_text="Message to be shown to Parents.")
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(default=timezone.now)

    def __str__(self):
        return self.message

    def clean(self):
        """Ensure that end date is not before start date."""
        if self.end_date < self.start_date:
            raise ValidationError("End date cannot be before the start date.")
        super().clean()

    @property
    def is_active(self):
        """Check if the message is currently active."""
        today = timezone.now().date()
        return self.start_date <= today <= self.end_date


class MessageToTeacher(models.Model):
    """Stores a message to be shown to Teachers for a specific amount of time."""

    message = models.TextField(help_text="Message to be shown to Teachers.")
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(default=timezone.now)

    def __str__(self):
        return self.message

    def clean(self):
        """Ensure that end date is not before start date."""
        if self.end_date < self.start_date:
            raise ValidationError("End date cannot be before the start date.")
        super().clean()

    @property
    def is_active(self):
        """Check if the message is currently active."""
        today = timezone.now().date()
        return self.start_date <= today <= self.end_date




# ============================================================================
# STUDENT PROMOTION MODELS (Phase 2.1)
# ============================================================================

class PromotionRule(models.Model):
    """
    Configuration for how students move from one Grade Level to another.
    Now leverages 'sequence_order' to strictly validate progression.
    """

    PROMOTION_METHODS = [
        ('annual_average', 'Annual Average (Nigeria Standard)'),
        ('gpa', 'GPA (International)'),
        ('cumulative', 'Cumulative Average (All Years)'),
    ]

    # CHANGED: Now links to GradeLevel (e.g., JSS 1) instead of ClassLevel (e.g., JSS 1A)
    from_grade = models.ForeignKey(
        'GradeLevel',
        on_delete=models.CASCADE,
        related_name='promotion_rules_from',
        help_text="The current grade level of the student"
    )
    
    to_grade = models.ForeignKey(
        'GradeLevel',
        on_delete=models.CASCADE,
        related_name='promotion_rules_to',
        help_text="The destination grade level (or same if repeating)"
    )

    # ===== PROMOTION LOGIC =====
    promotion_method = models.CharField(
        max_length=20,
        choices=PROMOTION_METHODS,
        default='annual_average',
        help_text="Method used to calculate promotion eligibility"
    )

    # Nigeria Standard: Average of Term 1, 2, 3
    min_average_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=50.00,
        help_text="Minimum Annual Average (0-100%) required to promote."
    )

    # Specific Subject Requirements (Critical for JSS -> SSS)
    must_pass_english = models.BooleanField(
        default=True, 
        help_text="Student must pass English Language?"
    )
    must_pass_math = models.BooleanField(
        default=True, 
        help_text="Student must pass Mathematics?"
    )
    
    # Minimum number of subjects passed (e.g., Must pass 6 subjects total)
    min_subjects_passed = models.PositiveIntegerField(
        default=5,
        help_text="Minimum count of subjects the student must pass."
    )

    # ===== VALIDATION & META =====
    description = models.CharField(
        max_length=255, 
        blank=True, 
        help_text="Auto-generated description of this rule"
    )
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    class Meta:
        unique_together = ['from_grade', 'to_grade']
        ordering = ['from_grade__sequence_order']
        verbose_name = "Promotion Rule"

    def __str__(self):
        return f"{self.from_grade} → {self.to_grade}"

    def clean(self):
        """
        Uses the new 'sequence_order' to ensure promotion logic is sound.
        """
        # 1. Prevent Demotion (Moving backwards)
        if self.to_grade.sequence_order < self.from_grade.sequence_order:
            raise ValidationError({
                'to_grade': _(
                    f"Cannot define a promotion rule that demotes students from "
                    f"{self.from_grade} (Order {self.from_grade.sequence_order}) to "
                    f"{self.to_grade} (Order {self.to_grade.sequence_order})."
                )
            })

        # 2. Handle "Double Promotion" (Skipping a class)
        # If moving more than 1 step up (e.g., JSS1 to JSS3), logic is valid but unusual.
        step_difference = self.to_grade.sequence_order - self.from_grade.sequence_order
        
        if step_difference > 1:
            # We allow it, but maybe we want to tag it in the description
            pass 

        # 3. Prevent mixing Sections illegitimately (Optional)
        # e.g., Preventing Primary 6 directly to SS 1 (skipping JSS) if that's a business rule.

    def save(self, *args, **kwargs):
        # Auto-generate a human-readable description
        direction = "Repeat" if self.from_grade == self.to_grade else "Promote to"
        criteria = f"Avg ≥ {self.min_average_score}%"
        
        if self.must_pass_english:
            criteria += ", Eng"
        if self.must_pass_math:
            criteria += ", Math"
            
        self.description = f"{direction} {self.to_grade}: Requires {criteria}"
        super().save(*args, **kwargs)

    @property
    def is_repeat_year(self):
        """Returns True if this rule is for repeating the same class."""
        return self.from_grade == self.to_grade

    @property
    def is_double_promotion(self):
        """Returns True if this rule skips a class."""
        return (self.to_grade.sequence_order - self.from_grade.sequence_order) > 1


class StudentPromotion(models.Model):
    """
    Records the historical movement of a student from one academic level to another.
    Uses GradeLevel.sequence_order to validate that students are moving forward correctly.
    """

    PROMOTION_STATUS_CHOICES = [
        ('PROMOTED', 'Promoted'),
        ('REPEATED', 'Repeated'),
        ('DOUBLE_PROMOTION', 'Double Promotion'),
        ('PROMOTED_ON_TRIAL', 'Promoted on Trial'),
        ('GRADUATED', 'Graduated'),
        ('WITHDRAWN', 'Withdrawn'),
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='promotion_history'
    )
    
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        help_text="The academic year of this result (e.g., 2023/2024)"
    )

    # ===== LOCATION: FROM =====
    from_class = models.ForeignKey(
        ClassRoom,
        on_delete=models.SET_NULL,
        null=True,
        related_name='promotions_out',
        help_text="The classroom the student is leaving (e.g., JSS 1 Gold)"
    )
    
    # We auto-populate this in save() so you don't have to select it manually
    from_grade = models.ForeignKey(
        GradeLevel,
        on_delete=models.CASCADE,
        related_name='grade_promotions_out',
        null=True,
        blank=True,
        help_text="Auto-populated: The grade level being completed (e.g., JSS 1)"
    )

    # ===== LOCATION: TO =====
    to_class = models.ForeignKey(
        ClassRoom,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='promotions_in',
        help_text="The destination classroom. Null if Graduated or Withdrawn."
    )
    
    to_grade = models.ForeignKey(
        GradeLevel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='grade_promotions_in',
        help_text="Auto-populated: The destination grade level."
    )

    # ===== DECISION METADATA =====
    status = models.CharField(
        max_length=20,
        choices=PROMOTION_STATUS_CHOICES,
        default='PROMOTED'
    )
    
    annual_average = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="The student's final average score used for this decision."
    )
    
    promotion_date = models.DateField(default=timezone.now)
    reason = models.TextField(blank=True, help_text="Optional remarks (e.g., 'Failed Math twice')")

    class Meta:
        ordering = ['-promotion_date']
        indexes = [
            models.Index(fields=['student', 'academic_year']),
            models.Index(fields=['status']),
        ]
        verbose_name = "Promotion Record"

    def __str__(self):
        return f"{self.student} ({self.academic_year}): {self.get_status_display()}"

    def clean(self):
        """
        Validates the promotion logic using sequence_order.
        """
        # Ensure grades are populated for validation if classes are selected
        if self.from_class and not self.from_grade:
             self.from_grade = self.from_class.grade_level.grade_level # Accessing GradeLevel model from ClassRoom
        
        if self.to_class and not self.to_grade:
             self.to_grade = self.to_class.grade_level.grade_level

        # 1. Logic for PROMOTED students
        if self.status in ['PROMOTED', 'DOUBLE_PROMOTION', 'PROMOTED_ON_TRIAL']:
            if not self.to_class:
                raise ValidationError("A promoted student must have a destination class.")
            
            # Ensure they are moving FORWARD in sequence (JSS 1 -> JSS 2)
            if self.to_grade.sequence_order <= self.from_grade.sequence_order:
                raise ValidationError(
                    f"Invalid Promotion: Cannot promote from {self.from_grade} (Order {self.from_grade.sequence_order}) "
                    f"to {self.to_grade} (Order {self.to_grade.sequence_order}). Sequence must increase."
                )

        # 2. Logic for REPEATED students
        if self.status == 'REPEATED':
            if self.to_grade and self.to_grade != self.from_grade:
                raise ValidationError(
                    f"Invalid Repeat: Destination grade ({self.to_grade}) must match current grade ({self.from_grade})."
                )

        # 3. Logic for GRADUATED/WITHDRAWN
        if self.status in ['GRADUATED', 'WITHDRAWN']:
            if self.to_class or self.to_grade:
                raise ValidationError(f"Students marked as {self.status} should not have a destination class.")

    def save(self, *args, **kwargs):
        """
        Auto-populates GradeLevels from the selected ClassRooms.
        """
        # Auto-fill 'from_grade' based on 'from_class'
        # Note: In your original model, ClassRoom.name links to ClassLevel. 
        # So the path is: ClassRoom -> name (ClassLevel) -> grade_level (GradeLevel)
        if self.from_class:
            self.from_grade = self.from_class.name.grade_level

        # Auto-fill 'to_grade' based on 'to_class'
        if self.to_class:
            self.to_grade = self.to_class.name.grade_level
        
        # Clear destination fields if Graduated/Withdrawn
        if self.status in ['GRADUATED', 'WITHDRAWN']:
            self.to_grade = None
            self.to_class = None

        super().save(*args, **kwargs)


class StudentClassEnrollment(models.Model):
    """
    Tracks student classroom enrollment per academic year.

    Phase 2.2: Class Advancement Automation

    This model maintains a historical record of which classroom each student
    was enrolled in for each academic year. This enables:
    - Academic year rollover tracking
    - Historical enrollment reports
    - Audit trail for class movements
    - Support for students repeating years
    - Updates classroom capacity when students are added or removed
    """
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='student_classes',
        blank=True,
        null=True,
    )
    classroom = models.ForeignKey(
        ClassRoom,
        on_delete=models.CASCADE,
        related_name='class_students'
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE
    )
    enrollment_date = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this enrollment is currently active"
    )
    notes = models.TextField(
        blank=True,
        help_text="Additional notes about this enrollment (e.g., 'Repeated year', 'Transferred mid-year')"
    )

    class Meta:
        ordering = ['-academic_year__start_date', 'student__admission_number']
        unique_together = ['student', 'academic_year']
        verbose_name = "Student Class Enrollment"
        verbose_name_plural = "Student Class Enrollments"

    def __str__(self):
        return f"{self.student.full_name} - {self.classroom} ({self.academic_year})"

    @property
    def is_current_class(self):
        return self.academic_year.is_current_session if hasattr(self.academic_year, 'is_current_session') else self.is_active

    def clean(self):
        """
        Perform custom validations:
        - Ensure the classroom matches the student's class level.
        - Check if the classroom has available seats.
        - Prevent duplicate assignments for the same student and academic year.
        """
        # Validate that the classroom matches the student's class level
        if self.classroom.name != self.student.class_level:
            raise ValidationError(
                f"The classroom '{self.classroom.name}' does not match the student's class level '{self.student.class_level}'."
            )

        # Validate that the classroom has available seats
        if not self.pk and self.classroom.occupied_sits >= self.classroom.capacity:
            raise ValidationError(
                f"The classroom '{self.classroom}' has reached its maximum capacity."
            )

        # Check if student is already enrolled in a different classroom for same year
        if self.is_active:
            existing = StudentClassEnrollment.objects.filter(
                student=self.student,
                academic_year=self.academic_year,
                is_active=True
            ).exclude(pk=self.pk)

            if existing.exists():
                raise ValidationError(
                    f"Student {self.student} is already enrolled in {existing.first().classroom} "
                    f"for {self.academic_year}. Deactivate that enrollment first."
                )

    def update_class_table(self, increment=True):
        """
        Updates the `occupied_sits` count in the classroom manually within a transaction.
        """
        # Use a transaction to ensure consistency
        with transaction.atomic():
            selected_class = ClassRoom.objects.select_for_update().get(
                pk=self.classroom.pk
            )

            if increment:
                # Check capacity before incrementing
                if selected_class.occupied_sits >= selected_class.capacity:
                    raise ValidationError(
                        "This class has reached its maximum capacity."
                    )
                selected_class.occupied_sits += 1
            else:
                # Ensure occupied_sits doesn't go below zero
                if selected_class.occupied_sits <= 0:
                    raise ValidationError("Cannot have negative occupied sits.")
                selected_class.occupied_sits -= 1

            # Save the updated classroom instance
            selected_class.save()

    def save(self, *args, **kwargs):
        """
        Override the save method to:
        - Validate before saving.
        - Update the classroom's capacity on creation.
        - Sync Student.classroom field if this is the current academic year.
        """
        if not self.pk:  # Only increment capacity on creation
            self.update_class_table(increment=True)

        super().save(*args, **kwargs)

        # Sync Student.classroom field if this enrollment is for the current/active academic year
        if self.student and self.academic_year:
            if self.academic_year.active_year:
                # Update the student's classroom field to match this enrollment
                if self.student.classroom != self.classroom:
                    self.student.classroom = self.classroom
                    # Use update to avoid triggering Student.save() logic
                    Student.objects.filter(pk=self.student.pk).update(classroom=self.classroom)

    def delete(self, *args, **kwargs):
        """
        Override the delete method to:
        - Decrement the classroom's capacity when a record is deleted.
        - Clear Student.classroom field if this was the current academic year enrollment.
        """
        # Clear Student.classroom if this enrollment was for the current academic year
        if self.student and self.academic_year and self.academic_year.active_year:
            if self.student.classroom == self.classroom:
                Student.objects.filter(pk=self.student.pk).update(classroom=None)

        self.update_class_table(increment=False)
        super().delete(*args, **kwargs)

    def delete_queryset(self, request, queryset):
        """
        Override the bulk delete behavior to update `occupied_sits` correctly.
        """
        with transaction.atomic():  # Ensure the operation is transactional
            for instance in queryset:
                instance.update_class_table(increment=False)  # Decrement capacity
            queryset.delete()  # Perform the actual deletion


# ============================================================================
# ADMISSION SYSTEM MODELS
# ============================================================================

class AdmissionStatus(models.TextChoices):
    """12-state admission workflow"""
    DRAFT = 'draft', _('Draft')
    SUBMITTED = 'submitted', _('Submitted')
    UNDER_REVIEW = 'under_review', _('Under Review')
    DOCUMENTS_PENDING = 'documents_pending', _('Documents Pending')
    EXAM_SCHEDULED = 'exam_scheduled', _('Exam Scheduled')
    EXAM_COMPLETED = 'exam_completed', _('Exam Completed')
    INTERVIEW_SCHEDULED = 'interview_scheduled', _('Interview Scheduled')
    APPROVED = 'approved', _('Approved')
    REJECTED = 'rejected', _('Rejected')
    ACCEPTED = 'accepted', _('Accepted')  # Parent accepted the offer
    ENROLLED = 'enrolled', _('Enrolled')  # Converted to Student
    WITHDRAWN = 'withdrawn', _('Withdrawn')


class AssessmentType(models.TextChoices):
    """Types of admission assessments"""
    ENTRANCE_EXAM = 'entrance_exam', _('Entrance Examination')
    INTERVIEW = 'interview', _('Interview')
    APTITUDE_TEST = 'aptitude_test', _('Aptitude Test')
    SCREENING = 'screening', _('Screening Test')
    ORAL_TEST = 'oral_test', _('Oral Test')
    PRACTICAL = 'practical', _('Practical Assessment')
    PSYCHOMETRIC = 'psychometric', _('Psychometric Test')
    PORTFOLIO_REVIEW = 'portfolio_review', _('Portfolio Review')


class AdmissionSession(models.Model):
    """
    Configure each admission cycle independently.

    Each session can have completely different:
    - Application dates
    - Acceptance fee requirements
    - Acceptance deadlines
    - Email settings
    - Custom approval messages
    """
    academic_year = models.OneToOneField(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name='admission_session',
        help_text="Academic year this admission session is for"
    )
    name = models.CharField(
        max_length=100,
        help_text="Example: '2025/2026 New Students Admission'"
    )
    start_date = models.DateField(help_text="When applications open")
    end_date = models.DateField(help_text="When applications close")

    # Acceptance fee configuration (per user feedback)
    require_acceptance_fee = models.BooleanField(
        default=True,
        help_text="Whether this session requires acceptance fees"
    )
    acceptance_fee_deadline_days = models.PositiveIntegerField(
        default=14,
        help_text="Days after approval to pay acceptance fee and accept offer"
    )

    # Application configuration
    application_number_prefix = models.CharField(
        max_length=10,
        default='ADM',
        help_text="Prefix for application numbers (e.g., 'ADM' -> ADM/2025/001)"
    )
    allow_public_applications = models.BooleanField(
        default=True,
        help_text="Allow external applications without login"
    )

    # Email settings
    send_confirmation_emails = models.BooleanField(
        default=True,
        help_text="Send email confirmations to applicants"
    )

    # Custom messages
    application_instructions = models.TextField(
        blank=True,
        help_text="Instructions shown to parents at the start of application"
    )
    approval_message = models.TextField(
        blank=True,
        help_text="Custom message sent when application is approved"
    )
    rejection_message_template = models.TextField(
        blank=True,
        help_text="Template for rejection messages"
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Only one session should be active at a time"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date']
        verbose_name = "Admission Session"
        verbose_name_plural = "Admission Sessions"

    def __str__(self):
        return f"{self.name} ({self.start_date.year})"

    def clean(self):
        """Validate admission session"""
        if self.end_date < self.start_date:
            raise ValidationError("End date must be after start date")

        if self.acceptance_fee_deadline_days < 1:
            raise ValidationError("Acceptance deadline must be at least 1 day")

    @property
    def is_open(self):
        """Check if applications are currently being accepted"""
        today = timezone.now().date()
        return self.is_active and self.start_date <= today <= self.end_date

    @property
    def total_applications(self):
        """Get total applications for this session"""
        return self.applications.count()

    @property
    def applications_by_status(self):
        """Get count of applications by status"""
        from django.db.models import Count
        return self.applications.values('status').annotate(count=Count('id'))


class AdmissionFeeStructure(models.Model):
    """
    Define fees per class within a session.

    Each class can have different:
    - Application fees
    - Entrance exam requirements and fees
    - Acceptance fee requirements
    - Interview requirements
    - Maximum application capacity
    """
    admission_session = models.ForeignKey(
        AdmissionSession,
        on_delete=models.CASCADE,
        related_name='fee_structures'
    )
    grade_levels = models.ManyToManyField(
        GradeLevel,
        blank=True,
        related_name='admission_fee_structures',
        help_text="Grade levels this fee applies to (e.g., JSS1, SS1)"
    )

    # Application fee
    application_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Fee to submit application"
    )
    application_fee_required = models.BooleanField(
        default=True,
        help_text="Must pay application fee to submit"
    )

    # Entrance exam
    entrance_exam_required = models.BooleanField(
        default=False,
        help_text="Does this class require entrance exam?"
    )
    entrance_exam_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Fee to take entrance exam"
    )
    entrance_exam_pass_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum score to pass entrance exam (percentage)"
    )

    # Interview
    interview_required = models.BooleanField(
        default=False,
        help_text="Does this class require interview?"
    )

    # Acceptance fee (per user feedback - configurable)
    acceptance_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Fee to accept admission offer"
    )
    acceptance_fee_required = models.BooleanField(
        default=True,
        help_text="Must pay acceptance fee to accept offer"
    )
    acceptance_fee_is_part_of_tuition = models.BooleanField(
        default=True,
        help_text="If True, acceptance fee is deducted from first term tuition"
    )

    # Capacity
    max_applications = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum number of applications for this class (optional)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['admission_session']
        verbose_name = "Admission Fee Structure"
        verbose_name_plural = "Admission Fee Structures"

    def __str__(self):
        grade_names = ", ".join([grade.name for grade in self.grade_levels.all()])
        return f"{grade_names} - {self.admission_session.name}"

    def clean(self):
        """Validate fee structure"""

        if self.entrance_exam_required and not self.entrance_exam_pass_score:
            raise ValidationError("Pass score is required when entrance exam is required")


    @property
    def current_applications_count(self):
        """Count applications whose applying_for_class.grade_level is in this fee's grade_levels,
        or match class_room if grade_levels empty (backwards compatibility)."""
        qs = self.admission_session.applications
        if self.grade_levels.exists():
            return qs.filter(applying_for_class__grade_level__in=self.grade_levels.all()).count()
        return 0

    @property
    def has_capacity(self):
        """Check if class still has application capacity"""
        if not self.max_applications:
            return True
        return self.current_applications_count < self.max_applications


class AdmissionApplication(models.Model):
    """
    Track individual student applications.

    Nigerian-specific features:
    - State of origin and LGA
    - Multiple parent contacts
    - Blood group
    - Previous school info
    - Alternative contact (common in Nigeria)
    """
    # Application metadata
    application_number = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        help_text="Auto-generated (e.g., ADM/2025/001)"
    )
    status = models.CharField(
        max_length=30,
        choices=AdmissionStatus.choices,
        default=AdmissionStatus.DRAFT
    )
    admission_session = models.ForeignKey(
        AdmissionSession,
        on_delete=models.CASCADE,
        related_name='applications'
    )
    applying_for_class = models.ForeignKey(
        GradeLevel,
        on_delete=models.CASCADE,
        help_text="Class student is applying for"
    )

    # Student information
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICE)
    date_of_birth = models.DateField()

    # Nigerian-specific fields
    state_of_origin = models.CharField(
        max_length=100,
        help_text="Nigerian state of origin"
    )
    lga = models.CharField(
        max_length=100,
        help_text="Local Government Area"
    )
    religion = models.CharField(
        max_length=50,
        choices=RELIGION_CHOICE,
        blank=True,
        null=True
    )
    blood_group = models.CharField(
        max_length=5,
        blank=True,
        help_text="e.g., O+, A-, AB+"
    )

    # Contact information
    address = models.TextField(help_text="Residential address")
    city = models.CharField(max_length=100)

    # Parent/Guardian information
    parent_first_name = models.CharField(max_length=100)
    parent_last_name = models.CharField(max_length=100)
    parent_email = models.EmailField()
    parent_phone = models.CharField(max_length=15)
    parent_occupation = models.CharField(max_length=100, blank=True)
    parent_relationship = models.CharField(
        max_length=50,
        choices=[
            ('father', 'Father'),
            ('mother', 'Mother'),
            ('guardian', 'Guardian'),
            ('other', 'Other')
        ],
        default='father'
    )

    # Alternative contact (common in Nigerian schools)
    alt_contact_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Alternative emergency contact"
    )
    alt_contact_phone = models.CharField(max_length=15, blank=True)
    alt_contact_relationship = models.CharField(max_length=100, blank=True)

    # Previous school information
    previous_school = models.CharField(
        max_length=255,
        blank=True,
        help_text="Name of previous school (if any)"
    )
    previous_class = models.CharField(
        max_length=100,
        blank=True,
        help_text="Last class attended"
    )

    # Medical information
    medical_conditions = models.TextField(
        blank=True,
        help_text="Any medical conditions or allergies"
    )
    special_needs = models.TextField(
        blank=True,
        help_text="Any special educational needs"
    )

    # Payment tracking (3 separate fees)
    application_fee_paid = models.BooleanField(default=False)
    application_fee_receipt = models.ForeignKey(
        'finance.Receipt',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='application_fees'
    )
    application_fee_payment_date = models.DateTimeField(null=True, blank=True)

    exam_fee_paid = models.BooleanField(default=False)
    exam_fee_receipt = models.ForeignKey(
        'finance.Receipt',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exam_fees'
    )
    exam_fee_payment_date = models.DateTimeField(null=True, blank=True)

    acceptance_fee_paid = models.BooleanField(default=False)
    acceptance_fee_receipt = models.ForeignKey(
        'finance.Receipt',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='acceptance_fees'
    )
    acceptance_fee_payment_date = models.DateTimeField(null=True, blank=True)

    # Acceptance deadline (auto-calculated on approval)
    acceptance_deadline = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Deadline to accept offer (calculated from approval date)"
    )

    # Admin notes and review
    admin_notes = models.TextField(
        blank=True,
        help_text="Internal notes from admin review"
    )
    rejection_reason = models.TextField(
        blank=True,
        help_text="Reason for rejection (if applicable)"
    )

    # Tracking
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_applications'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When parent accepted the offer"
    )

    # Enrollment link (when converted to student)
    enrolled_student = models.OneToOneField(
        Student,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='admission_application'
    )
    enrolled_at = models.DateTimeField(null=True, blank=True)

    # External portal token (for tracking application without login)
    tracking_token = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        help_text="Secure token for external application tracking"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Admission Application"
        verbose_name_plural = "Admission Applications"
        indexes = [
            models.Index(fields=['application_number']),
            models.Index(fields=['status']),
            models.Index(fields=['tracking_token']),
            models.Index(fields=['parent_email']),
        ]

    def __str__(self):
        return f"{self.application_number} - {self.first_name} {self.last_name}"

    def save(self, *args, **kwargs):
        """Auto-generate application number and tracking token"""
        if not self.application_number:
            # Get prefix from session
            prefix = self.admission_session.application_number_prefix
            year = self.admission_session.academic_year.year

            # Get last application number for this session
            last_app = AdmissionApplication.objects.filter(
                admission_session=self.admission_session
            ).order_by('-id').first()

            if last_app and last_app.application_number:
                # Extract number from last application
                try:
                    last_num = int(last_app.application_number.split('/')[-1])
                    next_num = last_num + 1
                except (ValueError, IndexError):
                    next_num = 1
            else:
                next_num = 1

            self.application_number = f"{prefix}/{year}/{next_num:03d}"

        if not self.tracking_token:
            self.tracking_token = get_random_string(64)

        # Update timestamps based on status
        if self.status == AdmissionStatus.SUBMITTED and not self.submitted_at:
            self.submitted_at = timezone.now()

        if self.status == AdmissionStatus.APPROVED and not self.approved_at:
            self.approved_at = timezone.now()
            # Calculate acceptance deadline
            if self.admission_session.require_acceptance_fee:
                deadline_days = self.admission_session.acceptance_fee_deadline_days
                self.acceptance_deadline = timezone.now() + timezone.timedelta(days=deadline_days)

        if self.status == AdmissionStatus.ACCEPTED and not self.accepted_at:
            self.accepted_at = timezone.now()

        if self.status == AdmissionStatus.ENROLLED and not self.enrolled_at:
            self.enrolled_at = timezone.now()

        super().save(*args, **kwargs)

    def clean(self):
        """Validate application"""
        fee_structure = AdmissionFeeStructure.objects.filter(
            admission_session=self.admission_session,
            grade_levels__in=[self.applying_for_class]
        ).first()

        if fee_structure and self.date_of_birth:
            age = (timezone.now().date() - self.date_of_birth).days // 365

            if fee_structure.minimum_age and age < fee_structure.minimum_age:
                raise ValidationError(
                    f"Applicant is too young for {self.applying_for_class}. "
                    f"Minimum age is {fee_structure.minimum_age} years."
                )

            if fee_structure.maximum_age and age > fee_structure.maximum_age:
                raise ValidationError(
                    f"Applicant is too old for {self.applying_for_class}. "
                    f"Maximum age is {fee_structure.maximum_age} years."
                )

    @property
    def full_name(self):
        """Get student's full name"""
        parts = filter(None, [self.first_name, self.middle_name, self.last_name])
        return " ".join(parts)

    @property
    def age(self):
        """Calculate applicant's age"""
        if not self.date_of_birth:
            return None
        return (timezone.now().date() - self.date_of_birth).days // 365

    @property
    def all_fees_paid(self):
        """Check if all required fees are paid"""
        fee_structure = AdmissionFeeStructure.objects.filter(
            admission_session=self.admission_session,
            grade_levels__in=[self.applying_for_class]
        ).first()

        if not fee_structure:
            return True

        # Check application fee
        if fee_structure.application_fee_required and not self.application_fee_paid:
            return False

        # Check exam fee (if exam required)
        if fee_structure.entrance_exam_required and not self.exam_fee_paid:
            return False

        # Check acceptance fee (if required and approved)
        if (self.status == AdmissionStatus.APPROVED and
            fee_structure.acceptance_fee_required and
            not self.acceptance_fee_paid):
            return False

        return True

    @property
    def can_submit(self):
        """Check if application can be submitted"""
        fee_structure = AdmissionFeeStructure.objects.filter(
            admission_session=self.admission_session,
            grade_levels__in=[self.applying_for_class]
        ).first()

        if not fee_structure:
            return False

        # Must pay application fee if required
        if fee_structure.application_fee_required and not self.application_fee_paid:
            return False

        return True

    @property
    def can_accept_offer(self):
        """Check if parent can accept the offer"""
        if self.status != AdmissionStatus.APPROVED:
            return False

        fee_structure = AdmissionFeeStructure.objects.filter(
            admission_session=self.admission_session,
            grade_levels__in=[self.applying_for_class]
        ).first()

        if not fee_structure:
            return False

        # Must pay acceptance fee if required
        if fee_structure.acceptance_fee_required and not self.acceptance_fee_paid:
            return False

        # Check if deadline has passed
        if self.acceptance_deadline and timezone.now() > self.acceptance_deadline:
            return False

        return True



class AdmissionDocument(models.Model):
    """
    Documents uploaded for admission application.

    Common documents in Nigerian schools:
    - Birth certificate
    - Passport photograph
    - Previous school results
    - Transfer certificate (if applicable)
    - Medical records
    """
    DOCUMENT_TYPES = [
        ('birth_certificate', 'Birth Certificate'),
        ('passport_photo', 'Passport Photograph'),
        ('previous_results', 'Previous School Results'),
        ('transfer_certificate', 'Transfer Certificate'),
        ('medical_records', 'Medical Records'),
        ('immunization_card', 'Immunization Card'),
        ('other', 'Other Document'),
    ]

    application = models.ForeignKey(
        AdmissionApplication,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPES)
    file = models.FileField(
        upload_to='admission_documents/%Y/%m/',
        validators=[
            FileExtensionValidator(
                allowed_extensions=['pdf', 'jpg', 'jpeg', 'png']
            )
        ]
    )
    description = models.CharField(max_length=255, blank=True)

    # Verification
    verified = models.BooleanField(
        default=False,
        help_text="Has admin verified this document?"
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_documents'
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_notes = models.TextField(blank=True)

    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = "Admission Document"
        verbose_name_plural = "Admission Documents"

    def __str__(self):
        return f"{self.application.application_number} - {self.get_document_type_display()}"

    def clean(self):
        """Validate file size"""
        if self.file.size > 5 * 1024 * 1024:  # 5MB limit
            raise ValidationError("File size must be under 5MB")


class AdmissionAssessment(models.Model):
    """
    Individual assessment instance (exam, interview, etc.)

    Supports 8 different assessment types with:
    - Scheduling and venue tracking
    - Assessor assignment
    - Detailed scoring with criteria breakdown
    - Rich feedback and recommendations
    """
    ASSESSMENT_STATUS = [
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('no_show', 'No Show'),
        ('cancelled', 'Cancelled'),
    ]

    RECOMMENDATION_CHOICES = [
        ('highly_recommended', 'Highly Recommended'),
        ('recommended', 'Recommended'),
        ('conditional', 'Conditional'),
        ('not_recommended', 'Not Recommended'),
    ]

    application = models.ForeignKey(
        AdmissionApplication,
        on_delete=models.CASCADE,
        related_name='assessments'
    )
    assessment_type = models.CharField(
        max_length=30,
        choices=AssessmentType.choices
    )

    # Scheduling
    scheduled_date = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(
        default=60,
        help_text="Duration in minutes"
    )
    venue = models.CharField(max_length=255, blank=True)
    assessor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='conducted_assessments',
        help_text="Staff member conducting assessment"
    )

    # Status
    status = models.CharField(
        max_length=20,
        choices=ASSESSMENT_STATUS,
        default='scheduled'
    )

    # Scoring
    overall_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Overall score achieved"
    )
    max_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100,
        help_text="Maximum possible score"
    )
    pass_mark = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=50,
        help_text="Minimum score to pass"
    )
    passed = models.BooleanField(
        default=False,
        help_text="Whether student passed this assessment"
    )

    # Feedback
    assessor_notes = models.TextField(
        blank=True,
        help_text="General notes from assessor"
    )
    strengths = models.TextField(
        blank=True,
        help_text="Student's strengths observed"
    )
    areas_for_improvement = models.TextField(
        blank=True,
        help_text="Areas needing improvement"
    )
    recommendation = models.CharField(
        max_length=20,
        choices=RECOMMENDATION_CHOICES,
        blank=True,
        help_text="Overall recommendation"
    )

    # Instructions (from template or custom)
    instructions = models.TextField(
        blank=True,
        help_text="Instructions for this assessment"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['scheduled_date']
        verbose_name = "Admission Assessment"
        verbose_name_plural = "Admission Assessments"
        indexes = [
            models.Index(fields=['scheduled_date']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.application.application_number} - {self.get_assessment_type_display()}"

    def save(self, *args, **kwargs):
        """Auto-calculate pass/fail and update timestamps"""
        if self.overall_score is not None and self.pass_mark is not None:
            self.passed = self.overall_score >= self.pass_mark

        if self.status == 'completed' and not self.completed_at:
            self.completed_at = timezone.now()

        super().save(*args, **kwargs)

    @property
    def percentage_score(self):
        """Get score as percentage"""
        if self.overall_score is None or self.max_score is None:
            return None
        return (self.overall_score / self.max_score) * 100

    @property
    def is_upcoming(self):
        """Check if assessment is upcoming"""
        return self.status == 'scheduled' and self.scheduled_date > timezone.now()

    def calculate_overall_score(self):
        """Calculate overall score from criteria (weighted if applicable)"""
        criteria = self.criteria.all()
        if not criteria:
            return None

        total_weighted_score = sum(c.weighted_score for c in criteria)
        total_possible = sum(float(c.max_score) * float(c.weight) for c in criteria)

        if total_possible == 0:
            return None

        # Normalize to max_score
        self.overall_score = (total_weighted_score / total_possible) * float(self.max_score)
        self.save()
        return self.overall_score


class AssessmentCriterion(models.Model):
    """
    Individual scoring component with weighted scoring.

    Example for entrance exam:
    - Mathematics: 50 points, weight 1.0
    - English: 50 points, weight 1.0
    - Science: 40 points, weight 0.8

    Example for interview:
    - Communication: 10 points, weight 1.0
    - Confidence: 10 points, weight 1.0
    - Subject Knowledge: 15 points, weight 1.5 (weighted higher!)
    """
    assessment = models.ForeignKey(
        AdmissionAssessment,
        on_delete=models.CASCADE,
        related_name='criteria'
    )
    name = models.CharField(
        max_length=255,
        help_text="e.g., 'Mathematics', 'Communication Skills'"
    )
    max_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Maximum score for this criterion"
    )
    achieved_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Score achieved by student"
    )
    weight = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1.0,
        help_text="Weight/importance multiplier (default 1.0)"
    )
    comments = models.TextField(
        blank=True,
        help_text="Specific feedback for this criterion"
    )

    order = models.PositiveIntegerField(
        default=0,
        help_text="Display order"
    )

    class Meta:
        ordering = ['order', 'name']
        verbose_name = "Assessment Criterion"
        verbose_name_plural = "Assessment Criteria"

    def __str__(self):
        return f"{self.name} ({self.achieved_score}/{self.max_score})"

    @property
    def weighted_score(self):
        """Calculate weighted score"""
        return float(self.achieved_score) * float(self.weight)

    @property
    def percentage(self):
        """Get score as percentage"""
        if self.max_score == 0:
            return 0
        return (float(self.achieved_score) / float(self.max_score)) * 100


class AssessmentTemplate(models.Model):
    """
    Reusable assessment blueprint for consistency.

    Templates ensure all students are assessed with the same criteria
    across different admission cycles.

    Example: "JSS 1 Entrance Exam Template"
    - Mathematics (50 points)
    - English (50 points)
    - Science (40 points)
    - Pass mark: 70%
    """
    name = models.CharField(
        max_length=255,
        help_text="e.g., 'JSS 1 Entrance Exam', 'Primary Interview'"
    )
    assessment_type = models.CharField(
        max_length=30,
        choices=AssessmentType.choices
    )
    description = models.TextField(blank=True)

    # Applicable classes
    applicable_classes = models.ManyToManyField(
        ClassLevel,
        blank=True,
        help_text="Which class levels can use this template"
    )

    # Default settings
    default_duration_minutes = models.PositiveIntegerField(
        default=60,
        help_text="Default duration in minutes"
    )
    default_max_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100,
        help_text="Default maximum score"
    )
    default_pass_mark = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=50,
        help_text="Default pass mark"
    )
    default_instructions = models.TextField(
        blank=True,
        help_text="Default instructions for this assessment"
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Only active templates are available for use"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['assessment_type', 'name']
        verbose_name = "Assessment Template"
        verbose_name_plural = "Assessment Templates"

    def __str__(self):
        return f"{self.name} ({self.get_assessment_type_display()})"

    def create_assessment_from_template(self, application, scheduled_date, venue='', assessor=None):
        """
        Create an assessment instance from this template.

        Automatically copies all criteria from template to the new assessment.
        """
        # Create assessment
        assessment = AdmissionAssessment.objects.create(
            application=application,
            assessment_type=self.assessment_type,
            scheduled_date=scheduled_date,
            duration_minutes=self.default_duration_minutes,
            venue=venue,
            assessor=assessor,
            max_score=self.default_max_score,
            pass_mark=self.default_pass_mark,
            instructions=self.default_instructions,
        )

        # Copy criteria from template
        for template_criterion in self.template_criteria.all():
            AssessmentCriterion.objects.create(
                assessment=assessment,
                name=template_criterion.name,
                max_score=template_criterion.max_score,
                weight=template_criterion.weight,
                order=template_criterion.order,
            )

        return assessment


class AssessmentTemplateCriterion(models.Model):
    """
    Predefined criteria for assessment templates.

    Ensures consistency across admission cycles.
    """
    template = models.ForeignKey(
        AssessmentTemplate,
        on_delete=models.CASCADE,
        related_name='template_criteria'
    )
    name = models.CharField(
        max_length=255,
        help_text="e.g., 'Mathematics', 'Communication Skills'"
    )
    max_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Maximum score for this criterion"
    )
    weight = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1.0,
        help_text="Weight/importance multiplier"
    )
    description = models.TextField(
        blank=True,
        help_text="What this criterion assesses"
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Display order"
    )

    class Meta:
        ordering = ['order', 'name']
        verbose_name = "Assessment Template Criterion"
        verbose_name_plural = "Assessment Template Criteria"

    def __str__(self):
        return f"{self.template.name} - {self.name}"
