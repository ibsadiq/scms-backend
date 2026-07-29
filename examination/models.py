import datetime
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from django.utils.translation import gettext_lazy as _
from academic.models import Student, Teacher, ClassRoom, StudentClassEnrollment, Subject, GradeLevel, SectionType
from academic.models import AllocatedSubject
from administration.models import AcademicYear, Term
from django.conf import settings

from django.core.validators import FileExtensionValidator

def validate_file_size(value):
    """Validate that the uploaded file size is no larger than 1MB."""
    max_size_mb = 1
    if value.size > max_size_mb * 1024 * 1024:
        raise ValidationError(f"The maximum file size that can be uploaded is {max_size_mb}MB")
    return value



class GradingScheme(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(
        blank=True
    )

    section = models.CharField(
        max_length=20,
        choices=SectionType.choices,
        null=True,
        blank=True
    )

    grade_level = models.ForeignKey(
        GradeLevel,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="grading_schemes"
    )

    classroom = models.ForeignKey(
        ClassRoom,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="grading_schemes"
    )

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "academic_year",
                    "section",
                    "grade_level",
                    "classroom"
                ],
                condition=models.Q(is_active=True),
                name="unique_active_grading_scheme"
            )
        ]

    def __str__(self):
        return self.name
    
    def clean(self):

        count = sum([
            bool(self.section),
            bool(self.grade_level),
            bool(self.classroom)
        ])

        if count == 0:
            raise ValidationError(
                "Scheme must apply to a section, grade level or classroom."
            )

        if count > 1:
            raise ValidationError(
                "Scheme should apply to only one level."
            )

        if self.classroom:
            if (
                self.grade_level and
                self.classroom.name.grade_level != self.grade_level
            ):
                raise ValidationError(
                    "Classroom grade level mismatch."
                )

class AssessmentComponent(models.Model):
    scheme = models.ForeignKey(
        GradingScheme,
        related_name="components",
        on_delete=models.CASCADE
    )

    name = models.CharField(max_length=100)

    max_score = models.DecimalField(
        max_digits=5,
        decimal_places=2
    )

    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2
    )

    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["scheme", "order"],
                name="unique_component_order_per_scheme"
            )
        ]

    def clean(self):

        if self.max_score <= 0:
            raise ValidationError(
                "Maximum score must be greater than zero."
            )

        if self.weight <= 0:
            raise ValidationError(
                "Weight must be greater than zero."
            )

        total = (
            AssessmentComponent.objects
            .filter(scheme=self.scheme)
            .exclude(pk=self.pk)
            .aggregate(
                total=models.Sum("weight")
            )["total"]
            or Decimal("0")
        )

        if total + self.weight > 100:
            raise ValidationError(
                "Total component weights cannot exceed 100."
            )


class GradeRule(models.Model):

    scheme = models.ForeignKey(
        GradingScheme,
        related_name="grade_rules",
        on_delete=models.CASCADE
    )

    min_score = models.DecimalField(
        max_digits=5,
        decimal_places=2
    )

    max_score = models.DecimalField(
        max_digits=5,
        decimal_places=2
    )

    grade = models.CharField(
        max_length=20
    )

    remark = models.CharField(
        max_length=100
    )

    grade_point = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )

    class Meta:
        ordering = ["-min_score"]

        unique_together = (
            "scheme",
            "grade"
        )
        indexes = [
            models.Index(
                fields=[
                    "scheme",
                    "min_score",
                    "max_score"
                ]
            )
        ]

    def clean(self):

        if self.min_score > self.max_score:
            raise ValidationError(
                "Minimum score cannot exceed maximum score."
            )

        overlap = GradeRule.objects.filter(
            scheme=self.scheme
        ).exclude(
            pk=self.pk
        ).filter(
            min_score__lte=self.max_score,
            max_score__gte=self.min_score
        )

        if overlap.exists():
            raise ValidationError(
                "Grade ranges overlap."
            )

