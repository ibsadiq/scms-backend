# Student Admission System Design

## Overview

This design adds a complete admission process before student enrollment, following typical Nigerian school workflows while integrating with your existing system.

## Typical Nigerian School Admission Process

### Standard Workflow:
1. **Application Submission** - Parents submit admission forms with student details
2. **Document Verification** - Check birth certificate, previous school records, etc.
3. **Entrance Examination** (for some classes/schools)
4. **Interview/Assessment** (optional)
5. **Admission Fee Payment** - Pay non-refundable admission processing fee
6. **Admission Decision** - Approve or reject based on criteria
7. **Acceptance & Full Fee Payment** - Parent accepts offer and pays tuition
8. **Enrollment** - Student officially enrolled in class

## Database Schema

### 1. AdmissionApplication Model

```python
# academic/models.py (add to existing file)

class AdmissionStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    SUBMITTED = 'submitted', 'Submitted'
    UNDER_REVIEW = 'under_review', 'Under Review'
    DOCUMENTS_PENDING = 'documents_pending', 'Documents Pending'
    EXAM_SCHEDULED = 'exam_scheduled', 'Exam Scheduled'
    EXAM_COMPLETED = 'exam_completed', 'Exam Completed'
    INTERVIEW_SCHEDULED = 'interview_scheduled', 'Interview Scheduled'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'
    ACCEPTED = 'accepted', 'Accepted (by Parent)'
    ENROLLED = 'enrolled', 'Enrolled'
    WITHDRAWN = 'withdrawn', 'Withdrawn'


class AdmissionApplication(models.Model):
    """
    Admission application for prospective students.
    Maps to Student model after enrollment.
    """
    # Application tracking
    application_number = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        help_text="Auto-generated: e.g., ADM/2025/001"
    )
    status = models.CharField(
        max_length=30,
        choices=AdmissionStatus.choices,
        default=AdmissionStatus.DRAFT
    )
    admission_session = models.ForeignKey(
        AdmissionSession,
        on_delete=models.CASCADE,
        related_name='applications',
        help_text="The admission session this application belongs to"
    )

    # For backward compatibility and easier queries
    @property
    def academic_year(self):
        return self.admission_session.academic_year

    # Student Information
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    gender = models.CharField(
        max_length=10,
        choices=[('male', 'Male'), ('female', 'Female')]
    )
    religion = models.CharField(max_length=50, blank=True)
    state_of_origin = models.CharField(max_length=100)
    lga = models.CharField(max_length=100, verbose_name="LGA")  # Local Government Area

    # Class application
    applying_for_class = models.ForeignKey(
        'academic.ClassRoom',
        on_delete=models.CASCADE,
        related_name='admission_applications',
        help_text="Class/grade student is applying for"
    )

    # Previous School (for transfers)
    previous_school_name = models.CharField(max_length=255, blank=True, null=True)
    previous_school_address = models.TextField(blank=True, null=True)
    previous_class = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Last class completed"
    )
    reason_for_transfer = models.TextField(blank=True, null=True)

    # Parent/Guardian Information
    parent_first_name = models.CharField(max_length=100)
    parent_last_name = models.CharField(max_length=100)
    parent_email = models.EmailField()
    parent_phone = models.CharField(max_length=15)
    parent_occupation = models.CharField(max_length=100, blank=True)
    parent_address = models.TextField()

    # Alternative contact (required in Nigeria)
    alt_contact_name = models.CharField(max_length=200, blank=True)
    alt_contact_phone = models.CharField(max_length=15, blank=True)
    alt_contact_relationship = models.CharField(max_length=50, blank=True)

    # Medical Information
    medical_conditions = models.TextField(
        blank=True,
        help_text="Any known medical conditions, allergies, etc."
    )
    blood_group = models.CharField(
        max_length=5,
        blank=True,
        choices=[
            ('A+', 'A+'), ('A-', 'A-'),
            ('B+', 'B+'), ('B-', 'B-'),
            ('AB+', 'AB+'), ('AB-', 'AB-'),
            ('O+', 'O+'), ('O-', 'O-'),
        ]
    )

    # Examination & Assessment
    entrance_exam_required = models.BooleanField(default=False)
    entrance_exam_date = models.DateTimeField(blank=True, null=True)
    entrance_exam_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True
    )
    entrance_exam_passed = models.BooleanField(default=False)

    interview_required = models.BooleanField(default=False)
    interview_date = models.DateTimeField(blank=True, null=True)
    interview_notes = models.TextField(blank=True)

    # Decision
    reviewed_by = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_applications'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    admin_notes = models.TextField(
        blank=True,
        help_text="Internal notes from admin/reviewers"
    )

    # Payment tracking
    application_fee_paid = models.BooleanField(default=False)
    application_fee_receipt = models.ForeignKey(
        'finance.Receipt',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='application_fee_receipts'
    )

    exam_fee_paid = models.BooleanField(default=False)
    exam_fee_receipt = models.ForeignKey(
        'finance.Receipt',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exam_fee_receipts'
    )

    acceptance_fee_paid = models.BooleanField(default=False)
    acceptance_fee_receipt = models.ForeignKey(
        'finance.Receipt',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='acceptance_fee_receipts'
    )

    # Acceptance deadline
    acceptance_deadline = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Deadline to pay acceptance fee and accept offer"
    )

    # Link to enrolled student (after acceptance)
    enrolled_student = models.OneToOneField(
        'academic.Student',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='admission_application'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['application_number']),
            models.Index(fields=['status', 'academic_year']),
            models.Index(fields=['parent_email']),
            models.Index(fields=['parent_phone']),
        ]

    def __str__(self):
        return f"{self.application_number} - {self.first_name} {self.last_name}"

    def save(self, *args, **kwargs):
        if not self.application_number:
            # Generate application number based on session config
            prefix = self.admission_session.application_number_prefix
            year = self.admission_session.academic_year.year

            last_app = AdmissionApplication.objects.filter(
                admission_session=self.admission_session
            ).order_by('-application_number').first()

            if last_app and last_app.application_number:
                try:
                    last_num = int(last_app.application_number.split('/')[-1])
                    new_num = last_num + 1
                except (ValueError, IndexError):
                    new_num = 1
            else:
                new_num = 1

            self.application_number = f"{prefix}/{year}/{new_num:04d}"

        super().save(*args, **kwargs)

    @property
    def full_name(self):
        return f"{self.first_name} {self.middle_name} {self.last_name}".strip()

    @property
    def age(self):
        """Calculate age as of today"""
        from datetime import date
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )

    def can_transition_to(self, new_status):
        """Validate status transitions"""
        valid_transitions = {
            AdmissionStatus.DRAFT: [AdmissionStatus.SUBMITTED, AdmissionStatus.WITHDRAWN],
            AdmissionStatus.SUBMITTED: [
                AdmissionStatus.UNDER_REVIEW,
                AdmissionStatus.DOCUMENTS_PENDING,
                AdmissionStatus.WITHDRAWN
            ],
            AdmissionStatus.UNDER_REVIEW: [
                AdmissionStatus.EXAM_SCHEDULED,
                AdmissionStatus.INTERVIEW_SCHEDULED,
                AdmissionStatus.APPROVED,
                AdmissionStatus.REJECTED,
                AdmissionStatus.DOCUMENTS_PENDING
            ],
            AdmissionStatus.DOCUMENTS_PENDING: [
                AdmissionStatus.UNDER_REVIEW,
                AdmissionStatus.WITHDRAWN
            ],
            AdmissionStatus.EXAM_SCHEDULED: [
                AdmissionStatus.EXAM_COMPLETED,
                AdmissionStatus.WITHDRAWN
            ],
            AdmissionStatus.EXAM_COMPLETED: [
                AdmissionStatus.INTERVIEW_SCHEDULED,
                AdmissionStatus.APPROVED,
                AdmissionStatus.REJECTED
            ],
            AdmissionStatus.INTERVIEW_SCHEDULED: [
                AdmissionStatus.APPROVED,
                AdmissionStatus.REJECTED,
                AdmissionStatus.WITHDRAWN
            ],
            AdmissionStatus.APPROVED: [
                AdmissionStatus.ACCEPTED,
                AdmissionStatus.WITHDRAWN
            ],
            AdmissionStatus.ACCEPTED: [AdmissionStatus.ENROLLED],
            AdmissionStatus.REJECTED: [],
            AdmissionStatus.ENROLLED: [],
            AdmissionStatus.WITHDRAWN: []
        }

        return new_status in valid_transitions.get(self.status, [])

    def get_fee_structure(self):
        """Get the admission fee structure for this application's class"""
        return AdmissionFeeStructure.objects.filter(
            admission_session=self.admission_session,
            class_room=self.applying_for_class,
            is_active=True
        ).first()

    def calculate_acceptance_deadline(self):
        """Calculate the deadline for paying acceptance fee"""
        if not self.admission_session.require_acceptance_fee:
            return None

        from django.utils import timezone
        from datetime import timedelta

        # Set deadline based on session configuration
        days = self.admission_session.acceptance_fee_deadline_days
        return timezone.now() + timedelta(days=days)

    def is_acceptance_deadline_passed(self):
        """Check if acceptance deadline has passed"""
        if not self.acceptance_deadline:
            return False

        from django.utils import timezone
        return timezone.now() > self.acceptance_deadline

    @property
    def can_accept_offer(self):
        """Check if application can be accepted by parent"""
        if self.status != AdmissionStatus.APPROVED:
            return False

        # Check if acceptance fee is required
        fee_structure = self.get_fee_structure()
        if not fee_structure:
            return True

        # If acceptance fee required, check if paid
        if fee_structure.acceptance_fee_required:
            return self.acceptance_fee_paid

        return True

    @property
    def total_fees_paid(self):
        """Calculate total fees paid so far"""
        total = 0
        if self.application_fee_receipt:
            total += self.application_fee_receipt.amount
        if self.exam_fee_receipt:
            total += self.exam_fee_receipt.amount
        if self.acceptance_fee_receipt:
            total += self.acceptance_fee_receipt.amount
        return total


class AdmissionDocument(models.Model):
    """
    Documents uploaded for admission application.
    """
    DOCUMENT_TYPES = [
        ('birth_certificate', 'Birth Certificate'),
        ('passport_photo', 'Passport Photograph'),
        ('previous_result', 'Previous School Result/Report Card'),
        ('transfer_certificate', 'Transfer Certificate'),
        ('immunization_record', 'Immunization Record'),
        ('parent_id', 'Parent/Guardian ID'),
        ('other', 'Other Document'),
    ]

    application = models.ForeignKey(
        AdmissionApplication,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPES)
    document_file = models.FileField(upload_to='admission_documents/%Y/%m/')
    description = models.CharField(max_length=255, blank=True)
    verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_documents'
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.application.application_number}"


class AssessmentType(models.TextChoices):
    """Types of assessments in admission process"""
    ENTRANCE_EXAM = 'entrance_exam', 'Entrance Examination'
    INTERVIEW = 'interview', 'Interview'
    APTITUDE_TEST = 'aptitude_test', 'Aptitude Test'
    SCREENING = 'screening', 'Screening Test'
    ORAL_TEST = 'oral_test', 'Oral Test'
    PRACTICAL = 'practical', 'Practical Assessment'
    PSYCHOMETRIC = 'psychometric', 'Psychometric Test'
    PORTFOLIO_REVIEW = 'portfolio_review', 'Portfolio Review'


class AdmissionAssessment(models.Model):
    """
    Comprehensive assessment/evaluation for admission applications.
    Supports multiple types: exams, interviews, aptitude tests, etc.
    """
    application = models.ForeignKey(
        AdmissionApplication,
        on_delete=models.CASCADE,
        related_name='assessments'
    )
    assessment_type = models.CharField(
        max_length=30,
        choices=AssessmentType.choices,
        default=AssessmentType.ENTRANCE_EXAM
    )

    # Scheduling
    scheduled_date = models.DateTimeField(
        help_text="Date and time of assessment"
    )
    duration_minutes = models.PositiveIntegerField(
        default=60,
        help_text="Duration of assessment in minutes"
    )
    venue = models.CharField(
        max_length=255,
        blank=True,
        help_text="Location/room for assessment"
    )

    # Instructions
    instructions = models.TextField(
        blank=True,
        help_text="Instructions for the applicant (what to bring, etc.)"
    )

    # Assessor
    assessor = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='conducted_assessments',
        help_text="Staff member conducting the assessment"
    )

    # Status
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='scheduled'
    )

    # Results - Overall
    overall_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Overall score/percentage (0-100)"
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
        blank=True,
        null=True,
        help_text="Minimum score required to pass"
    )
    passed = models.BooleanField(
        default=False,
        help_text="Whether applicant passed this assessment"
    )

    # Detailed feedback
    assessor_notes = models.TextField(
        blank=True,
        help_text="Assessor's notes and observations"
    )
    strengths = models.TextField(
        blank=True,
        help_text="Identified strengths"
    )
    areas_for_improvement = models.TextField(
        blank=True,
        help_text="Areas that need improvement"
    )
    recommendation = models.CharField(
        max_length=20,
        choices=[
            ('highly_recommended', 'Highly Recommended'),
            ('recommended', 'Recommended'),
            ('acceptable', 'Acceptable'),
            ('not_recommended', 'Not Recommended'),
        ],
        blank=True
    )

    # Timestamps
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['scheduled_date']
        indexes = [
            models.Index(fields=['application', 'assessment_type']),
            models.Index(fields=['scheduled_date']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.get_assessment_type_display()} - {self.application.application_number}"

    @property
    def percentage_score(self):
        """Calculate percentage score"""
        if self.overall_score and self.max_score:
            return (self.overall_score / self.max_score) * 100
        return None

    @property
    def is_upcoming(self):
        """Check if assessment is upcoming"""
        from django.utils import timezone
        return self.status == 'scheduled' and self.scheduled_date > timezone.now()

    @property
    def is_overdue(self):
        """Check if scheduled assessment is overdue"""
        from django.utils import timezone
        return self.status == 'scheduled' and self.scheduled_date < timezone.now()


class AssessmentCriterion(models.Model):
    """
    Individual criteria/components for an assessment.
    Allows breaking down assessments into multiple criteria.
    """
    assessment = models.ForeignKey(
        AdmissionAssessment,
        on_delete=models.CASCADE,
        related_name='criteria'
    )
    name = models.CharField(
        max_length=255,
        help_text="E.g., 'Mathematics', 'English', 'Communication Skills', 'Confidence'"
    )
    description = models.TextField(blank=True)

    # Scoring
    max_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Maximum score for this criterion"
    )
    achieved_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Score achieved by applicant"
    )
    weight = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1.0,
        help_text="Weight/importance of this criterion (1.0 = normal)"
    )

    # Feedback
    comments = models.TextField(
        blank=True,
        help_text="Specific feedback for this criterion"
    )

    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'name']
        verbose_name_plural = "Assessment Criteria"

    def __str__(self):
        return f"{self.name} - {self.assessment}"

    @property
    def percentage(self):
        """Calculate percentage for this criterion"""
        if self.achieved_score and self.max_score:
            return (self.achieved_score / self.max_score) * 100
        return None

    @property
    def weighted_score(self):
        """Calculate weighted score"""
        if self.achieved_score:
            return self.achieved_score * float(self.weight)
        return None


class AssessmentTemplate(models.Model):
    """
    Predefined assessment templates for different class levels.
    Allows creating consistent assessments across admission sessions.
    """
    name = models.CharField(
        max_length=255,
        help_text="E.g., 'Primary 1 Entrance Exam', 'JSS 1 Interview Template'"
    )
    assessment_type = models.CharField(
        max_length=30,
        choices=AssessmentType.choices
    )
    description = models.TextField(blank=True)

    # Default settings
    default_duration_minutes = models.PositiveIntegerField(default=60)
    default_max_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100
    )
    default_pass_mark = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Minimum score to pass"
    )
    default_instructions = models.TextField(
        blank=True,
        help_text="Standard instructions for this assessment"
    )

    # Applicable classes
    applicable_classes = models.ManyToManyField(
        'academic.ClassRoom',
        related_name='assessment_templates',
        blank=True,
        help_text="Classes this template can be used for"
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_assessment_type_display()})"

    def create_assessment_for_application(self, application, scheduled_date, venue='', assessor=None):
        """
        Create an assessment instance from this template for an application.
        """
        assessment = AdmissionAssessment.objects.create(
            application=application,
            assessment_type=self.assessment_type,
            scheduled_date=scheduled_date,
            duration_minutes=self.default_duration_minutes,
            venue=venue,
            instructions=self.default_instructions,
            assessor=assessor,
            max_score=self.default_max_score,
            pass_mark=self.default_pass_mark,
        )

        # Copy criteria from template
        for template_criterion in self.criteria.all():
            AssessmentCriterion.objects.create(
                assessment=assessment,
                name=template_criterion.name,
                description=template_criterion.description,
                max_score=template_criterion.max_score,
                weight=template_criterion.weight,
                display_order=template_criterion.display_order,
            )

        return assessment


class AssessmentTemplateCriterion(models.Model):
    """
    Predefined criteria for assessment templates.
    """
    template = models.ForeignKey(
        AssessmentTemplate,
        on_delete=models.CASCADE,
        related_name='criteria'
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    max_score = models.DecimalField(max_digits=5, decimal_places=2)
    weight = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1.0
    )
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'name']
        verbose_name_plural = "Assessment Template Criteria"

    def __str__(self):
        return f"{self.name} - {self.template.name}"


class AdmissionSession(models.Model):
    """
    Configuration for each admission cycle/session.
    Allows customizing the admission process per academic year.
    """
    academic_year = models.OneToOneField(
        'administration.AcademicYear',
        on_delete=models.CASCADE,
        related_name='admission_session'
    )
    name = models.CharField(
        max_length=100,
        help_text="E.g., '2025/2026 Admission'"
    )

    # Session period
    start_date = models.DateField(help_text="When applications open")
    end_date = models.DateField(help_text="When applications close")

    # Acceptance fee configuration
    require_acceptance_fee = models.BooleanField(
        default=True,
        help_text="Whether parents must pay acceptance fee to accept admission"
    )
    acceptance_fee_deadline_days = models.PositiveIntegerField(
        default=14,
        help_text="Days after approval for parent to pay acceptance fee and accept offer"
    )

    # General settings
    allow_public_applications = models.BooleanField(
        default=True,
        help_text="Allow new applications from public portal"
    )
    auto_assign_application_number = models.BooleanField(
        default=True,
        help_text="Auto-generate application numbers (ADM/2025/001)"
    )
    application_number_prefix = models.CharField(
        max_length=10,
        default='ADM',
        help_text="Prefix for application numbers"
    )

    # Email notifications
    send_confirmation_emails = models.BooleanField(default=True)
    send_status_update_emails = models.BooleanField(default=True)
    admin_notification_email = models.EmailField(
        blank=True,
        null=True,
        help_text="Email to notify about new applications (defaults to school contact email)"
    )

    # Instructions/messages
    application_instructions = models.TextField(
        blank=True,
        help_text="Instructions shown on application form"
    )
    approval_message = models.TextField(
        blank=True,
        help_text="Custom message in approval email (optional)"
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Only one session can be active at a time"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-academic_year__year']
        verbose_name = "Admission Session"
        verbose_name_plural = "Admission Sessions"

    def __str__(self):
        return f"{self.name} ({self.academic_year.year})"

    def save(self, *args, **kwargs):
        """Ensure only one active session at a time"""
        if self.is_active:
            AdmissionSession.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_active_session(cls):
        """Get the currently active admission session"""
        return cls.objects.filter(is_active=True).first()

    @property
    def is_open(self):
        """Check if applications are currently being accepted"""
        from django.utils import timezone
        today = timezone.now().date()
        return self.allow_public_applications and self.start_date <= today <= self.end_date

    @property
    def days_remaining(self):
        """Days until application deadline"""
        from django.utils import timezone
        today = timezone.now().date()
        if today > self.end_date:
            return 0
        return (self.end_date - today).days


class AdmissionFeeStructure(models.Model):
    """
    Defines admission fees for different classes/streams.
    Separate from tuition fees (FeeStructure).
    Now linked to AdmissionSession for per-session configuration.
    """
    admission_session = models.ForeignKey(
        AdmissionSession,
        on_delete=models.CASCADE,
        related_name='fee_structures'
    )
    class_room = models.ForeignKey(
        'academic.ClassRoom',
        on_delete=models.CASCADE,
        related_name='admission_fee_structures',
        help_text="Class this fee applies to"
    )

    # Admission-specific fees
    application_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Non-refundable application processing fee"
    )
    application_fee_required = models.BooleanField(
        default=True,
        help_text="Must pay application fee before submission"
    )

    entrance_exam_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Fee for entrance examination (if required)"
    )
    entrance_exam_required = models.BooleanField(
        default=False,
        help_text="Whether entrance exam is mandatory for this class"
    )
    entrance_exam_pass_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Minimum score to pass entrance exam (e.g., 50.00 for 50%)"
    )

    acceptance_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Fee to accept admission offer (can be part of first term fee)"
    )
    acceptance_fee_required = models.BooleanField(
        default=True,
        help_text="Must pay acceptance fee to confirm enrollment"
    )
    acceptance_fee_is_part_of_tuition = models.BooleanField(
        default=True,
        help_text="If true, acceptance fee is deducted from first term tuition"
    )

    # Interview settings
    interview_required = models.BooleanField(
        default=False,
        help_text="Whether interview is mandatory for this class"
    )

    # Capacity
    max_applications = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Maximum number of applications to accept (leave blank for unlimited)"
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['admission_session', 'class_room']
        ordering = ['admission_session', 'class_room']
        verbose_name = "Admission Fee Structure"
        verbose_name_plural = "Admission Fee Structures"

    def __str__(self):
        return f"{self.class_room.name} - {self.admission_session.name}"

    @property
    def total_fees_required(self):
        """Total mandatory fees for this class"""
        total = 0
        if self.application_fee_required:
            total += self.application_fee
        if self.entrance_exam_required:
            total += self.entrance_exam_fee
        if self.acceptance_fee_required:
            total += self.acceptance_fee
        return total

    @property
    def total_fees_possible(self):
        """Total possible fees (including optional)"""
        return self.application_fee + self.entrance_exam_fee + self.acceptance_fee

    @property
    def applications_count(self):
        """Number of applications for this class in this session"""
        return self.class_room.admission_applications.filter(
            academic_year=self.admission_session.academic_year
        ).count()

    @property
    def is_full(self):
        """Check if max applications reached"""
        if not self.max_applications:
            return False
        return self.applications_count >= self.max_applications
```

