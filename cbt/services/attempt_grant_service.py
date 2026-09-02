from dataclasses import dataclass
from datetime import datetime, timedelta

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from cbt.models import (
    AttemptGrant,
    AttemptGrantSource,
    AttemptGrantStatus,
    CBTExam,
    PublishedExamRevision,
)
from .cbt_actor_service import CBTActorService
from .exam_access_service import CBTExamAccessService, ExamAccessState


@dataclass(frozen=True)
class VerifiedAttemptGrant:
    grant: AttemptGrant
    claims: dict
    verified_at: object


class AttemptGrantService:
    TOKEN_VERSION = 1
    TOKEN_SALT = "ssync.cbt.attempt-grant.v1"

    @staticmethod
    def _student_binding(student_id):
        return salted_hmac(
            "ssync.cbt.attempt-grant.student", str(student_id)
        ).hexdigest()

    @staticmethod
    @transaction.atomic
    def issue(*, student, exam, revision=None, now=None,
              source=AttemptGrantSource.ONLINE_START, issued_by=None,
              valid_from=None, valid_until=None, exam_locked=False):
        if not exam_locked:
            exam = CBTExam.objects.select_for_update().get(pk=exam.pk)
        now = now or timezone.now()
        revision = revision or PublishedExamRevision.objects.filter(
            exam=exam, status=PublishedExamRevision.Status.FINALIZED
        ).order_by("-revision_number").first()
        decision = CBTExamAccessService.evaluate(
            student=student, exam=exam, now=now, revision=revision
        )
        if decision.state == ExamAccessState.ACTIVE_ATTEMPT:
            existing = getattr(decision.attempt, "attempt_grant", None)
            if existing is not None:
                return existing
        allowed_states = {ExamAccessState.AVAILABLE}
        if source == AttemptGrantSource.OFFLINE_PREPARATION:
            allowed_states.add(ExamAccessState.NOT_YET_OPEN)
        if decision.state not in allowed_states:
            raise ValidationError(decision.message)
        revision = decision.published_revision

        existing = AttemptGrant.objects.select_for_update().filter(
            student=student,
            exam=exam,
            published_revision=revision,
        ).order_by("pk").first()
        if existing is not None:
            if existing.status == AttemptGrantStatus.REVOKED:
                raise ValidationError("The attempt authorization has been revoked.")
            if now < existing.valid_until:
                if (
                    source == AttemptGrantSource.ONLINE_START
                    and now < existing.valid_from
                ):
                    raise ValidationError("The attempt authorization is not valid yet.")
                return existing
            raise ValidationError("The existing attempt authorization is no longer valid.")

        grant_from = valid_from or (
            exam.available_from
            if exam.available_from is not None and now < exam.available_from
            else now
        )
        grant_until = valid_until or exam.available_until or (
            grant_from + timedelta(minutes=revision.duration_minutes)
        )
        if exam.available_from is not None and grant_from < exam.available_from:
            raise ValidationError("Grant validity cannot begin before exam availability.")
        if exam.available_until is not None and grant_until > exam.available_until:
            raise ValidationError("Grant validity cannot extend beyond the start window.")
        if grant_until <= grant_from:
            raise ValidationError("The exam authorization window has closed.")
        try:
            with transaction.atomic():
                return AttemptGrant.objects.create(
                    student=student,
                    exam=exam,
                    published_revision=revision,
                    valid_from=grant_from,
                    valid_until=grant_until,
                    issuance_source=source,
                    issued_by=issued_by,
                )
        except IntegrityError:
            return AttemptGrant.objects.select_for_update().get(
                student=student,
                exam=exam,
                published_revision=revision,
                status=AttemptGrantStatus.ACTIVE,
            )

    @staticmethod
    def claims_for(grant):
        return {
            "v": AttemptGrantService.TOKEN_VERSION,
            "grant_id": str(grant.public_id),
            "student_binding": AttemptGrantService._student_binding(grant.student_id),
            "revision_id": str(grant.published_revision.public_id),
            "revision_hash": grant.published_revision.content_hash,
            "valid_from": grant.valid_from.isoformat(),
            "valid_until": grant.valid_until.isoformat(),
            "issued_at": grant.issued_at.isoformat(),
            "nonce": str(grant.nonce),
        }

    @staticmethod
    def sign(grant):
        return signing.dumps(
            AttemptGrantService.claims_for(grant),
            salt=AttemptGrantService.TOKEN_SALT,
            compress=True,
        )

    @staticmethod
    def verify_token(
        token, *, now=None, expected_student=None, allow_before_valid_from=False,
        allow_after_valid_until=False,
    ):
        now = now or timezone.now()
        try:
            claims = signing.loads(token, salt=AttemptGrantService.TOKEN_SALT)
        except signing.BadSignature as exc:
            raise ValidationError("Attempt grant token is invalid.") from exc
        if claims.get("v") != AttemptGrantService.TOKEN_VERSION:
            raise ValidationError("Attempt grant token version is unsupported.")
        try:
            grant = AttemptGrant.objects.select_related(
                "student", "exam", "published_revision"
            ).get(public_id=claims.get("grant_id"))
        except AttemptGrant.DoesNotExist as exc:
            raise ValidationError("Attempt grant does not exist.") from exc
        expected_claims = AttemptGrantService.claims_for(grant)
        if claims != expected_claims:
            raise ValidationError("Attempt grant claims no longer match authorization records.")
        if expected_student is not None and grant.student_id != expected_student.pk:
            raise ValidationError("Attempt grant does not belong to this student.")
        if grant.status == AttemptGrantStatus.REVOKED:
            raise ValidationError("Attempt grant has been revoked.")
        if grant.published_revision.status != PublishedExamRevision.Status.FINALIZED:
            raise ValidationError("Attempt grant revision is not finalized.")
        valid_from = datetime.fromisoformat(claims["valid_from"])
        valid_until = datetime.fromisoformat(claims["valid_until"])
        if (
            (now < valid_from and not allow_before_valid_from)
            or (now >= valid_until and not allow_after_valid_until)
        ):
            raise ValidationError("Attempt grant is outside its validity period.")
        return VerifiedAttemptGrant(grant=grant, claims=claims, verified_at=now)

    @staticmethod
    @transaction.atomic
    def revoke(*, grant, actor, reason=""):
        grant = AttemptGrant.objects.select_for_update().get(pk=grant.pk)
        if grant.status == AttemptGrantStatus.REVOKED:
            return grant
        grant.status = AttemptGrantStatus.REVOKED
        grant.revoked_at = timezone.now()
        grant.revoked_by = CBTActorService.resolve_teacher(actor)
        grant.revocation_reason = reason
        grant.save(update_fields=[
            "status", "revoked_at", "revoked_by", "revocation_reason", "updated_at"
        ])
        return grant