class PromotionRule(models.Model):

    class AnnualComputationMethod(models.TextChoices):
        AVERAGE_ALL_TERMS = "AVERAGE_ALL_TERMS", "Average of all three terms"
        FINAL_TERM_ONLY = "FINAL_TERM_ONLY", "Third term result is the annual result"

    scheme = models.OneToOneField(
        GradingScheme,
        related_name="promotion_rule",
        on_delete=models.CASCADE
    )

    annual_computation_method = models.CharField(
        max_length=30,
        choices=AnnualComputationMethod.choices,
        default=AnnualComputationMethod.AVERAGE_ALL_TERMS
    )

    minimum_average = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=40
    )

    minimum_subject_pass = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=40
    )

    required_pass_subjects = models.ManyToManyField(
        Subject,
        blank=True,
        related_name="promotion_rules_requiring_pass",
        help_text="Subjects a student must pass regardless of overall average"
    )

    max_failed_subjects = models.PositiveIntegerField(
        default=99
    )

    auto_promote = models.BooleanField(
        default=True
    )

    def clean(self):

        if self.minimum_average > 100:
            raise ValidationError(
                "Average cannot exceed 100."
            )

        if self.minimum_subject_pass > 100:
            raise ValidationError(
                "Subject pass cannot exceed 100."
            )


class AssessmentType(models.TextChoices):
    ASSIGNMENT = "ASSIGNMENT"
    TEST = "TEST"
    PROJECT = "PROJECT"
    PRACTICAL = "PRACTICAL"
    EXAMINATION = "EXAMINATION"


class AssessmentSession(models.Model):
    assessment_type = models.CharField(
        max_length=30,
        choices=AssessmentType.choices
    )
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    ends_date = models.DateField()
    out_of = models.IntegerField()
    classrooms = models.ManyToManyField(ClassRoom, related_name="class_exams")
    comments = models.CharField(
        max_length=200, blank=True, null=True, help_text="Comments Regarding Exam"
    )
    created_by = models.ForeignKey(Teacher, on_delete=models.CASCADE, null=True)
    created_on = models.DateTimeField(auto_now_add=True)

    @property
    def status(self):
        today = timezone.now().date()
        if today > self.ends_date:
            return "Completed"
        elif self.start_date <= today <= self.ends_date:
            return "Ongoing"
        return "Upcoming"

    def __str__(self):
        return self.name

    def clean(self):
        """Ensure the start date is not later than the end date."""
        if self.start_date > self.ends_date:
            raise ValidationError("Start date cannot be later than end date.")
        super(AssessmentSession, self).clean()

class AssessmentEntry(models.Model):
    component = models.ForeignKey(
        AssessmentComponent,
        on_delete=models.CASCADE,
        related_name="entries"
    )

    student = models.ForeignKey(
        StudentClassEnrollment,
        on_delete=models.CASCADE,
        related_name="assessment_entries"
    )

    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="assessment_entries"
    )

    score = models.DecimalField(
        max_digits=6,
        decimal_places=2
    )

    entered_by = models.ForeignKey(
        Teacher,
        on_delete=models.CASCADE,
        related_name="entered_assessments"
    )

    entered_at = models.DateTimeField(
        auto_now_add=True
    )

    remarks = models.TextField(
        blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "student",
                    "subject",
                    "component"
                ],
                name="unique_student_component_score"
            )
        ]

        indexes = [
            models.Index(
                fields=[
                    "student",
                    "subject"
                ]
            ),
            models.Index(
                fields=[
                    "component"
                ]
            )
        ]

    def clean(self):

        errors = {}

        # score validation
        if self.score < 0:
            errors["score"] = (
                "Score cannot be negative."
            )

        if (
            self.component and
            self.score >
            self.component.max_score
        ):
            errors["score"] = (
                f"Score cannot exceed "
                f"{self.component.max_score}."
            )

        # subject allocation validation
        if (
            self.entered_by and
            self.subject and
            self.student
        ):

            classroom = self.student.classroom

            is_allocated = (
                AllocatedSubject.objects.filter(
                    teacher_name=self.entered_by,
                    subject=self.subject,
                    class_room=classroom
                ).exists()
            )

            if not is_allocated:
                errors["entered_by"] = (
                    "Teacher is not allocated "
                    "to this subject/class."
                )

        # ensure component belongs to grading scheme
        if (
            self.component and
            self.student
        ):

            scheme = (
                self.student.classroom
                .grading_schemes
                .filter(is_active=True)
                .first()
            )

            if (
                scheme and
                self.component.scheme_id != scheme.id
            ):
                errors["component"] = (
                    "Assessment component does not "
                    "belong to the active grading scheme."
                )

        if errors:
            raise ValidationError(errors)

        super().clean()
