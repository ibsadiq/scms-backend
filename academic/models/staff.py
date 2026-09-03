from django.db import models
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.crypto import get_random_string

from administration.models import AcademicYear, Term
from .structure import Department, ClassRoom


class Staff(models.Model):
    """General school employee identity shared by teaching and non-teaching staff."""

    class Role(models.TextChoices):
        TEACHER = "TEACHER", "Teacher"
        ADMINISTRATOR = "ADMINISTRATOR", "Administrator"
        ACCOUNTANT = "ACCOUNTANT", "Accountant"
        OTHER = "OTHER", "Other"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="staff_profile",
        null=True,
        blank=True,
        help_text="Optional login account for this staff member.",
    )
    staff_id = models.CharField(max_length=50, unique=True, db_index=True, editable=False)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.OTHER)
    designation = models.CharField(max_length=255, blank=True)
    academic_qualification = models.CharField(max_length=255, blank=True)
    state = models.CharField(max_length=100, blank=True)
    address = models.CharField(max_length=255, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        related_name="staff_members",
        null=True,
        blank=True,
    )
    image = models.ImageField(upload_to="Employee_images", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("staff_id",)
        indexes = [models.Index(fields=["role", "is_active"])]

    def clean(self):
        super().clean()
        if self.date_of_birth and self.date_of_birth > timezone.now().date():
            raise ValidationError({"date_of_birth": "Date of birth cannot be in the future."})
        if self.salary is not None and self.salary < 0:
            raise ValidationError({"salary": "Salary cannot be negative."})

    def save(self, *args, **kwargs):
        self.full_clean()
        if not self.staff_id:
            for _ in range(20):
                candidate = f"STF-{get_random_string(8, allowed_chars='ABCDEFGHJKLMNPQRSTUVWXYZ23456789')}"
                if not type(self).objects.filter(staff_id=candidate).exists():
                    self.staff_id = candidate
                    break
            else:
                raise ValidationError("Unable to generate a unique staff ID.")
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        return self.user.get_full_name() if self.user else self.staff_id

    def __str__(self):
        return f"{self.full_name} ({self.staff_id})"


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
    staff = models.OneToOneField(
        Staff,
        on_delete=models.SET_NULL,
        related_name="teacher_profile",
        null=True,
        blank=True,
        help_text="General staff identity. Teacher.user remains authoritative during transition.",
    )
    teacher_id = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        db_index=True,
        blank=True,
        help_text="Globally unique teacher identifier (e.g., TCH-B3N8Y6P1)",
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
    alt_email = models.EmailField(blank=True, null=True)
    image = models.ImageField(upload_to="Employee_images", blank=True, null=True)
    inactive = models.BooleanField(default=False)

    class Meta:
        ordering = ("id", "user__first_name", "user__last_name")

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
        return getattr(self.user, "gender", None) if self.user else None

    @property
    def date_of_birth(self):
        if self.staff and self.staff.date_of_birth:
            return self.staff.date_of_birth
        return getattr(self.user, "date_of_birth", None) if self.user else None

    @property
    def academic_qualification(self):
        return self.staff.academic_qualification if self.staff else ""

    @property
    def state(self):
        return self.staff.state if self.staff else ""

    @property
    def salary(self):
        return self.staff.salary if self.staff else None

    @property
    def deleted(self):
        return self.inactive

    @property
    def last_login(self):
        return self.user.last_login if self.user else None

    def save(self, *args, **kwargs):
        if not self.user:
            raise ValidationError("Teacher must have an associated user account. Create the CustomUser first.")

        if not self.teacher_id:
            from django_tenants.utils import schema_context

            with schema_context("public"):
                from core.models import GlobalIDRegistry

                self.teacher_id = GlobalIDRegistry.generate_unique_id("teacher")

        if not self.user.is_teacher:
            self.user.is_teacher = True
            self.user.save(update_fields=["is_teacher"])

        group, _ = Group.objects.get_or_create(name="teacher")
        self.user.groups.add(group)

        super().save(*args, **kwargs)

        if not self.staff:
            staff, _ = Staff.objects.get_or_create(
                user=self.user,
                defaults={
                    "staff_id": self.teacher_id,
                    "role": Staff.Role.TEACHER,
                    "designation": "Teacher",
                    "image": self.image,
                    "is_active": not self.inactive,
                },
            )
            type(self).objects.filter(pk=self.pk, staff__isnull=True).update(staff=staff)
            self.staff = staff

        if self.teacher_id:
            from django.db import connection
            from django_tenants.utils import schema_context

            _schema = connection.schema_name
            with schema_context("public"):
                from core.models import GlobalIDRegistry

                GlobalIDRegistry.sync(
                    unique_id=self.teacher_id,
                    first_name=self.first_name or "",
                    last_name=self.last_name or "",
                    date_of_birth=getattr(self, "date_of_birth", None),
                    current_schema=_schema,
                )

    def __str__(self):
        if self.user:
            return f"{self.user.first_name} {self.user.last_name} ({self.teacher_id})"
        return f"Teacher {self.teacher_id}"


class AllocatedSubject(models.Model):
    teacher_name = models.ForeignKey(Teacher, on_delete=models.CASCADE)
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="allocated_subjects"
    )
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE)
    term = models.ForeignKey(
        Term,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="allocated_subjects",
    )
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


class MessageToTeacher(models.Model):
    message = models.TextField(help_text="Message to be shown to Teachers.")
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(default=timezone.now)

    def __str__(self):
        return self.message

    def clean(self):
        if self.end_date < self.start_date:
            raise ValidationError("End date cannot be before the start date.")
        super().clean()

    @property
    def is_active(self):
        today = timezone.now().date()
        return self.start_date <= today <= self.end_date
