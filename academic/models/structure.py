import re

from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .choices import SectionType, StandardClassCode
from academic.validators import stream_validator


class Department(models.Model):
    name = models.CharField(max_length=255, unique=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.name = self.name.lower()
        super().save(*args, **kwargs)


class SchoolSection(models.Model):
    system_code = models.CharField(
        max_length=20,
        choices=SectionType.choices,
        unique=True,
        help_text="Internal code for data analysis. Cannot be changed.",
    )

    default_name = models.CharField(
        max_length=100,
        help_text="Standard Universal Name",
    )

    alias = models.CharField(
        max_length=100,
        blank=True,
        help_text=(
            "School-specific name "
            "(e.g., 'Nursery' instead of 'Pre-Primary'). "
            "Admin editable."
        ),
    )

    number_code = models.CharField(
        max_length=20,
        blank=True,
        help_text=(
            "Optional short representation used in generated "
            "numbers, e.g. PN, JS, SS."
        ),
    )

    sequence_order = models.PositiveIntegerField(
        help_text="Order for display (1, 2, 3...)"
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sequence_order",)
        verbose_name = "School Section"

    def __str__(self):
        return self.alias if self.alias else self.default_name

    def clean(self):
        super().clean()

        if self.number_code:
            if not re.fullmatch(
                r"[A-Za-z0-9._/-]+",
                self.number_code,
            ):
                raise ValidationError({
                    "number_code": (
                        "Number code contains unsupported characters."
                    )
                })

    @classmethod
    def initialize_defaults(cls):
        defaults = [
            {
                "code": SectionType.PRE_PRIMARY,
                "name": "Pre-Primary / Nursery",
                "number_code": "PN",
                "order": 1,
            },
            {
                "code": SectionType.PRIMARY,
                "name": "Primary",
                "number_code": "PN",
                "order": 2,
            },
            {
                "code": SectionType.JUNIOR_SECONDARY,
                "name": "Junior Secondary (JSS)",
                "number_code": "JS",
                "order": 3,
            },
            {
                "code": SectionType.SENIOR_SECONDARY,
                "name": "Senior Secondary (SSS)",
                "number_code": "SS",
                "order": 4,
            },
        ]

        for item in defaults:
            obj, created = cls.objects.update_or_create(
                system_code=item["code"],
                defaults={
                    "default_name": item["name"],
                    "number_code": item["number_code"],
                    "sequence_order": item["order"],
                },
            )

            if created and not obj.alias:
                obj.alias = item["name"]
                obj.save(update_fields=["alias"])

class GradeLevel(models.Model):
    system_code = models.CharField(
        max_length=20,
        choices=StandardClassCode.choices,
        unique=True,
        help_text="Internal code for data analysis. Cannot be changed.",
    )
    section = models.CharField(max_length=20, choices=SectionType.choices)
    default_name = models.CharField(max_length=100, help_text="Standard Universal Name")
    alias = models.CharField(
        max_length=100,
        blank=True,
        help_text="School-specific name (e.g., 'Year 1' instead of 'Basic 1'). Admin editable.",
    )
    updated_at = models.DateTimeField(auto_now=True)
    sequence_order = models.PositiveIntegerField(help_text="Order for promotion (1, 2, 3...)")
    min_age = models.PositiveIntegerField(default=0)
    max_age = models.PositiveIntegerField(default=0)
    graduation_note = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="E.g., 'Graduates receive FSLC' or 'Graduates take WAEC'",
    )

    class Meta:
        ordering = ("sequence_order",)
        verbose_name = "Grade Configuration"

    def __str__(self):
        return self.alias if self.alias else self.default_name

    @classmethod
    def initialize_defaults(cls):
        defaults = [
            {
                "code": StandardClassCode.CRECHE,
                "name": "Creche/Playgroup",
                "section": SectionType.PRE_PRIMARY,
                "order": 1,
                "min": 0,
                "max": 2,
            },
            {
                "code": StandardClassCode.PRE_NURSERY,
                "name": "Pre-Nursery",
                "section": SectionType.PRE_PRIMARY,
                "order": 2,
                "min": 2,
                "max": 3,
            },

            # ...

            {
                "code": StandardClassCode.JSS_1,
                "name": "JSS 1",
                "section": SectionType.JUNIOR_SECONDARY,
                "order": 12,
                "min": 12,
                "max": 12,
            },

            # ...

            {
                "code": StandardClassCode.SS_3,
                "name": "SS 3",
                "section": SectionType.SENIOR_SECONDARY,
                "order": 17,
                "min": 17,
                "max": 17,
                "note": "SSCE (WAEC/NECO)",
            },
        ]
        for item in defaults:
            obj, created = cls.objects.update_or_create(
                system_code=item["code"],
                defaults={
                    "default_name": item["name"],
                    "section": item["section"],
                    "sequence_order": item["order"],
                    "min_age": item["min"],
                    "max_age": item["max"],
                    "graduation_note": item.get("note", ""),
                },
            )
            if created and not obj.alias:
                obj.alias = item["name"]
                obj.save()


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
    """
    Academic pathway / track (e.g. Science, Commercial, Arts, Technical, General).
    Tenant-configurable.
    """
    name = models.CharField(max_length=50, validators=[stream_validator])

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.name = self.name.upper()
        super().save(*args, **kwargs)


class ClassRoom(models.Model):
    name = models.CharField(max_length=150, help_text="Classroom name (e.g. 'Oleander', 'A', 'Gold')")
    grade_level = models.ForeignKey(
        GradeLevel,
        on_delete=models.CASCADE,
        related_name="classrooms",
        help_text="Academic stage (e.g. JSS 1 / Year 7)",
    )
    stream = models.ForeignKey(
        Stream,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="classrooms",
        help_text="Optional academic pathway (e.g. Science, Commercial, Arts)",
    )
    class_teacher = models.ForeignKey(
        "Teacher",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="homeroom_classrooms",
    )
    capacity = models.PositiveIntegerField(default=40, blank=True)
    occupied_sits = models.PositiveIntegerField(default=0, blank=True)

    class Meta:
        ordering = ("grade_level__sequence_order", "name")
        constraints = [
            models.UniqueConstraint(
                fields=["grade_level", "stream", "name"],
                name="unique_classroom_with_stream",
                condition=models.Q(stream__isnull=False),
            ),
            models.UniqueConstraint(
                fields=["grade_level", "name"],
                name="unique_classroom_without_stream",
                condition=models.Q(stream__isnull=True),
            ),
        ]

    @property
    def display_name(self):
        if self.stream:
            return f"{self.stream.name} - {self.name}"
        return f"{self.name}"

    @property
    def name_display(self):
        return self.display_name

    def __str__(self):
        return self.display_name

    @property
    def available_sits(self):
        return self.capacity - self.occupied_sits

    @property
    def class_status(self):
        if not self.capacity:
            return "0.00%"
        percentage = (self.occupied_sits / self.capacity) * 100
        return f"{percentage:.2f}%"

    def clean(self):
        if self.occupied_sits > self.capacity:
            raise ValidationError("Occupied sits cannot exceed the capacity.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class Dormitory(models.Model):
    name = models.CharField(max_length=150)
    capacity = models.PositiveIntegerField(blank=True, null=True)
    occupied_beds = models.IntegerField(blank=True, null=True)
    captain = models.ForeignKey("Student", on_delete=models.CASCADE, blank=True)

    def __str__(self):
        return self.name

    def available_beds(self):
        total = self.capacity - self.occupied_beds
        if total <= 0:
            return 0
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
    student = models.ForeignKey("Student", on_delete=models.CASCADE)
    dormitory = models.ForeignKey(Dormitory, on_delete=models.CASCADE)
    date_from = models.DateField(auto_now_add=True)
    date_till = models.DateField(blank=True, null=True)

    def __str__(self):
        return str(self.student.admission_number)

    @transaction.atomic
    def update_dormitory(self):
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
