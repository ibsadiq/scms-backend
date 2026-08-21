#serializers/result.py
from rest_framework import serializers
from ..models import (
    AssessmentScore, SubjectResult, TermResult,
    AnnualSubjectResult, AnnualResult, ReportCard, ResultAuditLog, PromotionDecision
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
            "last_audit_log", "lifecycle_state",
        ]
        read_only_fields = [
            "scheme_name", "total_marks", "average_percentage", "grade", "gpa",
            "position_in_class", "total_students", "computed_date", "computed_by",
            "homeroom_approved", "homeroom_approved_by", "homeroom_approved_at", "homeroom_approval_delegated",
            "admin_approved", "admin_approved_by", "admin_approved_at",
            "is_published", "published_date", "is_pass",
            "is_locked", "locked_at", "locked_by", "unlocked_by", "unlocked_at",
            "last_audit_log", "lifecycle_state",
        ]

    def get_last_audit_log(self, obj):
        log = obj.audit_logs.order_by('-timestamp').first()
        if log:
            return ResultAuditLogSerializer(log).data
        return None


class TermResultListSerializer(TermResultSerializer):
    """
    Lightweight serializer for listing TermResults.
    Omits `subject_results` to drastically reduce payload size and loading time.
    """
    subject_results = None

    class Meta(TermResultSerializer.Meta):
        fields = [f for f in TermResultSerializer.Meta.fields if f != "subject_results"]


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
            "first_term", "first_term_status",
            "second_term", "second_term_status",
            "third_term", "third_term_status",
            "annual_average", "grade", "grade_point", "is_pass",
            "position_in_subject"
        ]
        read_only_fields = fields[1:]  # entirely computed by PromotionService



class PromotionDecisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromotionDecision
        fields = [
            "id", "status", "reasons", "failed_subjects_count",
            "is_overridden", "overridden_by", "overridden_at",
            "override_reason", "promoted_to"
        ]

class AnnualResultSerializer(serializers.ModelSerializer):
    subjects = AnnualSubjectResultSerializer(many=True, read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    classroom_name = serializers.StringRelatedField(source="classroom", read_only=True)
    academic_year_name = serializers.StringRelatedField(source="academic_year", read_only=True)
    promotion_decision = PromotionDecisionSerializer(read_only=True)

    class Meta:
        model = AnnualResult
        fields = [
            "id", "student", "student_name", "academic_year", "academic_year_name", "classroom", "classroom_name",
            "grading_scheme", "total_marks", "average_percentage", "grade", "gpa",
            "position_in_class", "total_students", "is_promoted", "promoted_to",
            "promotion_reason", "computed_at", "computed_by",
            "is_published", "published_at", "subjects", "lifecycle_state",
            "promotion_decision"
        ]
        read_only_fields = [
            "total_marks", "average_percentage", "grade", "gpa",
            "position_in_class", "total_students", "is_promoted",
            "promoted_to", "promotion_reason", "computed_at", "computed_by",
            "lifecycle_state"
        ]


class AnnualResultListSerializer(AnnualResultSerializer):
    """
    Lightweight serializer for listing AnnualResults.
    Omits `subjects` to reduce payload size.
    """
    subjects = None

    class Meta(AnnualResultSerializer.Meta):
        fields = [f for f in AnnualResultSerializer.Meta.fields if f != "subjects"]

from ..models import CumulativeResult, CumulativeSubjectResult, AcademicTranscript, ResultAmendmentRequest

class CumulativeSubjectResultSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    
    class Meta:
        model = CumulativeSubjectResult
        fields = ["id", "subject", "subject_name", "cumulative_average", "grade", "grade_point"]

class CumulativeResultSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)
    subjects = CumulativeSubjectResultSerializer(many=True, read_only=True)
    
    class Meta:
        model = CumulativeResult
        fields = [
            "id", "student", "student_name", "academic_year", "academic_year_name",
            "total_marks", "cumulative_average", "cumulative_gpa", "grade",
            "lifecycle_state", "computed_at", "computed_by", "subjects"
        ]

class AcademicTranscriptSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    
    class Meta:
        model = AcademicTranscript
        fields = ["id", "student", "student_name", "version", "serial_number", "status", "date_generated", "generated_by", "metadata", "history_snapshot"]

class ResultAmendmentRequestSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.CharField(source="requested_by.get_full_name", read_only=True)
    resolved_by_name = serializers.CharField(source="resolved_by.get_full_name", read_only=True)
    
    class Meta:
        model = ResultAmendmentRequest
        fields = [
            "id", "term_result", "annual_result", "requested_by", "requested_by_name",
            "reason", "status", "resolved_by", "resolved_by_name", "resolved_at",
            "resolution_notes", "created_at"
        ]


class ReportCardSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="term_result.student.full_name", read_only=True)
    term_name = serializers.CharField(source="term_result.term.name", read_only=True)
    classroom_name = serializers.CharField(source="term_result.classroom.name", read_only=True)
    academic_year_name = serializers.CharField(source="term_result.academic_year.name", read_only=True)
    pdf_url = serializers.SerializerMethodField()

    class Meta:
        model = ReportCard
        fields = [
            "id", "term_result", "version", "student_name", "term_name", "classroom_name", "academic_year_name",
            "pdf_file", "pdf_url", "generated_date", "generated_by",
            "download_count", "last_downloaded", "status", "error_message",
        ]
        read_only_fields = [
            "version", "pdf_file", "generated_date", "generated_by",
            "download_count", "last_downloaded", "status", "error_message",
        ]

    def get_pdf_url(self, obj):
        request = self.context.get("request")
        if obj.pdf_file and request:
            return request.build_absolute_uri(f"/api/examination/report-cards/{obj.id}/download/")
        return None
    

class ResultAuditLogSerializer(serializers.ModelSerializer):
    performed_by_name = serializers.CharField(source="performed_by.get_full_name", read_only=True)
    performed_by_email = serializers.CharField(source="performed_by.email", read_only=True, allow_null=True)
    student_name = serializers.CharField(source="term_result.student.full_name", read_only=True)
    student_admission_number = serializers.CharField(source="term_result.student.admission_number", read_only=True)
    classroom_name = serializers.SerializerMethodField()
    term_name = serializers.CharField(source="term_result.term.name", read_only=True)

    class Meta:
        model = ResultAuditLog
        fields = [
            "id",
            "term_result",
            "action",
            "performed_by",
            "performed_by_name",
            "performed_by_email",
            "student_name",
            "student_admission_number",
            "classroom_name",
            "term_name",
            "timestamp",
            "notes",
        ]

    def get_classroom_name(self, obj):
        if obj.term_result and obj.term_result.classroom:
            return getattr(obj.term_result.classroom, 'name_display', None) or (obj.term_result.classroom.name.name if obj.term_result.classroom.name else str(obj.term_result.classroom))
        return None