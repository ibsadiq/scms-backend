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
    option_id = serializers.IntegerField(source="question_option.id", read_only=True)
    text = serializers.CharField(source="question_option.text", read_only=True)

    class Meta:
        model = AttemptQuestionOption
        fields = [
            "id",
            "option_id",
            "text",
            "display_order",
        ]


class AttemptQuestionSerializer(serializers.ModelSerializer):
    """
    Student-safe question representation.
    Uses attempt-level display_order and option shuffle order.
    NEVER includes answer keys or grading rubrics!
    """
    question_type = serializers.CharField(
        source="exam_question.question_version.question_type", read_only=True
    )
    question_text = serializers.CharField(
        source="exam_question.question_version.text", read_only=True
    )
    instructions = serializers.CharField(
        source="exam_question.question_version.instructions", read_only=True
    )
    marks = serializers.DecimalField(
        source="exam_question.marks", max_digits=5, decimal_places=2, read_only=True
    )
    options = serializers.SerializerMethodField()
    student_response = serializers.SerializerMethodField()
    blank_items = serializers.SerializerMethodField()
    matching_items = serializers.SerializerMethodField()

    class Meta:
        model = AttemptQuestion
        fields = [
            "id",
            "display_order",
            "question_type",
            "question_text",
            "instructions",
            "marks",
            "is_flagged",
            "options",
            "blank_items",
            "matching_items",
            "student_response",
        ]

    def get_options(self, obj):
        # Order options according to the attempt's presentation ordering
        option_orders = obj.option_order.select_related("question_option").order_by("display_order")
        return AttemptQuestionOptionSerializer(option_orders, many=True).data

    def get_blank_items(self, obj):
        version = obj.exam_question.question_version
        if version.question_type == QuestionType.FILL_BLANK:
            if hasattr(version, "fill_blank_definition"):
                items = version.fill_blank_definition.blanks.order_by("position")
                return [{"id": item.id, "position": item.position} for item in items]
        return []

    def get_matching_items(self, obj):
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
        q_type = obj.exam_question.question_version.question_type

        if q_type in {QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE, QuestionType.TRUE_FALSE}:
            selected_ids = list(
                answer.selected_options.values_list("question_option_id", flat=True)
            )
            return {"option_ids": selected_ids}

        elif q_type in {QuestionType.SHORT_ANSWER, QuestionType.ESSAY}:
            if hasattr(answer, "text_response"):
                return {"text": answer.text_response.text}

        elif q_type == QuestionType.NUMERIC:
            if hasattr(answer, "numeric_response"):
                return {"value": str(answer.numeric_response.value)}

        elif q_type == QuestionType.FILL_BLANK:
            responses = {
                str(b.blank_id): b.answer
                for b in answer.blank_responses.all()
            }
            return {"responses": responses}

        elif q_type == QuestionType.MATCHING:
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
    exam_title = serializers.CharField(source="cbt_exam.title", read_only=True)
    subject_name = serializers.CharField(source="cbt_exam.subject.name", read_only=True)
    classroom_name = serializers.CharField(source="cbt_exam.classroom.__str__", read_only=True)
    duration_minutes = serializers.IntegerField(source="cbt_exam.duration_minutes", read_only=True)
    total_marks = serializers.SerializerMethodField()
    remaining_seconds = serializers.SerializerMethodField()
    total_questions = serializers.SerializerMethodField()
    answered_count = serializers.SerializerMethodField()
    flagged_count = serializers.SerializerMethodField()
    questions = serializers.SerializerMethodField()

    class Meta:
        model = ExamAttempt
        fields = [
            "id",
            "exam_id",
            "exam_title",
            "subject_name",
            "classroom_name",
            "duration_minutes",
            "total_marks",
            "status",
            "started_at",
            "expires_at",
            "submitted_at",
            "remaining_seconds",
            "total_questions",
            "answered_count",
            "flagged_count",
            "questions",
            "created_at",
        ]

    def get_total_marks(self, obj):
        total = sum(q.marks for q in obj.cbt_exam.exam_questions.all())
        return str(total) if total else "0.00"

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
            "answer",
        ).prefetch_related(
            "option_order__question_option",
            "answer__selected_options",
            "answer__blank_responses",
            "answer__matching_responses",
            "matching_item_order__matching_pair",
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
            "cbt_exam",
            "exam_title",
            "subject_name",
            "student",
            "student_name",
            "admission_number",
            "status",
            "started_at",
            "expires_at",
            "submitted_at",
            "created_at",
        ]

    def get_student_name(self, obj):
        user = getattr(obj.student, "user", None)
        return user.get_full_name() if user else ""