### 2. Integration with Existing Models

**Student Model - Add tracking field:**
```python
# academic/models.py - Add to existing Student model

class Student(models.Model):
    # ... existing fields ...

    # New field to track admission source
    admission_type = models.CharField(
        max_length=20,
        choices=[
            ('new', 'New Admission'),
            ('transfer', 'Transfer'),
            ('promoted', 'Promoted'),
            ('legacy', 'Legacy (Direct Enrollment)'),
        ],
        default='legacy',
        help_text="How student was enrolled"
    )
```

## API Endpoints

### Public Endpoints (No Authentication - For External Portal)

```
# Session Information
GET    /api/public/admissions/session/                    # Get active admission session info
GET    /api/public/admissions/classes/                    # List available classes for application
GET    /api/public/admissions/states/                     # Nigerian states and LGAs

# Application Submission (External Form)
POST   /api/public/admissions/applications/               # Submit new application
GET    /api/public/admissions/applications/track/         # Track application (requires app_number + email/phone)
PATCH  /api/public/admissions/applications/{token}/       # Update draft application (before submission)
POST   /api/public/admissions/applications/{token}/submit/# Submit application (DRAFT → SUBMITTED)

# Document Upload (Public)
POST   /api/public/admissions/applications/{token}/documents/ # Upload documents
GET    /api/public/admissions/applications/{token}/documents/ # List uploaded documents

# Acceptance (Public)
POST   /api/public/admissions/applications/{token}/accept/    # Accept admission offer
GET    /api/public/admissions/applications/{token}/payment/   # Get payment instructions

# Payment Webhook (for payment gateway callbacks)
POST   /api/public/admissions/webhooks/payment/           # Payment confirmation webhook
```

