from django.db import transaction
from django.db import models
from django.core.exceptions import ValidationError
from typing import List, Dict, Any

from examination.models import (
    TermResult, BehavioralTrait, StudentBehavioralRating, LifecycleState
)
from academic.models import ClassRoom

class BehavioralRatingService:
    """
    Service layer for managing student behavioral (Affective & Psychomotor) ratings.
    Ensures lifecycle constraints, authorization, and data integrity.
    """

    RATING_INDEX = [
        {"value": 5, "label": "Excellent"},
        {"value": 4, "label": "Very Good"},
        {"value": 3, "label": "Good"},
        {"value": 2, "label": "Fair"},
        {"value": 1, "label": "Needs Improvement"}
    ]

    @classmethod
    def get_applicable_traits(cls, student_section: str = None) -> List[BehavioralTrait]:
        """
        Get all active behavioral traits applicable to a specific section,
        including school-wide traits.
        """
        queryset = BehavioralTrait.objects.filter(is_active=True)
        if student_section:
            return list(queryset.filter(
                models.Q(section__isnull=True) | models.Q(section=student_section)
            ))
        return list(queryset)

    @classmethod
    def validate_term_result_editable(cls, term_result: TermResult):
        """
        Validate if the term result's lifecycle state permits editing behavioral ratings.
        """
        if term_result.lifecycle_state in [
            LifecycleState.HOMEROOM_APPROVED,
            LifecycleState.ADMIN_APPROVED,
            LifecycleState.LOCKED,
            LifecycleState.PUBLISHED
        ]:
            raise ValidationError(
                f"Cannot modify behavioral ratings because the result is in '{term_result.lifecycle_state}' state."
            )

    @classmethod
    def authorize_user_for_rating(cls, user, term_result: TermResult):
        """
        Validate if the user is authorized to enter behavioral ratings for this result.
        Only the homeroom teacher, or admin/management can enter it.
        """
        if not user or not user.is_authenticated:
            raise ValidationError("Authentication credentials were not provided.")
        if user.is_superuser or getattr(user, 'is_admin', False) or user.groups.filter(name__in=["admin", "management"]).exists():
            return True

        classroom = term_result.classroom
        if not classroom:
            raise ValidationError("Term result is not linked to a classroom.")

        if classroom.class_teacher_id:
            from academic.models import Teacher
            if Teacher.objects.filter(id=classroom.class_teacher_id, user=user).exists():
                return True
            if hasattr(classroom, "class_teacher") and classroom.class_teacher and classroom.class_teacher.user_id == user.id:
                return True

        teacher = getattr(user, 'teacher', None)
        if not teacher:
            from academic.models import Teacher
            teacher = Teacher.objects.filter(user=user).first()

        if teacher and classroom.class_teacher_id == teacher.id:
            return True

        raise ValidationError("You are not authorized to enter behavioral ratings for this classroom.")

    @classmethod
    @transaction.atomic
    def record_rating(cls, term_result: TermResult, trait: BehavioralTrait, rating: int, user):
        """
        Record a single behavioral rating.
        """
        cls.validate_term_result_editable(term_result)
        cls.authorize_user_for_rating(user, term_result)

        if rating < 1 or rating > 5:
            raise ValidationError("Rating must be between 1 and 5.")

        if not trait.is_active:
            raise ValidationError(f"Trait '{trait.name}' is inactive and cannot be rated.")

        student_section = None
        if term_result.classroom and term_result.classroom.grade_level:
            student_section = term_result.classroom.grade_level.section

        if trait.section and trait.section != student_section:
            raise ValidationError(
                f"Trait '{trait.name}' does not apply to section '{student_section}'."
            )

        obj, created = StudentBehavioralRating.objects.update_or_create(
            term_result=term_result,
            trait=trait,
            defaults={
                'rating': rating,
                'entered_by': user
            }
        )
        return obj

    @classmethod
    @transaction.atomic
    def bulk_record_ratings(cls, term_result: TermResult, ratings_data: List[Dict[str, Any]], user):
        """
        Bulk record multiple ratings for a single TermResult.
        ratings_data format: [{"trait_id": 1, "rating": 5}, ...]
        """
        cls.validate_term_result_editable(term_result)
        cls.authorize_user_for_rating(user, term_result)

        student_section = None
        if term_result.classroom and term_result.classroom.grade_level:
            student_section = term_result.classroom.grade_level.section

        trait_ids = [item['trait_id'] for item in ratings_data]
        traits = BehavioralTrait.objects.filter(id__in=trait_ids)
        trait_map = {t.id: t for t in traits}

        for item in ratings_data:
            trait_id = item.get('trait_id')
            rating = item.get('rating')

            if not trait_id or rating is None:
                raise ValidationError("Each rating must provide 'trait_id' and 'rating'.")
            
            try:
                rating_int = int(rating)
            except (ValueError, TypeError):
                raise ValidationError(f"Invalid rating value '{rating}' for trait ID {trait_id}.")

            if rating_int < 1 or rating_int > 5:
                raise ValidationError(f"Rating for trait ID {trait_id} must be between 1 and 5.")

            trait = trait_map.get(trait_id)
            if not trait:
                raise ValidationError(f"Behavioral trait with ID {trait_id} does not exist.")

            if not trait.is_active:
                raise ValidationError(f"Trait '{trait.name}' is inactive and cannot be rated.")

            if trait.section and trait.section != student_section:
                raise ValidationError(
                    f"Trait '{trait.name}' does not apply to section '{student_section}'."
                )

            StudentBehavioralRating.objects.update_or_create(
                term_result=term_result,
                trait=trait,
                defaults={
                    'rating': rating_int,
                    'entered_by': user
                }
            )
