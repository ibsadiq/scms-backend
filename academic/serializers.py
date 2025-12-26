from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from .models import (
    ClassYear,
    ClassRoom,
    GradeLevel,
    ClassLevel,
    Subject,
    Department,
    ReasonLeft,
    StudentClassEnrollment,
    Stream,
    PromotionRule,
    StudentPromotion
)


class ClassYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassYear
        fields = "__all__"


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = "__all__"


class ClassLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassLevel
        fields = "__all__"


class StreamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stream
        fields = "__all__"


class SubjectSerializer(serializers.ModelSerializer):
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects.all())

    class Meta:
        model = Subject
        fields = "__all__"

    def validate_subject_code(self, value):
        # Add custom validation if needed (e.g., regex validation)
        if len(value) < 3:
            raise serializers.ValidationError(
                "Subject code must be at least 3 characters."
            )
        return value


class GradeLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = GradeLevel
        fields = "__all__"


class ClassRoomSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    class_teacher_name = serializers.SerializerMethodField()
    stream_name = serializers.SerializerMethodField()
    stream_id = serializers.IntegerField(source='stream.id', read_only=True, allow_null=True)
    available_sits = serializers.IntegerField(read_only=True)
    class_status = serializers.CharField(read_only=True)

    class Meta:
        model = ClassRoom
        fields = "__all__"
        extra_fields = ['class_teacher_name', 'stream_name', 'stream_id']

    def get_fields(self):
        fields = super().get_fields()
        # Add the extra fields to the fields dict
        return fields

    @extend_schema_field(serializers.CharField)
    def get_name(self, obj):
        return obj.name.name

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_stream_name(self, obj):
        if obj.stream:
            return obj.stream.name
        return None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_class_teacher_name(self, obj):
        if obj.class_teacher:
            return f"{obj.class_teacher.first_name} {obj.class_teacher.last_name}"
        return None


class SchoolYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassYear
        fields = "__all__"


class ReasonLeftSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReasonLeft
        fields = "__all__"


class StudentClassEnrollmentSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    student_admission_number = serializers.SerializerMethodField()
    student_gender = serializers.SerializerMethodField()

    class Meta:
        model = StudentClassEnrollment
        fields = "__all__"

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_student_name(self, obj):
        if obj.student:
            return obj.student.full_name
        return None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_student_admission_number(self, obj):
        if obj.student:
            return obj.student.admission_number
        return None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_student_gender(self, obj):
        if obj.student:
            return obj.student.gender
        return None

    def validate(self, data):
        classroom = data.get("classroom")
        if classroom.occupied_sits >= classroom.capacity:
            raise serializers.ValidationError("This class is already full.")
        return data


class BulkUploadClassRoomsSerializer(serializers.Serializer):
    file = serializers.FileField()

class BulkUploadStudentsSerializer(serializers.Serializer):
    file = serializers.FileField()

class BulkUploadSubjectsSerializer(serializers.Serializer):
    file = serializers.FileField()


# ============================================================================
# PROMOTION SERIALIZERS (Phase 2.1)
# ============================================================================

class PromotionRuleSerializer(serializers.ModelSerializer):
    """Serializer for PromotionRule model"""
    from_class_level_name = serializers.CharField(
        source='from_class_level.name',
        read_only=True
    )
    to_class_level_name = serializers.CharField(
        source='to_class_level.name',
        read_only=True
    )

    class Meta:
        model = PromotionRule
        fields = [
            'id',
            'from_class_level',
            'from_class_level_name',
            'to_class_level',
            'to_class_level_name',
            'promotion_method',
            'minimum_annual_average',
            'use_weighted_terms',
            'term1_weight',
            'term2_weight',
            'term3_weight',
            'require_english_pass',
            'require_mathematics_pass',
            'minimum_subject_pass_percentage',
            'minimum_passed_subjects',
            'minimum_attendance_percentage',
            'minimum_gpa',
            'requires_approval',
            'is_active',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class StudentPromotionSerializer(serializers.ModelSerializer):
    """Serializer for StudentPromotion model"""
    student_name = serializers.CharField(
        source='student.full_name',
        read_only=True
    )
    student_admission_number = serializers.CharField(
        source='student.admission_number',
        read_only=True
    )
    from_class_name = serializers.CharField(
        source='from_class.__str__',
        read_only=True
    )
    to_class_name = serializers.CharField(
        source='to_class.__str__',
        read_only=True
    )
    approved_by_name = serializers.SerializerMethodField()
    promotion_summary = serializers.ReadOnlyField()

    class Meta:
        model = StudentPromotion
        fields = [
            'id',
            'student',
            'student_name',
            'student_admission_number',
            'from_class',
            'from_class_name',
            'to_class',
            'to_class_name',
            'from_class_level',
            'to_class_level',
            'academic_year',
            'status',
            'term1_average',
            'term2_average',
            'term3_average',
            'annual_average',
            'final_gpa',
            'total_subjects',
            'subjects_passed',
            'subjects_failed',
            'english_passed',
            'mathematics_passed',
            'attendance_percentage',
            'total_school_days',
            'days_present',
            'days_absent',
            'class_position',
            'total_students_in_class',
            'meets_criteria',
            'reason',
            'approved_by',
            'approved_by_name',
            'promotion_date',
            'promotion_summary',
            'created_at'
        ]
        read_only_fields = ['created_at', 'promotion_summary']

    def get_approved_by_name(self, obj):
        """Get name of user who approved promotion"""
        if obj.approved_by:
            return f"{obj.approved_by.first_name} {obj.approved_by.last_name}"
        return None


class PromotionPreviewSerializer(serializers.Serializer):
    """Serializer for promotion preview data"""
    student_id = serializers.IntegerField()
    student_name = serializers.CharField()
    admission_number = serializers.CharField()
    current_class = serializers.CharField()
    recommended_status = serializers.ChoiceField(
        choices=['promoted', 'repeated', 'conditional', 'graduated']
    )
    to_class = serializers.CharField(allow_null=True)
    annual_average = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)
    term1_average = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)
    term2_average = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)
    term3_average = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)
    final_gpa = serializers.DecimalField(max_digits=3, decimal_places=2, allow_null=True)
    attendance_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)
    subjects_passed = serializers.IntegerField()
    total_subjects = serializers.IntegerField()
    english_passed = serializers.BooleanField()
    mathematics_passed = serializers.BooleanField()
    meets_criteria = serializers.BooleanField()
    reason = serializers.CharField(allow_blank=True)