### Admin/Staff Endpoints (Authenticated)

```
# Session Management
GET    /api/admissions/sessions/                          # List all admission sessions
POST   /api/admissions/sessions/                          # Create new session
GET    /api/admissions/sessions/{id}/                     # Session details
PATCH  /api/admissions/sessions/{id}/                     # Update session
POST   /api/admissions/sessions/{id}/activate/            # Activate session (deactivates others)
GET    /api/admissions/sessions/{id}/statistics/          # Session statistics

# Application Management
GET    /api/admissions/applications/                      # List all applications (with filters)
GET    /api/admissions/applications/{id}/                 # Application details
PATCH  /api/admissions/applications/{id}/                 # Update application
DELETE /api/admissions/applications/{id}/                 # Delete application (admin only)

# Workflow Actions
POST   /api/admissions/applications/{id}/review/          # Start review (SUBMITTED → UNDER_REVIEW)
POST   /api/admissions/applications/{id}/request-documents/ # Request missing documents
POST   /api/admissions/applications/{id}/schedule-exam/   # Schedule entrance exam
POST   /api/admissions/applications/{id}/record-exam/     # Record exam results
POST   /api/admissions/applications/{id}/schedule-interview/ # Schedule interview
POST   /api/admissions/applications/{id}/approve/         # Approve application (sets deadline)
POST   /api/admissions/applications/{id}/reject/          # Reject application
POST   /api/admissions/applications/{id}/enroll/          # Convert to enrolled student
POST   /api/admissions/applications/{id}/withdraw/        # Withdraw application

# Document Management
GET    /api/admissions/applications/{id}/documents/       # List application documents
POST   /api/admissions/documents/{id}/verify/             # Verify a document
POST   /api/admissions/documents/{id}/reject/             # Reject a document

# Assessment Management
GET    /api/admissions/applications/{id}/assessments/     # List all assessments for application
POST   /api/admissions/applications/{id}/assessments/     # Create new assessment
GET    /api/admissions/assessments/{id}/                  # Assessment details
PATCH  /api/admissions/assessments/{id}/                  # Update assessment
DELETE /api/admissions/assessments/{id}/                  # Delete assessment
POST   /api/admissions/assessments/{id}/start/            # Start assessment (mark in_progress)
POST   /api/admissions/assessments/{id}/complete/         # Complete assessment with results
POST   /api/admissions/assessments/{id}/mark-no-show/     # Mark applicant as no-show
POST   /api/admissions/assessments/{id}/cancel/           # Cancel assessment

# Assessment Criteria
GET    /api/admissions/assessments/{id}/criteria/         # List criteria for assessment
POST   /api/admissions/assessments/{id}/criteria/         # Add criterion
PATCH  /api/admissions/criteria/{id}/                     # Update criterion score/feedback
DELETE /api/admissions/criteria/{id}/                     # Delete criterion

# Assessment Templates
GET    /api/admissions/assessment-templates/              # List all templates
POST   /api/admissions/assessment-templates/              # Create template
GET    /api/admissions/assessment-templates/{id}/         # Template details
PATCH  /api/admissions/assessment-templates/{id}/         # Update template
DELETE /api/admissions/assessment-templates/{id}/         # Delete template
POST   /api/admissions/assessment-templates/{id}/use/     # Create assessment from template

# Reporting
GET    /api/admissions/statistics/                        # Overall admission statistics
GET    /api/admissions/reports/by-status/                 # Applications grouped by status
GET    /api/admissions/reports/by-class/                  # Applications grouped by class
GET    /api/admissions/reports/revenue/                   # Admission fee revenue
GET    /api/admissions/reports/assessment-performance/    # Assessment pass rates, averages
GET    /api/admissions/export/csv/                        # Export applications to CSV
GET    /api/admissions/export/excel/                      # Export applications to Excel
```