# ============================================================================
# RESULT COMPUTATION MODELS (Phase 1.1)
# ============================================================================

class TermResult(models.Model):
    """
    Stores computed results for a student in a specific term.
    This is the master result record that aggregates all subject results.
    """
    grading_scheme = models.ForeignKey(
        GradingScheme,
        on_delete=models.PROTECT
    )
    scheme_name = models.CharField(
        max_length=100
    )

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='term_results'
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name='student_results'
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name='student_results'
    )
    classroom = models.ForeignKey(
        ClassRoom,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Classroom at the time of result computation"
    )

    # Computed scores
    total_marks = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Sum of all subject scores"
    )
    average_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Average percentage across all subjects"
    )
    grade = models.CharField(
        max_length=20,
        help_text="Overall grade for the term"
    )
    gpa = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        help_text="Grade Point Average (0.00 - 4.00)"
    )

    # Ranking
    position_in_class = models.IntegerField(
        help_text="Student's rank in the class",
        null=True,
        blank=True
    )
    total_students = models.IntegerField(
        help_text="Total number of students in class",
        null=True,
        blank=True
    )

    remark = models.CharField(
        max_length=100,
        blank=True
    )

    # Remarks
    class_teacher_remarks = models.TextField(
        blank=True,
        null=True,
        help_text="Remarks from class teacher"
    )
    principal_remarks = models.TextField(
        blank=True,
        null=True,
        help_text="Remarks from principal/head teacher"
    )

    # Metadata
    computed_date = models.DateTimeField(
        default=timezone.now,
        help_text="When the result was computed"
    )
    computed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='computed_results'
    )
    homeroom_approved = models.BooleanField(default=False)
    homeroom_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="homeroom_approved_results"
    )
    homeroom_approved_at = models.DateTimeField(
        null=True,
        blank=True
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_results"
    )

    approved_at = models.DateTimeField(
        null=True,
        blank=True
    )

    is_approved = models.BooleanField(
        default=False
    )
    is_published = models.BooleanField(
        default=False,
        help_text="Whether result is visible to parents/students"
    )
    published_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the result was published"
    )
    is_pass = models.BooleanField(
        default=True
    )
    is_locked = models.BooleanField(
        default=False
    )

    locked_at = models.DateTimeField(
        null=True,
        blank=True
    )

    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="locked_results"
    )
    unlock_reason = models.TextField(
        blank=True
    )

    unlocked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="unlocked_results"
    )

    unlocked_at = models.DateTimeField(
        null=True,
        blank=True
    )
    result_release_date = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        unique_together = ('student', 'term', 'academic_year')
        ordering = ['-academic_year__start_date', '-term__start_date', 'position_in_class']
        indexes = [
            models.Index(fields=['student', 'term']),
            models.Index(fields=['classroom', 'term']),
            models.Index(fields=['is_published']),
        ]
        verbose_name = "Term Result"
        verbose_name_plural = "Term Results"

    def __str__(self):
        return f"{self.student.full_name} - {self.term.name} ({self.academic_year.name})"

    @property
    def status(self):
        return (
            "Pass"
            if self.is_pass
            else "Fail"
        )

    @property
    def percentage_str(self):
        """Return formatted percentage"""
        return f"{self.average_percentage}%"

    def approve(self, user):
        self.is_approved = True
        self.approved_by = user
        self.approved_at = timezone.now()
        self.save()

    def lock(self, user):
        self.is_locked = True
        self.locked_by = user
        self.locked_at = timezone.now()
        self.save()


    def unlock(self):
        self.is_locked = False
        self.locked_by = None
        self.locked_at = None
        self.save()

    def publish(self, published_by=None):
        """Publish result to make it visible to parents/students"""
        if not self.is_approved:
            raise ValidationError(
                "Result must be approved first."
            )
        self.is_published = True
        self.published_date = timezone.now()
        self.save()

    def unpublish(self):
        """Unpublish result"""
        self.is_published = False
        self.published_date = None
        self.save()

    @property
    def can_view(self):

        if not self.is_published:
            return False

        if (
            self.result_release_date and
            timezone.now() <
            self.result_release_date
        ):
            return False

        return True
    
    def homeroom_approve(self, user):
        if self.is_locked:
            raise ValidationError("Result is locked.")
        self.homeroom_approved = True
        self.homeroom_approved_by = user
        self.homeroom_approved_at = timezone.now()
        self.save(update_fields=["homeroom_approved", "homeroom_approved_by", "homeroom_approved_at"])
        self.audit_logs.create(action=ResultAuditLog.Action.HOMEROOM_APPROVED, performed_by=user)

    def approve(self, user):
        if not self.homeroom_approved:
            raise ValidationError("Homeroom teacher must approve before admin approval.")
        if self.is_locked:
            raise ValidationError("Result is locked.")
        self.is_approved = True
        self.approved_by = user
        self.approved_at = timezone.now()
        self.save(update_fields=["is_approved", "approved_by", "approved_at"])
        self.audit_logs.create(action=ResultAuditLog.Action.APPROVED, performed_by=user)

    def lock(self, user):
        self.is_locked = True
        self.locked_by = user
        self.locked_at = timezone.now()
        self.save()
        self.audit_logs.create(action=ResultAuditLog.Action.LOCKED, performed_by=user)

    def unlock(self, user, reason=""):        
        self.is_locked = False
        self.locked_by = None
        self.locked_at = None
        self.unlock_reason = reason
        self.unlocked_by = user
        self.unlocked_at = timezone.now()
        self.save()
        self.audit_logs.create(action=ResultAuditLog.Action.UNLOCKED, performed_by=user, notes=reason)

    def publish(self, published_by=None):
        if not self.is_approved:
            raise ValidationError("Result must be approved first.")
        self.is_published = True
        self.published_date = timezone.now()
        self.save()
        self.audit_logs.create(action=ResultAuditLog.Action.PUBLISHED, performed_by=published_by)

    def unpublish(self, user=None):
        self.is_published = False
        self.published_date = None
        self.save()
        self.audit_logs.create(action=ResultAuditLog.Action.UNPUBLISHED, performed_by=user)




