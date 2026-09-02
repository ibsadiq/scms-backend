from rest_framework import serializers
from django.db.models import Count, Q

from academic.models import StudentClassEnrollment
from cbt.models import (
    CBTExam,
    ExamAttempt,
    AttemptQuestion,
    AttemptAnswerEvent,
    ExamAttemptStatus,
)


class InvigilationExamListSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    classroom_name = serializers.CharField(source="classroom.name", read_only=True)
    session_name = serializers.CharField(source="session.name", read_only=True)
    total_candidates = serializers.SerializerMethodField()
    started_count = serializers.SerializerMethodField()
    in_progress_count = serializers.SerializerMethodField()
    submitted_count = serializers.SerializerMethodField()
    expired_count = serializers.SerializerMethodField()

    class Meta:
        model = CBTExam
        fields = [
            "id",
            "title",
            "subject",
            "subject_name",
            "classroom",
            "classroom_name",
            "session",
            "session_name",
            "status",
            "duration_minutes",
            "available_from",
            "available_until",
            "attempt_expiry_policy",
            "total_candidates",
            "started_count",
            "in_progress_count",
            "submitted_count",
            "expired_count",
            "created_at",
        ]

    def get_total_candidates(self, obj) -> int:
        if not obj.classroom_id or not obj.session_id:
            return 0
        return StudentClassEnrollment.objects.filter(
            classroom_id=obj.classroom_id,
            academic_year_id=obj.session.academic_year_id,
            is_active=True,
        ).count()

    def get_started_count(self, obj) -> int:
        return obj.attempts.count()

    def get_in_progress_count(self, obj) -> int:
        return obj.attempts.filter(status=ExamAttemptStatus.IN_PROGRESS).count()

    def get_submitted_count(self, obj) -> int:
        return obj.attempts.filter(status=ExamAttemptStatus.SUBMITTED).count()

    def get_expired_count(self, obj) -> int:
        return obj.attempts.filter(status=ExamAttemptStatus.EXPIRED).count()


class MonitoredAttemptListSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    admission_number = serializers.CharField(source="student.admission_number", read_only=True)
    total_questions = serializers.SerializerMethodField()
    answered_count = serializers.SerializerMethodField()
    flagged_count = serializers.SerializerMethodField()
    grading_status = serializers.SerializerMethodField()

    class Meta:
        model = ExamAttempt
        fields = [
            "public_id",
            "student",
            "student_name",
            "admission_number",
            "status",
            "start_source",
            "started_at",
            "expires_at",
            "submitted_at",
            "last_activity_at",
            "revision",
            "total_questions",
            "answered_count",
            "flagged_count",
            "grading_status",
            "created_at",
        ]

    def get_student_name(self, obj) -> str:
        student = obj.student
        return f"{student.first_name} {student.last_name}".strip()

    def get_total_questions(self, obj) -> int:
        return obj.attempt_questions.count()

    def get_answered_count(self, obj) -> int:
        return obj.attempt_questions.filter(answer__is_answered=True).count()

    def get_flagged_count(self, obj) -> int:
        return obj.attempt_questions.filter(is_flagged=True).count()

    def get_grading_status(self, obj) -> str | None:
        if hasattr(obj, "grade") and obj.grade:
            return obj.grade.status
        return None


class MonitoredAttemptDetailSerializer(MonitoredAttemptListSerializer):
    exam_title = serializers.CharField(source="cbt_exam.title", read_only=True)
    subject_name = serializers.CharField(source="cbt_exam.subject.name", read_only=True)
    classroom_name = serializers.CharField(source="cbt_exam.classroom.name", read_only=True)
    questions_progress = serializers.SerializerMethodField()
    events_summary = serializers.SerializerMethodField()
    grade_summary = serializers.SerializerMethodField()

    class Meta(MonitoredAttemptListSerializer.Meta):
        fields = MonitoredAttemptListSerializer.Meta.fields + [
            "exam_title",
            "subject_name",
            "classroom_name",
            "client_reported_started_at",
            "server_reconciled_at",
            "client_reported_submitted_at",
            "questions_progress",
            "events_summary",
            "grade_summary",
        ]

    def get_questions_progress(self, obj) -> list[dict]:
        items = []
        questions = obj.attempt_questions.all().select_related("answer").order_by("display_order")
        for q in questions:
            is_ans = hasattr(q, "answer") and q.answer and q.answer.is_answered
            ans_time = q.answer.answered_at if (is_ans and q.answer) else None
            items.append({
                "display_order": q.display_order,
                "is_flagged": q.is_flagged,
                "is_answered": is_ans,
                "answered_at": ans_time,
            })
        return items

    def get_events_summary(self, obj) -> dict:
        events = obj.answer_events.all().order_by("-created_at")
        latest = events.first()
        return {
            "total_events": events.count(),
            "latest_event_at": latest.created_at if latest else None,
            "latest_origin": latest.origin if latest else None,
        }

    def get_grade_summary(self, obj) -> dict | None:
        if not hasattr(obj, "grade") or not obj.grade:
            return None
        g = obj.grade
        return {
            "status": g.status,
            "raw_score": g.raw_score,
            "total_marks": g.total_marks,
            "percentage": g.percentage,
            "normalized_score": g.normalized_score,
            "graded_at": g.graded_at,
            "posted_at": g.posted_at,
        }
