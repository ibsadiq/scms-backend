from decimal import Decimal
from django.db import models, transaction
from django.db.models import F
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from administration.models import AcademicYear, Term
from administration.common_objs import GENDER_CHOICE, PARENT_CHOICE, RELIGION_CHOICE
from .structure import GradeLevel, ClassYear, ClassRoom, ReasonLeft


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
    alt_phone = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        help_text="Alternate phone number",
    )
    alt_email = models.EmailField(blank=True, null=True, help_text="Personal email")
    date = models.DateTimeField(auto_now_add=True)
    image = models.ImageField(upload_to="Parent_images", blank=True)
    inactive = models.BooleanField(default=False)

    class Meta:
        ordering = ["email", "first_name", "last_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"

class Student(models.Model):
    student_id = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        db_index=True,
        blank=True,
        help_text="Globally unique student identifier (e.g., STU-A7K9X2M4)",
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_profile",
        help_text="Optional: Student's user account for portal access",
    )
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Student's phone number for login/notifications",
    )
    can_login = models.BooleanField(
        default=False,
        help_text="Allow student to access student portal",
    )

    first_name = models.CharField(max_length=150, null=True, verbose_name="First Name")
    middle_name = models.CharField(max_length=150, blank=True, null=True, verbose_name="Middle Name")
    last_name = models.CharField(max_length=150, null=True, verbose_name="Last Name")

    graduation_date = models.DateField(blank=True, null=True)
    date_dismissed = models.DateField(blank=True, null=True)
    reason_left = models.ForeignKey(
        ReasonLeft, blank=True, null=True, on_delete=models.SET_NULL
    )

    class_of_year = models.ForeignKey(ClassYear, blank=True, null=True, on_delete=models.SET_NULL)
    classroom = models.ForeignKey(ClassRoom, blank=True, null=True, on_delete=models.SET_NULL, related_name="students")


    gender = models.CharField(max_length=10, choices=GENDER_CHOICE, blank=True, null=True)
    religion = models.CharField(max_length=50, choices=RELIGION_CHOICE, blank=True, null=True)
    region = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=255, blank=True, null=True)
    street = models.CharField(max_length=255, blank=True)
    blood_group = models.CharField(max_length=10, blank=True, null=True)

    parent_guardian = models.ForeignKey(
        Parent, on_delete=models.SET_NULL, blank=True, null=True, related_name="children"
    )
    parent_contact = models.CharField(max_length=15, blank=True, null=True)

    date_of_birth = models.DateField(blank=True, null=True)
    admission_date = models.DateTimeField(blank=True, null=True)
    admission_number = models.CharField(max_length=100, blank=True, unique=True)
    siblings = models.ManyToManyField("self", blank=True)
    image = models.ImageField(upload_to="Student_images", blank=True)
    cache_gpa = models.DecimalField(editable=False, max_digits=5, decimal_places=2, blank=True, null=True)

    is_active = models.BooleanField(default=True, help_text="Indicates whether the student is currently active.")

    STREAM_CHOICES = [
        ("science", "Science"),
        ("commercial", "Commercial"),
        ("arts", "Arts"),
    ]
    preferred_stream = models.CharField(
        max_length=20,
        choices=STREAM_CHOICES,
        blank=True,
        null=True,
        help_text="Student/Parent preferred stream for SS1 (Science/Commercial/Arts)",
    )
    assigned_stream = models.CharField(
        max_length=20,
        choices=STREAM_CHOICES,
        blank=True,
        null=True,
        help_text="Admin-assigned stream for SS1+ (final decision)",
    )

    class Meta:
        ordering = ["admission_number", "last_name", "first_name"]

    @property
    def full_name(self):
        parts = filter(None, [self.first_name, self.middle_name, self.last_name])
        return " ".join(part.capitalize() for part in parts)

    @property
    def total_paid(self):
        return self.receipts.filter(status="Completed").aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")


    @property
    def grade_level(self):
        """Return the GradeLevel of the student's current active classroom."""
        if self.classroom and hasattr(self.classroom, "grade_level"):
            return self.classroom.grade_level
        return None

    @property
    def class_level(self):
        """Compatibility property returning the grade level."""
        return self.grade_level

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

    def clean(self):
        from .staff import Teacher

        if Teacher.objects.filter(id=self.id).exists():
            raise ValidationError("A person cannot be both a student and a teacher.")
        super().clean()

    def save(self, *args, **kwargs):
        if not self.student_id:
            from django_tenants.utils import schema_context

            with schema_context("public"):
                from core.models import GlobalIDRegistry

                self.student_id = (
                    GlobalIDRegistry.generate_unique_id(
                        "student"
                    )
                )

        self.first_name = (
            self.first_name.lower()
            if self.first_name
            else ""
        )
        self.middle_name = (
            self.middle_name.lower()
            if self.middle_name
            else ""
        )
        self.last_name = (
            self.last_name.lower()
            if self.last_name
            else ""
        )

        if not self.admission_date:
            self.admission_date = timezone.now()

        if self.date_dismissed or self.graduation_date:
            self.is_active = False
        else:
            self.is_active = True

        super().save(*args, **kwargs)

        if self.student_id:
            from django.db import connection
            from django_tenants.utils import schema_context

            _schema = connection.schema_name

            with schema_context("public"):
                from core.models import GlobalIDRegistry

                GlobalIDRegistry.sync(
                    unique_id=self.student_id,
                    first_name=self.first_name or "",
                    last_name=self.last_name or "",
                    date_of_birth=self.date_of_birth,
                    current_schema=(
                        _schema
                        if self.is_active
                        else ""
                    ),
                )

        if self.parent_guardian_id:
            existing_siblings = (
                Student.objects.filter(
                    parent_guardian_id=self.parent_guardian_id
                ).exclude(id=self.id)
            )
            self.siblings.set(existing_siblings)
            for sibling in existing_siblings:
                sibling.siblings.add(self)
        else:
            self.siblings.clear()

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
        if not self.former_school:
            raise ValidationError("Former school name is required.")


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
        if self.file.size > 10 * 1024 * 1024:
            raise ValidationError("File size must be under 10MB.")
        super().clean()


