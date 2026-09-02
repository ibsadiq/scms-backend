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
from django.core.files.storage import default_storage

def get_pdf_storage():
    """Returns RawMediaCloudinaryStorage if Cloudinary is used, else default storage"""
    if getattr(settings, 'USE_CLOUDINARY', False):
        try:
            from cloudinary_storage.storage import RawMediaCloudinaryStorage
            return RawMediaCloudinaryStorage()
        except ImportError:
            pass
    return default_storage

from django.core.validators import FileExtensionValidator


def validate_file_size(value):
    """Validate that the uploaded file size is no larger than 10MB."""
    max_size_mb = 10
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
                self.classroom.grade_level != self.grade_level
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
        AVERAGE_ALL_TERMS = "AVERAGE_ALL_TERMS", "Average of all terms"
        FINAL_TERM_ONLY = "FINAL_TERM_ONLY", "Third term result is the annual result"
        WEIGHTED_TERMS = "WEIGHTED_TERMS", "Use custom term weights"

    class MissingTermPolicy(models.TextChoices):
        TREAT_AS_ZERO = "TREAT_AS_ZERO", "Treat missing terms as 0%"
        IGNORE_AND_AVERAGE = "IGNORE_AND_AVERAGE", "Ignore missing terms and average the rest"
        FAIL_SUBJECT = "FAIL_SUBJECT", "Automatically fail the subject if a term is missing"

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
    
    missing_term_policy = models.CharField(
        max_length=30,
        choices=MissingTermPolicy.choices,
        default=MissingTermPolicy.IGNORE_AND_AVERAGE,
        help_text="How to handle missing terms when computing annual results"
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

class TermWeightConfig(models.Model):
    promotion_rule = models.ForeignKey(
        PromotionRule,
        related_name="term_weights",
        on_delete=models.CASCADE
    )
    term_number = models.PositiveIntegerField(help_text="e.g. 1 for First Term")
    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Percentage weight of this term (e.g. 30.00)"
    )

    class Meta:
        unique_together = ("promotion_rule", "term_number")
        ordering = ["term_number"]

    def __str__(self):
        return f"Term {self.term_number}: {self.weight}%"

class CumulativePolicy(models.Model):
    class CumulativeComputationMethod(models.TextChoices):
        AVERAGE_ANNUAL_RESULTS = "AVERAGE_ANNUAL_RESULTS", "Average Annual Results"
        WEIGHTED_ANNUAL_RESULTS = "WEIGHTED_ANNUAL_RESULTS", "Weighted Annual Results"
        FINAL_YEAR_ONLY = "FINAL_YEAR_ONLY", "Final Year Only"

    scheme = models.OneToOneField(
        GradingScheme,
        related_name="cumulative_policy",
        on_delete=models.CASCADE
    )
    
    computation_method = models.CharField(
        max_length=50,
        choices=CumulativeComputationMethod.choices,
        default=CumulativeComputationMethod.AVERAGE_ANNUAL_RESULTS
    )
    
    include_failed_years = models.BooleanField(default=True)
    include_repeated_years = models.BooleanField(default=False)
    
    def __str__(self):
        return f"Cumulative Policy for {self.scheme.name}"

