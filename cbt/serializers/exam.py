from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError

from academic.models import Subject, ClassRoom, AllocatedSubject
from examination.models import AssessmentSession, AssessmentComponent
from cbt.models import (
    CBTExam,
    CBTExamStatus,
    ExamBlueprint,
    BlueprintRule,
    ExamQuestion,
    QuestionType,
    QuestionDifficulty,
    PublishedExamRevision,
)
from cbt.serializers.question_bank import QuestionVersionSerializer
from cbt.services import CBTActorService, CBTAcademicScopeService


class BlueprintRuleSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source="topic.name", read_only=True, default="")
    subtopic_name = serializers.CharField(source="subtopic.name", read_only=True, default="")

    class Meta:
        model = BlueprintRule
        fields = [
            "id",
            "blueprint",
            "topic",
            "topic_name",
            "subtopic",
            "subtopic_name",
            "learning_objective",
            "question_type",
            "difficulty",
            "question_count",
            "order",
        ]
        read_only_fields = ["blueprint"]


class ExamBlueprintSerializer(serializers.ModelSerializer):
    rules = BlueprintRuleSerializer(many=True, read_only=True)
    total_questions = serializers.IntegerField(read_only=True)
    generated_question_count = serializers.IntegerField(read_only=True)
    is_generated = serializers.BooleanField(read_only=True)

    class Meta:
        model = ExamBlueprint
        fields = [
            "id",
            "cbt_exam",
            "is_locked",
            "total_questions",
            "generated_question_count",
            "is_generated",
            "rules",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "cbt_exam",
            "is_locked",
            "total_questions",
            "generated_question_count",
            "is_generated",
            "created_at",
            "updated_at",
        ]


class ExamQuestionManagementSerializer(serializers.ModelSerializer):
    question_type = serializers.CharField(
        source="question_version.question_type", read_only=True
    )
    question_text = serializers.CharField(
        source="question_version.text", read_only=True
    )
    question_version_detail = QuestionVersionSerializer(
        source="question_version", read_only=True
    )

    class Meta:
        model = ExamQuestion
        fields = [
            "id",
            "cbt_exam",
            "question_version",
            "question_type",
            "question_text",
            "marks",
            "order",
            "question_version_detail",
            "created_at",
        ]
        read_only_fields = ["cbt_exam", "created_at"]


class PublishedExamRevisionMetadataSerializer(serializers.ModelSerializer):
    question_count = serializers.IntegerField(source="questions.count", read_only=True)

    class Meta:
        model = PublishedExamRevision
        fields = [
            "public_id",
            "revision_number",
            "status",
            "schema_version",
            "content_hash",
            "published_at",
            "question_count",
        ]