class SubjectResult(models.Model):
    """
    Stores individual subject results for a term.
    Links to TermResult as the parent record.
    """

    grading_scheme_name = models.CharField(
        max_length=100,
        blank=True
    )

    grading_rule_snapshot = models.JSONField(
        default=dict,
        blank=True
    )
   
    term_result = models.ForeignKey(
        TermResult,
        on_delete=models.CASCADE,
        related_name='subject_results'
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='student_results'
    )
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Teacher who taught this subject"
    )
    # Computed totals
    total_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="CA + Exam score"
    )
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Percentage score"
    )
    remark = models.CharField(
        max_length=100,
        blank=True
    )
    grade = models.CharField(
        max_length=20,
        help_text="Letter grade for this subject"
    )
    grade_point = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        help_text="Grade point (0.00 - 4.00)"
    )
    teacher_comment = models.TextField(
        blank=True
    )
    # Ranking
    position_in_subject = models.IntegerField(
        null=True,
        blank=True,
        help_text="Student's rank in this subject within the class"
    )
    total_students = models.IntegerField(
        null=True,
        blank=True,
        help_text="Total students who took this subject"
    )
    highest_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Highest score in class for this subject"
    )
    lowest_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Lowest score in class for this subject"
    )
    class_average = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Class average for this subject"
    )
    is_pass = models.BooleanField(
        default=True
    )

    class Meta:
        unique_together = ('term_result', 'subject')
        ordering = ['subject__subject_code', 'subject__name']
        indexes = [
            models.Index(fields=['term_result', 'subject']),
            models.Index(fields=['subject', 'grade']),
        ]
        verbose_name = "Subject Result"
        verbose_name_plural = "Subject Results"

    def __str__(self):
        return f"{self.term_result.student.full_name} - {self.subject.name} ({self.grade})"

