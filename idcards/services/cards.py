from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from academic.models import Staff, Student
from idcards.models import HolderType, IDCard, RFIDCredential
from .fields import DynamicFieldRegistry
from .layout import TemplateService
from .templates import IDCardTemplateLifecycleService
from .resolution import IDCardTemplateResolver


class CardService:
    @classmethod
    def _next_number(cls):
        year = timezone.localdate().year
        prefix = f"IDC-{year}-"
        last = IDCard.objects.select_for_update().filter(card_number__startswith=prefix).order_by("-card_number").first()
        sequence = int(last.card_number.rsplit("-", 1)[1]) + 1 if last else 1
        return f"{prefix}{sequence:06d}"

    @classmethod
    def _issue(cls, *, template, template_version=None, student=None, staff=None, issued_by=None, expires_at=None):
        # Lifecycle operations may have published the caller's template in a
        # separate service call; always evaluate issuance against database state.
        template = type(template).objects.select_related("current_published_version").get(pk=template.pk)
        holder_type = HolderType.STUDENT if student else HolderType.STAFF if staff else None
        if bool(student) == bool(staff):
            raise ValidationError("Provide exactly one student or staff member.")
        if not template.is_active:
            raise ValidationError({"template": "Inactive templates cannot issue cards."})
        if template.holder_type != holder_type:
            raise ValidationError({"template": "Template holder type does not match the card holder."})
        if template_version is None:
            template_version = IDCardTemplateLifecycleService.ensure_legacy_published_version(template, actor=issued_by)
        if template_version.template_id != template.pk:
            raise ValidationError({"template_version": "Template version does not belong to the selected template."})
        was_published = (
            template_version.status == template_version.Status.PUBLISHED
            or (template_version.status == template_version.Status.ARCHIVED and template_version.published_at is not None)
        )
        if not was_published:
            raise ValidationError({"template_version": "Cards can only be issued from a published template version."})
        template_version.full_clean()
        with transaction.atomic():
            holder_model = Student if student else Staff
            holder = holder_model.objects.select_for_update().get(pk=(student or staff).pk)
            student = holder if student else None
            staff = holder if staff else None
            holder_filter = {"student": student} if student else {"staff": staff}
            if IDCard.objects.filter(status=IDCard.Status.ACTIVE, **holder_filter).exists():
                raise ValidationError({"code": "ACTIVE_CARD_EXISTS", "holder": "This holder already has an active ID card."})
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    [f"{connection.schema_name}:idcards:card-number:{timezone.localdate().year}"],
                )
            try:
                with transaction.atomic():
                    card = IDCard(
                        student=student, staff=staff, template=template, template_version=template_version,
                        card_number=cls._next_number(),
                        issued_by=issued_by, expires_at=expires_at,
                    )
                    card.full_clean()
                    card.save()
            except IntegrityError:
                if IDCard.objects.filter(status=IDCard.Status.ACTIVE, **holder_filter).exists():
                    raise ValidationError({"code": "ACTIVE_CARD_EXISTS", "holder": "This holder already has an active ID card."})
                raise ValidationError({"code": "CARD_NUMBER_CONFLICT", "card_number": "Could not allocate a unique card number."})
        return card

    @classmethod
    def issue_student_card(cls, *, student, template=None, issued_by=None, expires_at=None):
        resolution = IDCardTemplateResolver.resolve_for_student(student) if template is None else None
        return cls._issue(student=student, template=template or resolution.template,
                          template_version=resolution.template_version if resolution else None,
                          issued_by=issued_by, expires_at=expires_at)

    @classmethod
    def issue_staff_card(cls, *, staff, template=None, issued_by=None, expires_at=None):
        resolution = IDCardTemplateResolver.resolve_for_staff(staff) if template is None else None
        return cls._issue(staff=staff, template=template or resolution.template,
                          template_version=resolution.template_version if resolution else None,
                          issued_by=issued_by, expires_at=expires_at)

    @classmethod
    def deactivate_card(cls, card, *, reason="", revoke=False):
        if card.status != IDCard.Status.ACTIVE:
            raise ValidationError("Only an active card can be deactivated.")
        card.status = IDCard.Status.REVOKED if revoke else IDCard.Status.INACTIVE
        card.deactivated_at = timezone.now()
        card.deactivation_reason = reason
        card.save(update_fields=("status", "deactivated_at", "deactivation_reason", "updated_at"))
        return card

    @classmethod
    @transaction.atomic
    def replace_card(cls, card, *, template=None, template_version=None, actor=None, reason="Replacement", expires_at=None):
        holder_model = Student if card.student_id else Staff
        holder_id = card.student_id or card.staff_id
        holder = holder_model.objects.select_for_update().get(pk=holder_id)
        card = IDCard.objects.select_for_update().get(pk=card.pk)
        if card.status != IDCard.Status.ACTIVE:
            raise ValidationError({"code": "CARD_NOT_ACTIVE", "card": "Only an active card can be replaced."})

        RFIDCredential.objects.select_for_update().filter(
            id_card=card, status=RFIDCredential.Status.ACTIVE
        ).update(
            status=RFIDCredential.Status.REPLACED,
            revoked_at=timezone.now(),
            revoked_by=actor,
            revocation_reason=reason,
            updated_at=timezone.now(),
        )
        replaced_at = timezone.now()
        card.status = IDCard.Status.REPLACED
        card.deactivated_at = replaced_at
        card.deactivation_reason = reason
        card.save(update_fields=("status", "deactivated_at", "deactivation_reason", "updated_at"))

        kwargs = {"student": holder} if card.student_id else {"staff": holder}
        replacement = cls._issue(
            template=template or card.template,
            template_version=template_version or (card.template_version if not template else None),
            issued_by=actor,
            expires_at=expires_at,
            **kwargs,
        )
        replacement.replaces = card
        replacement.replacement_reason = reason
        replacement.replaced_at = replaced_at
        replacement.replaced_by = actor
        replacement.save(update_fields=(
            "replaces", "replacement_reason", "replaced_at", "replaced_by", "updated_at"
        ))
        return replacement

    @classmethod
    def prepare_card_context(cls, card):
        version = card.template_version or card.template.current_published_version
        return {
            "card": card,
            "template": card.template,
            "template_version": version,
            "values": DynamicFieldRegistry.resolve(TemplateService.dynamic_keys(version or card.template), card),
        }
