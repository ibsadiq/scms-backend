"""
Assignment Serializers - Phase 1.7: Assignment & Homework Management
"""
from rest_framework import serializers
from .models import (
    Assignment,
    AssignmentAttachment,
    AssignmentSubmission,
    SubmissionAttachment,
    AssignmentGrade
)


class AssignmentAttachmentSerializer(serializers.ModelSerializer):
    """Serializer for assignment attachments"""
    file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = AssignmentAttachment
        fields = ['id', 'file', 'file_url', 'file_name', 'file_size', 'uploaded_at']
        read_only_fields = ['id', 'file_name', 'file_size', 'uploaded_at']
    
    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return None


class AssignmentSerializer(serializers.ModelSerializer):
    """Serializer for Assignment model"""
    teacher_name = serializers.CharField(source='teacher.user.get_full_name', read_only=True)
    classroom_name = serializers.CharField(source='classroom.__str__', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    academic_year_name = serializers.CharField(source='academic_year.__str__', read_only=True)
    term_name = serializers.CharField(source='term.__str__', read_only=True, allow_null=True)
    
    attachments = AssignmentAttachmentSerializer(many=True, read_only=True)
    
    # Computed fields
    is_overdue = serializers.ReadOnlyField()
    total_students = serializers.ReadOnlyField()
    submission_count = serializers.ReadOnlyField()
    graded_count = serializers.ReadOnlyField()
    submission_rate = serializers.ReadOnlyField()
    
    class Meta:
        model = Assignment
        fields = [
            'id', 'title', 'description', 'assignment_type',
            'teacher', 'teacher_name',
            'classroom', 'classroom_name',
            'subject', 'subject_name',
            'academic_year', 'academic_year_name',
            'term', 'term_name',
            'assigned_date', 'due_date',
            'max_score', 'allow_late_submission', 'late_penalty_percent',
            'status', 'is_active',
            'attachments',
            'is_overdue', 'total_students', 'submission_count', 'graded_count', 'submission_rate',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'assigned_date', 'created_at', 'updated_at']


class AssignmentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating assignments"""
    
    class Meta:
        model = Assignment
        fields = [
            'title', 'description', 'assignment_type',
            'classroom', 'subject', 'academic_year', 'term',
            'due_date', 'max_score',
            'allow_late_submission', 'late_penalty_percent',
            'status'
        ]
    
    def validate_due_date(self, value):
        """Ensure due date is in the future"""
        from django.utils import timezone
        if value < timezone.now():
            raise serializers.ValidationError("Due date must be in the future")
        return value


class SubmissionAttachmentSerializer(serializers.ModelSerializer):
    """Serializer for submission attachments"""
    file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = SubmissionAttachment
        fields = ['id', 'file', 'file_url', 'file_name', 'file_size', 'uploaded_at']
        read_only_fields = ['id', 'file_name', 'file_size', 'uploaded_at']
    
    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return None


class AssignmentGradeSerializer(serializers.ModelSerializer):
    """Serializer for assignment grades"""
    graded_by_name = serializers.CharField(source='graded_by.user.get_full_name', read_only=True)
    final_score = serializers.ReadOnlyField()
    percentage = serializers.ReadOnlyField()
    grade_letter = serializers.ReadOnlyField()
    
    class Meta:
        model = AssignmentGrade
        fields = [
            'id', 'score', 'late_penalty_applied',
            'feedback', 'graded_by', 'graded_by_name',
            'graded_at', 'updated_at',
            'final_score', 'percentage', 'grade_letter'
        ]
        read_only_fields = ['id', 'graded_by', 'graded_at', 'updated_at']


class AssignmentSubmissionSerializer(serializers.ModelSerializer):
    """Serializer for assignment submissions"""
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    student_admission_number = serializers.CharField(source='student.admission_number', read_only=True)
    assignment_title = serializers.CharField(source='assignment.title', read_only=True)
    
    attachments = SubmissionAttachmentSerializer(many=True, read_only=True)
    grade = AssignmentGradeSerializer(read_only=True)
    is_graded = serializers.ReadOnlyField()
    
    class Meta:
        model = AssignmentSubmission
        fields = [
            'id', 'assignment', 'assignment_title',
            'student', 'student_name', 'student_admission_number',
            'submission_text', 'submitted_at', 'updated_at',
            'is_late', 'is_graded',
            'attachments', 'grade'
        ]
        read_only_fields = ['id', 'submitted_at', 'updated_at', 'is_late']


class AssignmentSubmissionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating submissions"""
    
    class Meta:
        model = AssignmentSubmission
        fields = ['assignment', 'submission_text']
    
    def validate_assignment(self, value):
        """Ensure assignment is published and active"""
        if value.status != 'published':
            raise serializers.ValidationError("Cannot submit to unpublished assignment")
        if not value.is_active:
            raise serializers.ValidationError("Cannot submit to inactive assignment")
        return value


class AssignmentGradeCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating grades"""
    
    class Meta:
        model = AssignmentGrade
        fields = ['submission', 'score', 'late_penalty_applied', 'feedback']
    
    def validate(self, data):
        """Validate grade data"""
        submission = data['submission']
        score = data['score']
        
        if score > submission.assignment.max_score:
            raise serializers.ValidationError({
                'score': f"Score cannot exceed maximum score of {submission.assignment.max_score}"
            })
        
        return data


# Summary serializers for dashboards

class AssignmentSummarySerializer(serializers.ModelSerializer):
    """Lightweight serializer for assignment lists"""
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    classroom_name = serializers.CharField(source='classroom.__str__', read_only=True)
    is_overdue = serializers.ReadOnlyField()
    submission_rate = serializers.ReadOnlyField()
    
    class Meta:
        model = Assignment
        fields = [
            'id', 'title', 'assignment_type',
            'subject_name', 'classroom_name',
            'due_date', 'max_score', 'status',
            'is_overdue', 'submission_rate'
        ]


class StudentAssignmentSerializer(serializers.Serializer):
    """Serializer for student view of assignments"""
    id = serializers.IntegerField()
    title = serializers.CharField()
    description = serializers.CharField()
    assignment_type = serializers.CharField()
    subject_name = serializers.CharField()
    teacher_name = serializers.CharField()
    due_date = serializers.DateTimeField()
    max_score = serializers.DecimalField(max_digits=5, decimal_places=2)
    is_overdue = serializers.BooleanField()
    
    # Student-specific
    has_submitted = serializers.BooleanField()
    submission_id = serializers.IntegerField(allow_null=True)
    is_graded = serializers.BooleanField()
    grade = serializers.DictField(allow_null=True)
    
    attachments = AssignmentAttachmentSerializer(many=True)
