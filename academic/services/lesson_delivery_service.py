from academic.models import LessonDeliveryStatus
from django.core.exceptions import ValidationError

class LessonDeliveryService:

    @staticmethod
    def validate_coverage(
        *,
        lesson_plan,
        objectives_covered,
        subtopics_covered,
    ):
        planned_objective_ids = set(
            lesson_plan.learning_objectives
            .values_list("id", flat=True)
        )

        covered_objective_ids = {
            objective.id
            for objective in objectives_covered
        }

        if not covered_objective_ids.issubset(
            planned_objective_ids
        ):
            raise ValidationError(
                "Covered objectives must belong to "
                "the lesson plan."
            )

        planned_subtopic_ids = set(
            lesson_plan.subtopics
            .values_list("id", flat=True)
        )

        covered_subtopic_ids = {
            subtopic.id
            for subtopic in subtopics_covered
        }

        if not covered_subtopic_ids.issubset(
            planned_subtopic_ids
        ):
            raise ValidationError(
                "Covered subtopics must belong to "
                "the lesson plan."
            )

    @staticmethod
    def validate_status(
        *,
        status,
        objectives_covered,
        subtopics_covered,
    ):
        has_coverage = bool(
            objectives_covered or subtopics_covered
        )

        if (
            status in {
                LessonDeliveryStatus.NOT_TAUGHT,
                LessonDeliveryStatus.RESCHEDULED,
            }
            and has_coverage
        ):
            raise ValidationError(
                "A lesson marked as not taught or "
                "rescheduled cannot have covered content."
            )

    @staticmethod
    def validate_recorder(
        *,
        lesson_plan,
        recorded_by,
    ):
        if recorded_by is None:
            return

        allocated_teacher = (
            lesson_plan.allocation.teacher_name
        )

        if recorded_by != allocated_teacher:
            raise ValidationError(
                "Lesson delivery must be recorded by "
                "the teacher allocated to this lesson."
            )