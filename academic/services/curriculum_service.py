from django.core.exceptions import ValidationError


class CurriculumService:

    @staticmethod
    def validate_topic_mapping(
        *,
        curriculum_subject,
        topic,
    ):
        if (
            topic
            and topic.subject_id
            and curriculum_subject.subject_id
            and topic.subject_id != curriculum_subject.subject_id
        ):
            raise ValidationError(
                "Topic subject must match the "
                "curriculum subject."
            )

        if (
            topic
            and topic.grade_level_id
            and topic.grade_level_id != curriculum_subject.grade_level_id
        ):
            raise ValidationError(
                "Topic grade level must match the "
                "curriculum subject grade level."
            )

    @staticmethod
    def validate_objective_subtopic(
        *,
        curriculum_topic,
        subtopic,
    ):
        if subtopic:
            if (
                subtopic.topic_id
                and curriculum_topic.topic_id
                and subtopic.topic_id != curriculum_topic.topic_id
            ):
                raise ValidationError(
                    "Subtopic must belong to the "
                    "curriculum topic."
                )
            if (
                curriculum_topic.pk
                and curriculum_topic.subtopics.exists()
                and not curriculum_topic.subtopics.filter(pk=subtopic.pk).exists()
            ):
                raise ValidationError(
                    "Subtopic must belong to the "
                    "curriculum topic."
                )