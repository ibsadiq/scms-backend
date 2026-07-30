#serializers/result.py
from rest_framework import serializers
from ..models import (
    AssessmentScore, SubjectResult, TermResult,
    AnnualSubjectResult, AnnualResult, ReportCard, ResultAuditLog
)


class AssessmentScoreSerializer(serializers.ModelSerializer):
    component_name = serializers.CharField(source="component.name", read_only=True)
    component_max_score = serializers.DecimalField(source="component.max_score", max_digits=5, decimal_places=2, read_only=True)
    component_order = serializers.IntegerField(source="component.order", read_only=True)

    class Meta:
        model = AssessmentScore
        fields = ["id", "component", "component_name", "component_max_score", "component_order", "score"]


class SubjectResultSerializer(serializers.ModelSerializer):
    assessment_scores = AssessmentScoreSerializer(many=True, read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    teacher_name = serializers.CharField(source="teacher.__str__", read_only=True)

    class Meta:
        model = SubjectResult
        fields = [
            "id", "term_result", "subject", "subject_name", "teacher", "teacher_name",
            "total_score", "percentage", "remark", "grade", "grade_point",
            "teacher_comment", "position_in_subject", "total_students",
            "highest_score", "lowest_score", "class_average", "is_pass",
            "assessment_scores",
        ]
        # All of these are computed by ResultComputationService — never
        # writable directly through this serializer.
        read_only_fields = [
            "total_score", "percentage", "grade", "grade_point",
            "position_in_subject", "total_students",
            "highest_score", "lowest_score", "class_average", "is_pass",
        ]


class TermResultSerializer(serializers.ModelSerializer):
    subject_results = SubjectResultSerializer(many=True, read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    classroom_name = serializers.StringRelatedField(source="classroom", read_only=True)
    term_name = serializers.StringRelatedField(source="term", read_only=True)
    academic_year_name = serializers.StringRelatedField(source="academic_year", read_only=True)
    status = serializers.CharField(read_only=True)
    can_view = serializers.BooleanField(read_only=True)

    # NEW: Last audit log for quick reference in list views
    last_audit_log = serializers.SerializerMethodField()

    class Meta:
        model = TermResult
        fields = [
            "id", "student", "student_name", "term", "term_name", "academic_year", "academic_year_name", "classroom", "classroom_name",
            "grading_scheme", "scheme_name", "total_marks", "average_percentage",
            "grade", "gpa", "position_in_class", "total_students", "remark",
            "class_teacher_remarks", "principal_remarks",
            "computed_date", "computed_by",
            "homeroom_approved", "homeroom_approved_by", "homeroom_approved_at", "homeroom_approval_delegated",
            "admin_approved", "admin_approved_by", "admin_approved_at",
            "is_published", "published_date",
            "is_pass", "is_locked", "locked_at", "locked_by",
            "unlock_reason", "unlocked_by", "unlocked_at", "result_release_date",
            "status", "can_view", "subject_results",
            "last_audit_log",  # <-- ADDED
        ]
        read_only_fields = [
            "scheme_name", "total_marks", "average_percentage", "grade", "gpa",
            "position_in_class", "total_students", "computed_date", "computed_by",
            "homeroom_approved", "homeroom_approved_by", "homeroom_approved_at", "homeroom_approval_delegated",
            "admin_approved", "admin_approved_by", "admin_approved_at",
            "is_published", "published_date", "is_pass",
            "is_locked", "locked_at", "locked_by", "unlocked_by", "unlocked_at",
            "last_audit_log",  # <-- ADDED
        ]

    def get_last_audit_log(self, obj):
        """Return the most recent audit log entry for this result."""
        log = obj.audit_logs.select_related("performed_by").first()
        if log:
            return {
                "id": log.id,
                "action": log.action,
                "performed_by_name": log.performed_by.get_full_name() if log.performed_by else None,
                "timestamp": log.timestamp,
                "notes": log.notes,
            }
        return None


class HomeroomRemarksSerializer(serializers.ModelSerializer):
    """Only field a homeroom teacher can PATCH."""
    class Meta:
        model = TermResult
        fields = ["id", "class_teacher_remarks"]


class AdminRemarksSerializer(serializers.ModelSerializer):
    """Only field an admin can PATCH via the remarks endpoint."""
    class Meta:
        model = TermResult
        fields = ["id", "principal_remarks"]


class AnnualSubjectResultSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)

    class Meta:
        model = AnnualSubjectResult
        fields = [
            "id", "annual_result", "subject", "subject_name",
            "first_term", "second_term", "third_term",
            "annual_average", "grade", "grade_point", "is_pass",
        ]
        read_only_fields = fields[1:]  # entirely computed by PromotionService


class AnnualResultSerializer(serializers.ModelSerializer):
    subjects = AnnualSubjectResultSerializer(many=True, read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    classroom_name = serializers.StringRelatedField(source="classroom", read_only=True)
    academic_year_name = serializers.StringRelatedField(source="academic_year", read_only=True)

    class Meta:
        model = AnnualResult
        fields = [
            "id", "student", "student_name", "academic_year", "academic_year_name", "classroom", "classroom_name",
            "grading_scheme", "total_marks", "average_percentage", "grade", "gpa",
            "position_in_class", "total_students", "is_promoted", "promoted_to",
            "promotion_reason", "computed_at", "computed_by",
            "is_published", "published_at", "subjects",
        ]
        read_only_fields = [
            "total_marks", "average_percentage", "grade", "gpa",
            "position_in_class", "total_students", "is_promoted",
            "promoted_to", "promotion_reason", "computed_at", "computed_by",
        ]

class ReportCardSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="term_result.student.full_name", read_only=True)
    term_name = serializers.CharField(source="term_result.term.name", read_only=True)
    pdf_url = serializers.SerializerMethodField()

    class Meta:
        model = ReportCard
        fields = [
            "id", "term_result", "student_name", "term_name",
            "pdf_file", "pdf_url", "generated_date", "generated_by",
            "download_count", "last_downloaded", "status", "error_message",
        ]
        read_only_fields = [
            "pdf_file", "generated_date", "generated_by",
            "download_count", "last_downloaded", "status", "error_message",
        ]

    def get_pdf_url(self, obj):
        request = self.context.get("request")
        if obj.pdf_file and request:
            return request.build_absolute_uri(f"/api/examination/report-cards/{obj.id}/download/")
        return None
    

class ResultAuditLogSerializer(serializers.ModelSerializer):
    performed_by_name = serializers.CharField(source="performed_by.get_full_name", read_only=True)
    
    class Meta:
        model = ResultAuditLog
        fields = ["id", "action", "performed_by_name", "timestamp", "notes"]