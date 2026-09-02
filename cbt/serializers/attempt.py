from django.utils import timezone
from rest_framework import serializers

from cbt.models import (
    ExamAttempt,
    AttemptQuestion,
    AttemptQuestionOption,
    AttemptMatchingItem,
    StudentAnswer,
    QuestionType,
)


class AttemptQuestionOptionSerializer(serializers.ModelSerializer):
    """
    Student-safe option representation.
    NEVER includes is_correct or internal answer feedback!
    """
    option_id = serializers.SerializerMethodField()
    text = serializers.SerializerMethodField()

    class Meta:
        model = AttemptQuestionOption
        fields = [
            "id",
            "option_id",
            "text",
            "display_order",
        ]

    def get_option_id(self, obj):
        return str(obj.published_choice.public_id) if obj.published_choice_id else obj.question_option_id

    def get_text(self, obj):
        return obj.published_choice.text if obj.published_choice_id else obj.question_option.text


class AttemptQuestionSerializer(serializers.ModelSerializer):
    """
    Student-safe question representation.
    Uses attempt-level display_order and option shuffle order.
    NEVER includes answer keys or grading rubrics!
    """
    question_type = serializers.SerializerMethodField()
    question_text = serializers.SerializerMethodField()
    instructions = serializers.SerializerMethodField()
    marks = serializers.SerializerMethodField()
    options = serializers.SerializerMethodField()
    student_response = serializers.SerializerMethodField()
    blank_items = serializers.SerializerMethodField()
    matching_items = serializers.SerializerMethodField()
    interaction_config = serializers.SerializerMethodField()
    media = serializers.SerializerMethodField()

    class Meta:
        model = AttemptQuestion
        fields = [
            "id",
            "public_id",
            "display_order",
            "question_type",
            "question_text",
            "instructions",
            "marks",
            "is_flagged",
            "options",
            "blank_items",
            "matching_items",
            "interaction_config",
            "media",
            "student_response",
        ]

    def get_options(self, obj):
        # Order options according to the attempt's presentation ordering
        option_orders = obj.option_order.select_related(
            "question_option", "published_choice"
        ).order_by("display_order")
        return AttemptQuestionOptionSerializer(option_orders, many=True).data

    def get_question_type(self, obj):
        return obj.published_question.question_type if obj.published_question_id else obj.exam_question.question_version.question_type

    def get_question_text(self, obj):
        return obj.published_question.question_text if obj.published_question_id else obj.exam_question.question_version.text

    def get_instructions(self, obj):
        return obj.published_question.instructions if obj.published_question_id else obj.exam_question.question_version.instructions

    def get_marks(self, obj):
        marks = obj.published_question.marks if obj.published_question_id else obj.exam_question.marks
        return f"{marks:.2f}"

    def get_interaction_config(self, obj):
        return obj.published_question.interaction_config if obj.published_question_id else {}

    def get_media(self, obj):
        if not obj.published_question_id:
            return []
        return [
            {
                "id": str(item.public_id),
                "filename": item.filename,
                "caption": item.caption,
                "order": item.order,
                "sha256": item.content_sha256,
                "size_bytes": item.size_bytes,
            }
            for item in obj.published_question.media.all().order_by("order")
        ]

    def get_blank_items(self, obj):
        if obj.published_question_id:
            return [
                {"id": str(item.public_id), "position": item.position}
                for item in obj.published_question.blanks.all().order_by("position")
            ]
        version = obj.exam_question.question_version
        if version.question_type == QuestionType.FILL_BLANK:
            if hasattr(version, "fill_blank_definition"):
                items = version.fill_blank_definition.blanks.order_by("position")
                return [{"id": item.id, "position": item.position} for item in items]
        return []

    def get_matching_items(self, obj):
        if obj.published_question_id:
            items = obj.matching_item_order.select_related("published_item")
            return {
                "left_items": [
                    {"id": str(item.published_item.public_id), "text": item.published_item.text, "order": item.display_order}
                    for item in items.filter(side=AttemptMatchingItem.Side.LEFT).order_by("display_order")
                ],
                "right_items": [
                    {"id": str(item.published_item.public_id), "text": item.published_item.text, "order": item.display_order}
                    for item in items.filter(side=AttemptMatchingItem.Side.RIGHT).order_by("display_order")
                ],
            }
        version = obj.exam_question.question_version
        if version.question_type == QuestionType.MATCHING:
            items = obj.matching_item_order.select_related("matching_pair")
            left_items = [
                {
                    "id": str(item.public_id),
                    "text": item.matching_pair.left_text,
                    "order": item.display_order,
                }
                for item in items.filter(side=AttemptMatchingItem.Side.LEFT)
                .order_by("display_order")
            ]
            right_items = [
                {
                    "id": str(item.public_id),
                    "text": item.matching_pair.right_text,
                    "order": item.display_order,
                }
                for item in items.filter(side=AttemptMatchingItem.Side.RIGHT)
                .order_by("display_order")
            ]
            return {"left_items": left_items, "right_items": right_items}
        return None

    def get_student_response(self, obj):
        if not hasattr(obj, "answer") or not obj.answer.is_answered:
            return None

        answer = obj.answer
        q_type = self.get_question_type(obj)

        if q_type in {QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE, QuestionType.TRUE_FALSE}:
            selected_ids = [
                str(item.published_choice.public_id) if item.published_choice_id else item.question_option_id
                for item in answer.selected_options.select_related("published_choice")
            ]
            return {"option_ids": selected_ids}

        elif q_type in {QuestionType.SHORT_ANSWER, QuestionType.ESSAY}:
            if hasattr(answer, "text_response"):
                return {"text": answer.text_response.text}

        elif q_type == QuestionType.NUMERIC:
            if hasattr(answer, "numeric_response"):
                return {"value": str(answer.numeric_response.value)}

        elif q_type == QuestionType.FILL_BLANK:
            responses = {
                (str(b.published_blank.public_id) if b.published_blank_id else str(b.blank_id)): b.answer
                for b in answer.blank_responses.all()
            }
            return {"responses": responses}

        elif q_type == QuestionType.MATCHING:
            if obj.published_question_id:
                matches = {
                    str(item.published_left_item.public_id): str(item.published_right_item.public_id)
                    for item in answer.matching_responses.select_related(
                        "published_left_item", "published_right_item"
                    )
                }
                return {"matches": matches}
            presentation = obj.matching_item_order.all()
            left_ids = {
                item.matching_pair_id: str(item.public_id)
                for item in presentation
                if item.side == AttemptMatchingItem.Side.LEFT
            }
            right_ids = {
                item.matching_pair_id: str(item.public_id)
                for item in presentation
                if item.side == AttemptMatchingItem.Side.RIGHT
            }
            matches = {
                left_ids[m.left_pair_id]: right_ids[m.selected_right_pair_id]
                for m in answer.matching_responses.all()
            }
            return {"matches": matches}

        return None