class AnnualResult(models.Model):

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="annual_results"
    )

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="annual_results"
    )

    classroom = models.ForeignKey(
        ClassRoom,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    grading_scheme = models.ForeignKey(
        GradingScheme,
        on_delete=models.PROTECT
    )

    total_marks = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    average_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )

    grade = models.CharField(
        max_length=20,
        blank=True
    )

    gpa = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=0
    )

    position_in_class = models.PositiveIntegerField(
        null=True,
        blank=True
    )

    total_students = models.PositiveIntegerField(
        null=True,
        blank=True
    )

    is_promoted = models.BooleanField(
        default=True
    )

    promoted_to = models.ForeignKey(
        GradeLevel,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="promoted_students"
    )

    promotion_reason = models.TextField(
        blank=True
    )

    computed_at = models.DateTimeField(
        default=timezone.now
    )

    computed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="computed_annual_results"
    )

    is_published = models.BooleanField(
        default=False
    )

    published_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        unique_together = (
            "student",
            "academic_year"
        )

        ordering = [
            "-academic_year__start_date",
            "position_in_class"
        ]

        indexes = [
            models.Index(
                fields=[
                    "student",
                    "academic_year"
                ]
            ),
            models.Index(
                fields=[
                    "classroom"
                ]
            )
        ]

    @property
    def can_view(self):
        if not self.is_published:
            return False
        if self.result_release_date and timezone.now() < self.result_release_date:
            return False
        return True

class AnnualSubjectResult(models.Model):

    annual_result = models.ForeignKey(
        AnnualResult,
        on_delete=models.CASCADE,
        related_name="subjects"
    )

    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE
    )

    first_term = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )

    second_term = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )

    third_term = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )

    annual_average = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )

    grade = models.CharField(
        max_length=20
    )

    grade_point = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=0
    )

    is_pass = models.BooleanField(
        default=True
    )

    class Meta:
        unique_together = (
            "annual_result",
            "subject"
        )
    
class AssessmentScore(models.Model):

    subject_result = models.ForeignKey(
        SubjectResult,
        related_name="assessment_scores",
        on_delete=models.CASCADE
    )

    component = models.ForeignKey(
        AssessmentComponent,
        on_delete=models.CASCADE
    )

    score = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0
    )

    class Meta:
        unique_together = (
            "subject_result",
            "component"
        )
        indexes = [
            models.Index(
                fields=[
                    "subject_result"
                ]
            )
        ]

    def clean(self):

        if self.score < 0:
            raise ValidationError(
                "Score cannot be negative."
            )

        if (
            self.component and
            self.score >
            self.component.max_score
        ):
            raise ValidationError(
                f"Score cannot exceed "
                f"{self.component.max_score}"
            )



# ============================================================================
# REPORT CARD MODEL (Phase 1.2)
# ============================================================================
class ReportCardStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    GENERATING = "GENERATING", "Generating"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


class ReportCard(models.Model):
    """
    Stores generated report card PDFs for term results.
    Allows caching of generated PDFs and tracking of downloads.
    """
    term_result = models.OneToOneField(
        TermResult,
        on_delete=models.CASCADE,
        related_name='report_card',
        help_text="Associated term result"
    )
    pdf_file = models.FileField(
        upload_to='report_cards/%Y/%m/',
        null=True,
        blank=True,
        help_text="Generated PDF file"
    )
    generated_date = models.DateTimeField(
        auto_now_add=True,
        help_text="When the PDF was generated"
    )
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generated_report_cards'
    )
    download_count = models.IntegerField(
        default=0,
        help_text="Number of times downloaded"
    )
    last_downloaded = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last download timestamp"
    )
    status = models.CharField(
        max_length=20,
        choices=ReportCardStatus.choices,
        default=ReportCardStatus.COMPLETED,
        help_text="Generation status"
    )
    error_message = models.TextField(
        blank=True,
        null=True,
        help_text="Error message if generation failed"
    )

    class Meta:
        ordering = ['-generated_date']
        indexes = [
            models.Index(fields=['term_result']),
            models.Index(fields=['generated_date']),
        ]
        verbose_name = "Report Card"
        verbose_name_plural = "Report Cards"

    def __str__(self):
        return f"Report Card - {self.term_result.student.full_name} ({self.term_result.term.name})"

    def increment_download_count(self):
        """Increment download counter and update timestamp"""
        self.download_count += 1
        self.last_downloaded = timezone.now()
        self.save(update_fields=['download_count', 'last_downloaded'])


# ============================================================================
# MARKED EXAM SCRIPTS MODEL
# ============================================================================

