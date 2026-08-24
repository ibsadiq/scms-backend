from academic.models import LessonPlanStatus
from django.core.exceptions import ValidationError

class LessonPlanMaterialService:

    @staticmethod
    def require_mutable(lesson_plan):
        if lesson_plan.status in {
            LessonPlanStatus.SUBMITTED,
            LessonPlanStatus.APPROVED,
        }:
            raise ValidationError(
                "Materials cannot be changed while the "
                "lesson plan is submitted or approved."
            )

    @staticmethod
    def validate_material(
        *,
        lesson_plan,
        file=None,
        external_url="",
    ):
        if not file and not external_url:
            raise ValidationError(
                "Provide either a file or external URL."
            )

        if file and external_url:
            raise ValidationError(
                "Provide either a file or external URL, "
                "not both."
            )

        LessonPlanMaterialService.require_mutable(lesson_plan)
