import uuid

from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.utils.crypto import get_random_string
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from administration.models import AcademicYear
from administration.common_objs import GENDER_CHOICE, RELIGION_CHOICE
from .choices import AdmissionStatus, AssessmentType
from .structure import GradeLevel
from .student import Student


class AdmissionSession(models.Model):
    academic_year = models.OneToOneField(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="admission_session",
        help_text="Academic year this admission session is for",
    )
    name = models.CharField(
        max_length=100,
        help_text="Example: '2025/2026 New Students Admission'",
    )
    start_date = models.DateField(help_text="When applications open")
    end_date = models.DateField(help_text="When applications close")

    require_acceptance_fee = models.BooleanField(
        default=True,
        help_text="Whether this session requires acceptance fees",
    )
    acceptance_fee_deadline_days = models.PositiveIntegerField(
        default=14,
        help_text="Days after approval to pay acceptance fee and accept offer",
    )
    application_number_prefix = models.CharField(
        max_length=10,
        default="ADM",
        help_text="Prefix for application numbers (e.g., 'ADM' -> ADM/2025/001)",
    )
    allow_public_applications = models.BooleanField(
        default=True,
        help_text="Allow external applications without login",
    )
    send_confirmation_emails = models.BooleanField(
        default=True,
        help_text="Send email confirmations to applicants",
    )
    application_instructions = models.TextField(
        blank=True,
        help_text="Instructions shown to parents at the start of application",
    )
    approval_message = models.TextField(
        blank=True,
        help_text="Custom message sent when application is approved",
    )
    rejection_message_template = models.TextField(
        blank=True,
        help_text="Template for rejection messages",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Only one session should be active at a time",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date"]
        verbose_name = "Admission Session"
        verbose_name_plural = "Admission Sessions"

    def __str__(self):
        return f"{self.name} ({self.start_date.year})"

    def clean(self):
        if self.end_date < self.start_date:
            raise ValidationError("End date must be after start date")
        if self.acceptance_fee_deadline_days < 1:
            raise ValidationError("Acceptance deadline must be at least 1 day")

    @property
    def is_open(self):
        today = timezone.now().date()
        return self.is_active and self.start_date <= today <= self.end_date

    @property
    def total_applications(self):
        return self.applications.count()

    @property
    def applications_by_status(self):
        from django.db.models import Count

        return self.applications.values("status").annotate(count=Count("id"))


class AdmissionFeeStructure(models.Model):
    admission_session = models.ForeignKey(
        AdmissionSession,
        on_delete=models.CASCADE,
        related_name="fee_structures",
    )
    grade_levels = models.ManyToManyField(
        GradeLevel,
        blank=True,
        related_name="admission_fee_structures",
        help_text="Grade levels this fee applies to (e.g., JSS1, SS1)",
    )
    application_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Fee to submit application",
    )
    application_fee_required = models.BooleanField(
        default=True,
        help_text="Must pay application fee to submit",
    )
    entrance_exam_required = models.BooleanField(
        default=False,
        help_text="Does this class require entrance exam?",
    )
    entrance_exam_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Fee to take entrance exam",
    )
    entrance_exam_pass_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum score to pass entrance exam (percentage)",
    )
    interview_required = models.BooleanField(
        default=False,
        help_text="Does this class require interview?",
    )
    acceptance_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Fee to accept admission offer",
    )
    acceptance_fee_required = models.BooleanField(
        default=True,
        help_text="Must pay acceptance fee to accept offer",
    )
    acceptance_fee_is_part_of_tuition = models.BooleanField(
        default=True,
        help_text="If True, acceptance fee is deducted from first term tuition",
    )
    max_applications = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum number of applications for this class (optional)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["admission_session"]
        verbose_name = "Admission Fee Structure"
        verbose_name_plural = "Admission Fee Structures"

    def __str__(self):
        grade_names = ", ".join(str(grade) for grade in self.grade_levels.all())
        return f"{grade_names} - {self.admission_session.name}"

    def clean(self):
        if self.entrance_exam_required and not self.entrance_exam_pass_score:
            raise ValidationError("Pass score is required when entrance exam is required")

    @property
    def current_applications_count(self):
        qs = self.admission_session.applications
        if self.grade_levels.exists():
            return qs.filter(applying_for_class__grade_level__in=self.grade_levels.all()).count()
        return 0

    @property
    def has_capacity(self):
        if not self.max_applications:
            return True
        return self.current_applications_count < self.max_applications


