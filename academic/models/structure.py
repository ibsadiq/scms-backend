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
    default_name = models.CharField(max_length=100, help_text="Standard Universal Name")
    alias = models.CharField(
        max_length=100,
        blank=True,
        help_text="School-specific name (e.g., 'Nursery' instead of 'Pre-Primary'). Admin editable.",
    )
    sequence_order = models.PositiveIntegerField(help_text="Order for display (1, 2, 3...)")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sequence_order",)
        verbose_name = "School Section"

    def __str__(self):
        return self.alias if self.alias else self.default_name

    @classmethod
    def initialize_defaults(cls):
        defaults = [
            {"code": SectionType.PRE_PRIMARY, "name": "Pre-Primary / Nursery", "order": 1},
            {"code": SectionType.PRIMARY, "name": "Primary", "order": 2},
            {"code": SectionType.JUNIOR_SECONDARY, "name": "Junior Secondary (JSS)", "order": 3},
            {"code": SectionType.SENIOR_SECONDARY, "name": "Senior Secondary (SSS)", "order": 4},
        ]
        for item in defaults:
            obj, created = cls.objects.update_or_create(
                system_code=item["code"],
                defaults={
                    "default_name": item["name"],
                    "sequence_order": item["order"],
                },
            )
            if created and not obj.alias:
                obj.alias = item["name"]
                obj.save()


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
            {"code": "CRECHE", "name": "Creche/Playgroup", "section": "PRE_PRIMARY", "order": 1, "min": 0, "max": 2},
            {"code": "PRE_NURSERY", "name": "Pre-Nursery", "section": "PRE_PRIMARY", "order": 2, "min": 2, "max": 3},
            {"code": "NURSERY_1", "name": "Nursery 1", "section": "PRE_PRIMARY", "order": 3, "min": 3, "max": 4},
            {"code": "NURSERY_2", "name": "Nursery 2", "section": "PRE_PRIMARY", "order": 4, "min": 4, "max": 5},
            {"code": "NURSERY_3", "name": "Nursery 3", "section": "PRE_PRIMARY", "order": 5, "min": 5, "max": 6},
            {"code": "BASIC_1", "name": "Basic 1", "section": "PRIMARY", "order": 6, "min": 6, "max": 6},
            {"code": "BASIC_2", "name": "Basic 2", "section": "PRIMARY", "order": 7, "min": 7, "max": 7},
            {"code": "BASIC_3", "name": "Basic 3", "section": "PRIMARY", "order": 8, "min": 8, "max": 8},
            {"code": "BASIC_4", "name": "Basic 4", "section": "PRIMARY", "order": 9, "min": 9, "max": 9},
            {"code": "BASIC_5", "name": "Basic 5", "section": "PRIMARY", "order": 10, "min": 10, "max": 10},
            {"code": "BASIC_6", "name": "Basic 6", "section": "PRIMARY", "order": 11, "min": 11, "max": 11, "note": "First School Leaving Certificate"},
            {"code": "JSS_1", "name": "JSS 1", "section": "JSS", "order": 12, "min": 12, "max": 12},
            {"code": "JSS_2", "name": "JSS 2", "section": "JSS", "order": 13, "min": 13, "max": 13},
            {"code": "JSS_3", "name": "JSS 3", "section": "JSS", "order": 14, "min": 14, "max": 14, "note": "BECE/JSCE"},
            {"code": "SS_1", "name": "SS 1", "section": "SSS", "order": 15, "min": 15, "max": 15},
            {"code": "SS_2", "name": "SS 2", "section": "SSS", "order": 16, "min": 16, "max": 16},
            {"code": "SS_3", "name": "SS 3", "section": "SSS", "order": 17, "min": 17, "max": 17, "note": "SSCE (WAEC/NECO)"},
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
        grade = str(self.grade_level)
        if self.stream:
            return f"{grade} - {self.stream.name} - {self.name}"
        return f"{grade} - {self.name}"

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