# ===== PHASE 2.2: CLASS ADVANCEMENT SERIALIZERS =====

class StudentClassEnrollmentSerializer(serializers.ModelSerializer):
    """Serializer for StudentClassEnrollment model"""
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    student_admission_number = serializers.CharField(source='student.admission_number', read_only=True)
    classroom_name = serializers.CharField(source='classroom.__str__', read_only=True)
    academic_year_name = serializers.CharField(source='academic_year.__str__', read_only=True)

    class Meta:
        model = StudentClassEnrollment
        fields = [
            'id', 'student', 'student_name', 'student_admission_number',
            'classroom', 'classroom_name', 'academic_year', 'academic_year_name',
            'enrollment_date', 'is_active', 'notes'
        ]
        read_only_fields = ['enrollment_date']


class StreamAssignmentSerializer(serializers.Serializer):
    """Serializer for assigning streams to SS1 students"""
    student_id = serializers.IntegerField()
    student_name = serializers.CharField(read_only=True)
    preferred_stream = serializers.CharField(read_only=True)
    assigned_stream = serializers.ChoiceField(
        choices=['science', 'commercial', 'arts'],
        required=True
    )

    class Meta:
        fields = ['student_id', 'student_name', 'preferred_stream', 'assigned_stream']


class ClassMovementPreviewSerializer(serializers.Serializer):
    """Serializer for previewing class movements"""
    student_id = serializers.IntegerField()
    student_name = serializers.CharField()
    admission_number = serializers.CharField()
    from_class = serializers.CharField(allow_null=True)
    to_class = serializers.CharField(allow_null=True)
    assigned_stream = serializers.CharField(allow_null=True)
    preferred_stream = serializers.CharField(allow_null=True)
    needs_stream_assignment = serializers.BooleanField()


class ClassMovementExecutionSerializer(serializers.Serializer):
    """Serializer for executing class movements"""
    academic_year_id = serializers.IntegerField(required=True)
    new_academic_year_id = serializers.IntegerField(required=True)
    promotion_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="Optional: specific promotion IDs to execute. If not provided, all promotions for the year will be executed."
    )
    auto_create_classrooms = serializers.BooleanField(default=True)
    default_teacher_id = serializers.IntegerField(required=False, allow_null=True)


class CapacityWarningSerializer(serializers.Serializer):
    """Serializer for classroom capacity warnings"""
    classroom = serializers.CharField()
    current = serializers.IntegerField()
    capacity = serializers.IntegerField()
    message = serializers.CharField()


class NewClassroomNeededSerializer(serializers.Serializer):
    """Serializer for new classrooms that need to be created"""
    class_level = serializers.CharField()
    stream = serializers.CharField(allow_null=True)
    section = serializers.CharField()
    student_count = serializers.IntegerField()
    capacity = serializers.IntegerField()


# ============================================================================
# Phase 1.6: Student Portal Serializers
# ============================================================================

class StudentRegistrationSerializer(serializers.Serializer):
    """Serializer for student registration"""
    phone_number = serializers.CharField(max_length=20, help_text="Student's phone number")
    password = serializers.CharField(
        min_length=8,
        write_only=True,
        help_text="Password (minimum 8 characters)"
    )
    password_confirm = serializers.CharField(
        min_length=8,
        write_only=True,
        help_text="Confirm password"
    )
    admission_number = serializers.CharField(
        max_length=50,
        help_text="Student admission number for verification"
    )

    def validate(self, data):
        """Validate passwords match"""
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({
                'password_confirm': 'Passwords do not match'
            })
        return data


