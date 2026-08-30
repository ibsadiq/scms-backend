from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q

from academic.models import (
    AllocatedSubject,
    PublishedSchemeEntryType,
    SchemeOfWork,
    SchemeOfWorkItem,
)
from .academic_authority_service import AcademicAuthorityService
from .scheme_of_work_service import SchemeOfWorkService


class PublishedSchemeAdoptionService:
    """Atomic, idempotent copy of one official term into a school scheme."""

    @staticmethod
    def _term_number(term):
        term_ids = list(
            term.academic_year.terms.order_by("start_date", "id").values_list("id", flat=True)
        )
        try:
            number = term_ids.index(term.id) + 1
        except ValueError as exc:
            raise ValidationError("Term does not belong to the selected academic year.") from exc
        if number not in {1, 2, 3}:
            raise ValidationError("Published schemes can only map to the first three chronological terms.")
        return number

    @staticmethod
    def _require_adoption_authority(*, actor, published_scheme, academic_year, term):
        if AcademicAuthorityService.is_school_admin(actor):
            return None
        teacher = AcademicAuthorityService.get_teacher(actor)
        if not teacher:
            raise PermissionDenied("A teacher profile is required to adopt a published scheme.")
        mapping = published_scheme.curriculum_subject
        if not mapping.subject:
            raise PermissionDenied(
                "This curriculum subject is not mapped to an operational school subject. Only school administrators may adopt unmapped curriculum subjects."
            )
        allowed = AllocatedSubject.objects.filter(
            teacher_name=teacher,
            subject=mapping.subject,
            class_room__grade_level=mapping.grade_level,
            academic_year=academic_year,
        ).filter(Q(term=term) | Q(term__isnull=True))
        if not allowed.exists():
            raise PermissionDenied("You do not have a matching teaching allocation for this scheme.")
        return teacher

    @classmethod
    def capability(cls, *, actor, published_scheme, academic_year, term):
        try:
            cls._require_adoption_authority(
                actor=actor, published_scheme=published_scheme,
                academic_year=academic_year, term=term,
            )
        except PermissionDenied as exc:
            return {"allowed": False, "reason": str(exc)}
        return {"allowed": True, "reason": ""}

    @classmethod
    @transaction.atomic
    def adopt(cls, *, published_scheme, academic_year, term, actor):
        if term.academic_year_id != academic_year.id:
            raise ValidationError("Term must belong to the selected academic year.")
        if not published_scheme.is_active or not published_scheme.curriculum_subject.is_active:
            raise ValidationError("Only an active published scheme and curriculum subject can be adopted.")

        responsible_teacher = cls._require_adoption_authority(
            actor=actor, published_scheme=published_scheme,
            academic_year=academic_year, term=term,
        )
        term_number = cls._term_number(term)
        entries = list(
            published_scheme.entries.filter(term_number=term_number, is_active=True)
            .select_related("curriculum_topic__topic")
            .prefetch_related("subtopics", "learning_objectives")
            .order_by("order", "week_start", "id")
        )
        if not entries:
            raise ValidationError("The published scheme has no active entries for this term.")

        for entry in entries:
            SchemeOfWorkService.validate_item(
                scheme=type("SchemeContext", (), {"curriculum_subject_id": published_scheme.curriculum_subject_id})(),
                curriculum_topic=entry.curriculum_topic,
                subtopics=entry.subtopics.all(),
                learning_objectives=entry.learning_objectives.all(),
            )
            if entry.entry_type == PublishedSchemeEntryType.INSTRUCTION and not entry.curriculum_topic_id:
                raise ValidationError(f"Published entry {entry.id} is instructional but has no curriculum topic.")

        scheme, scheme_created = SchemeOfWork.objects.get_or_create(
            academic_year=academic_year,
            term=term,
            curriculum_subject=published_scheme.curriculum_subject,
            is_active=True,
            defaults={"created_by": getattr(actor, "user", actor), "responsible_teacher": responsible_teacher},
        )
        if (
            not scheme_created
            and not AcademicAuthorityService.is_school_admin(actor)
            and (
                responsible_teacher is None
                or scheme.responsible_teacher_id != responsible_teacher.id
            )
        ):
            raise PermissionDenied("An active scheme already exists and belongs to another teacher.")
        if scheme.status != "DRAFT":
            raise ValidationError("Published entries can only be adopted into a draft scheme.")

        created = 0
        skipped = 0
        next_order = scheme.items.order_by("-order").values_list("order", flat=True).first() or 0
        for entry in entries:
            if scheme.items.filter(published_scheme_entry=entry).exists():
                skipped += 1
                continue
            next_order += 1
            item = SchemeOfWorkItem(
                scheme=scheme,
                published_scheme_entry=entry,
                entry_type=entry.entry_type,
                week_start=entry.week_start,
                week_end=entry.week_end,
                curriculum_topic=entry.curriculum_topic,
                title=entry.title,
                content_summary=entry.content_summary,
                teacher_activities=entry.teacher_activities,
                learner_activities=entry.pupil_activities,
                learning_resources=entry.learning_resources,
                order=next_order,
            )
            item.full_clean()
            item.save()
            item.subtopics.set(entry.subtopics.all())
            item.learning_objectives.set(entry.learning_objectives.all())
            created += 1
        return scheme, created, skipped
