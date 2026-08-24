from django.core.exceptions import ValidationError
from django.db.models import Q

from cbt.models import (
    Question,
    QuestionStatus,
)


class BlueprintValidationService:

    @staticmethod
    def validate(blueprint):
        if blueprint.is_locked:
            raise ValidationError(
                "A locked blueprint cannot be regenerated."
            )

        rules = list(
            blueprint.rules
            .select_related(
                "topic",
                "subtopic",
                "learning_objective",
                "learning_objective__curriculum_topic",
                "learning_objective__curriculum_topic__topic",
            )
            .order_by("order", "id")
        )

        if not rules:
            raise ValidationError(
                "The blueprint must contain at least one rule."
            )

        selected_question_ids = set()

        for rule in rules:
            BlueprintValidationService.validate_rule_context(
                rule
            )

            candidates = (
                BlueprintValidationService
                .get_candidates(
                    rule=rule,
                    exclude_question_ids=selected_question_ids,
                )
            )

            available_ids = list(
                candidates.values_list(
                    "id",
                    flat=True,
                )[:rule.question_count]
            )

            if len(available_ids) < rule.question_count:
                available_count = candidates.count()

                raise ValidationError(
                    {
                        "blueprint": (
                            f"Rule {rule.order} requires "
                            f"{rule.question_count} questions, "
                            f"but only {available_count} eligible "
                            f"questions are available after "
                            f"excluding questions already allocated "
                            f"to earlier rules."
                        )
                    }
                )

            selected_question_ids.update(
                available_ids
            )

        return True

    @staticmethod
    def validate_rule_context(rule):
        exam = rule.blueprint.cbt_exam

        exam_grade_level = (
            exam.classroom.name.grade_level
        )

        if rule.topic_id:
            if rule.topic.subject_id != exam.subject_id:
                raise ValidationError(
                    {
                        "topic": (
                            f"Rule {rule.order}: topic subject "
                            f"must match the CBT exam subject."
                        )
                    }
                )

            if (
                rule.topic.grade_level_id
                != exam_grade_level.id
            ):
                raise ValidationError(
                    {
                        "topic": (
                            f"Rule {rule.order}: topic grade level "
                            f"must match the CBT exam classroom "
                            f"grade level."
                        )
                    }
                )

        if rule.subtopic_id:
            if not rule.topic_id:
                raise ValidationError(
                    {
                        "subtopic": (
                            f"Rule {rule.order}: a topic is "
                            f"required when a subtopic is selected."
                        )
                    }
                )

            if rule.subtopic.topic_id != rule.topic_id:
                raise ValidationError(
                    {
                        "subtopic": (
                            f"Rule {rule.order}: subtopic must "
                            f"belong to the selected topic."
                        )
                    }
                )

        if rule.learning_objective_id:
            objective = rule.learning_objective
            curriculum_topic = (
                objective.curriculum_topic
            )

            if (
                curriculum_topic.curriculum_subject.subject_id
                != exam.subject_id
            ):
                raise ValidationError(
                    {
                        "learning_objective": (
                            f"Rule {rule.order}: learning objective "
                            f"subject must match the CBT exam subject."
                        )
                    }
                )

            if (
                curriculum_topic.curriculum_subject.grade_level_id
                != exam_grade_level.id
            ):
                raise ValidationError(
                    {
                        "learning_objective": (
                            f"Rule {rule.order}: learning objective "
                            f"grade level must match the CBT exam "
                            f"classroom grade level."
                        )
                    }
                )

    @staticmethod
    def get_candidates(
        *,
        rule,
        exclude_question_ids=None,
    ):
        exam = rule.blueprint.cbt_exam

        exam_grade_level = (
            exam.classroom.name.grade_level
        )

        candidates = (
            Question.objects
            .filter(
                subject=exam.subject,
                grade_levels=exam_grade_level,
                status=QuestionStatus.APPROVED,
                is_active=True,
                current_version__isnull=False,
            )
            .filter(
                Q(bank__isnull=True)
                | Q(bank__is_active=True)
            )
        )

        if exclude_question_ids:
            candidates = candidates.exclude(
                id__in=exclude_question_ids
            )

        if rule.topic_id:
            candidates = candidates.filter(
                topic_id=rule.topic_id
            )

        if rule.subtopic_id:
            candidates = candidates.filter(
                subtopic_id=rule.subtopic_id
            )

        if rule.question_type:
            candidates = candidates.filter(
                question_type=rule.question_type
            )

        if rule.difficulty:
            candidates = candidates.filter(
                difficulty=rule.difficulty
            )

        if rule.learning_objective_id:
            candidates = candidates.filter(
                current_version__objective_alignments__learning_objective_id=(
                    rule.learning_objective_id
                )
            )

        return (
            candidates
            .select_related(
                "current_version",
                "topic",
                "subtopic",
            )
            .distinct()
            .order_by("id")
        )

    @staticmethod
    def rule_specificity(rule):
        score = 0

        if rule.learning_objective_id:
            score += 8

        if rule.subtopic_id:
            score += 4

        if rule.topic_id:
            score += 2

        if rule.question_type:
            score += 1

        if rule.difficulty:
            score += 1

        return score