from django.contrib import admin
from django import forms
from users.models import CustomUser

from .models import *


class TeacherAdminForm(forms.ModelForm):
    """Custom form for Teacher admin to handle user-related fields"""
    first_name = forms.CharField(max_length=100, required=False)
    last_name = forms.CharField(max_length=100, required=False)
    middle_name = forms.CharField(max_length=100, required=False)
    email = forms.EmailField(required=True)
    phone_number = forms.CharField(max_length=15, required=False)

    class Meta:
        model = Teacher
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-populate user fields if teacher already exists
        if self.instance and self.instance.pk and self.instance.user:
            self.fields['first_name'].initial = self.instance.user.first_name
            self.fields['last_name'].initial = self.instance.user.last_name
            self.fields['middle_name'].initial = self.instance.user.middle_name
            self.fields['email'].initial = self.instance.user.email
            self.fields['phone_number'].initial = self.instance.user.phone_number

    def save(self, commit=True):
        teacher = super().save(commit=False)

        # Create or update the associated CustomUser
        if teacher.user:
            # Update existing user
            user = teacher.user
            user.first_name = self.cleaned_data.get('first_name', '')
            user.last_name = self.cleaned_data.get('last_name', '')
            user.middle_name = self.cleaned_data.get('middle_name', '')
            user.email = self.cleaned_data.get('email')
            user.phone_number = self.cleaned_data.get('phone_number', '')
            if not user.is_teacher:
                user.is_teacher = True
            user.save()
        else:
            # Create new user
            user = CustomUser.objects.create(
                first_name=self.cleaned_data.get('first_name', ''),
                last_name=self.cleaned_data.get('last_name', ''),
                middle_name=self.cleaned_data.get('middle_name', ''),
                email=self.cleaned_data.get('email'),
                phone_number=self.cleaned_data.get('phone_number', ''),
                is_teacher=True,
            )
            # Set default password
            default_password = f"Complex.{teacher.empId[-4:] if teacher.empId and len(teacher.empId) >= 4 else '0000'}"
            user.set_password(default_password)
            user.save()

            # Add to teacher group
            from django.contrib.auth.models import Group
            group, _ = Group.objects.get_or_create(name="teacher")
            user.groups.add(group)

            teacher.user = user

        if commit:
            teacher.save()
            self.save_m2m()

        return teacher


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    form = TeacherAdminForm
    list_display = ('empId', 'get_full_name', 'get_email', 'get_phone', 'designation', 'salary', 'inactive')
    list_filter = ('inactive', 'designation', 'subject_specialization')
    search_fields = ('empId', 'user__first_name', 'user__last_name', 'user__email', 'user__phone_number')
    filter_horizontal = ('subject_specialization',)

    fieldsets = (
        ('User Information', {
            'fields': ('user', 'first_name', 'middle_name', 'last_name', 'email', 'phone_number')
        }),
        ('Employment Details', {
            'fields': ('empId', 'designation', 'short_name', 'salary', 'unpaid_salary')
        }),
        ('Additional Information', {
            'fields': ('national_id', 'tin_number', 'address', 'alt_email', 'image')
        }),
        ('Academic Information', {
            'fields': ('subject_specialization',)
        }),
        ('Status', {
            'fields': ('inactive',)
        }),
    )

    readonly_fields = ('user',)

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}" if obj.user else "N/A"
    get_full_name.short_description = 'Full Name'

    def get_email(self, obj):
        return obj.email if obj.user else "N/A"
    get_email.short_description = 'Email'

    def get_phone(self, obj):
        return obj.phone_number if obj.user else "N/A"
    get_phone.short_description = 'Phone'