class AdmissionApplication(models.Model):
    application_number = models.CharField(
        max_length=100,
        unique=True,
        editable=False,
        help_text="Auto-generated (e.g., ADM/2025/001)",
    )
    status = models.CharField(
        max_length=30,
        choices=AdmissionStatus.choices,
        default=AdmissionStatus.DRAFT,
    )
    admission_session = models.ForeignKey(
        AdmissionSession,
        on_delete=models.CASCADE,
        related_name="applications",
    )
    applying_for_class = models.ForeignKey(
        GradeLevel,
        on_delete=models.CASCADE,
        help_text="Class student is applying for",
    )

    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICE)
    date_of_birth = models.DateField()

    state_of_origin = models.CharField(
        max_length=100,
        help_text="Nigerian state of origin",
    )
    lga = models.CharField(
        max_length=100,
        help_text="Local Government Area",
    )
    religion = models.CharField(
        max_length=50,
        choices=RELIGION_CHOICE,
        blank=True,
        null=True,
    )
    blood_group = models.CharField(
        max_length=5,
        blank=True,
        help_text="e.g., O+, A-, AB+",
    )

    address = models.TextField(help_text="Residential address")
    city = models.CharField(max_length=100)

    parent_first_name = models.CharField(max_length=100)
    parent_last_name = models.CharField(max_length=100)
    parent_email = models.EmailField()
    parent_phone = models.CharField(max_length=15)
    parent_occupation = models.CharField(max_length=100, blank=True)
    parent_relationship = models.CharField(
        max_length=50,
        choices=[
            ("father", "Father"),
            ("mother", "Mother"),
            ("guardian", "Guardian"),
            ("other", "Other"),
        ],
        default="father",
    )

    alt_contact_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Alternative emergency contact",
    )
    alt_contact_phone = models.CharField(max_length=15, blank=True)
    alt_contact_relationship = models.CharField(max_length=100, blank=True)

    previous_school = models.CharField(
        max_length=255,
        blank=True,
        help_text="Name of previous school (if any)",
    )
    previous_class = models.CharField(
        max_length=100,
        blank=True,
        help_text="Last class attended",
    )

    medical_conditions = models.TextField(
        blank=True,
        help_text="Any medical conditions or allergies",
    )
    special_needs = models.TextField(
        blank=True,
        help_text="Any special educational needs",
    )

    application_fee_paid = models.BooleanField(default=False)
    application_fee_receipt = models.ForeignKey(
        "finance.Receipt",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="application_fees",
    )
    application_fee_payment_date = models.DateTimeField(null=True, blank=True)

    exam_fee_paid = models.BooleanField(default=False)
    exam_fee_receipt = models.ForeignKey(
        "finance.Receipt",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exam_fees",
    )
    exam_fee_payment_date = models.DateTimeField(null=True, blank=True)

    acceptance_fee_paid = models.BooleanField(default=False)
    acceptance_fee_receipt = models.ForeignKey(
        "finance.Receipt",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acceptance_fees",
    )
    acceptance_fee_payment_date = models.DateTimeField(null=True, blank=True)

    acceptance_deadline = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Deadline to accept offer (calculated from approval date)",
    )

    admin_notes = models.TextField(
        blank=True,
        help_text="Internal notes from admin review",
    )
    rejection_reason = models.TextField(
        blank=True,
        help_text="Reason for rejection (if applicable)",
    )

    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_applications",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When parent accepted the offer",
    )

    enrolled_student = models.OneToOneField(
        Student,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admission_application",
    )
    enrolled_at = models.DateTimeField(null=True, blank=True)

    tracking_token = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        help_text="Secure token for external application tracking",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Admission Application"
        verbose_name_plural = "Admission Applications"
        indexes = [
            models.Index(fields=["application_number"]),
            models.Index(fields=["status"]),
            models.Index(fields=["tracking_token"]),
            models.Index(fields=["parent_email"]),
        ]

    def __str__(self):
        return f"{self.application_number} - {self.first_name} {self.last_name}"

    def save(self, *args, **kwargs):
        if not self.application_number:
            from academic.admission_numbers import ApplicationNumberService
            self.application_number = ApplicationNumberService.allocate(self.admission_session)

        if not self.tracking_token:
            self.tracking_token = get_random_string(64)

        if self.status == AdmissionStatus.SUBMITTED and not self.submitted_at:
            self.submitted_at = timezone.now()

        if self.status == AdmissionStatus.APPROVED and not self.approved_at:
            self.approved_at = timezone.now()
            if self.admission_session.require_acceptance_fee:
                deadline_days = self.admission_session.acceptance_fee_deadline_days
                self.acceptance_deadline = timezone.now() + timezone.timedelta(days=deadline_days)

        if self.status == AdmissionStatus.ACCEPTED and not self.accepted_at:
            self.accepted_at = timezone.now()

        if self.status == AdmissionStatus.ENROLLED and not self.enrolled_at:
            self.enrolled_at = timezone.now()

        super().save(*args, **kwargs)

    def clean(self):
        fee_structure = AdmissionFeeStructure.objects.filter(
            admission_session=self.admission_session,
            grade_levels__in=[self.applying_for_class],
        ).first()

        if fee_structure and self.date_of_birth:
            age = (timezone.now().date() - self.date_of_birth).days // 365
            if hasattr(fee_structure, "minimum_age") and fee_structure.minimum_age and age < fee_structure.minimum_age:
                raise ValidationError(
                    f"Applicant is too young for {self.applying_for_class}. "
                    f"Minimum age is {fee_structure.minimum_age} years."
                )
            if hasattr(fee_structure, "maximum_age") and fee_structure.maximum_age and age > fee_structure.maximum_age:
                raise ValidationError(
                    f"Applicant is too old for {self.applying_for_class}. "
                    f"Maximum age is {fee_structure.maximum_age} years."
                )

    @property
    def full_name(self):
        parts = filter(None, [self.first_name, self.middle_name, self.last_name])
        return " ".join(parts)

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        return (timezone.now().date() - self.date_of_birth).days // 365

    @property
    def all_fees_paid(self):
        fee_structure = AdmissionFeeStructure.objects.filter(
            admission_session=self.admission_session,
            grade_levels__in=[self.applying_for_class],
        ).first()

        if not fee_structure:
            return True

        if fee_structure.application_fee_required and not self.application_fee_paid:
            return False

        if fee_structure.entrance_exam_required and not self.exam_fee_paid:
            return False

        if (
            self.status == AdmissionStatus.APPROVED
            and fee_structure.acceptance_fee_required
            and not self.acceptance_fee_paid
        ):
            return False

        return True

    @property
    def can_submit(self):
        fee_structure = AdmissionFeeStructure.objects.filter(
            admission_session=self.admission_session,
            grade_levels__in=[self.applying_for_class],
        ).first()

        if not fee_structure:
            return False

        if fee_structure.application_fee_required and not self.application_fee_paid:
            return False

        return True

    @property
    def can_accept_offer(self):
        if self.status != AdmissionStatus.APPROVED:
            return False

        fee_structure = AdmissionFeeStructure.objects.filter(
            admission_session=self.admission_session,
            grade_levels__in=[self.applying_for_class],
        ).first()

        if not fee_structure:
            return False

        if fee_structure.acceptance_fee_required and not self.acceptance_fee_paid:
            return False

        if self.acceptance_deadline and timezone.now() > self.acceptance_deadline:
            return False

        return True