class AnnualWeightConfig(models.Model):
    cumulative_policy = models.ForeignKey(
        CumulativePolicy,
        related_name="annual_weights",
        on_delete=models.CASCADE
    )
    grade_level = models.ForeignKey(
        GradeLevel,
        on_delete=models.CASCADE,
        help_text="The grade level this weight applies to (e.g. JSS 1)"
    )
    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Weight percentage (e.g. 30.00 for 30%)"
    )

    class Meta:
        unique_together = ("cumulative_policy", "grade_level")

    def __str__(self):
        return f"{self.grade_level.name}: {self.weight}%"

    def clean(self):
        if self.weight < 0 or self.weight > 100:
            raise ValidationError("Weight must be between 0 and 100.")
            
        # Optional: ensure total weights for the policy do not exceed 100
        existing_weights = self.cumulative_policy.annual_weights.exclude(id=self.id)
        total = sum(w.weight for w in existing_weights) + self.weight
        if total > 100:
            raise ValidationError(f"Total weights for this policy cannot exceed 100%. Current total would be {total}%.")



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
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name="assessment_sessions",
        null=True, blank=True
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="assessment_sessions",
        null=True, blank=True
    )
    start_date = models.DateField()
    ends_date = models.DateField()
    out_of = models.IntegerField()
    classrooms = models.ManyToManyField(ClassRoom, related_name="class_exams")
    comments = models.CharField(
        max_length=200, blank=True, null=True, help_text="Comments Regarding Exam"
    )
    created_by = models.ForeignKey(Teacher, on_delete=models.CASCADE, null=True, blank=True)
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

    session = models.ForeignKey(
        AssessmentSession,
        on_delete=models.CASCADE,
        related_name="entries",
        null=True, blank=True
    )

    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name="assessment_entries",
        null=True, blank=True
    )

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="assessment_entries",
        null=True, blank=True
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
        decimal_places=2,
        null=True,
        blank=True
    )

    class EntryStatus(models.TextChoices):
        COMPLETE = "COMPLETE", "Complete"
        INCOMPLETE = "INCOMPLETE", "Incomplete"
        PENDING = "PENDING", "Pending"
        MISSING = "MISSING", "Missing"
        ABSENT = "ABSENT", "Absent"
        EXEMPTED = "EXEMPTED", "Exempted"
        NOT_OFFERED = "NOT_OFFERED", "Not Offered"

    status = models.CharField(
        max_length=20,
        choices=EntryStatus.choices,
        default=EntryStatus.COMPLETE
    )

    class EntrySource(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        CBT = "CBT", "CBT"
        IMPORT = "IMPORT", "Import"
        API = "API", "API"

    source = models.CharField(
        max_length=20,
        choices=EntrySource.choices,
        default=EntrySource.MANUAL
    )

    source_reference = models.CharField(
        max_length=100,
        null=True, blank=True, unique=True,
        help_text="External reference ID (e.g. CBT Attempt ID) for traceability."
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

        if self.session:
            if self.term and self.session.term and self.term != self.session.term:
                errors["term"] = "Term must match the assessment session's term."
            if self.academic_year and self.session.academic_year and self.academic_year != self.session.academic_year:
                errors["academic_year"] = "Academic year must match the assessment session's academic year."
            
            # Inherit if not explicitly set
            if not self.term and self.session.term:
                self.term = self.session.term
            if not self.academic_year and self.session.academic_year:
                self.academic_year = self.session.academic_year

        if not self.term:
            errors["term"] = "Assessment entry must be tied to a specific term."

        if not self.academic_year:
            errors["academic_year"] = "Assessment entry must be tied to a specific academic year."

        # score validation
        if self.score is not None and self.score < 0:
            errors["score"] = (
                "Score cannot be negative."
            )

        if (
            self.component and
            self.score is not None and
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

class LifecycleState(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    COMPUTED = "COMPUTED", "Computed"
    HOMEROOM_APPROVED = "HOMEROOM_APPROVED", "Homeroom Approved"
    ADMIN_APPROVED = "ADMIN_APPROVED", "Admin Approved"
    LOCKED = "LOCKED", "Locked"
    PUBLISHED = "PUBLISHED", "Published"

class TermResult(models.Model):
    """
    Stores computed results for a student in a specific term.
    This is the master result record that aggregates all subject results.
    """
    lifecycle_state = models.CharField(
        max_length=25,
        choices=LifecycleState.choices,
        default=LifecycleState.COMPUTED
    )

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
        help_text="Class teacher's assessment/remarks"
    )
    principal_remarks = models.TextField(
        blank=True,
        null=True,
        help_text="Principal's assessment/remarks"
    )

    grading_scale_snapshot = models.JSONField(
        default=list,
        blank=True,
        help_text="Snapshot of the complete grading scheme rules at computation time"
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
    homeroom_approval_delegated = models.BooleanField(default=False)
    admin_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_results"
    )

    admin_approved_at = models.DateTimeField(
        null=True,
        blank=True
    )

    admin_approved = models.BooleanField(default=False)
    is_published = models.BooleanField(
        default=False,
        help_text="Whether result is visible to parents/students"
    )
    published_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the result was published"
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="published_results",
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
    
    def homeroom_approve(self, user, delegated=False):
        from .services.result_lifecycle_service import ResultLifecycleService
        ResultLifecycleService.homeroom_approve(self, user, delegated=delegated)
        self.audit_logs.create(
            action=ResultAuditLog.Action.HOMEROOM_APPROVED,
            performed_by=user,
            notes="Delegated by administrator" if delegated else "",
        )

    def approve(self, user):
        from .services.result_lifecycle_service import ResultLifecycleService
        ResultLifecycleService.admin_approve(self, user)
        self.audit_logs.create(action=ResultAuditLog.Action.ADMIN_APPROVED, performed_by=user)

    def lock(self, user):
        from .services.result_lifecycle_service import ResultLifecycleService
        ResultLifecycleService.lock(self, user)
        self.audit_logs.create(action=ResultAuditLog.Action.LOCKED, performed_by=user)

    def unlock(self, user, reason=""): 
        from .services.result_lifecycle_service import ResultLifecycleService
        ResultLifecycleService.unlock_for_amendment(self, user, None, reason)
        self.audit_logs.create(action=ResultAuditLog.Action.UNLOCKED, performed_by=user, notes=reason)

    def publish(self, published_by=None):
        from .services.result_lifecycle_service import ResultLifecycleService
        ResultLifecycleService.publish(self, published_by)
        self.audit_logs.create(action=ResultAuditLog.Action.PUBLISHED, performed_by=published_by)

    def unpublish(self, user=None):
        from .services.result_lifecycle_service import ResultLifecycleService
        ResultLifecycleService.unpublish(self, user)
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
    class SubjectResultStatus(models.TextChoices):
        COMPLETE = "COMPLETE", "Complete"
        MISSING = "MISSING", "Missing"
        EXCUSED = "EXCUSED", "Excused"

    status = models.CharField(
        max_length=20,
        choices=SubjectResultStatus.choices,
        default=SubjectResultStatus.COMPLETE
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
        return f"{self.term_result.student.full_name} - {self.subject.name} - Term"


class PromotionDecision(models.Model):
    class Status(models.TextChoices):
        PROMOTED = "PROMOTED", "Promoted"
        NOT_PROMOTED = "NOT_PROMOTED", "Not Promoted"
        CONDITIONAL_PROMOTION = "CONDITIONAL_PROMOTION", "Conditional Promotion"
        REPEAT_CLASS = "REPEAT_CLASS", "Repeat Class"
        PENDING_REVIEW = "PENDING_REVIEW", "Pending Review"
        GRADUATED = "GRADUATED", "Graduated"

    annual_result = models.OneToOneField(
        "AnnualResult",
        on_delete=models.CASCADE,
        related_name="promotion_decision"
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING_REVIEW
    )

    promoted_to = models.ForeignKey(
        GradeLevel,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="promotion_decisions"
    )

    reasons = models.TextField(
        blank=True,
        help_text="Automated human-readable reasons for this decision"
    )
    
    structured_reasons = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured decision payload for programmatic checks"
    )
    
    failed_subjects_count = models.PositiveIntegerField(default=0)
    
    # Manual overrides
    is_overridden = models.BooleanField(default=False)
    overridden_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="overridden_promotions"
    )
    overridden_at = models.DateTimeField(null=True, blank=True)
    override_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.annual_result.student.full_name} - {self.status}"

class AnnualResult(models.Model):
    lifecycle_state = models.CharField(
        max_length=25,
        choices=LifecycleState.choices,
        default=LifecycleState.COMPUTED
    )

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

    @property
    def is_promoted(self):
        if hasattr(self, 'promotion_decision'):
            return self.promotion_decision.status == PromotionDecision.Status.PROMOTED
        return False

    @property
    def promoted_to(self):
        if hasattr(self, 'promotion_decision'):
            return self.promotion_decision.promoted_to
        return None

    @property
    def promotion_reason(self):
        if hasattr(self, 'promotion_decision'):
            return self.promotion_decision.reasons
        return ""

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

class CumulativeResult(models.Model):
    lifecycle_state = models.CharField(
        max_length=25,
        choices=LifecycleState.choices,
        default=LifecycleState.COMPUTED
    )
    
    is_locked = models.BooleanField(
        default=False,
        help_text="If true, modifications are blocked without an amendment."
    )
    
    homeroom_approved = models.BooleanField(default=False)
    homeroom_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="homeroom_approved_cumulative_results"
    )
    homeroom_approved_at = models.DateTimeField(null=True, blank=True)

    admin_approved = models.BooleanField(default=False)
    admin_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="admin_approved_cumulative_results"
    )
    admin_approved_at = models.DateTimeField(null=True, blank=True)

    is_published = models.BooleanField(default=False)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="published_cumulative_results"
    )
    published_at = models.DateTimeField(null=True, blank=True)

    
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="cumulative_results"
    )

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        help_text="The latest academic year included in this cumulative result"
    )
    
    grading_scheme = models.ForeignKey(
        GradingScheme,
        on_delete=models.PROTECT,
        null=True
    )

    total_marks = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cumulative_average = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    cumulative_gpa = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    grade = models.CharField(max_length=20, blank=True)

    computed_at = models.DateTimeField(auto_now_add=True)
    computed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
    )

    policy_snapshot = models.JSONField(
        null=True, blank=True,
        help_text="Snapshot of the cumulative policy at the time of computation"
    )

    class Meta:
        unique_together = ("student", "academic_year")

    def __str__(self):
        return f"{self.student.full_name} - Cumulative ({self.academic_year})"