admin.site.register(Department)
admin.site.register(Subject)
admin.site.register(GradeLevel)
admin.site.register(ClassLevel)
admin.site.register(ClassYear)
admin.site.register(ClassRoom)
admin.site.register(AllocatedSubject)
# StudentClassEnrollment registered below with custom admin (Phase 2.2)
admin.site.register(Topic)
admin.site.register(SubTopic)
admin.site.register(Dormitory)
admin.site.register(DormitoryAllocation)
admin.site.register(MessageToParent)
admin.site.register(MessageToTeacher)


# ===== PROMOTION MODELS (Phase 2.1) =====

@admin.register(PromotionRule)
class PromotionRuleAdmin(admin.ModelAdmin):
    list_display = [
        'from_class_level',
        'to_class_level',
        'promotion_method',
        'minimum_annual_average',
        'minimum_attendance_percentage',
        'requires_approval',
        'is_active'
    ]
    list_filter = ['promotion_method', 'requires_approval', 'is_active', 'from_class_level']
    search_fields = ['from_class_level__name', 'to_class_level__name']
    fieldsets = (
        ('Class Levels', {
            'fields': ('from_class_level', 'to_class_level')
        }),
        ('Promotion Method', {
            'fields': ('promotion_method',)
        }),
        ('Annual Average Settings (Nigerian Method)', {
            'fields': (
                'minimum_annual_average',
                'use_weighted_terms',
                'term1_weight',
                'term2_weight',
                'term3_weight'
            ),
            'classes': ('collapse',)
        }),
        ('Subject Requirements', {
            'fields': (
                'require_english_pass',
                'require_mathematics_pass',
                'minimum_subject_pass_percentage',
                'minimum_passed_subjects'
            )
        }),
        ('Attendance & GPA', {
            'fields': (
                'minimum_attendance_percentage',
                'minimum_gpa'
            )
        }),
        ('Configuration', {
            'fields': ('requires_approval', 'is_active')
        }),
    )


