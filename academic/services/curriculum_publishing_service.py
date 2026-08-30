from django.core.exceptions import ValidationError
from django.db import transaction

from academic.models import (
    CurriculumResource,
    PublishedScheme,
    PublishedSchemeEntry,
)


class PublishedSchemeService:
    """Validated persistence for authoritative published schemes and entries."""

    @staticmethod
    def validate_entry_selections(*, curriculum_topic, subtopics, learning_objectives):
        subtopics = list(subtopics or [])
        learning_objectives = list(learning_objectives or [])

        if curriculum_topic is None and (subtopics or learning_objectives):
            raise ValidationError(
                "A curriculum topic is required when subtopics or objectives are selected."
            )

        if curriculum_topic is None:
            return

        unrelated_subtopics = [
            subtopic.pk
            for subtopic in subtopics
            if subtopic.topic_id != curriculum_topic.topic_id
        ]
        if unrelated_subtopics:
            raise ValidationError(
                {"subtopics": "Every subtopic must belong to the selected curriculum topic."}
            )

        unrelated_objectives = [
            objective.pk
            for objective in learning_objectives
            if objective.curriculum_topic_id != curriculum_topic.pk
        ]
        if unrelated_objectives:
            raise ValidationError(
                {
                    "learning_objectives": (
                        "Every learning objective must belong to the selected curriculum topic."
                    )
                }
            )

    @classmethod
    @transaction.atomic
    def save_scheme(cls, *, instance=None, **validated_data):
        scheme = instance or PublishedScheme()
        for field, value in validated_data.items():
            setattr(scheme, field, value)
        scheme.full_clean()
        scheme.save()
        return scheme

    @classmethod
    @transaction.atomic
    def save_entry(
        cls,
        *,
        instance=None,
        subtopics=None,
        learning_objectives=None,
        **validated_data,
    ):
        entry = instance or PublishedSchemeEntry()
        for field, value in validated_data.items():
            setattr(entry, field, value)

        selected_subtopics = (
            list(subtopics)
            if subtopics is not None
            else list(entry.subtopics.all()) if entry.pk else []
        )
        selected_objectives = (
            list(learning_objectives)
            if learning_objectives is not None
            else list(entry.learning_objectives.all()) if entry.pk else []
        )
        cls.validate_entry_selections(
            curriculum_topic=entry.curriculum_topic,
            subtopics=selected_subtopics,
            learning_objectives=selected_objectives,
        )
        entry.full_clean()
        entry.save()
        if subtopics is not None:
            entry.subtopics.set(selected_subtopics)
        if learning_objectives is not None:
            entry.learning_objectives.set(selected_objectives)
        return entry


class CurriculumResourceService:
    """Validated persistence for official curriculum-owned resources."""

    @staticmethod
    @transaction.atomic
    def save_resource(*, instance=None, **validated_data):
        resource = instance or CurriculumResource()
        for field, value in validated_data.items():
            setattr(resource, field, value)
        resource.full_clean()
        resource.save()
        return resource
