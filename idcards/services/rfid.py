import hashlib
import re

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from idcards.models import IDCard, RFIDCredential


class RFIDCredentialService:
    UID_PATTERN = re.compile(r"^[0-9A-F]{8,64}$")

    @classmethod
    def normalize_uid(cls, uid):
        normalized = re.sub(r"[\s:\-]", "", str(uid or "")).upper()
        if not cls.UID_PATTERN.fullmatch(normalized) or len(normalized) % 2:
            raise ValidationError({"uid": "UID must contain 4–32 hexadecimal bytes."})
        return normalized

    @classmethod
    def hash_uid(cls, normalized_uid):
        return hashlib.sha256(normalized_uid.encode("ascii")).hexdigest()

    @classmethod
    def validate_card(cls, id_card):
        if id_card.effective_status == "EXPIRED":
            raise ValidationError({"code": "CARD_EXPIRED", "id_card": "Expired cards cannot receive an RFID credential."})
        if id_card.status != IDCard.Status.ACTIVE:
            raise ValidationError({"code": "CARD_NOT_ACTIVE", "id_card": "Only active cards can receive an RFID credential."})
        holder = id_card.student or id_card.staff
        if not holder.is_active:
            raise ValidationError({"id_card": "The card holder is inactive."})

    @classmethod
    @transaction.atomic
    def assign(cls, *, id_card, uid):
        id_card = IDCard.objects.select_for_update().get(pk=id_card.pk)
        cls.validate_card(id_card)
        normalized = cls.normalize_uid(uid)
        uid_hash = cls.hash_uid(normalized)
        if RFIDCredential.objects.filter(uid_hash=uid_hash).exists():
            raise ValidationError({"code": "UID_ALREADY_ASSIGNED", "uid": "This RFID UID has already been assigned and cannot be reused."})
        if RFIDCredential.objects.filter(id_card=id_card, status=RFIDCredential.Status.ACTIVE).exists():
            raise ValidationError({"code": "ACTIVE_CREDENTIAL_EXISTS", "id_card": "This ID card already has an active RFID credential."})
        try:
            with transaction.atomic():
                return RFIDCredential.objects.create(
                    id_card=id_card, uid_hash=uid_hash, uid_last_four=normalized[-4:]
                )
        except IntegrityError:
            if RFIDCredential.objects.filter(uid_hash=uid_hash).exists():
                raise ValidationError({"code": "UID_ALREADY_ASSIGNED", "uid": "This RFID UID has already been assigned and cannot be reused."})
            if RFIDCredential.objects.filter(id_card=id_card, status=RFIDCredential.Status.ACTIVE).exists():
                raise ValidationError({"code": "ACTIVE_CREDENTIAL_EXISTS", "id_card": "This ID card already has an active RFID credential."})
            raise

    @classmethod
    def resolve(cls, uid):
        normalized = cls.normalize_uid(uid)
        return normalized, RFIDCredential.objects.select_related(
            "id_card__student", "id_card__staff", "id_card__template"
        ).filter(uid_hash=cls.hash_uid(normalized)).first()

    @classmethod
    def revoke(cls, credential, *, actor=None, reason="", status=RFIDCredential.Status.REVOKED):
        if credential.status != RFIDCredential.Status.ACTIVE:
            raise ValidationError("Only an active RFID credential can be revoked.")
        credential.status = status
        credential.revoked_at = timezone.now()
        credential.revoked_by = actor
        credential.revocation_reason = reason
        credential.save(update_fields=("status", "revoked_at", "revoked_by", "revocation_reason", "updated_at"))
        return credential

    @classmethod
    @transaction.atomic
    def replace(cls, credential, *, new_uid, actor=None, reason="Replacement"):
        cls.revoke(credential, actor=actor, reason=reason, status=RFIDCredential.Status.REPLACED)
        return cls.assign(id_card=credential.id_card, uid=new_uid)
