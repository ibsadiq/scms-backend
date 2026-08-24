import random

from django.core.exceptions import ValidationError
from django.db import transaction

from cbt.models import (
    CBTExamStatus,
    ExamQuestion,
)

from .blueprint_validation_service import (
    BlueprintValidationService,
)


class ExamGenerationService:

    @staticmethod
    @transaction.atomic
    def generate(*, blueprint):
        """
        Generate and materialize ExamQuestion records
        from an ExamBlueprint.
        """

        # Lock the blueprint row for the duration
        # of generation.
        blueprint = (
            blueprint.__class__.objects
            .select_for_update()
            .select_related("cbt_exam")
            .get(pk=blueprint.pk)
        )

        exam = blueprint.cbt_exam

        # Validate before making any changes.
        BlueprintValidationService.validate(
            blueprint
        )

        # Defensive check.
        if exam.exam_questions.exists():
            raise ValidationError(
                "This CBT exam already has generated questions."
            )

        rules = list(
            blueprint.rules
            .select_related(
                "topic",
                "subtopic",
                "learning_objective",
                "learning_objective__curriculum_topic",
                "learning_objective__curriculum_topic__topic",
                "learning_objective__curriculum_topic__curriculum_subject",
            )
        )

        rules = sorted(
            rules,
            key=lambda rule: (
                -BlueprintValidationService
                .rule_specificity(rule),
                rule.order,
                rule.id,
            ),
        )

        selected_question_ids = set()
        selected = []

        for rule in rules:
            candidates = (
                BlueprintValidationService
                .get_candidates(
                    rule=rule,
                    exclude_question_ids=selected_question_ids,
                )
            )

            candidate_ids = list(
                candidates.values_list(
                    "id",
                    flat=True,
                )
            )

            if len(candidate_ids) < rule.question_count:
                raise ValidationError(
                    {
                        "blueprint": (
                            f"Rule {rule.order} requires "
                            f"{rule.question_count} questions, "
                            f"but only {len(candidate_ids)} "
                            f"eligible questions are available."
                        )
                    }
                )

            selected_ids = random.sample(
                candidate_ids,
                rule.question_count,
            )

            selected_questions = {
                question.id: question
                for question in (
                    candidates
                    .filter(id__in=selected_ids)
                    .select_related("current_version")
                )
            }

            for question_id in selected_ids:
                question = selected_questions[
                    question_id
                ]

                selected.append(
                    (
                        rule,
                        question,
                    )
                )

                selected_question_ids.add(
                    question.id
                )

        ExamGenerationService._materialize(
            exam=exam,
            selected=selected,
        )

        blueprint.is_locked = True
        blueprint.save(
            update_fields=[
                "is_locked",
                "updated_at",
            ]
        )

        exam.status = CBTExamStatus.READY
        exam.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        return exam


    @staticmethod
    def _materialize(
        *,
        exam,
        selected,
    ):
        exam_questions = []

        for order, (
            rule,
            question,
        ) in enumerate(
            selected,
            start=1,
        ):
            version = question.current_version

            if version is None:
                raise ValidationError(
                    f"Question {question.pk} has no "
                    f"current version."
                )

            exam_questions.append(
                ExamQuestion(
                    cbt_exam=exam,
                    question_version=version,
                    blueprint_rule=rule,
                    order=order,
                    marks=version.default_marks,
                )
            )

        ExamQuestion.objects.bulk_create(
            exam_questions
        )