class CBTExamManagementSerializer(serializers.ModelSerializer):
    session_name = serializers.CharField(source="session.name", read_only=True)
    component_name = serializers.CharField(source="component.name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    classroom_name = serializers.CharField(source="classroom.__str__", read_only=True)
    created_by_name = serializers.CharField(
        source="created_by.user.get_full_name", read_only=True, default=""
    )
    blueprint = ExamBlueprintSerializer(read_only=True)
    exam_questions = ExamQuestionManagementSerializer(many=True, read_only=True)
    question_count = serializers.IntegerField(source="exam_questions.count", read_only=True)
    total_marks = serializers.SerializerMethodField()
    current_published_revision = serializers.SerializerMethodField()

    class Meta:
        model = CBTExam
        fields = [
            "id",
            "title",
            "session",
            "session_name",
            "component",
            "component_name",
            "subject",
            "subject_name",
            "classroom",
            "classroom_name",
            "duration_minutes",
            "available_from",
            "available_until",
            "attempt_expiry_policy",
            "total_marks",
            "shuffle_questions",
            "shuffle_options",
            "allow_back_navigation",
            "auto_submit",
            "instructions",
            "status",
            "current_published_revision",
            "created_by",
            "created_by_name",
            "blueprint",
            "exam_questions",
            "question_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "status",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_total_marks(self, obj):
        total = sum(q.marks for q in obj.exam_questions.all())
        return str(total) if total else "0.00"

    def get_current_published_revision(self, obj):
        revision = obj.published_revisions.filter(
            status=PublishedExamRevision.Status.FINALIZED
        ).order_by("-revision_number").first()
        if revision is None:
            return None
        return PublishedExamRevisionMetadataSerializer(revision).data


    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        start = attrs.get("available_from", getattr(self.instance, "available_from", None))
        end = attrs.get("available_until", getattr(self.instance, "available_until", None))
        if start and end and start >= end:
            raise serializers.ValidationError(
                {"available_until": "Availability end must be after its start."}
            )

        if user and user.is_authenticated:
            subject = attrs.get("subject", getattr(self.instance, "subject", None))
            classroom = attrs.get("classroom", getattr(self.instance, "classroom", None))
            session = attrs.get("session", getattr(self.instance, "session", None))

            if subject and not CBTAcademicScopeService.can_use_subject(user, subject, session=session):
                raise serializers.ValidationError(
                    {"subject": "You are not authorized to create or manage exams for this subject."}
                )

            if classroom and subject and not CBTAcademicScopeService.can_use_classroom_for_subject(
                user, classroom, subject, session=session
            ):
                raise serializers.ValidationError(
                    {"classroom": "You are not allocated to teach this subject in this classroom."}
                )

        return attrs


class CBTExamCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CBTExam
        fields = [
            "id",
            "title",
            "session",
            "component",
            "subject",
            "classroom",
            "duration_minutes",
            "available_from",
            "available_until",
            "attempt_expiry_policy",
            "instructions",
            "shuffle_questions",
            "shuffle_options",
            "allow_back_navigation",
            "auto_submit",
        ]

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        start = attrs.get("available_from")
        end = attrs.get("available_until")
        if start and end and start >= end:
            raise serializers.ValidationError(
                {"available_until": "Availability end must be after its start."}
            )

        if user and user.is_authenticated:
            subject = attrs.get("subject")
            classroom = attrs.get("classroom")
            session = attrs.get("session")

            if subject and not CBTAcademicScopeService.can_use_subject(user, subject, session=session):
                raise serializers.ValidationError(
                    {"subject": "You are not authorized to create or manage exams for this subject."}
                )

            if classroom and subject and not CBTAcademicScopeService.can_use_classroom_for_subject(
                user, classroom, subject, session=session
            ):
                raise serializers.ValidationError(
                    {"classroom": "You are not allocated to teach this subject in this classroom."}
                )

        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        try:
            teacher = CBTActorService.resolve_teacher(user)
        except DjangoValidationError:
            teacher = None

        validated_data["created_by"] = teacher
        validated_data["status"] = CBTExamStatus.DRAFT
        return super().create(validated_data)


class StudentAvailableExamSerializer(serializers.ModelSerializer):
    """
    Student-safe exam serializer.
    Hides all blueprint internals, raw questions, bank metadata, and answer keys.
    """
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    classroom_name = serializers.CharField(source="classroom.__str__", read_only=True)
    question_count = serializers.IntegerField(source="exam_questions.count", read_only=True)
    total_marks = serializers.SerializerMethodField()
    attempt_status = serializers.SerializerMethodField()
    has_active_attempt = serializers.SerializerMethodField()
    availability = serializers.SerializerMethodField()
    published_revision = serializers.SerializerMethodField()

    class Meta:
        model = CBTExam
        fields = [
            "id",
            "title",
            "subject_name",
            "classroom_name",
            "duration_minutes",
            "available_from",
            "available_until",
            "attempt_expiry_policy",
            "total_marks",
            "question_count",
            "instructions",
            "status",
            "has_active_attempt",
            "attempt_status",
            "availability",
            "published_revision",
            "created_at",
        ]

    def get_total_marks(self, obj):
        total = sum(q.marks for q in obj.exam_questions.all())
        return str(total) if total else "0.00"

    def get_attempt_status(self, obj):
        user = getattr(self.context.get("request", None), "user", None)
        if not user:
            return None
        try:
            student = CBTActorService.resolve_student(user)
        except DjangoValidationError:
            return None

        last_attempt = obj.attempts.filter(student=student).order_by("-started_at").first()
        return last_attempt.status if last_attempt else None

    def get_has_active_attempt(self, obj):
        user = getattr(self.context.get("request", None), "user", None)
        if not user:
            return False
        try:
            student = CBTActorService.resolve_student(user)
        except DjangoValidationError:
            return False

        from cbt.models import ExamAttemptStatus
        return obj.attempts.filter(
            student=student,
            status=ExamAttemptStatus.IN_PROGRESS,
        ).exists()

    def _decision(self, obj):
        cache_name = "_student_access_decision"
        if hasattr(obj, cache_name):
            return getattr(obj, cache_name)
        request = self.context.get("request")
        try:
            student = CBTActorService.resolve_student(request.user)
        except (DjangoValidationError, AttributeError):
            return None
        from cbt.services import CBTExamAccessService
        decision = CBTExamAccessService.evaluate(student=student, exam=obj)
        setattr(obj, cache_name, decision)
        return decision

    def get_availability(self, obj):
        decision = self._decision(obj)
        if decision is None:
            return None
        return {
            "status": decision.state.value,
            "message": decision.message,
            "server_time": decision.server_time,
            "available_from": obj.available_from,
            "available_until": obj.available_until,
            "can_start": decision.can_start,
            "can_resume": decision.can_resume,
            "attempt_status": decision.attempt.status if decision.attempt else None,
            "attempt_public_id": (
                str(decision.attempt.public_id) if decision.can_resume else None
            ),
        }

    def get_published_revision(self, obj):
        decision = self._decision(obj)
        revision = decision.published_revision if decision else None
        if revision is None:
            return None
        return {
            "public_id": str(revision.public_id),
            "content_hash": revision.content_hash,
            "schema_version": revision.schema_version,
        }


class CBTExamAvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = CBTExam
        fields = ["available_from", "available_until", "attempt_expiry_policy"]

    def validate(self, attrs):
        start = attrs.get("available_from", getattr(self.instance, "available_from", None))
        end = attrs.get("available_until", getattr(self.instance, "available_until", None))
        if start and end and start >= end:
            raise serializers.ValidationError(
                {"available_until": "Availability end must be after its start."}
            )
        return attrs
