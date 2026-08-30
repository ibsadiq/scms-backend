from urllib.parse import urlparse

from academic.models import CurriculumResource, LessonPlanMaterial, LessonPlanStatus
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

class LessonPlanMaterialService:

    @staticmethod
    def relevant_curriculum_resources(lesson_plan):
        from django.db.models import Q

        item = lesson_plan.scheme_item
        scope = Q(curriculum_topic__isnull=True, published_scheme_entry__isnull=True)
        if item.curriculum_topic_id:
            scope |= Q(curriculum_topic_id=item.curriculum_topic_id)
        if item.published_scheme_entry_id:
            scope |= Q(published_scheme_entry_id=item.published_scheme_entry_id)
        return CurriculumResource.objects.filter(
            Q(curriculum_subject_id=item.scheme.curriculum_subject_id),
            scope,
            is_active=True,
        ).select_related(
            "curriculum_subject__curriculum",
            "curriculum_topic",
            "published_scheme_entry",
            "source",
        ).distinct()

    @staticmethod
    def _resource_url(resource):
        metadata = resource.metadata or {}
        candidates = [metadata.get("external_url"), metadata.get("url"), resource.source_reference]
        for candidate in candidates:
            if candidate and urlparse(str(candidate)).scheme in {"http", "https"}:
                return str(candidate)
        return ""

    @classmethod
    def add_curriculum_resource(cls, *, lesson_plan, resource):
        cls.require_mutable(lesson_plan)
        if not cls.relevant_curriculum_resources(lesson_plan).filter(pk=resource.pk).exists():
            raise ValidationError("This curriculum resource is not relevant to the lesson plan context.")
        if LessonPlanMaterial.objects.filter(
            lesson_plan=lesson_plan,
            source_curriculum_resource=resource,
        ).exists():
            raise ValidationError("This curriculum resource has already been added to the lesson plan.")

        external_url = cls._resource_url(resource)
        content = resource.content or ""
        if not external_url and not content.strip():
            raise ValidationError("This curriculum resource has no URL or textual content to copy.")

        curriculum = resource.curriculum_subject.curriculum
        try:
            with transaction.atomic():
                return LessonPlanMaterial.objects.create(
                    lesson_plan=lesson_plan,
                    title=resource.title,
                    description=resource.content,
                    content=content,
                    external_url=external_url,
                    source_curriculum_resource=resource,
                    source_resource_title=resource.title,
                    source_resource_type=resource.resource_type,
                    source_curriculum_name=curriculum.name,
                    source_curriculum_version=curriculum.version,
                )
        except IntegrityError as exc:
            raise ValidationError(
                "This curriculum resource has already been added to the lesson plan."
            ) from exc

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
        content="",
    ):
        if not file and not external_url and not str(content or "").strip():
            raise ValidationError(
                "Provide a file, external URL, or textual content."
            )

        if file and external_url:
            raise ValidationError(
                "Provide either a file or external URL, "
                "not both."
            )

        LessonPlanMaterialService.require_mutable(lesson_plan)