### Fee Structure Endpoints (Admin)

```
GET    /api/admissions/fee-structures/                    # List admission fee structures
POST   /api/admissions/fee-structures/                    # Create fee structure
GET    /api/admissions/fee-structures/{id}/               # Fee structure details
PATCH  /api/admissions/fee-structures/{id}/               # Update fee structure
DELETE /api/admissions/fee-structures/{id}/               # Delete fee structure
POST   /api/admissions/fee-structures/bulk-create/        # Create fees for all classes in session
```

## Workflow Implementation

### 1. Application Submission (Parent/Public - External Form)

**Important:** The admission form is typically completed from an **external source** (public website/portal), not from within the authenticated school management system.

**Process:**
1. Parent visits **public admission portal** (external, no login required)
2. Fills application form with:
   - Student details (name, DOB, gender, religion, state, LGA)
   - Parent/guardian details (name, email, phone, address, occupation)
   - Alternative contact person (common in Nigeria)
   - Class applying for (dropdown from available classes)
   - Previous school information (for transfers)
   - Medical information (conditions, blood group)
3. System validates:
   - Active admission session exists
   - Class is accepting applications (not full)
   - Student age meets class requirements
4. System generates application number (e.g., ADM/2025/001)
5. Status: DRAFT (auto-save) → SUBMITTED (when parent clicks submit)
6. Emails sent:
   - **To parent:** Application confirmation with application number, tracking link, payment instructions
   - **To admin:** New application notification (if configured in session)
