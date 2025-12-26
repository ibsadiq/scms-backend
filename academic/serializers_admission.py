from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from django.utils import timezone

from .models import (
    AdmissionSession,
    AdmissionFeeStructure,
    AdmissionApplication,
    AdmissionDocument,
    AdmissionAssessment,
    AssessmentCriterion,
    AssessmentTemplate,
    AssessmentTemplateCriterion,
    AdmissionStatus,
    AssessmentType,
    ClassLevel,
    Student,
)
from administration.models import AcademicYear
from users.models import CustomUser


# ============================================================================
# ADMISSION SESSION SERIALIZERS
# ============================================================================

class AdmissionSessionSerializer(serializers.ModelSerializer):
    """
    Full admission session details with statistics.
    Used for admin management.
    """
    academic_year_display = serializers.CharField(source='academic_year.year', read_only=True)
    is_open = serializers.BooleanField(read_only=True)
    total_applications = serializers.IntegerField(read_only=True)
    applications_by_status = serializers.SerializerMethodField()

    class Meta:
        model = AdmissionSession
        fields = '__all__'

    def get_applications_by_status(self, obj):
        """Get count of applications by status"""
        status_counts = {}
        for item in obj.applications_by_status:
            status_counts[item['status']] = item['count']
        return status_counts


class AdmissionSessionListSerializer(serializers.ModelSerializer):
    """
    Minimal admission session info for list views.
    """
    academic_year_display = serializers.CharField(source='academic_year.year', read_only=True)
    is_open = serializers.BooleanField(read_only=True)
    total_applications = serializers.IntegerField(read_only=True)

    class Meta:
        model = AdmissionSession
        fields = [
            'id', 'name', 'academic_year', 'academic_year_display',
            'start_date', 'end_date', 'is_active', 'is_open',
            'total_applications', 'require_acceptance_fee',
            'acceptance_fee_deadline_days'
        ]


class AdmissionSessionPublicSerializer(serializers.ModelSerializer):
    """
    Public-facing admission session info.
    Used for external portal (no sensitive data).
    """
    academic_year_display = serializers.CharField(source='academic_year.year', read_only=True)
    is_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = AdmissionSession
        fields = [
            'id', 'name', 'academic_year_display',
            'start_date', 'end_date', 'is_open',
            'application_instructions', 'allow_public_applications'
        ]


# ============================================================================
# ADMISSION FEE STRUCTURE SERIALIZERS
# ============================================================================

class AdmissionFeeStructureSerializer(serializers.ModelSerializer):
    """
    Full fee structure details.
    """
    class_room_name = serializers.CharField(source='class_room.name', read_only=True)
    current_applications_count = serializers.IntegerField(read_only=True)
    has_capacity = serializers.BooleanField(read_only=True)

    class Meta:
        model = AdmissionFeeStructure
        fields = '__all__'


class AdmissionFeeStructurePublicSerializer(serializers.ModelSerializer):
    """
    Public fee structure for external portal.
    Shows what parents need to pay.
    """
    class_room_name = serializers.CharField(source='class_room.name', read_only=True)
    has_capacity = serializers.BooleanField(read_only=True)

    class Meta:
        model = AdmissionFeeStructure
        fields = [
            'id', 'class_room', 'class_room_name',
            'application_fee', 'application_fee_required',
            'entrance_exam_required', 'entrance_exam_fee',
            'interview_required',
            'acceptance_fee', 'acceptance_fee_required',
            'acceptance_fee_is_part_of_tuition',
            'minimum_age', 'maximum_age', 'has_capacity'
        ]


# ============================================================================
# ADMISSION APPLICATION SERIALIZERS
# ============================================================================