class CumulativeSubjectResult(models.Model):
    cumulative_result = models.ForeignKey(
        CumulativeResult,
        on_delete=models.CASCADE,
        related_name="subjects"
    )

    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE
    )

    cumulative_average = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    grade = models.CharField(max_length=20, blank=True)
    grade_point = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    
    annual_subject_results = models.ManyToManyField(
        'AnnualSubjectResult',
        blank=True,
        related_name="cumulative_subject_results"
    )

    class Meta:
        unique_together = ("cumulative_result", "subject")

    def __str__(self):
        return f"{self.cumulative_result.student.full_name} - {self.subject.name} (Cumulative)"

class ResultAmendmentRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    term_result = models.ForeignKey(
        TermResult,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="amendment_requests"
    )
    
    annual_result = models.ForeignKey(
        AnnualResult,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="amendment_requests"
    )

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="requested_amendments"
    )
    reason = models.TextField()
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="resolved_amendments"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if not self.term_result and not self.annual_result:
            raise ValidationError("Amendment must be for either a term or annual result.")
        if self.term_result and self.annual_result:
            raise ValidationError("Amendment cannot be for both term and annual result simultaneously.")

class AcademicTranscript(models.Model):
    class Status(models.TextChoices):
        CURRENT = "CURRENT", "Current"
        SUPERSEDED = "SUPERSEDED", "Superseded"
        REVOKED = "REVOKED", "Revoked"

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="academic_transcripts"
    )
    
    version = models.PositiveIntegerField(default=1)
    serial_number = models.CharField(max_length=50, unique=True, null=True, blank=True)
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CURRENT
    )
    
    date_generated = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL
    )
    
    metadata = models.JSONField(default=dict, blank=True)
    
    # Stores a JSON snapshot of the student's entire finalized academic history
    # This ensures that even if models change, the generated transcript remains intact.
    history_snapshot = models.JSONField(default=dict)
    
    pdf_document = models.FileField(
        upload_to="transcripts/",
        null=True, blank=True,
        storage=get_pdf_storage(),
        validators=[
            FileExtensionValidator(['pdf']),
            validate_file_size
        ]
    )

    def __str__(self):
        return f"Transcript - {self.student.full_name}"


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
    
    class TermStatus(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        NOT_OFFERED = "NOT_OFFERED", "Not Offered"
        MISSING = "MISSING", "Missing"
        EXEMPTED = "EXEMPTED", "Exempted"

    first_term_status = models.CharField(
        max_length=20,
        choices=TermStatus.choices,
        default=TermStatus.AVAILABLE
    )
    
    second_term_status = models.CharField(
        max_length=20,
        choices=TermStatus.choices,
        default=TermStatus.AVAILABLE
    )
    
    third_term_status = models.CharField(
        max_length=20,
        choices=TermStatus.choices,
        default=TermStatus.AVAILABLE
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
    
    position_in_subject = models.IntegerField(
        null=True,
        blank=True
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
    CURRENT = "CURRENT", "Current"
    SUPERSEDED = "SUPERSEDED", "Superseded"
    FAILED = "FAILED", "Failed"


class ReportCard(models.Model):
    """
    Stores generated report card PDFs for term results.
    Allows caching of generated PDFs and tracking of downloads.
    """
    term_result = models.ForeignKey(
        TermResult,
        on_delete=models.CASCADE,
        related_name='report_cards',
        help_text="Associated term result"
    )
    version = models.PositiveIntegerField(default=1)
    pdf_file = models.FileField(
        upload_to='report_cards/%Y/%m/',
        storage=get_pdf_storage,
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
        default=ReportCardStatus.CURRENT,
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
    classroom = models.ForeignKey(
        "academic.ClassRoom",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='marked_scripts',
        help_text="Snapshot classroom for this marked script"
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
        storage=get_pdf_storage,
        validators=[
            FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png', 'webp']),
            validate_file_size
        ],
        help_text="Marked exam script file (PDF, images, etc.) - Max 10MB"
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

    def save(self, *args, **kwargs):
        if not self.classroom_id and self.student and getattr(self.student, "classroom", None):
            self.classroom = self.student.classroom
        super().save(*args, **kwargs)

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

                    is_allocated = AllocatedSubject.objects.filter(
                        teacher_name=self.uploaded_by,
                        subject=self.subject,
                        class_room=student_classroom
                    ).exists()

                    is_admin_user = getattr(self.uploaded_by.user, 'is_admin', False) if hasattr(self.uploaded_by, 'user') else False
                    if not is_allocated and not is_admin_user:
                        raise ValidationError(
                            f"You are not authorized to upload marked scripts for {self.subject.name} "
                            f"in {student_classroom}. Please check your subject allocations."
                        )
            except ValidationError:
                raise
            except Exception:
                pass

        super().clean()

class ResultAuditLog(models.Model):

    class Action(models.TextChoices):
        COMPUTED = "COMPUTED", "Computed"
        RECOMPUTED = "RECOMPUTED", "Recomputed"

        HOMEROOM_APPROVED = "HOMEROOM_APPROVED", "Homeroom Approved"
        ADMIN_APPROVED = "ADMIN_APPROVED", "Admin Approved"

        LOCKED = "LOCKED", "Locked"
        UNLOCKED = "UNLOCKED", "Unlocked"

        PUBLISHED = "PUBLISHED", "Published"
        UNPUBLISHED = "UNPUBLISHED", "Unpublished"

    term_result = models.ForeignKey(
        TermResult,
        on_delete=models.CASCADE,
        related_name="audit_logs"
    )
    action = models.CharField(
        max_length=50,
        choices=Action.choices
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="result_audit_logs",
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


# ============================================================================
# BEHAVIORAL DOMAINS (Affective & Psychomotor)
# ============================================================================

class BehavioralDomain(models.TextChoices):
    AFFECTIVE = "AFFECTIVE", _("Affective")
    PSYCHOMOTOR = "PSYCHOMOTOR", _("Psychomotor")

class BehavioralTrait(models.Model):
    domain = models.CharField(
        max_length=20, 
        choices=BehavioralDomain.choices
    )
    name = models.CharField(max_length=100)
    section = models.CharField(
        max_length=20, 
        choices=SectionType.choices, 
        null=True, 
        blank=True,
        help_text="If null, applies school-wide"
    )
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["domain", "order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["domain", "section", "name"],
                name="unique_active_trait_section",
                condition=models.Q(is_active=True, section__isnull=False)
            ),
            models.UniqueConstraint(
                fields=["domain", "name"],
                name="unique_active_trait_schoolwide",
                condition=models.Q(is_active=True, section__isnull=True)
            )
        ]
        indexes = [
            models.Index(fields=["domain"]),
            models.Index(fields=["section"]),
            models.Index(fields=["is_active"])
        ]

    def delete(self, *args, **kwargs):
        if self.student_ratings.exists():
            raise ValidationError("Cannot delete a behavioral trait that has existing ratings. Please deactivate it instead.")
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.get_domain_display()} - {self.name}"

class StudentBehavioralRating(models.Model):
    term_result = models.ForeignKey(
        TermResult, 
        on_delete=models.CASCADE, 
        related_name='behavioral_ratings'
    )
    trait = models.ForeignKey(
        BehavioralTrait, 
        on_delete=models.CASCADE,
        related_name='student_ratings'
    )
    rating = models.PositiveSmallIntegerField()
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["term_result", "trait"],
                name="unique_trait_rating_per_term_result"
            ),
            models.CheckConstraint(
                check=models.Q(rating__gte=1) & models.Q(rating__lte=5),
                name="valid_behavioral_rating_range"
            )
        ]