7. Parent receives tracking credentials to check status later

**Payment (Configurable per Session):**
- Application fee requirement controlled by `AdmissionFeeStructure.application_fee_required`
- If required and unpaid: Status stays SUBMITTED (cannot progress)
- After payment: SUBMITTED → UNDER_REVIEW
- If not required: SUBMITTED → UNDER_REVIEW (automatic)

**External Portal Features:**
- No authentication needed to submit application
- Application number used for tracking (with email verification)
- Parent can save draft and continue later
- Mobile-responsive form
- Payment gateway integration (Paystack, Flutterwave common in Nigeria)

### 2. Document Upload

**Process:**
1. Parent logs in with application number/email
2. Uploads required documents (birth cert, passport photo, etc.)
3. Admin receives notification
4. Admin verifies each document
5. If documents incomplete: UNDER_REVIEW → DOCUMENTS_PENDING
6. Email sent to parent requesting missing documents

### 3. Assessment Process (Comprehensive)

The system supports **multiple types of assessments**, not just exams and interviews. Each application can have multiple assessments.

#### Assessment Types Supported:
1. **Entrance Examination** - Written test (Mathematics, English, etc.)
2. **Interview** - One-on-one or panel interview
3. **Aptitude Test** - Logical reasoning, problem-solving
4. **Screening Test** - Quick assessment
5. **Oral Test** - Verbal assessment
6. **Practical Assessment** - Hands-on skills
7. **Psychometric Test** - Personality/behavior assessment
8. **Portfolio Review** - For creative/arts programs

#### 3a. Creating Assessments

**Option 1: From Template (Recommended)**
```python
# Admin creates assessment from template
template = AssessmentTemplate.objects.get(name="Primary 1 Entrance Exam")
assessment = template.create_assessment_for_application(
    application=application,
    scheduled_date="2025-02-15 09:00",
    venue="Exam Hall A",
    assessor=teacher_user
)
# Automatically creates assessment with predefined criteria
```

**Option 2: Manual Creation**
Admin manually creates assessment with custom criteria.

#### 3b. Scheduling Assessment

**Process:**
1. Admin selects application
2. Clicks "Schedule Assessment"
3. Selects assessment type (entrance exam, interview, etc.)
4. Chooses template (optional) or creates custom
5. Sets:
   - Date and time
   - Duration (minutes)
   - Venue/location
   - Assessor (staff member)
   - Instructions (what to bring, etc.)
6. Status: UNDER_REVIEW → EXAM_SCHEDULED or INTERVIEW_SCHEDULED
7. Email sent to parent with:
   - Assessment type
   - Date, time, venue
   - Duration
   - What to bring
   - Google Maps link to venue (optional)
   - Payment link if exam fee required

**Payment:**
- If exam fee required and unpaid: Assessment scheduled but parent must pay
- After payment confirmed: Assessment is confirmed
- Email confirmation sent

#### 3c. Conducting Assessment

**During Assessment:**
1. Assessor marks attendance:
   - Status: scheduled → in_progress (present)
   - OR: scheduled → no_show (absent)
2. For entrance exams with multiple subjects:
   - Each subject is a criterion (Mathematics, English, etc.)
   - Assessor enters scores for each subject
   - System calculates overall score
3. For interviews:
   - Criteria might be: Communication, Confidence, Knowledge, etc.
   - Assessor rates each criterion
   - Assessor adds notes, strengths, areas for improvement

**Example: Entrance Exam Criteria**
```python
# Primary 1 Entrance Exam has 3 subjects
criteria = [
    {'name': 'Mathematics', 'max_score': 40, 'achieved_score': 35},
    {'name': 'English', 'max_score': 40, 'achieved_score': 32},
    {'name': 'General Knowledge', 'max_score': 20, 'achieved_score': 15},
]
# Overall: 82/100 = 82% (PASS if pass_mark is 50%)
```

**Example: Interview Criteria**
```python
# JSS 1 Interview assessment
criteria = [
    {'name': 'Communication Skills', 'max_score': 10, 'achieved_score': 8},
    {'name': 'Confidence', 'max_score': 10, 'achieved_score': 7},
    {'name': 'Subject Knowledge', 'max_score': 10, 'achieved_score': 9, 'weight': 1.5},  # Weighted higher
    {'name': 'Teamwork/Social Skills', 'max_score': 10, 'achieved_score': 8},
]
# System calculates weighted average
```

#### 3d. Recording Results

**Process:**
1. Assessor completes scoring all criteria
2. System auto-calculates overall score
3. System checks if score ≥ pass_mark
4. Assessor adds:
   - Notes/observations
   - Strengths identified
   - Areas for improvement
   - Recommendation (Highly Recommended / Recommended / Acceptable / Not Recommended)
5. Assessor clicks "Complete Assessment"
6. Status: in_progress → completed
7. Application status: EXAM_COMPLETED or back to UNDER_REVIEW

**Auto-Decision Based on Assessment:**
- If all required assessments completed AND all passed:
  - Admin can proceed to approve
- If any required assessment failed:
  - Admin sees warning
  - Can still approve (override) with reason
  - Or reject application

#### 3e. Multiple Assessments

Applications can have **multiple assessments**:

**Example Workflow for JSS 1:**
1. **Written Exam** (Mathematics, English, Science) - 60 minutes
2. **Aptitude Test** (Logical reasoning) - 30 minutes
3. **Interview** (Panel interview) - 15 minutes

Each assessment is tracked separately with its own:
- Schedule
- Venue
- Assessor
- Criteria
- Results
- Feedback

**Viewing Results:**
```
Application: ADM/2025/042 - John Doe

Assessments:
1. ✅ Entrance Examination (Completed)
   Date: Feb 15, 2025 9:00 AM
   Venue: Exam Hall A
   Score: 85/100 (85%) - PASSED
   - Mathematics: 38/40
   - English: 35/40
   - Science: 12/20
   Recommendation: Recommended

2. ✅ Interview (Completed)
   Date: Feb 20, 2025 2:00 PM
   Venue: Principal's Office
   Score: 42/50 (84%) - PASSED
   - Communication: 9/10
   - Confidence: 7/10
   - Knowledge: 18/20 (weighted 1.5x)
   - Social Skills: 8/10
   Recommendation: Highly Recommended
   Notes: "Excellent candidate, shows strong aptitude"

Overall Assessment: PASSED ALL ASSESSMENTS
Admin Decision: Ready for approval
```

### 5. Admission Decision

**Approval:**
1. Admin clicks "Approve Application"
2. System automatically:
   - Changes status: → APPROVED
   - Calculates acceptance deadline (based on `AdmissionSession.acceptance_fee_deadline_days`)
   - Sets `application.acceptance_deadline` field
3. Email sent to parent with:
   - Congratulations message
   - Custom approval message (if set in `AdmissionSession.approval_message`)
   - **If acceptance fee required:**
     - Acceptance fee amount (from `AdmissionFeeStructure.acceptance_fee`)
     - Payment deadline (e.g., "You have 14 days to accept this offer")
     - Payment instructions and link
     - Note if fee is part of tuition or separate
   - **If acceptance fee NOT required:**
     - Simple "Accept Offer" button in portal
   - Portal link to respond to offer