class StudentHealthRecord(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    record = models.TextField()

    def __str__(self):
        return str(self.student)

    def clean(self):
        if len(self.record) < 10:
            raise ValidationError("Health record must contain more information.")
        super().clean()


class MessageToParent(models.Model):
    message = models.TextField(help_text="Message to be shown to Parents.")
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


class PromotionRule(models.Model):
    PROMOTION_METHODS = [
        ("annual_average", "Annual Average (Nigeria Standard)"),
        ("gpa", "GPA (International)"),
        ("cumulative", "Cumulative Average (All Years)"),
    ]

    from_grade = models.ForeignKey(
        GradeLevel,
        on_delete=models.CASCADE,
        related_name="promotion_rules_from",
        help_text="The current grade level of the student",
    )
    to_grade = models.ForeignKey(
        GradeLevel,
        on_delete=models.CASCADE,
        related_name="promotion_rules_to",
        help_text="The destination grade level (or same if repeating)",
    )
    promotion_method = models.CharField(
        max_length=20,
        choices=PROMOTION_METHODS,
        default="annual_average",
        help_text="Method used to calculate promotion eligibility",
    )
    min_average_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=50.00,
        help_text="Minimum Annual Average (0-100%) required to promote.",
    )
    must_pass_english = models.BooleanField(
        default=True,
        help_text="Student must pass English Language?",
    )
    must_pass_math = models.BooleanField(
        default=True,
        help_text="Student must pass Mathematics?",
    )
    min_subjects_passed = models.PositiveIntegerField(
        default=5,
        help_text="Minimum count of subjects the student must pass.",
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        help_text="Auto-generated description of this rule",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["from_grade", "to_grade"]
        ordering = ["from_grade__sequence_order"]
        verbose_name = "Promotion Rule"

    def __str__(self):
        return f"{self.from_grade} → {self.to_grade}"

    def clean(self):
        if self.to_grade.sequence_order < self.from_grade.sequence_order:
            raise ValidationError({
                "to_grade": _(
                    f"Cannot define a promotion rule that demotes students from "
                    f"{self.from_grade} (Order {self.from_grade.sequence_order}) to "
                    f"{self.to_grade} (Order {self.to_grade.sequence_order})."
                )
            })

    def save(self, *args, **kwargs):
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
        return self.from_grade == self.to_grade

    @property
    def is_double_promotion(self):
        return (self.to_grade.sequence_order - self.from_grade.sequence_order) > 1


class StudentPromotion(models.Model):
    PROMOTION_STATUS_CHOICES = [
        ("PROMOTED", "Promoted"),
        ("REPEATED", "Repeated"),
        ("DOUBLE_PROMOTION", "Double Promotion"),
        ("PROMOTED_ON_TRIAL", "Promoted on Trial"),
        ("GRADUATED", "Graduated"),
        ("WITHDRAWN", "Withdrawn"),
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="promotion_history",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        help_text="The academic year of this result (e.g., 2023/2024)",
    )
    from_class = models.ForeignKey(
        ClassRoom,
        on_delete=models.SET_NULL,
        null=True,
        related_name="promotions_out",
        help_text="The classroom the student is leaving (e.g., JSS 1 Gold)",
    )
    from_grade = models.ForeignKey(
        GradeLevel,
        on_delete=models.CASCADE,
        related_name="grade_promotions_out",
        null=True,
        blank=True,
        help_text="Auto-populated: The grade level being completed (e.g., JSS 1)",
    )
    to_class = models.ForeignKey(
        ClassRoom,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promotions_in",
        help_text="The destination classroom. Null if Graduated or Withdrawn.",
    )
    to_grade = models.ForeignKey(
        GradeLevel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="grade_promotions_in",
        help_text="Auto-populated: The destination grade level.",
    )
    status = models.CharField(
        max_length=20,
        choices=PROMOTION_STATUS_CHOICES,
        default="PROMOTED",
    )
    annual_average = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="The student's final average score used for this decision.",
    )
    promotion_date = models.DateField(default=timezone.now)
    reason = models.TextField(blank=True, help_text="Optional remarks (e.g., 'Failed Math twice')")

    class Meta:
        ordering = ["-promotion_date"]
        indexes = [
            models.Index(fields=["student", "academic_year"]),
            models.Index(fields=["status"]),
        ]
        verbose_name = "Promotion Record"

    def __str__(self):
        return f"{self.student} ({self.academic_year}): {self.get_status_display()}"

    def clean(self):
        if self.from_class and not self.from_grade:
            self.from_grade = self.from_class.grade_level
        if self.to_class and not self.to_grade:
            self.to_grade = self.to_class.grade_level

        if self.status in ["PROMOTED", "DOUBLE_PROMOTION", "PROMOTED_ON_TRIAL"]:
            if not self.to_class:
                raise ValidationError("A promoted student must have a destination class.")
            if self.to_grade.sequence_order <= self.from_grade.sequence_order:
                raise ValidationError(
                    f"Invalid Promotion: Cannot promote from {self.from_grade} (Order {self.from_grade.sequence_order}) "
                    f"to {self.to_grade} (Order {self.to_grade.sequence_order}). Sequence must increase."
                )

        if self.status == "REPEATED":
            if self.to_grade and self.to_grade != self.from_grade:
                raise ValidationError(
                    f"Invalid Repeat: Destination grade ({self.to_grade}) must match current grade ({self.from_grade})."
                )

        if self.status in ["GRADUATED", "WITHDRAWN"]:
            if self.to_class or self.to_grade:
                raise ValidationError(f"Students marked as {self.status} should not have a destination class.")

    def save(self, *args, **kwargs):
        if self.from_class:
            self.from_grade = self.from_class.grade_level
        if self.to_class:
            self.to_grade = self.to_class.grade_level

        if self.status in ["GRADUATED", "WITHDRAWN"]:
            self.to_grade = None
            self.to_class = None

        super().save(*args, **kwargs)