class ExamAttemptSerializer(serializers.ModelSerializer):
    """
    Student-safe Exam Attempt detail serializer.
    Includes active countdown, answered/flagged aggregation, and sorted questions.
    """
    exam_id = serializers.IntegerField(source="cbt_exam.id", read_only=True)
    exam_title = serializers.SerializerMethodField()
    subject_name = serializers.CharField(source="cbt_exam.subject.name", read_only=True)
    classroom_name = serializers.CharField(source="cbt_exam.classroom.__str__", read_only=True)
    duration_minutes = serializers.SerializerMethodField()
    instructions = serializers.SerializerMethodField()
    shuffle_questions = serializers.SerializerMethodField()
    shuffle_options = serializers.SerializerMethodField()
    allow_back_navigation = serializers.SerializerMethodField()
    auto_submit = serializers.SerializerMethodField()
    total_marks = serializers.SerializerMethodField()
    remaining_seconds = serializers.SerializerMethodField()
    total_questions = serializers.SerializerMethodField()
    answered_count = serializers.SerializerMethodField()
    flagged_count = serializers.SerializerMethodField()
    questions = serializers.SerializerMethodField()
    server_time = serializers.SerializerMethodField()
    attempt_grant_id = serializers.SerializerMethodField()
    attempt_grant_status = serializers.SerializerMethodField()

    class Meta:
        model = ExamAttempt
        fields = [
            "id",
            "public_id",
            "exam_id",
            "exam_title",
            "subject_name",
            "classroom_name",
            "duration_minutes",
            "instructions",
            "shuffle_questions",
            "shuffle_options",
            "allow_back_navigation",
            "auto_submit",
            "total_marks",
            "status",
            "revision",
            "published_revision_id",
            "published_revision_hash",
            "published_schema_version",
            "attempt_grant_id",
            "attempt_grant_status",
            "started_at",
            "expires_at",
            "submitted_at",
            "submission_id",
            "submitted_revision",
            "submission_snapshot_hash",
            "server_time",
            "remaining_seconds",
            "total_questions",
            "answered_count",
            "flagged_count",
            "questions",
            "created_at",
        ]

    def get_total_marks(self, obj):
        total = (
            sum(q.marks for q in obj.published_revision.questions.all())
            if obj.published_revision_id
            else sum(q.marks for q in obj.cbt_exam.exam_questions.all())
        )
        return str(total) if total else "0.00"

    def get_exam_title(self, obj):
        return obj.published_revision.title if obj.published_revision_id else obj.cbt_exam.title

    def get_duration_minutes(self, obj):
        return obj.published_revision.duration_minutes if obj.published_revision_id else obj.cbt_exam.duration_minutes

    def _config(self, obj, name):
        source = obj.published_revision if obj.published_revision_id else obj.cbt_exam
        return getattr(source, name)

    def get_instructions(self, obj):
        return self._config(obj, "instructions")

    def get_shuffle_questions(self, obj):
        return self._config(obj, "shuffle_questions")

    def get_shuffle_options(self, obj):
        return self._config(obj, "shuffle_options")

    def get_allow_back_navigation(self, obj):
        return self._config(obj, "allow_back_navigation")

    def get_auto_submit(self, obj):
        return self._config(obj, "auto_submit")

    published_revision_id = serializers.SerializerMethodField()
    published_revision_hash = serializers.SerializerMethodField()
    published_schema_version = serializers.SerializerMethodField()

    def get_published_revision_id(self, obj):
        return str(obj.published_revision.public_id) if obj.published_revision_id else None

    def get_published_revision_hash(self, obj):
        return obj.published_revision.content_hash if obj.published_revision_id else None

    def get_published_schema_version(self, obj):
        return obj.published_revision.schema_version if obj.published_revision_id else None

    def get_attempt_grant_id(self, obj):
        return str(obj.attempt_grant.public_id) if obj.attempt_grant_id else None

    def get_attempt_grant_status(self, obj):
        return obj.attempt_grant.status if obj.attempt_grant_id else None

    def get_server_time(self, obj):
        return timezone.now()

    def get_remaining_seconds(self, obj):
        now = timezone.now()
        if obj.expires_at > now:
            return max(0, int((obj.expires_at - now).total_seconds()))
        return 0

    def get_total_questions(self, obj):
        return obj.attempt_questions.count()

    def get_answered_count(self, obj):
        return obj.attempt_questions.filter(answer__is_answered=True).count()

    def get_flagged_count(self, obj):
        return obj.attempt_questions.filter(is_flagged=True).count()

    def get_questions(self, obj):
        questions = obj.attempt_questions.select_related(
            "exam_question__question_version__question",
            "published_question",
            "answer",
        ).prefetch_related(
            "option_order__question_option",
            "option_order__published_choice",
            "published_question__blanks",
            "published_question__media",
            "answer__selected_options",
            "answer__blank_responses",
            "answer__matching_responses",
            "matching_item_order__matching_pair",
            "matching_item_order__published_item",
        ).order_by("display_order")
        return AttemptQuestionSerializer(questions, many=True).data


class ExamAttemptListSerializer(serializers.ModelSerializer):
    exam_title = serializers.CharField(source="cbt_exam.title", read_only=True)
    subject_name = serializers.CharField(source="cbt_exam.subject.name", read_only=True)
    student_name = serializers.SerializerMethodField()
    admission_number = serializers.CharField(source="student.admission_number", read_only=True)

    class Meta:
        model = ExamAttempt
        fields = [
            "id",
            "public_id",
            "cbt_exam",
            "exam_title",
            "subject_name",
            "student",
            "student_name",
            "admission_number",
            "status",
            "revision",
            "started_at",
            "expires_at",
            "submitted_at",
            "created_at",
        ]

    def get_student_name(self, obj):
        user = getattr(obj.student, "user", None)
        return user.get_full_name() if user else ""
