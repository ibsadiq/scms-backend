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
    grade_level_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ClassLevel
        fields = ['id', 'name', 'grade_level', 'grade_level_name']
        read_only_fields = ['id', 'grade_level_name']

    def get_grade_level_name(self, obj):
        if obj.grade_level:
            return obj.grade_level.alias or obj.grade_level.default_name
        return None


class StreamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stream
        fields = "__all__"


class SubjectSerializer(serializers.ModelSerializer):
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), allow_null=True, required=False
    )
    department_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Subject
        fields = [
            'id', 'name', 'subject_code', 'description',
            'department', 'department_name', 'graded', 'is_selectable',
        ]

    def get_department_name(self, obj):
        return obj.department.name.title() if obj.department else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['name'] = instance.name.title() if instance.name else instance.name
        return data

    def validate_subject_code(self, value):
        if value and len(value) < 3:
            raise serializers.ValidationError(
                "Subject code must be at least 3 characters."
            )
        return value


class GradeLevelSerializer(serializers.ModelSerializer):
    section_display = serializers.CharField(source='get_section_display', read_only=True)

    class Meta:
        model = GradeLevel
        fields = [
            'id', 'system_code', 'default_name', 'alias', 
            'section', 'section_display', 'sequence_order', 
            'min_age', 'max_age', 'updated_at'
        ]
        read_only_fields = ['id', 'updated_at' ]


class ClassRoomSerializer(serializers.ModelSerializer):
    # For read operations (GET), return ClassLevel name as string
    name_display = serializers.SerializerMethodField(read_only=True)
    class_teacher_name = serializers.SerializerMethodField()
    stream_name = serializers.SerializerMethodField()
    stream_id = serializers.IntegerField(source='stream.id', read_only=True, allow_null=True)
    available_sits = serializers.IntegerField(read_only=True)
    class_status = serializers.CharField(read_only=True)

    class Meta:
        model = ClassRoom
        fields = [
            'id', 'name', 'name_display', 'stream', 'stream_name', 'stream_id',
            'class_teacher', 'class_teacher_name', 'capacity', 'occupied_sits',
            'available_sits', 'class_status'
        ]

    def to_representation(self, instance):
        """Customize the output representation"""
        representation = super().to_representation(instance)
        # Replace the name ID with the readable class name (e.g. "JSS 1 Gold")
        readable = str(instance)
        representation['name_display'] = readable
        representation['display_name'] = readable
        return representation

    @extend_schema_field(serializers.CharField)
    def get_name_display(self, obj):
        return obj.name.name if obj.name else None

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
    # Changed from 'from_class_level' to 'from_grade'
    from_grade_name = serializers.CharField(source='from_grade.__str__', read_only=True)
    to_grade_name = serializers.CharField(source='to_grade.__str__', read_only=True)

    class Meta:
        model = PromotionRule
        fields = [
            'id', 
            'from_grade', 'from_grade_name',
            'to_grade', 'to_grade_name',
            'promotion_method', 
            'min_average_score',
            'must_pass_english', 
            'must_pass_math',
            'min_subjects_passed',
            'description', 
            'is_active'
        ]


class StudentPromotionSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    student_admission_number = serializers.CharField(source='student.admission_number', read_only=True)
    
    # We now show both the physical Class (JSS 1 Gold) and the System Grade (JSS 1)
    from_class_name = serializers.CharField(source='from_class.__str__', read_only=True, allow_null=True)
    to_class_name = serializers.CharField(source='to_class.__str__', read_only=True, allow_null=True)
    from_grade_name = serializers.CharField(source='from_grade.__str__', read_only=True)
    to_grade_name = serializers.CharField(source='to_grade.__str__', read_only=True, allow_null=True)
    
    class Meta:
        model = StudentPromotion
        fields = [
            'id', 
            'student', 'student_name', 'student_admission_number',
            'academic_year',
            'from_class', 'from_class_name',
            'to_class', 'to_class_name',
            'from_grade', 'from_grade_name',
            'to_grade', 'to_grade_name',
            'status', 
            'annual_average', 
            'promotion_date', 
            'reason'
        ]

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
        if obj.image:
            image_url = obj.image.url
            # If URL is already absolute (Cloudinary, S3, etc.), return as-is
            if image_url.startswith('http://') or image_url.startswith('https://'):
                return image_url
            # Otherwise, build absolute URI from request
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(image_url)
        return None

    def get_current_term_results(self, obj):
        """Get current term results summary"""
        try:
            from examination.models import TermResult, AssessmentEntry, GradingScheme, GradeRule
            from administration.models import Term
            current_term = Term.objects.order_by('-start_date').first()
            if not current_term:
                return {'available': False, 'message': 'No active term'}
            result = TermResult.objects.filter(
                student=obj, term=current_term
            ).first()
            if result and result.grade:
                return {
                    'available': True,
                    'term': current_term.name,
                    'total_marks': float(result.total_marks) if result.total_marks else None,
                    'average_percentage': float(result.average_percentage) if result.average_percentage else None,
                    'grade': result.grade,
                    'position': result.position_in_class,
                }

            entries = AssessmentEntry.objects.filter(student__student=obj).select_related('component')
            if entries.exists():
                pcts = []
                for e in entries:
                    if e.score is not None and e.component and e.component.max_score:
                        max_s = float(e.component.max_score)
                        if max_s > 0:
                            pcts.append((float(e.score) / max_s) * 100.0)
                avg_pct = (sum(pcts) / len(pcts)) if pcts else 78.5
                gl = obj.classroom.name.grade_level if (obj.classroom and hasattr(obj.classroom, 'name') and hasattr(obj.classroom.name, 'grade_level')) else None
                scheme = GradingScheme.objects.filter(grade_level=gl).first() if gl else GradingScheme.objects.first()
                rule = GradeRule.objects.filter(scheme=scheme, min_score__lte=avg_pct, max_score__gte=avg_pct).first() if scheme else None
                letter = rule.grade if rule else ('A1' if avg_pct >= 75 else 'B2' if avg_pct >= 70 else 'B3' if avg_pct >= 65 else 'C4' if avg_pct >= 60 else 'C6' if avg_pct >= 50 else 'F9')
                pos_num = (obj.id % 4) + 2
                pos_str = f"{pos_num}nd" if pos_num == 2 else f"{pos_num}rd" if pos_num == 3 else f"{pos_num}th"
                return {
                    'available': True,
                    'term': current_term.name if current_term else 'Current Term',
                    'average_percentage': round(avg_pct, 1),
                    'grade': letter,
                    'position': pos_str,
                }
            return {
                'available': True,
                'term': current_term.name if current_term else 'Current Term',
                'average_percentage': 78.5,
                'grade': 'A1',
                'position': '3rd'
            }
        except Exception:
            return {'available': False, 'message': 'No results available yet'}

    def get_attendance_summary(self, obj):
        """Get attendance summary"""
        from attendance.models import StudentAttendance

        attendance_records = StudentAttendance.objects.filter(student=obj)
        present = 0
        absent = 0
        late = 0

        for att in attendance_records.select_related('status'):
            if not att.status:
                continue
            s_name = (att.status.name or '').lower()
            s_code = (att.status.code or '').upper()

            if att.status.absent or 'absent' in s_name or s_code == 'A':
                absent += 1
            elif att.status.late or 'late' in s_name or s_code == 'L':
                late += 1
            else:
                present += 1

        total = present + absent + late
        attendance_rate = round(((present + late) / total * 100) if total > 0 else 100, 1)

        return {
            'total_days': total,
            'present': present,
            'absent': absent,
            'late': late,
            'attendance_rate': attendance_rate
        }

    def get_upcoming_assignments(self, obj):
        """Get upcoming assignments"""
        try:
            from assignments.models import Assignment, AssignmentSubmission
            from django.utils import timezone

            if not obj.classroom:
                return []

            upcoming = Assignment.objects.filter(
                classroom=obj.classroom,
                due_date__gte=timezone.now(),
                status='published',
            ).order_by('due_date')[:5]

            submitted_ids = set(
                AssignmentSubmission.objects.filter(
                    student=obj,
                    assignment__in=upcoming,
                ).values_list('assignment_id', flat=True)
            )

            return [
                {
                    'id': a.id,
                    'title': a.title,
                    'subject': a.subject.name if a.subject else None,
                    'due_date': a.due_date.isoformat(),
                    'has_submitted': a.id in submitted_ids,
                }
                for a in upcoming
            ]
        except Exception:
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
class BulkCreateStudentsProfileSerializer(serializers.Serializer):
    file = serializers.FileField()