class StudentLoginSerializer(serializers.Serializer):
    """Serializer for student login"""
    phone_number = serializers.CharField(max_length=20, help_text="Student's phone number")
    password = serializers.CharField(write_only=True, help_text="Password")


class StudentProfileSerializer(serializers.Serializer):
    """Serializer for student profile"""
    id = serializers.IntegerField(read_only=True)
    admission_number = serializers.CharField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    middle_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)

    # Contact info
    phone_number = serializers.CharField(allow_blank=True, allow_null=True)
    email = serializers.SerializerMethodField()

    # Academic info
    class_level = serializers.SerializerMethodField()
    classroom = serializers.SerializerMethodField()
    class_of_year = serializers.SerializerMethodField()

    # Personal info
    gender = serializers.CharField(read_only=True)
    date_of_birth = serializers.DateField(read_only=True)
    blood_group = serializers.CharField(read_only=True)
    religion = serializers.CharField(read_only=True)

    # Location
    region = serializers.CharField(read_only=True)
    city = serializers.CharField(read_only=True)
    street = serializers.CharField(read_only=True)

    # Stream preferences (SS1)
    preferred_stream = serializers.CharField(allow_blank=True, allow_null=True)
    assigned_stream = serializers.CharField(read_only=True)

    # Status
    is_active = serializers.BooleanField(read_only=True)
    admission_date = serializers.DateTimeField(read_only=True)

    # Parent/Guardian
    parent_guardian = serializers.SerializerMethodField()

    def get_email(self, obj):
        """Get user email"""
        return obj.user.email if obj.user else None

    def get_class_level(self, obj):
        """Get class level name"""
        return str(obj.class_level) if obj.class_level else None

    def get_classroom(self, obj):
        """Get classroom name"""
        return str(obj.classroom) if obj.classroom else None

    def get_class_of_year(self, obj):
        """Get class year"""
        return str(obj.class_of_year) if obj.class_of_year else None

    def get_parent_guardian(self, obj):
        """Get parent/guardian basic info"""
        if obj.parent_guardian:
            return {
                'name': f"{obj.parent_guardian.first_name} {obj.parent_guardian.last_name}",
                'phone': obj.parent_guardian.phone_number,
                'email': obj.parent_guardian.email
            }
        return None


class StudentDashboardSerializer(serializers.Serializer):
    """Serializer for student dashboard"""
    # Basic info
    id = serializers.IntegerField(read_only=True)
    admission_number = serializers.CharField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    classroom = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    # Academic summary
    current_term_results = serializers.SerializerMethodField()
    attendance_summary = serializers.SerializerMethodField()
    upcoming_assignments = serializers.SerializerMethodField()

    # Fee info
    fee_balance = serializers.SerializerMethodField()

    # Notifications
    unread_notifications = serializers.SerializerMethodField()

    def get_classroom(self, obj):
        """Get classroom name"""
        return str(obj.classroom) if obj.classroom else 'Not Assigned'

    def get_image_url(self, obj):
        """Get student image URL"""
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None

    def get_current_term_results(self, obj):
        """Get current term results summary"""
        # TODO: Implement when examination system is available
        return {
            'available': False,
            'message': 'No results available yet'
        }

    def get_attendance_summary(self, obj):
        """Get attendance summary"""
        from attendance.models import StudentAttendance
        from django.db.models import Count, Q

        attendance_records = StudentAttendance.objects.filter(student=obj)
        total = attendance_records.count()

        if total == 0:
            return {
                'total_days': 0,
                'present': 0,
                'absent': 0,
                'attendance_rate': 0
            }

        present = attendance_records.filter(status='present').count()
        absent = attendance_records.filter(status='absent').count()
        attendance_rate = (present / total * 100) if total > 0 else 0

        return {
            'total_days': total,
            'present': present,
            'absent': absent,
            'attendance_rate': round(attendance_rate, 1)
        }

    def get_upcoming_assignments(self, obj):
        """Get upcoming assignments"""
        # TODO: Implement when assignment system is available
        return []

    def get_fee_balance(self, obj):
        """Get fee balance"""
        from finance.models import StudentFeeAssignment

        try:
            # Get student's fee assignment for current term
            from administration.models import Term
            current_term = Term.objects.filter(academic_year__active_year=True).first()

            if not current_term:
                return {
                    'total_balance': 0,
                    'amount_paid': 0,
                    'remaining': 0,
                    'term': 'N/A'
                }

            fee_assignment = StudentFeeAssignment.objects.filter(
                student=obj,
                term=current_term
            ).first()

            if fee_assignment:
                return {
                    'total_balance': float(fee_assignment.total_fee),
                    'amount_paid': float(fee_assignment.amount_paid),
                    'remaining': float(fee_assignment.balance),
                    'term': str(current_term)
                }
        except Exception:
            pass

        return {
            'total_balance': 0,
            'amount_paid': 0,
            'remaining': 0,
            'term': 'N/A'
        }

    def get_unread_notifications(self, obj):
        """Get unread notifications count"""
        if not obj.user:
            return 0

        from notifications.models import Notification
        return Notification.objects.filter(
            recipient=obj.user,
            is_read=False
        ).count()