class AdmissionApplicationListSerializer(serializers.ModelSerializer):
    """
    Minimal application info for list views.
    """
    full_name = serializers.CharField(read_only=True)
    age = serializers.IntegerField(read_only=True)
    applying_for_class_name = serializers.CharField(source='applying_for_class.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = AdmissionApplication
        fields = [
            'id', 'application_number', 'full_name', 'age',
            'gender', 'applying_for_class', 'applying_for_class_name',
            'status', 'status_display', 'parent_email', 'parent_phone',
            'application_fee_paid', 'exam_fee_paid', 'acceptance_fee_paid',
            'submitted_at', 'created_at'
        ]


class AdmissionApplicationDetailSerializer(serializers.ModelSerializer):
    """
    Full application details for admin review.
    """
    full_name = serializers.CharField(read_only=True)
    age = serializers.IntegerField(read_only=True)
    applying_for_class_name = serializers.CharField(source='applying_for_class.name', read_only=True)
    admission_session_name = serializers.CharField(source='admission_session.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    all_fees_paid = serializers.BooleanField(read_only=True)
    can_submit = serializers.BooleanField(read_only=True)
    can_accept_offer = serializers.BooleanField(read_only=True)
    reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = AdmissionApplication
        fields = '__all__'

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_reviewed_by_name(self, obj):
        if obj.reviewed_by:
            return f"{obj.reviewed_by.first_name} {obj.reviewed_by.last_name}"
        return None


class AdmissionApplicationCreateSerializer(serializers.ModelSerializer):
    """
    Create new application (external portal).
    """
    class Meta:
        model = AdmissionApplication
        fields = [
            'admission_session', 'applying_for_class',
            # Student info
            'first_name', 'middle_name', 'last_name', 'gender', 'date_of_birth',
            # Nigerian-specific
            'state_of_origin', 'lga', 'religion', 'blood_group',
            # Contact
            'address', 'city',
            # Parent
            'parent_first_name', 'parent_last_name', 'parent_email',
            'parent_phone', 'parent_occupation', 'parent_relationship',
            # Alternative contact
            'alt_contact_name', 'alt_contact_phone', 'alt_contact_relationship',
            # Previous school
            'previous_school', 'previous_class',
            # Medical
            'medical_conditions', 'special_needs'
        ]

    def validate(self, data):
        """Validate application data"""
        # Check if session is open
        session = data.get('admission_session')
        if not session.is_open:
            raise serializers.ValidationError(
                f"Applications for {session.name} are not currently being accepted."
            )

        # Check class capacity
        fee_structure = AdmissionFeeStructure.objects.filter(
            admission_session=session,
            class_room=data.get('applying_for_class')
        ).first()

        if not fee_structure:
            raise serializers.ValidationError(
                f"No fee structure configured for this class in {session.name}."
            )

        if not fee_structure.has_capacity:
            raise serializers.ValidationError(
                f"{data.get('applying_for_class').name} has reached maximum application capacity."
            )

        # Age validation
        if data.get('date_of_birth'):
            age = (timezone.now().date() - data['date_of_birth']).days // 365

            if fee_structure.minimum_age and age < fee_structure.minimum_age:
                raise serializers.ValidationError(
                    f"Applicant must be at least {fee_structure.minimum_age} years old for this class."
                )

            if fee_structure.maximum_age and age > fee_structure.maximum_age:
                raise serializers.ValidationError(
                    f"Applicant must be at most {fee_structure.maximum_age} years old for this class."
                )

        return data


class AdmissionApplicationUpdateSerializer(serializers.ModelSerializer):
    """
    Update application (parent can update draft applications).
    """
    class Meta:
        model = AdmissionApplication
        fields = [
            'first_name', 'middle_name', 'last_name', 'gender', 'date_of_birth',
            'state_of_origin', 'lga', 'religion', 'blood_group',
            'address', 'city',
            'parent_first_name', 'parent_last_name', 'parent_email',
            'parent_phone', 'parent_occupation', 'parent_relationship',
            'alt_contact_name', 'alt_contact_phone', 'alt_contact_relationship',
            'previous_school', 'previous_class',
            'medical_conditions', 'special_needs'
        ]

    def validate(self, data):
        """Only draft applications can be updated by parents"""
        if self.instance and self.instance.status != AdmissionStatus.DRAFT:
            raise serializers.ValidationError(
                "Only draft applications can be updated. This application has been submitted."
            )
        return data


class AdmissionApplicationStatusUpdateSerializer(serializers.Serializer):
    """
    Update application status (admin only).
    """
    status = serializers.ChoiceField(choices=AdmissionStatus.choices)
    admin_notes = serializers.CharField(required=False, allow_blank=True)
    rejection_reason = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        """Validate status transitions"""
        application = self.context.get('application')
        new_status = data['status']

        # If rejecting, must provide reason
        if new_status == AdmissionStatus.REJECTED and not data.get('rejection_reason'):
            raise serializers.ValidationError({
                'rejection_reason': 'Rejection reason is required when rejecting an application.'
            })

        return data


# ============================================================================
# ADMISSION DOCUMENT SERIALIZERS
# ============================================================================

class AdmissionDocumentSerializer(serializers.ModelSerializer):
    """
    Document upload/list serializer.
    """
    document_type_display = serializers.CharField(source='get_document_type_display', read_only=True)
    verified_by_name = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = AdmissionDocument
        fields = [
            'id', 'application', 'document_type', 'document_type_display',
            'file', 'file_url', 'description', 'verified', 'verified_by',
            'verified_by_name', 'verified_at', 'verification_notes',
            'uploaded_at'
        ]
        read_only_fields = ['verified', 'verified_by', 'verified_at', 'verification_notes']

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_verified_by_name(self, obj):
        if obj.verified_by:
            return f"{obj.verified_by.first_name} {obj.verified_by.last_name}"
        return None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class AdmissionDocumentVerifySerializer(serializers.Serializer):
    """
    Verify document (admin only).
    """
    verified = serializers.BooleanField()
    verification_notes = serializers.CharField(required=False, allow_blank=True)


# ============================================================================
# ADMISSION ASSESSMENT SERIALIZERS
# ============================================================================

class AssessmentCriterionSerializer(serializers.ModelSerializer):
    """
    Assessment criterion with calculated fields.
    """
    weighted_score = serializers.DecimalField(max_digits=7, decimal_places=2, read_only=True)
    percentage = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)

    class Meta:
        model = AssessmentCriterion
        fields = '__all__'


class AdmissionAssessmentListSerializer(serializers.ModelSerializer):
    """
    List view for assessments.
    """
    application_number = serializers.CharField(source='application.application_number', read_only=True)
    applicant_name = serializers.CharField(source='application.full_name', read_only=True)
    assessment_type_display = serializers.CharField(source='get_assessment_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    assessor_name = serializers.SerializerMethodField()
    percentage_score = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    is_upcoming = serializers.BooleanField(read_only=True)

    class Meta:
        model = AdmissionAssessment
        fields = [
            'id', 'application', 'application_number', 'applicant_name',
            'assessment_type', 'assessment_type_display', 'scheduled_date',
            'venue', 'assessor', 'assessor_name', 'status', 'status_display',
            'overall_score', 'max_score', 'percentage_score', 'passed',
            'is_upcoming'
        ]

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_assessor_name(self, obj):
        if obj.assessor:
            return f"{obj.assessor.first_name} {obj.assessor.last_name}"
        return None


class AdmissionAssessmentDetailSerializer(serializers.ModelSerializer):
    """
    Full assessment details with criteria.
    """
    application_number = serializers.CharField(source='application.application_number', read_only=True)
    applicant_name = serializers.CharField(source='application.full_name', read_only=True)
    assessment_type_display = serializers.CharField(source='get_assessment_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    assessor_name = serializers.SerializerMethodField()
    percentage_score = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    is_upcoming = serializers.BooleanField(read_only=True)
    criteria = AssessmentCriterionSerializer(many=True, read_only=True)

    class Meta:
        model = AdmissionAssessment
        fields = '__all__'

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_assessor_name(self, obj):
        if obj.assessor:
            return f"{obj.assessor.first_name} {obj.assessor.last_name}"
        return None


class AdmissionAssessmentCreateSerializer(serializers.ModelSerializer):
    """
    Create new assessment.
    """
    class Meta:
        model = AdmissionAssessment
        fields = [
            'application', 'assessment_type', 'scheduled_date',
            'duration_minutes', 'venue', 'assessor', 'max_score',
            'pass_mark', 'instructions'
        ]


class AdmissionAssessmentScoreSerializer(serializers.Serializer):
    """
    Submit assessment scores.
    """
    overall_score = serializers.DecimalField(max_digits=5, decimal_places=2)
    assessor_notes = serializers.CharField(required=False, allow_blank=True)
    strengths = serializers.CharField(required=False, allow_blank=True)
    areas_for_improvement = serializers.CharField(required=False, allow_blank=True)
    recommendation = serializers.ChoiceField(
        choices=[
            ('highly_recommended', 'Highly Recommended'),
            ('recommended', 'Recommended'),
            ('conditional', 'Conditional'),
            ('not_recommended', 'Not Recommended'),
        ],
        required=False
    )
    criteria = AssessmentCriterionSerializer(many=True, required=False)

    def validate_overall_score(self, value):
        """Validate score is within range"""
        assessment = self.context.get('assessment')
        if assessment and value > assessment.max_score:
            raise serializers.ValidationError(
                f"Score cannot exceed maximum score of {assessment.max_score}"
            )
        return value


# ============================================================================
# ASSESSMENT TEMPLATE SERIALIZERS
# ============================================================================

class AssessmentTemplateCriterionSerializer(serializers.ModelSerializer):
    """
    Template criterion serializer.
    """
    class Meta:
        model = AssessmentTemplateCriterion
        fields = '__all__'


class AssessmentTemplateListSerializer(serializers.ModelSerializer):
    """
    List view for templates.
    """
    assessment_type_display = serializers.CharField(source='get_assessment_type_display', read_only=True)
    applicable_classes_names = serializers.SerializerMethodField()

    class Meta:
        model = AssessmentTemplate
        fields = [
            'id', 'name', 'assessment_type', 'assessment_type_display',
            'applicable_classes', 'applicable_classes_names',
            'default_duration_minutes', 'default_pass_mark',
            'is_active'
        ]

    def get_applicable_classes_names(self, obj):
        return [cls.name for cls in obj.applicable_classes.all()]


class AssessmentTemplateDetailSerializer(serializers.ModelSerializer):
    """
    Full template details with criteria.
    """
    assessment_type_display = serializers.CharField(source='get_assessment_type_display', read_only=True)
    applicable_classes_names = serializers.SerializerMethodField()
    template_criteria = AssessmentTemplateCriterionSerializer(many=True, read_only=True)

    class Meta:
        model = AssessmentTemplate
        fields = '__all__'

    def get_applicable_classes_names(self, obj):
        return [cls.name for cls in obj.applicable_classes.all()]


# ============================================================================
# STATISTICS & REPORTS SERIALIZERS
# ============================================================================

class AdmissionStatisticsSerializer(serializers.Serializer):
    """
    Admission statistics for dashboard.
    """
    total_applications = serializers.IntegerField()
    applications_by_status = serializers.DictField()
    applications_by_class = serializers.DictField()
    pending_reviews = serializers.IntegerField()
    pending_documents = serializers.IntegerField()
    upcoming_assessments = serializers.IntegerField()
    approval_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    revenue = serializers.DictField()


class ApplicationTrackingSerializer(serializers.Serializer):
    """
    Public application tracking response.
    """
    application_number = serializers.CharField()
    status = serializers.CharField()
    status_display = serializers.CharField()
    applicant_name = serializers.CharField()
    applying_for_class = serializers.CharField()
    submitted_at = serializers.DateTimeField(allow_null=True)
    application_fee_paid = serializers.BooleanField()
    exam_fee_paid = serializers.BooleanField()
    acceptance_fee_paid = serializers.BooleanField()
    acceptance_deadline = serializers.DateTimeField(allow_null=True)
    next_steps = serializers.CharField()