@admin.register(StudentPromotion)
class StudentPromotionAdmin(admin.ModelAdmin):
    list_display = [
        'student',
        'from_class',
        'to_class',
        'status',
        'annual_average',
        'subjects_passed',
        'attendance_percentage',
        'meets_criteria',
        'promotion_date'
    ]
    list_filter = [
        'status',
        'meets_criteria',
        'academic_year',
        'english_passed',
        'mathematics_passed',
        'promotion_date'
    ]
    search_fields = [
        'student__first_name',
        'student__last_name',
        'student__admission_number'
    ]
    readonly_fields = ['created_at']
    fieldsets = (
        ('Student & Classes', {
            'fields': (
                'student',
                'from_class',
                'to_class',
                'from_class_level',
                'to_class_level',
                'academic_year'
            )
        }),
        ('Academic Performance', {
            'fields': (
                'term1_average',
                'term2_average',
                'term3_average',
                'annual_average',
                'final_gpa'
            )
        }),
        ('Subject Performance', {
            'fields': (
                'total_subjects',
                'subjects_passed',
                'subjects_failed',
                'english_passed',
                'mathematics_passed'
            )
        }),
        ('Attendance', {
            'fields': (
                'attendance_percentage',
                'total_school_days',
                'days_present',
                'days_absent'
            )
        }),
        ('Class Ranking', {
            'fields': (
                'class_position',
                'total_students_in_class'
            )
        }),
        ('Promotion Decision', {
            'fields': (
                'status',
                'meets_criteria',
                'reason',
                'approved_by',
                'promotion_date',
                'created_at'
            )
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        """Make from_class and from_class_level readonly after creation"""
        if obj:  # Editing existing object
            return self.readonly_fields + ['from_class', 'from_class_level', 'student', 'academic_year']
        return self.readonly_fields


@admin.register(StudentClassEnrollment)
class StudentClassEnrollmentAdmin(admin.ModelAdmin):
    """Admin interface for Student Class Enrollments (Phase 2.2)"""
    list_display = [
        'student',
        'classroom',
        'academic_year',
        'enrollment_date',
        'is_active',
    ]
    list_filter = [
        'academic_year',
        'is_active',
        'classroom__name',
    ]
    search_fields = [
        'student__first_name',
        'student__last_name',
        'student__admission_number',
    ]
    readonly_fields = ['enrollment_date']
    date_hierarchy = 'enrollment_date'

    fieldsets = (
        ('Student Information', {
            'fields': ('student', 'classroom', 'academic_year')
        }),
        ('Enrollment Details', {
            'fields': ('enrollment_date', 'is_active', 'notes')
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        """Make student, classroom, and academic_year readonly after creation"""
        if obj:  # Editing existing object
            return self.readonly_fields + ['student', 'classroom', 'academic_year']
        return self.readonly_fields


# ============================================================================
# ADMISSION SYSTEM ADMIN
# ============================================================================

class AdmissionFeeStructureInline(admin.TabularInline):
    """Inline for fee structures in admission session"""
    model = AdmissionFeeStructure
    extra = 1
    fields = [
        'class_room', 'application_fee', 'application_fee_required',
        'entrance_exam_required', 'entrance_exam_fee', 'entrance_exam_pass_score',
        'interview_required', 'acceptance_fee', 'acceptance_fee_required',
        'acceptance_fee_is_part_of_tuition', 'max_applications'
    ]


@admin.register(AdmissionSession)
class AdmissionSessionAdmin(admin.ModelAdmin):
    """Admin for admission sessions"""
    list_display = [
        'name', 'academic_year', 'start_date', 'end_date',
        'is_active', 'is_open', 'total_applications',
        'require_acceptance_fee'
    ]
    list_filter = ['is_active', 'require_acceptance_fee', 'start_date']
    search_fields = ['name', 'academic_year__year']
    readonly_fields = ['created_at', 'updated_at', 'total_applications', 'is_open']
    inlines = [AdmissionFeeStructureInline]

    fieldsets = (
        ('Basic Information', {
            'fields': ('academic_year', 'name', 'start_date', 'end_date', 'is_active')
        }),
        ('Acceptance Fee Configuration', {
            'fields': ('require_acceptance_fee', 'acceptance_fee_deadline_days')
        }),
        ('Application Settings', {
            'fields': (
                'application_number_prefix',
                'allow_public_applications',
                'send_confirmation_emails'
            )
        }),
        ('Custom Messages', {
            'fields': (
                'application_instructions',
                'approval_message',
                'rejection_message_template'
            ),
            'classes': ('collapse',)
        }),
        ('Statistics', {
            'fields': ('total_applications', 'is_open'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AdmissionFeeStructure)
class AdmissionFeeStructureAdmin(admin.ModelAdmin):
    """Admin for fee structures"""
    list_display = [
        'admission_session', 'class_room', 'application_fee',
        'entrance_exam_required', 'acceptance_fee_required',
        'current_applications_count', 'has_capacity'
    ]
    list_filter = [
        'admission_session', 'entrance_exam_required',
        'interview_required', 'acceptance_fee_required'
    ]
    search_fields = ['admission_session__name', 'class_room__name']
    readonly_fields = ['created_at', 'updated_at', 'current_applications_count', 'has_capacity']

    fieldsets = (
        ('Session & Class', {
            'fields': ('admission_session', 'class_room')
        }),
        ('Application Fee', {
            'fields': ('application_fee', 'application_fee_required')
        }),
        ('Entrance Exam', {
            'fields': (
                'entrance_exam_required',
                'entrance_exam_fee',
                'entrance_exam_pass_score'
            )
        }),
        ('Interview', {
            'fields': ('interview_required',)
        }),
        ('Acceptance Fee', {
            'fields': (
                'acceptance_fee',
                'acceptance_fee_required',
                'acceptance_fee_is_part_of_tuition'
            )
        }),
        ('Capacity & Age Limits', {
            'fields': (
                'max_applications',
                'minimum_age',
                'maximum_age',
                'current_applications_count',
                'has_capacity'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


class AdmissionDocumentInline(admin.TabularInline):
    """Inline for documents in application"""
    model = AdmissionDocument
    extra = 0
    readonly_fields = ['uploaded_at', 'verified_by', 'verified_at']
    fields = [
        'document_type', 'file', 'verified',
        'verification_notes', 'uploaded_at'
    ]


class AdmissionAssessmentInline(admin.TabularInline):
    """Inline for assessments in application"""
    model = AdmissionAssessment
    extra = 0
    readonly_fields = ['created_at', 'percentage_score']
    fields = [
        'assessment_type', 'scheduled_date', 'status',
        'overall_score', 'max_score', 'percentage_score',
        'passed', 'assessor'
    ]


@admin.register(AdmissionApplication)
class AdmissionApplicationAdmin(admin.ModelAdmin):
    """Admin for admission applications"""
    list_display = [
        'application_number', 'full_name', 'applying_for_class',
        'status', 'age', 'application_fee_paid', 'exam_fee_paid',
        'acceptance_fee_paid', 'submitted_at'
    ]
    list_filter = [
        'status', 'admission_session', 'applying_for_class',
        'gender', 'application_fee_paid', 'exam_fee_paid',
        'acceptance_fee_paid'
    ]
    search_fields = [
        'application_number', 'first_name', 'last_name',
        'parent_email', 'parent_phone', 'tracking_token'
    ]
    readonly_fields = [
        'application_number', 'tracking_token', 'full_name', 'age',
        'all_fees_paid', 'can_submit', 'can_accept_offer',
        'submitted_at', 'approved_at', 'accepted_at', 'enrolled_at',
        'created_at', 'updated_at'
    ]
    inlines = [AdmissionDocumentInline, AdmissionAssessmentInline]
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Application Info', {
            'fields': (
                'application_number', 'tracking_token', 'admission_session',
                'applying_for_class', 'status'
            )
        }),
        ('Student Information', {
            'fields': (
                'first_name', 'middle_name', 'last_name', 'full_name',
                'gender', 'date_of_birth', 'age'
            )
        }),
        ('Nigerian-Specific Fields', {
            'fields': ('state_of_origin', 'lga', 'religion', 'blood_group')
        }),
        ('Contact Information', {
            'fields': ('address', 'city')
        }),
        ('Parent/Guardian Information', {
            'fields': (
                'parent_first_name', 'parent_last_name', 'parent_email',
                'parent_phone', 'parent_occupation', 'parent_relationship'
            )
        }),
        ('Alternative Contact', {
            'fields': (
                'alt_contact_name', 'alt_contact_phone',
                'alt_contact_relationship'
            ),
            'classes': ('collapse',)
        }),
        ('Previous School', {
            'fields': ('previous_school', 'previous_class'),
            'classes': ('collapse',)
        }),
        ('Medical Information', {
            'fields': ('medical_conditions', 'special_needs'),
            'classes': ('collapse',)
        }),
        ('Payment Tracking', {
            'fields': (
                'application_fee_paid', 'application_fee_receipt',
                'application_fee_payment_date',
                'exam_fee_paid', 'exam_fee_receipt', 'exam_fee_payment_date',
                'acceptance_fee_paid', 'acceptance_fee_receipt',
                'acceptance_fee_payment_date', 'acceptance_deadline',
                'all_fees_paid', 'can_submit', 'can_accept_offer'
            )
        }),
        ('Admin Review', {
            'fields': (
                'admin_notes', 'rejection_reason', 'reviewed_by'
            )
        }),
        ('Enrollment', {
            'fields': ('enrolled_student', 'enrolled_at')
        }),
        ('Timestamps', {
            'fields': (
                'submitted_at', 'approved_at', 'accepted_at',
                'created_at', 'updated_at'
            ),
            'classes': ('collapse',)
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        """Make certain fields readonly after submission"""
        if obj and obj.status not in [AdmissionStatus.DRAFT, AdmissionStatus.SUBMITTED]:
            return self.readonly_fields + [
                'admission_session', 'applying_for_class',
                'first_name', 'middle_name', 'last_name',
                'gender', 'date_of_birth'
            ]
        return self.readonly_fields

    actions = ['approve_applications', 'reject_applications', 'mark_as_under_review']

    def approve_applications(self, request, queryset):
        """Bulk approve applications"""
        count = 0
        for app in queryset:
            if app.status in [AdmissionStatus.SUBMITTED, AdmissionStatus.UNDER_REVIEW]:
                app.status = AdmissionStatus.APPROVED
                app.reviewed_by = request.user
                app.save()
                count += 1
        self.message_user(request, f"{count} application(s) approved successfully.")
    approve_applications.short_description = "Approve selected applications"

    def reject_applications(self, request, queryset):
        """Bulk reject applications"""
        count = 0
        for app in queryset:
            if app.status in [AdmissionStatus.SUBMITTED, AdmissionStatus.UNDER_REVIEW]:
                app.status = AdmissionStatus.REJECTED
                app.reviewed_by = request.user
                app.save()
                count += 1
        self.message_user(request, f"{count} application(s) rejected.")
    reject_applications.short_description = "Reject selected applications"

    def mark_as_under_review(self, request, queryset):
        """Mark applications as under review"""
        count = queryset.filter(status=AdmissionStatus.SUBMITTED).update(
            status=AdmissionStatus.UNDER_REVIEW,
            reviewed_by=request.user
        )
        self.message_user(request, f"{count} application(s) marked as under review.")
    mark_as_under_review.short_description = "Mark as under review"


@admin.register(AdmissionDocument)
class AdmissionDocumentAdmin(admin.ModelAdmin):
    """Admin for admission documents"""
    list_display = [
        'application', 'document_type', 'verified',
        'verified_by', 'uploaded_at'
    ]
    list_filter = ['document_type', 'verified', 'uploaded_at']
    search_fields = [
        'application__application_number',
        'application__first_name',
        'application__last_name'
    ]
    readonly_fields = ['uploaded_at', 'verified_by', 'verified_at']
    date_hierarchy = 'uploaded_at'

    fieldsets = (
        ('Document Info', {
            'fields': ('application', 'document_type', 'file', 'description')
        }),
        ('Verification', {
            'fields': (
                'verified', 'verified_by', 'verified_at',
                'verification_notes'
            )
        }),
        ('Timestamps', {
            'fields': ('uploaded_at',)
        }),
    )

    actions = ['verify_documents', 'unverify_documents']

    def verify_documents(self, request, queryset):
        """Bulk verify documents"""
        count = queryset.update(
            verified=True,
            verified_by=request.user,
            verified_at=timezone.now()
        )
        self.message_user(request, f"{count} document(s) verified.")
    verify_documents.short_description = "Verify selected documents"

    def unverify_documents(self, request, queryset):
        """Bulk unverify documents"""
        count = queryset.update(
            verified=False,
            verified_by=None,
            verified_at=None
        )
        self.message_user(request, f"{count} document(s) unmarked as verified.")
    unverify_documents.short_description = "Unverify selected documents"


class AssessmentCriterionInline(admin.TabularInline):
    """Inline for assessment criteria"""
    model = AssessmentCriterion
    extra = 1
    fields = ['name', 'max_score', 'achieved_score', 'weight', 'comments', 'order']


@admin.register(AdmissionAssessment)
class AdmissionAssessmentAdmin(admin.ModelAdmin):
    """Admin for admission assessments"""
    list_display = [
        'application', 'assessment_type', 'scheduled_date',
        'status', 'overall_score', 'max_score', 'passed',
        'assessor'
    ]
    list_filter = [
        'assessment_type', 'status', 'passed',
        'scheduled_date', 'assessor'
    ]
    search_fields = [
        'application__application_number',
        'application__first_name',
        'application__last_name'
    ]
    readonly_fields = [
        'percentage_score', 'is_upcoming',
        'created_at', 'updated_at', 'completed_at'
    ]
    inlines = [AssessmentCriterionInline]
    date_hierarchy = 'scheduled_date'

    fieldsets = (
        ('Assessment Info', {
            'fields': (
                'application', 'assessment_type', 'status'
            )
        }),
        ('Scheduling', {
            'fields': (
                'scheduled_date', 'duration_minutes',
                'venue', 'assessor', 'is_upcoming'
            )
        }),
        ('Scoring', {
            'fields': (
                'overall_score', 'max_score', 'percentage_score',
                'pass_mark', 'passed'
            )
        }),
        ('Feedback', {
            'fields': (
                'assessor_notes', 'strengths',
                'areas_for_improvement', 'recommendation'
            )
        }),
        ('Instructions', {
            'fields': ('instructions',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )

    actions = ['mark_as_completed', 'mark_as_no_show']

    def mark_as_completed(self, request, queryset):
        """Mark assessments as completed"""
        count = queryset.filter(status='scheduled').update(
            status='completed',
            completed_at=timezone.now()
        )
        self.message_user(request, f"{count} assessment(s) marked as completed.")
    mark_as_completed.short_description = "Mark as completed"

    def mark_as_no_show(self, request, queryset):
        """Mark assessments as no show"""
        count = queryset.filter(status='scheduled').update(status='no_show')
        self.message_user(request, f"{count} assessment(s) marked as no show.")
    mark_as_no_show.short_description = "Mark as no show"


@admin.register(AssessmentCriterion)
class AssessmentCriterionAdmin(admin.ModelAdmin):
    """Admin for assessment criteria"""
    list_display = [
        'assessment', 'name', 'achieved_score', 'max_score',
        'weight', 'percentage'
    ]
    list_filter = ['assessment__assessment_type']
    search_fields = ['name', 'assessment__application__application_number']
    readonly_fields = ['weighted_score', 'percentage']

    fieldsets = (
        ('Criterion Info', {
            'fields': ('assessment', 'name', 'order')
        }),
        ('Scoring', {
            'fields': (
                'max_score', 'achieved_score', 'weight',
                'weighted_score', 'percentage'
            )
        }),
        ('Feedback', {
            'fields': ('comments',)
        }),
    )


class AssessmentTemplateCriterionInline(admin.TabularInline):
    """Inline for template criteria"""
    model = AssessmentTemplateCriterion
    extra = 1
    fields = ['name', 'max_score', 'weight', 'description', 'order']


@admin.register(AssessmentTemplate)
class AssessmentTemplateAdmin(admin.ModelAdmin):
    """Admin for assessment templates"""
    list_display = [
        'name', 'assessment_type', 'default_duration_minutes',
        'default_pass_mark', 'is_active'
    ]
    list_filter = ['assessment_type', 'is_active']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    filter_horizontal = ['applicable_classes']
    inlines = [AssessmentTemplateCriterionInline]

    fieldsets = (
        ('Template Info', {
            'fields': ('name', 'assessment_type', 'description', 'is_active')
        }),
        ('Applicable Classes', {
            'fields': ('applicable_classes',)
        }),
        ('Default Settings', {
            'fields': (
                'default_duration_minutes',
                'default_max_score',
                'default_pass_mark',
                'default_instructions'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AssessmentTemplateCriterion)
class AssessmentTemplateCriterionAdmin(admin.ModelAdmin):
    """Admin for template criteria"""
    list_display = ['template', 'name', 'max_score', 'weight', 'order']
    list_filter = ['template__assessment_type']
    search_fields = ['name', 'template__name']

    fieldsets = (
        ('Criterion Info', {
            'fields': ('template', 'name', 'order')
        }),
        ('Scoring Configuration', {
            'fields': ('max_score', 'weight', 'description')
        }),
    )