**Rejection:**
1. Admin rejects: → REJECTED
2. Admin enters rejection reason (optional but recommended)
3. Email sent with:
   - Polite rejection notice
   - Reason (if provided)
   - Encouragement to reapply next session
   - Contact information for questions

### 6. Parent Acceptance (Configurable)

**Scenario A: Acceptance Fee Required** (Most common in Nigerian schools)
1. Parent receives approval email
2. Parent pays acceptance fee via payment link
3. System updates:
   - `application.acceptance_fee_paid = True`
   - Links receipt to `application.acceptance_fee_receipt`
4. Parent clicks "Accept Offer" button in portal (enabled after payment)
5. Status: APPROVED → ACCEPTED
6. Email confirmation sent

**Scenario B: Acceptance Fee NOT Required**
1. Parent receives approval email
2. Parent simply clicks "Accept Offer" in portal
3. Status: APPROVED → ACCEPTED (immediate)
4. Email confirmation sent

**Scenario C: Acceptance Fee Optional**
1. Same as Scenario B, but parent is encouraged to pay
2. Acceptance can proceed without payment
3. Fee tracked for later collection

**Deadline Handling:**
- If `acceptance_deadline` passes without response:
  - Admin receives notification
  - Application stays APPROVED (admin can manually withdraw if needed)
  - System can auto-send reminder emails before deadline

### 7. Enrollment (Final Step)

**Process:**
1. Admin clicks "Enroll Student"
2. System automatically:
   - Creates Student record from application data
   - Creates/links Parent record (reuses if phone exists)
   - Creates StudentClassEnrollment
   - Assigns FeeStructure for the term
   - Creates student login credentials
   - Sends welcome email with credentials to parent
3. Status: ACCEPTED → ENROLLED
4. Application is now complete

## Email Templates Needed

### 1. Application Submission Confirmation
```python
# core/email_utils.py

def send_application_confirmation(application):
    """Email sent when application is submitted"""
    context = {
        'parent_name': f"{application.parent_first_name} {application.parent_last_name}",
        'student_name': application.full_name,
        'application_number': application.application_number,
        'class_applied': application.applying_for_class.name,
        'tracking_url': f"{settings.FRONTEND_URL}/track-application/{application.application_number}",
    }

    return send_email(
        subject=f"Application Received - {application.application_number}",
        to_email=application.parent_email,
        template_name='admission_confirmation',
        context=context
    )
```

### 2. Application Status Updates
- Document verification request
- Exam schedule notification
- Interview schedule notification
- Approval notification (with payment link)
- Rejection notification
- Enrollment confirmation

### 3. Admin Notifications
- New application received
- Document uploaded
- Payment received
- Application approaching deadline

## Nigerian School-Specific Features

### Age Requirements
```python
# Validation in serializer
def validate_date_of_birth(self, value):
    """Ensure student meets age requirement for class"""
    from datetime import date

    age = date.today().year - value.year
    class_level = self.initial_data.get('applying_for_class')

    # Example: Primary 1 requires age 5-7
    age_requirements = {
        'Primary 1': (5, 7),
        'Primary 2': (6, 8),
        # ... etc
    }

    min_age, max_age = age_requirements.get(class_level, (0, 100))
    if not (min_age <= age <= max_age):
        raise serializers.ValidationError(
            f"Student must be between {min_age} and {max_age} years old for {class_level}"
        )

    return value
```

### State of Origin & LGA
- Required fields for Nigerian students
- Dropdown with all Nigerian states
- LGA dropdown based on selected state

### Multiple Contacts
- Primary parent contact
- Alternative contact (common in Nigeria)
- Both with relationship field

### Previous School Information
- Essential for transfer students
- Reason for transfer field
- Previous class completed

### Medical Information
- Blood group (important in Nigeria)
- Medical conditions/allergies
- For school health records

## Integration Points

### With Existing Student Enrollment
```python
def enroll_student_from_application(application):
    """
    Convert approved application to enrolled student.
    Integrates with existing enrollment system.
    """
    from django.db import transaction

    with transaction.atomic():
        # 1. Create Student (your existing model)
        student = Student.objects.create(
            first_name=application.first_name,
            middle_name=application.middle_name,
            last_name=application.last_name,
            date_of_birth=application.date_of_birth,
            gender=application.gender,
            religion=application.religion,
            admission_type='new',  # or 'transfer'
            is_active=True,
            # admission_number auto-generated by your existing logic
        )

        # 2. Link/Create Parent (reuses existing parent if phone matches)
        parent, created = Parent.objects.get_or_create(
            phoneNumber=application.parent_phone,
            defaults={
                'first_name': application.parent_first_name,
                'last_name': application.parent_last_name,
                'email': application.parent_email,
                'occupation': application.parent_occupation,
                'address': application.parent_address,
            }
        )
        student.parent_guardian = parent
        student.save()

        # 3. Create Class Enrollment (your existing StudentClassEnrollment)
        StudentClassEnrollment.objects.create(
            student=student,
            class_room=application.applying_for_class,
            academic_year=application.academic_year,
            enrollment_date=timezone.now().date()
        )

        # 4. Assign Fees (your existing FeeStructure system)
        current_term = Term.objects.filter(is_current=True).first()
        if current_term:
            fee_structure = FeeStructure.objects.filter(
                class_room=application.applying_for_class,
                term=current_term
            ).first()

            if fee_structure:
                StudentFeeAssignment.objects.create(
                    student=student,
                    fee_structure=fee_structure,
                    academic_year=application.academic_year,
                    term=current_term
                )

        # 5. Link application to student
        application.enrolled_student = student
        application.status = AdmissionStatus.ENROLLED
        application.save()

        # 6. Send welcome email (your existing function)
        from core.email_utils import send_welcome_parent_email
        send_welcome_parent_email(parent)

        return student
```

### With Finance System
```python
# Admission fee receipts link to finance.Receipt model
# When parent pays admission fee:

receipt = Receipt.objects.create(
    payer=f"{application.parent_first_name} {application.parent_last_name}",
    amount=admission_fee_structure.application_fee,
    payment_reason=f"Admission Application Fee - {application.application_number}",
    term=current_term,
    # ... other receipt fields
)

application.admission_fee_paid = True
application.admission_fee_receipt = receipt
application.save()
```

## Dashboard Statistics

**Admin Dashboard Metrics:**
- Total applications (current year)
- Applications by status (pie chart)
- Approval rate (%)
- Applications by class
- Pending reviews count
- Documents pending verification
- Upcoming exams/interviews
- Revenue from admission fees

**Sample Stats API Response:**
```json
{
  "total_applications": 245,
  "by_status": {
    "submitted": 45,
    "under_review": 67,
    "approved": 89,
    "enrolled": 34,
    "rejected": 10
  },
  "approval_rate": 89.9,
  "by_class": {
    "Primary 1": 78,
    "Primary 2": 45,
    "JSS 1": 56
  },
  "pending_actions": {
    "needs_review": 45,
    "documents_pending": 12,
    "exams_scheduled": 8
  },
  "revenue": {
    "application_fees": 245000,
    "exam_fees": 134000,
    "acceptance_fees": 890000
  }
}
```