class AdmissionDocument(models.Model):
    DOCUMENT_TYPES = [
        ("birth_certificate", "Birth Certificate"),
        ("passport_photo", "Passport Photograph"),
        ("previous_results", "Previous School Results"),
        ("transfer_certificate", "Transfer Certificate"),
        ("medical_records", "Medical Records"),
        ("immunization_card", "Immunization Card"),
        ("other", "Other Document"),
    ]

    application = models.ForeignKey(
        AdmissionApplication,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPES)
    file = models.FileField(
        upload_to="admission_documents/%Y/%m/",
        validators=[
            FileExtensionValidator(
                allowed_extensions=["pdf", "jpg", "jpeg", "png"]
            )
        ],
    )
    description = models.CharField(max_length=255, blank=True)
    verified = models.BooleanField(
        default=False,
        help_text="Has admin verified this document?",
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_documents",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_notes = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "Admission Document"
        verbose_name_plural = "Admission Documents"

    def __str__(self):
        return f"{self.application.application_number} - {self.get_document_type_display()}"

    def clean(self):
        if self.file.size > 5 * 1024 * 1024:
            raise ValidationError("File size must be under 5MB")


class AdmissionAssessment(models.Model):
    ASSESSMENT_STATUS = [
        ("scheduled", "Scheduled"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("no_show", "No Show"),
        ("cancelled", "Cancelled"),
    ]

    RECOMMENDATION_CHOICES = [
        ("highly_recommended", "Highly Recommended"),
        ("recommended", "Recommended"),
        ("conditional", "Conditional"),
        ("not_recommended", "Not Recommended"),
    ]

    application = models.ForeignKey(
        AdmissionApplication,
        on_delete=models.CASCADE,
        related_name="assessments",
    )
    assessment_type = models.CharField(
        max_length=30,
        choices=AssessmentType.choices,
    )
    scheduled_date = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(
        default=60,
        help_text="Duration in minutes",
    )
    venue = models.CharField(max_length=255, blank=True)
    assessor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conducted_assessments",
        help_text="Staff member conducting assessment",
    )
    status = models.CharField(
        max_length=20,
        choices=ASSESSMENT_STATUS,
        default="scheduled",
    )
    overall_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Overall score achieved",
    )
    max_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100,
        help_text="Maximum possible score",
    )
    pass_mark = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=50,
        help_text="Minimum score to pass",
    )
    passed = models.BooleanField(
        default=False,
        help_text="Whether student passed this assessment",
    )
    assessor_notes = models.TextField(
        blank=True,
        help_text="General notes from assessor",
    )
    strengths = models.TextField(
        blank=True,
        help_text="Student's strengths observed",
    )
    areas_for_improvement = models.TextField(
        blank=True,
        help_text="Areas needing improvement",
    )
    recommendation = models.CharField(
        max_length=20,
        choices=RECOMMENDATION_CHOICES,
        blank=True,
        help_text="Overall recommendation",
    )
    instructions = models.TextField(
        blank=True,
        help_text="Instructions for this assessment",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["scheduled_date"]
        verbose_name = "Admission Assessment"
        verbose_name_plural = "Admission Assessments"
        indexes = [
            models.Index(fields=["scheduled_date"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.application.application_number} - {self.get_assessment_type_display()}"

    def save(self, *args, **kwargs):
        if self.overall_score is not None and self.pass_mark is not None:
            self.passed = self.overall_score >= self.pass_mark
        if self.status == "completed" and not self.completed_at:
            self.completed_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def percentage_score(self):
        if self.overall_score is None or self.max_score is None:
            return None
        return (self.overall_score / self.max_score) * 100

    @property
    def is_upcoming(self):
        return self.status == "scheduled" and self.scheduled_date > timezone.now()

    def calculate_overall_score(self):
        criteria = self.criteria.all()
        if not criteria:
            return None
        total_weighted_score = sum(c.weighted_score for c in criteria)
        total_possible = sum(float(c.max_score) * float(c.weight) for c in criteria)
        if total_possible == 0:
            return None
        self.overall_score = (total_weighted_score / total_possible) * float(self.max_score)
        self.save()
        return self.overall_score


class AssessmentCriterion(models.Model):
    assessment = models.ForeignKey(
        AdmissionAssessment,
        on_delete=models.CASCADE,
        related_name="criteria",
    )
    name = models.CharField(
        max_length=255,
        help_text="e.g., 'Mathematics', 'Communication Skills'",
    )
    max_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Maximum score for this criterion",
    )
    achieved_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Score achieved by student",
    )
    weight = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1.0,
        help_text="Weight/importance multiplier (default 1.0)",
    )
    comments = models.TextField(
        blank=True,
        help_text="Specific feedback for this criterion",
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Display order",
    )

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Assessment Criterion"
        verbose_name_plural = "Assessment Criteria"

    def __str__(self):
        return f"{self.name} ({self.achieved_score}/{self.max_score})"

    @property
    def weighted_score(self):
        return float(self.achieved_score) * float(self.weight)

    @property
    def percentage(self):
        if self.max_score == 0:
            return 0
        return (float(self.achieved_score) / float(self.max_score)) * 100