class MarkedScript(models.Model):
    """
    Stores marked exam/test scripts uploaded by teachers.
    Allows teachers to upload scanned or digital copies of graded assessments.
    """
    exam = models.ForeignKey(
        AssessmentSession,
        on_delete=models.CASCADE,
        related_name='marked_scripts',
        help_text="Associated examination/assessment"
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='marked_scripts',
        help_text="Student whose script this is"
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='marked_scripts',
        help_text="Subject of the assessment"
    )
    assessment_entry = models.ForeignKey(
        AssessmentEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='marked_scripts',
        help_text="Associated marks entry (if applicable)"
    )

    # File upload
    script_file = models.FileField(
        upload_to='examination/marked_scripts/%Y/%m/',
        validators=[
            FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png', 'webp']),
            validate_file_size
        ],
        help_text="Marked exam script file (PDF, images, etc.) - Max 1MB"
    )
    file_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Original filename"
    )
    file_size = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="File size in bytes"
    )

    # Metadata
    uploaded_by = models.ForeignKey(
        Teacher,
        on_delete=models.CASCADE,
        related_name='uploaded_marked_scripts',
        help_text="Teacher who uploaded the script",
        null=True,
        blank=True
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Upload timestamp"
    )
    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Additional notes about the marked script"
    )

    # Visibility control
    visible_to_student = models.BooleanField(
        default=False,
        help_text="Whether student can view this marked script"
    )
    visible_to_parent = models.BooleanField(
        default=False,
        help_text="Whether parent can view this marked script"
    )

    class Meta:
        ordering = ['-uploaded_at']
        unique_together = ('exam', 'student', 'subject')
        indexes = [
            models.Index(fields=['exam', 'student', 'subject']),
            models.Index(fields=['student']),
            models.Index(fields=['uploaded_by']),
            models.Index(fields=['uploaded_at']),
        ]
        verbose_name = "Marked Script"
        verbose_name_plural = "Marked Scripts"

    def __str__(self):
        return f"{self.exam.name} - {self.student.full_name} - {self.subject.name}"

    def save(self, *args, **kwargs):
        """Auto-capture file metadata"""
        if self.script_file:
            if not self.file_name:
                self.file_name = self.script_file.name
            if not self.file_size:
                self.file_size = self.script_file.size
        super().save(*args, **kwargs)

    def clean(self):
        """Validate that teacher is authorized to upload for this subject/student"""
        if self.uploaded_by and self.subject and self.student:
            from academic.models import AllocatedSubject, StudentClassEnrollment

            # Get student's classroom
            try:
                enrollment = StudentClassEnrollment.objects.filter(
                    student=self.student
                ).order_by('-academic_year__start_date').first()

                if enrollment:
                    student_classroom = enrollment.classroom

                    # Check if teacher is allocated to this subject and classroom
                    is_allocated = AllocatedSubject.objects.filter(
                        teacher_name=self.uploaded_by,
                        subject=self.subject,
                        class_room=student_classroom
                    ).exists()

                    if not is_allocated:
                        raise ValidationError(
                            f"You are not authorized to upload marked scripts for {self.subject.name} "
                            f"in {student_classroom}. Please check your subject allocations."
                        )
            except Exception:
                pass

        super().clean()

class ResultAuditLog(models.Model):

    class Action(models.TextChoices):
        COMPUTED = "COMPUTED", "Computed"
        RECOMPUTED = "RECOMPUTED", "Recomputed"
        HOMEROOM_APPROVED = "HOMEROOM_APPROVED", "Homeroom Approved"
        APPROVED = "APPROVED", "Approved"
        PUBLISHED = "PUBLISHED", "Published"
        UNPUBLISHED = "UNPUBLISHED", "Unpublished"
        LOCKED = "LOCKED", "Locked"
        UNLOCKED = "UNLOCKED", "Unlocked"

    term_result = models.ForeignKey(
        TermResult,
        on_delete=models.CASCADE,
        related_name="audit_logs"
    )
    action = models.CharField(
        max_length=30,
        choices=Action.choices
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    timestamp = models.DateTimeField(
        auto_now_add=True
    )
    notes = models.TextField(
        blank=True
    )

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["term_result", "-timestamp"]),
        ]

    def __str__(self):
        return f"{self.term_result} - {self.action} @ {self.timestamp:%Y-%m-%d %H:%M}"