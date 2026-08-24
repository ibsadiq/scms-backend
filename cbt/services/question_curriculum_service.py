# question_curriculum_service.py

from django.core.exceptions import ValidationError


class QuestionCurriculumService:

    @staticmethod
    def validate_objective(
        *,
        question_version,
        learning_objective,
    ):
        question = question_version.question
        curriculum_topic = (
            learning_objective.curriculum_topic
        )

        if (
            curriculum_topic.topic.subject_id
            != question.subject_id
        ):
            raise ValidationError(
                "Learning objective subject must match "
                "the question subject."
            )

        if (
            question.topic_id
            and curriculum_topic.topic_id
            != question.topic_id
        ):
            raise ValidationError(
                "Learning objective must belong to the "
                "question's selected topic."
            )

        if (
            question.subtopic_id
            and learning_objective.subtopic_id
            and learning_objective.subtopic_id
            != question.subtopic_id
        ):
            raise ValidationError(
                "Learning objective subtopic must match "
                "the question's selected subtopic."
            )
        question_grade_ids = set(
            question.grade_levels.values_list(
                "id",
                flat=True,
            )
        )

        objective_grade_id = (
            curriculum_topic.curriculum_subject.grade_level_id
        )

        if objective_grade_id not in question_grade_ids:
            raise ValidationError(
                "Learning objective grade level must be "
                "included in the question grade levels."
            )

    @staticmethod
    def validate_question_grade_scope(
        *,
        question,
        grade_levels,
    ):
        grade_ids = {
            grade.id
            for grade in grade_levels
        }

        if (
            question.topic_id
            and question.topic.grade_level_id
            not in grade_ids
        ):
            raise ValidationError(
                "The selected topic's grade level must be "
                "included in the question grade levels."
            )

    @staticmethod
    def validate_bank_grade_scope(
        *,
        question,
        grade_levels,
    ):
        if not question.bank_id:
            return

        bank_grade_ids = set(
            question.bank.grade_levels.values_list(
                "id",
                flat=True,
            )
        )

        # Empty bank grade scope means unrestricted.
        if not bank_grade_ids:
            return

        submitted_ids = {
            grade.id
            for grade in grade_levels
        }

        if not submitted_ids.issubset(bank_grade_ids):
            raise ValidationError(
                "Question grade levels must fall within "
                "the question bank grade levels."
            )