class AssessmentTemplate(models.Model):
    name = models.CharField(
        max_length=255,
        help_text="e.g., 'JSS 1 Entrance Exam', 'Primary Interview'",
    )
    assessment_type = models.CharField(
        max_length=30,
        choices=AssessmentType.choices,
    )
    description = models.TextField(blank=True)
    applicable_classes = models.ManyToManyField(
        GradeLevel,
        blank=True,
        help_text="Which grade levels can use this template",
    )
    default_duration_minutes = models.PositiveIntegerField(
        default=60,
        help_text="Default duration in minutes",
    )
    default_max_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100,
        help_text="Default maximum score",
    )
    default_pass_mark = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=50,
        help_text="Default pass mark",
    )
    default_instructions = models.TextField(
        blank=True,
        help_text="Default instructions for this assessment",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Only active templates are available for use",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["assessment_type", "name"]
        verbose_name = "Assessment Template"
        verbose_name_plural = "Assessment Templates"

    def __str__(self):
        return f"{self.name} ({self.get_assessment_type_display()})"

    def create_assessment_from_template(self, application, scheduled_date, venue="", assessor=None):
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
    template = models.ForeignKey(
        AssessmentTemplate,
        on_delete=models.CASCADE,
        related_name="template_criteria",
    )
    name = models.CharField(
        max_length=255,
        help_text="e.g., 'Mathematics', 'Communication Skills'",
    )
    max_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Maximum score for this criterion",
    )
    weight = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1.0,
        help_text="Weight/importance multiplier",
    )
    description = models.TextField(
        blank=True,
        help_text="What this criterion assesses",
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Display order",
    )

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Assessment Template Criterion"
        verbose_name_plural = "Assessment Template Criteria"

    def __str__(self):
        return f"{self.template.name} - {self.name}"