## File Structure

```
academic/
├── models.py (add AdmissionApplication, AdmissionDocument, AdmissionFeeStructure)
├── serializers.py (add admission serializers)
├── views_admissions.py (new file for admission views)
├── permissions.py (add admission permissions)

api/admissions/
├── __init__.py
├── urls.py (admission API routes)

core/
├── email_utils.py (add admission email functions)
├── templates/email/
    ├── admission_confirmation.html
    ├── admission_approved.html
    ├── admission_rejected.html
    ├── exam_scheduled.html
    ├── interview_scheduled.html
    ├── enrollment_complete.html

finance/
├── models.py (existing - Receipt model integrates with admission fees)
```

## Migration Strategy

### Phase 1: Database Models
1. Create AdmissionApplication, AdmissionDocument, AdmissionFeeStructure models
2. Add `admission_type` field to Student model
3. Run migrations

### Phase 2: Admin Interface
1. Create admin views for managing applications
2. Add document verification UI
3. Add exam/interview scheduling UI
4. Add enrollment action

### Phase 3: Public Portal
1. Create public application form
2. Add application tracking page
3. Add document upload interface
4. Add payment integration

### Phase 4: Email & Notifications
1. Add all email templates
2. Implement email triggers at each status change
3. Add SMS notifications (optional - common in Nigeria)

### Phase 5: Testing & Launch
1. Test complete workflow end-to-end
2. Train admin staff
3. Launch admission cycle

## Key Benefits

✅ **Organized Process**: Clear workflow from application to enrollment
✅ **Highly Configurable**: Per-session settings for fees, deadlines, and requirements
✅ **Flexible Acceptance Fee**: Can be mandatory, optional, or disabled per session
✅ **Document Management**: Track and verify all required documents
✅ **Payment Tracking**: Separate admission fees from tuition fees (application, exam, acceptance)
✅ **Nigerian Context**: State/LGA, multiple contacts, age requirements, payment gateways
✅ **External Portal**: Public application form (no login required)
✅ **Seamless Integration**: Uses your existing Student, Parent, Fee models
✅ **Audit Trail**: Complete history of application journey
✅ **Automated Emails**: Parents stay informed at every step
✅ **Data Quality**: All student data verified before enrollment
✅ **Reporting**: Admission statistics and analytics
✅ **Deadline Management**: Automatic acceptance deadline calculation and reminders

## Configuration Examples

### Example 1: Strict Admission with All Fees
```python
# Create admission session for 2025/2026
session = AdmissionSession.objects.create(
    academic_year=academic_year_2025,
    name="2025/2026 Admission",
    start_date="2025-01-01",
    end_date="2025-03-31",
    require_acceptance_fee=True,  # ← Acceptance fee mandatory
    acceptance_fee_deadline_days=14,  # Parent has 14 days to respond
    allow_public_applications=True,
    send_confirmation_emails=True,
    is_active=True
)

# Set up fees for Primary 1
AdmissionFeeStructure.objects.create(
    admission_session=session,
    class_room=primary_1_class,
    application_fee=5000,  # ₦5,000
    application_fee_required=True,
    entrance_exam_fee=10000,  # ₦10,000
    entrance_exam_required=True,
    entrance_exam_pass_score=50.00,  # 50% to pass
    acceptance_fee=50000,  # ₦50,000
    acceptance_fee_required=True,  # ← Must pay to accept offer
    acceptance_fee_is_part_of_tuition=True,  # Deducted from first term fee
    interview_required=True,
    max_applications=100  # Only accept 100 applications
)
```

**Workflow:** Parent pays application fee → takes exam → interview → if approved, pays ₦50k acceptance fee within 14 days → clicks accept → gets enrolled

### Example 2: Simple Admission - No Acceptance Fee
```python
# Create session without acceptance fee requirement
session = AdmissionSession.objects.create(
    academic_year=academic_year_2025,
    name="2025/2026 Admission (Simplified)",
    start_date="2025-01-01",
    end_date="2025-03-31",
    require_acceptance_fee=False,  # ← No acceptance fee needed
    allow_public_applications=True,
    is_active=True
)

# Minimal fees for Nursery classes
AdmissionFeeStructure.objects.create(
    admission_session=session,
    class_room=nursery_class,
    application_fee=2000,  # ₦2,000
    application_fee_required=True,
    entrance_exam_required=False,  # No exam for nursery
    acceptance_fee=0,
    acceptance_fee_required=False,  # ← Not required
    interview_required=False,
)
```

**Workflow:** Parent pays ₦2k application fee → admin reviews documents → if approved, parent simply clicks "Accept Offer" → gets enrolled (no waiting for payment)

### Example 3: Optional Acceptance Fee (Flexible)
```python
session = AdmissionSession.objects.create(
    academic_year=academic_year_2025,
    name="2025/2026 Admission",
    start_date="2025-01-01",
    end_date="2025-03-31",
    require_acceptance_fee=True,  # Session-level: enabled
    acceptance_fee_deadline_days=21,  # 3 weeks
    is_active=True
)

# JSS 1: Acceptance fee required
AdmissionFeeStructure.objects.create(
    admission_session=session,
    class_room=jss_1_class,
    application_fee=7500,
    application_fee_required=True,
    entrance_exam_required=True,
    acceptance_fee=75000,  # ₦75,000
    acceptance_fee_required=True,  # ← Required for this class
)

# Primary 1: Acceptance fee optional
AdmissionFeeStructure.objects.create(
    admission_session=session,
    class_room=primary_1_class,
    application_fee=5000,
    application_fee_required=True,
    entrance_exam_required=False,
    acceptance_fee=30000,  # ₦30,000 (encouraged but not mandatory)
    acceptance_fee_required=False,  # ← Optional for this class
)
```

**Result:** Different requirements per class within same session. JSS 1 applicants must pay acceptance fee, Primary 1 applicants can accept without paying.

## Assessment System Examples

### Example 1: Setting Up Assessment Templates

```python
# Create assessment template for Primary 1 entrance exam
primary_1_exam = AssessmentTemplate.objects.create(
    name="Primary 1 Entrance Exam",
    assessment_type=AssessmentType.ENTRANCE_EXAM,
    description="Standard entrance examination for Primary 1 applicants",
    default_duration_minutes=90,
    default_max_score=100,
    default_pass_mark=50,
    default_instructions="""
    What to bring:
    - 2 pencils
    - Eraser
    - Sharpener
    - Water bottle

    Arrive 15 minutes early.
    Parents wait in the waiting area.
    """
)

# Add applicable classes
primary_1_exam.applicable_classes.add(primary_1_class)

# Add criteria (subjects)
AssessmentTemplateCriterion.objects.bulk_create([
    AssessmentTemplateCriterion(
        template=primary_1_exam,
        name="Mathematics",
        description="Basic arithmetic, counting, shapes",
        max_score=40,
        weight=1.0,
        display_order=1
    ),
    AssessmentTemplateCriterion(
        template=primary_1_exam,
        name="English Language",
        description="Alphabets, simple words, reading comprehension",
        max_score=40,
        weight=1.0,
        display_order=2
    ),
    AssessmentTemplateCriterion(
        template=primary_1_exam,
        name="General Knowledge",
        description="Colors, animals, everyday objects",
        max_score=20,
        weight=1.0,
        display_order=3
    ),
])
```

### Example 2: Creating Interview Template for JSS 1