class StudentClassEnrollment(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="student_classes",
    )
    classroom = models.ForeignKey(
        ClassRoom,
        on_delete=models.CASCADE,
        related_name="class_students",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
    )
    enrollment_date = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this enrollment is currently active",
    )
    notes = models.TextField(
        blank=True,
        help_text="Additional notes about this enrollment (e.g., 'Repeated year', 'Transferred mid-year')",
    )

    class Meta:
        ordering = ["-academic_year__start_date", "student__admission_number"]
        unique_together = ["student", "academic_year"]
        verbose_name = "Student Class Enrollment"
        verbose_name_plural = "Student Class Enrollments"

    def __str__(self):
        return f"{self.student.full_name} - {self.classroom} ({self.academic_year})"

    @property
    def is_current_class(self):
        return self.academic_year.is_current_session if hasattr(self.academic_year, "is_current_session") else self.is_active

    def clean(self):
        if not self.pk and self.classroom.occupied_sits >= self.classroom.capacity:
            raise ValidationError(
                f"The classroom '{self.classroom}' has reached its maximum capacity."
            )

        if self.is_active:
            existing = StudentClassEnrollment.objects.filter(
                student=self.student,
                academic_year=self.academic_year,
                is_active=True,
            ).exclude(pk=self.pk)

            if existing.exists():
                raise ValidationError(
                    f"Student {self.student} is already enrolled in {existing.first().classroom} "
                    f"for {self.academic_year}. Deactivate that enrollment first."
                )

    def update_class_table(self, increment=True):
        with transaction.atomic():
            selected_class = ClassRoom.objects.select_for_update().get(
                pk=self.classroom.pk
            )
            if increment:
                if selected_class.occupied_sits >= selected_class.capacity:
                    raise ValidationError(
                        "This class has reached its maximum capacity."
                    )
                selected_class.occupied_sits += 1
            else:
                if selected_class.occupied_sits <= 0:
                    raise ValidationError("Cannot have negative occupied sits.")
                selected_class.occupied_sits -= 1
            selected_class.save()

    @transaction.atomic
    def save(self, *args, **kwargs):
        student = Student.objects.select_for_update().get(pk=self.student_id)
        previous = None
        if self.pk:
            previous = StudentClassEnrollment.objects.select_for_update().get(pk=self.pk)

        self.full_clean()
        old_active_classroom_id = previous.classroom_id if previous and previous.is_active else None
        new_active_classroom_id = self.classroom_id if self.is_active else None
        changed_classroom_ids = sorted(
            classroom_id for classroom_id in {old_active_classroom_id, new_active_classroom_id}
            if classroom_id and old_active_classroom_id != new_active_classroom_id
        )
        locked_classrooms = {
            classroom.pk: classroom
            for classroom in ClassRoom.objects.select_for_update().filter(
                pk__in=changed_classroom_ids
            ).order_by("pk")
        }
        for classroom_id, delta in (
            (old_active_classroom_id, -1),
            (new_active_classroom_id, 1),
        ):
            if classroom_id not in locked_classrooms:
                continue
            classroom = locked_classrooms[classroom_id]
            if delta > 0 and classroom.occupied_sits >= classroom.capacity:
                raise ValidationError("This class has reached its maximum capacity.")
            if delta < 0 and classroom.occupied_sits <= 0:
                raise ValidationError("Cannot have negative occupied sits.")
            # The row lock makes this concrete read/modify/write safe. Keep an
            # integer on the instance because ClassRoom.save() validates it.
            classroom.occupied_sits += delta
            classroom.save(update_fields=("occupied_sits",))

        result = super().save(*args, **kwargs)
        if self.academic_year.active_year:
            snapshots = {
                "classroom": self.classroom if self.is_active else None,
            }
            Student.objects.filter(pk=student.pk).update(**snapshots)
            student.classroom = snapshots["classroom"]
        return result

    @transaction.atomic
    def delete(self, *args, **kwargs):
        # Allow standard deletion to proceed. Occupancy updates are now handled by the post_delete signal below.
        return super().delete(*args, **kwargs)


from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.db.models import F

@receiver(post_delete, sender=StudentClassEnrollment)
def handle_student_enrollment_delete(sender, instance, **kwargs):
    """
    Handle classroom occupancy updates when an enrollment is deleted.
    Using a post_delete signal ensures this logic is executed even during cascade deletions.
    """
    with transaction.atomic():
        # Decrement class capacity if the enrollment was active
        if instance.is_active and instance.classroom_id:
            ClassRoom.objects.filter(
                pk=instance.classroom_id, 
                occupied_sits__gt=0
            ).update(occupied_sits=F('occupied_sits') - 1)
        
        # If the student's current classroom was tied to this enrollment in the active academic year, clear it
        if getattr(instance, 'academic_year', None) and getattr(instance.academic_year, 'active_year', False):
            if instance.student_id:
                Student.objects.filter(
                    pk=instance.student_id, 
                    classroom_id=instance.classroom_id
                ).update(classroom=None)