```python
# Create interview template
jss_1_interview = AssessmentTemplate.objects.create(
    name="JSS 1 Interview",
    assessment_type=AssessmentType.INTERVIEW,
    description="Panel interview for JSS 1 applicants",
    default_duration_minutes=20,
    default_max_score=50,
    default_pass_mark=30,
    default_instructions="""
    Interview will be conducted by:
    - Principal or Vice Principal
    - Head of Department
    - Class Teacher

    Duration: 15-20 minutes
    Format: Question and answer
    Be yourself and answer honestly.
    """
)

jss_1_interview.applicable_classes.add(jss_1_class, jss_2_class, jss_3_class)

# Add interview criteria
AssessmentTemplateCriterion.objects.bulk_create([
    AssessmentTemplateCriterion(
        template=jss_1_interview,
        name="Communication Skills",
        description="Clarity, articulation, language proficiency",
        max_score=10,
        weight=1.0,
        display_order=1
    ),
    AssessmentTemplateCriterion(
        template=jss_1_interview,
        name="Confidence & Presentation",
        description="Self-confidence, body language, composure",
        max_score=10,
        weight=1.0,
        display_order=2
    ),
    AssessmentTemplateCriterion(
        template=jss_1_interview,
        name="Subject Knowledge",
        description="Understanding of basic subjects covered in primary school",
        max_score=15,
        weight=1.5,  # Weighted higher
        display_order=3
    ),
    AssessmentTemplateCriterion(
        template=jss_1_interview,
        name="Critical Thinking",
        description="Ability to reason and solve problems",
        max_score=10,
        weight=1.2,
        display_order=4
    ),
    AssessmentTemplateCriterion(
        template=jss_1_interview,
        name="Social Skills & Teamwork",
        description="Ability to work with others, empathy",
        max_score=5,
        weight=0.8,
        display_order=5
    ),
])
```

### Example 3: Complete Assessment Workflow

```python
from django.utils import timezone
from datetime import timedelta

# 1. Parent submits application
application = AdmissionApplication.objects.create(
    admission_session=active_session,
    first_name="Chioma",
    last_name="Okafor",
    # ... other fields
    applying_for_class=primary_1_class
)

# 2. Admin reviews application, schedules entrance exam
template = AssessmentTemplate.objects.get(name="Primary 1 Entrance Exam")
exam_date = timezone.now() + timedelta(days=7)  # Next week

entrance_exam = template.create_assessment_for_application(
    application=application,
    scheduled_date=exam_date,
    venue="Exam Hall B",
    assessor=teacher_user
)

# Email automatically sent to parent with exam details

# 3. On exam day, assessor conducts exam
entrance_exam.status = 'in_progress'
entrance_exam.save()

# 4. Assessor enters scores for each subject
for criterion in entrance_exam.criteria.all():
    if criterion.name == "Mathematics":
        criterion.achieved_score = 35  # Out of 40
    elif criterion.name == "English Language":
        criterion.achieved_score = 32  # Out of 40
    elif criterion.name == "General Knowledge":
        criterion.achieved_score = 15  # Out of 20
    criterion.save()

# 5. Calculate overall score
total_achieved = sum(c.achieved_score for c in entrance_exam.criteria.all())
entrance_exam.overall_score = total_achieved  # 82/100 = 82%
entrance_exam.passed = entrance_exam.overall_score >= entrance_exam.pass_mark
entrance_exam.assessor_notes = "Student showed good understanding of basic concepts"
entrance_exam.strengths = "Strong in Mathematics, good problem-solving skills"
entrance_exam.areas_for_improvement = "Needs to improve reading comprehension"
entrance_exam.recommendation = 'recommended'
entrance_exam.status = 'completed'
entrance_exam.completed_at = timezone.now()
entrance_exam.save()

# 6. Application moves to next stage
application.status = AdmissionStatus.EXAM_COMPLETED
application.entrance_exam_score = entrance_exam.overall_score
application.entrance_exam_passed = entrance_exam.passed
application.save()

# 7. Admin approves application (all assessments passed)
application.status = AdmissionStatus.APPROVED
application.acceptance_deadline = application.calculate_acceptance_deadline()
application.reviewed_by = admin_user
application.reviewed_at = timezone.now()
application.save()

# Email sent to parent with approval and acceptance instructions
```

### Example 4: Multiple Assessments for One Application

```python
# JSS 1 applicant requires: Exam + Aptitude Test + Interview

application = AdmissionApplication.objects.get(application_number="ADM/2025/042")

# Assessment 1: Written Entrance Exam
exam_template = AssessmentTemplate.objects.get(name="JSS 1 Entrance Exam")
written_exam = exam_template.create_assessment_for_application(
    application=application,
    scheduled_date=timezone.now() + timedelta(days=5),
    venue="Exam Hall A",
    assessor=math_teacher
)

# Assessment 2: Aptitude Test
aptitude_template = AssessmentTemplate.objects.get(name="JSS 1 Aptitude Test")
aptitude_test = aptitude_template.create_assessment_for_application(
    application=application,
    scheduled_date=timezone.now() + timedelta(days=12),  # Week after exam
    venue="Computer Lab",
    assessor=counselor_user
)

# Assessment 3: Panel Interview (only scheduled after exam + aptitude pass)
# Admin schedules this manually after reviewing exam/aptitude results

# Check if all assessments passed
all_assessments = application.assessments.all()
all_passed = all(a.passed for a in all_assessments if a.status == 'completed')

if all_passed:
    print("✅ All assessments passed - Ready for approval")
else:
    print("❌ Some assessments failed - Review required")
```

### Example 5: Assessment Dashboard View

```python
# View for admin dashboard showing upcoming assessments

def get_upcoming_assessments():
    """Get all upcoming assessments grouped by date"""
    from django.utils import timezone
    from collections import defaultdict

    upcoming = AdmissionAssessment.objects.filter(
        status='scheduled',
        scheduled_date__gte=timezone.now()
    ).select_related(
        'application',
        'assessor'
    ).order_by('scheduled_date')

    # Group by date
    by_date = defaultdict(list)
    for assessment in upcoming:
        date_key = assessment.scheduled_date.date()
        by_date[date_key].append({
            'time': assessment.scheduled_date.time(),
            'type': assessment.get_assessment_type_display(),
            'applicant': assessment.application.full_name,
            'app_number': assessment.application.application_number,
            'venue': assessment.venue,
            'assessor': assessment.assessor.get_full_name() if assessment.assessor else 'TBD',
            'duration': assessment.duration_minutes,
        })

    return dict(by_date)

# Output:
{
    '2025-02-15': [
        {'time': '09:00', 'type': 'Entrance Examination', 'applicant': 'John Doe', ...},
        {'time': '09:00', 'type': 'Entrance Examination', 'applicant': 'Jane Smith', ...},
        {'time': '14:00', 'type': 'Interview', 'applicant': 'Ahmed Ibrahim', ...},
    ],
    '2025-02-16': [
        {'time': '10:00', 'type': 'Aptitude Test', 'applicant': 'Grace Eze', ...},
    ]
}
```

## Next Steps

Would you like me to:
1. Implement the database models (AdmissionApplication, AdmissionAssessment, etc.) and migrations?
2. Create the API endpoints and serializers?
3. Build the email templates for admission workflow?
4. Set up the admin interface for managing applications and assessments?
5. Create the public admission form frontend integration guide?
