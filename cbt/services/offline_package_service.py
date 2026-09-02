import hashlib
import json
import mimetypes

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from cbt.models import (
    AttemptGrantSource,
    AttemptGrantStatus,
    OfflineExamPackage,
    PublishedExamMatchingItem,
    PublishedExamRevision,
    QuestionType,
)
from .attempt_grant_service import AttemptGrantService


class OfflinePackageError(ValidationError):
    def __init__(self, message, *, code):
        self.package_code = code
        super().__init__(message, code=code)


class OfflinePackageService:
    SCHEMA_VERSION = 1
    SIGNATURE_VERSION = 1
    SIGNATURE_SALT = "ssync.cbt.offline-package.v1"

    ANSWER_PROTOCOL = {
        "version": 1,
        "operations": ["SET", "CLEAR"],
        "event_fields": [
            "event_id", "client_id", "client_sequence", "base_revision",
            "question_id", "operation", "payload", "client_timestamp",
        ],
        "payloads": {
            QuestionType.SINGLE_CHOICE: {"option_ids": "choice_public_id[]"},
            QuestionType.MULTIPLE_CHOICE: {"option_ids": "choice_public_id[]"},
            QuestionType.TRUE_FALSE: {"option_ids": "choice_public_id[]"},
            QuestionType.SHORT_ANSWER: {"text": "string"},
            QuestionType.NUMERIC: {"value": "decimal_string"},
            QuestionType.FILL_BLANK: {"responses": "{blank_public_id: string}"},
            QuestionType.MATCHING: {"matches": "{left_public_id: right_public_id}"},
            QuestionType.ESSAY: {"text": "string"},
        },
    }

    @staticmethod
    def _stable_order(items, *, seed, namespace):
        return sorted(
            items,
            key=lambda item: hashlib.sha256(
                f"{seed}:{namespace}:{item.public_id}".encode("utf-8")
            ).digest(),
        )

    @staticmethod
    def _matching_right_order(question, *, seed):
        items = list(question.matching_items.all())
        left = sorted(
            [item for item in items if item.side == PublishedExamMatchingItem.Side.LEFT],
            key=lambda item: item.order,
        )
        right = OfflinePackageService._stable_order(
            [item for item in items if item.side == PublishedExamMatchingItem.Side.RIGHT],
            seed=seed,
            namespace=f"matching-right:{question.public_id}",
        )
        if len(right) > 1:
            for offset in range(len(right)):
                candidate = right[offset:] + right[:offset]
                if all(
                    left[index].source_pair_id != candidate[index].source_pair_id
                    for index in range(len(left))
                ):
                    right = candidate
                    break
        return left, right

    @staticmethod
    def _question_payload(question, *, seed, shuffle_options):
        payload = {
            "public_id": str(question.public_id),
            "question_type": question.question_type,
            "question_text": question.question_text,
            "instructions": question.instructions,
            "marks": str(question.marks),
        }
        if question.question_type in {
            QuestionType.SINGLE_CHOICE,
            QuestionType.MULTIPLE_CHOICE,
            QuestionType.TRUE_FALSE,
        }:
            choices = sorted(question.choices.all(), key=lambda item: item.order)
            if shuffle_options:
                choices = OfflinePackageService._stable_order(
                    choices, seed=seed, namespace=f"choices:{question.public_id}"
                )
            payload["choices"] = [
                {"public_id": str(choice.public_id), "text": choice.text}
                for choice in choices
            ]
        elif question.question_type == QuestionType.FILL_BLANK:
            payload["blanks"] = [
                {"public_id": str(blank.public_id), "position": blank.position}
                for blank in sorted(question.blanks.all(), key=lambda item: item.position)
            ]
        elif question.question_type == QuestionType.MATCHING:
            left, right = OfflinePackageService._matching_right_order(
                question, seed=seed
            )
            payload["matching"] = {
                "left": [
                    {"public_id": str(item.public_id), "text": item.text}
                    for item in left
                ],
                "right": [
                    {"public_id": str(item.public_id), "text": item.text}
                    for item in right
                ],
            }
        elif question.question_type == QuestionType.ESSAY:
            payload["interaction"] = {
                "minimum_words": question.interaction_config.get("minimum_words"),
                "maximum_words": question.interaction_config.get("maximum_words"),
            }
        return payload

    @staticmethod
    def _build_content(package):
        revision = package.published_revision
        seed = str(package.presentation_seed)
        questions = sorted(revision.questions.all(), key=lambda item: item.order)
        if revision.shuffle_questions:
            questions = OfflinePackageService._stable_order(
                questions, seed=seed, namespace="questions"
            )
        question_payloads = [
            OfflinePackageService._question_payload(
                question, seed=seed, shuffle_options=revision.shuffle_options
            )
            for question in questions
        ]
        media = []
        for question in questions:
            for item in sorted(question.media.all(), key=lambda value: value.order):
                media.append({
                    "public_id": str(item.public_id),
                    "question_id": str(question.public_id),
                    "filename": item.filename,
                    "caption": item.caption,
                    "order": item.order,
                    "content_type": mimetypes.guess_type(item.filename)[0]
                    or "application/octet-stream",
                    "byte_size": item.size_bytes,
                    "sha256": item.content_sha256,
                    "download_path": f"/api/cbt/student/offline-media/{item.public_id}/",
                })
        grant = package.attempt_grant
        return {
            "schema_version": package.schema_version,
            "package_id": str(package.public_id),
            "presentation_seed": seed,
            "exam": {
                "title": revision.title,
                "instructions": revision.instructions,
                "duration_minutes": revision.duration_minutes,
                "randomization": {
                    "shuffle_questions": revision.shuffle_questions,
                    "shuffle_options": revision.shuffle_options,
                },
                "navigation": {
                    "allow_back_navigation": revision.allow_back_navigation,
                    "auto_submit": revision.auto_submit,
                },
            },
            "revision": {
                "public_id": str(revision.public_id),
                "revision_number": revision.revision_number,
                "schema_version": revision.schema_version,
                "content_hash": revision.content_hash,
            },
            "grant": {
                "public_id": str(grant.public_id),
                "valid_from": grant.valid_from.isoformat(),
                "valid_until": grant.valid_until.isoformat(),
                "issuance_source": grant.issuance_source,
            },
            "questions": question_payloads,
            "media": media,
            "execution": {
                "attempt_expiry_policy": package.exam.attempt_expiry_policy,
                "exam_available_until": (
                    package.exam.available_until.isoformat()
                    if package.exam.available_until else None
                ),
                "offline_start_reconciliation_required": True,
                "client_clock_is_not_authoritative": True,
            },
            "answer_protocol": OfflinePackageService.ANSWER_PROTOCOL,
        }

    @staticmethod
    def _hash(content):
        encoded = json.dumps(
            content, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _signature_claims(package):
        return {
            "v": OfflinePackageService.SIGNATURE_VERSION,
            "package_id": str(package.public_id),
            "package_hash": package.package_hash,
            "revision_id": str(package.published_revision.public_id),
            "revision_hash": package.published_revision.content_hash,
            "grant_id": str(package.attempt_grant.public_id),
        }

    @staticmethod
    def _sign(package):
        return signing.dumps(
            OfflinePackageService._signature_claims(package),
            salt=OfflinePackageService.SIGNATURE_SALT,
            compress=True,
        )

    @staticmethod
    @transaction.atomic
    def issue(*, student, exam, grant_token, now=None):
        now = now or timezone.now()
        try:
            verified = AttemptGrantService.verify_token(
                grant_token,
                now=now,
                expected_student=student,
                allow_before_valid_from=True,
            )
        except ValidationError as exc:
            message = " ".join(getattr(exc, "messages", [])).casefold()
            if "revoked" in message:
                code = "GRANT_REVOKED"
            elif "validity" in message or "expired" in message:
                code = "GRANT_EXPIRED"
            else:
                code = "INVALID_GRANT"
            raise OfflinePackageError("Grant authorization is invalid.", code=code) from exc
        grant = verified.grant
        if grant.exam_id != exam.pk:
            raise OfflinePackageError("Grant does not authorize this exam.", code="REVISION_MISMATCH")
        if now < grant.valid_from and grant.issuance_source != AttemptGrantSource.OFFLINE_PREPARATION:
            raise OfflinePackageError("Package is not available yet.", code="PACKAGE_NOT_AVAILABLE")
        grant = grant.__class__.objects.select_for_update().select_related(
            "published_revision", "exam"
        ).get(pk=grant.pk)
        if grant.status == AttemptGrantStatus.REVOKED:
            raise OfflinePackageError("Grant has been revoked.", code="GRANT_REVOKED")
        existing = OfflineExamPackage.objects.filter(attempt_grant=grant).first()
        if existing is not None:
            OfflinePackageService.verify(package=existing, student=student)
            return existing
        if grant.published_revision.status != PublishedExamRevision.Status.FINALIZED:
            raise OfflinePackageError("Published revision is unavailable.", code="REVISION_MISMATCH")
        try:
            with transaction.atomic():
                package = OfflineExamPackage.objects.create(
                    student=student,
                    exam=exam,
                    published_revision=grant.published_revision,
                    attempt_grant=grant,
                    schema_version=OfflinePackageService.SCHEMA_VERSION,
                )
        except IntegrityError:
            package = OfflineExamPackage.objects.get(attempt_grant=grant)
            OfflinePackageService.verify(package=package, student=student)
            return package
        package = OfflineExamPackage.objects.select_related(
            "exam", "published_revision", "attempt_grant"
        ).prefetch_related(
            "published_revision__questions__choices",
            "published_revision__questions__blanks",
            "published_revision__questions__matching_items",
            "published_revision__questions__media",
        ).get(pk=package.pk)
        content = OfflinePackageService._build_content(package)
        package_hash = OfflinePackageService._hash(content)
        OfflineExamPackage.objects.filter(pk=package.pk).update(
            content=content,
            package_hash=package_hash,
        )
        package.refresh_from_db()
        signature = OfflinePackageService._sign(package)
        OfflineExamPackage.objects.filter(pk=package.pk).update(
            package_signature=signature
        )
        package.refresh_from_db()
        return package

    @staticmethod
    def verify(*, package, student=None, content=None, signature=None):
        if package.schema_version != OfflinePackageService.SCHEMA_VERSION:
            raise OfflinePackageError("Unsupported package version.", code="UNSUPPORTED_PACKAGE_VERSION")
        if student is not None and package.student_id != student.pk:
            raise OfflinePackageError("Package does not belong to this student.", code="PACKAGE_NOT_AVAILABLE")
        if package.published_revision.content_hash != package.content["revision"]["content_hash"]:
            raise OfflinePackageError("Revision integrity check failed.", code="PACKAGE_INTEGRITY_ERROR")
        checked_content = content if content is not None else package.content
        if OfflinePackageService._hash(checked_content) != package.package_hash:
            raise OfflinePackageError("Package integrity check failed.", code="PACKAGE_INTEGRITY_ERROR")
        checked_signature = signature if signature is not None else package.package_signature
        try:
            claims = signing.loads(
                checked_signature, salt=OfflinePackageService.SIGNATURE_SALT
            )
        except signing.BadSignature as exc:
            raise OfflinePackageError("Package signature is invalid.", code="PACKAGE_INTEGRITY_ERROR") from exc
        if claims.get("v") != OfflinePackageService.SIGNATURE_VERSION:
            raise OfflinePackageError("Unsupported package signature version.", code="UNSUPPORTED_PACKAGE_VERSION")
        if claims != OfflinePackageService._signature_claims(package):
            raise OfflinePackageError("Package signature claims do not match.", code="PACKAGE_INTEGRITY_ERROR")
        if package.attempt_grant.__class__.objects.filter(
            pk=package.attempt_grant_id,
            status=AttemptGrantStatus.REVOKED,
        ).exists():
            raise OfflinePackageError("Grant has been revoked.", code="GRANT_REVOKED")
        return package

    @staticmethod
    def response_payload(*, package, grant_token, server_time=None):
        OfflinePackageService.verify(package=package, student=package.student)
        return {
            **package.content,
            "package_hash": package.package_hash,
            "package_signature": package.package_signature,
            "generated_at": package.generated_at,
            "server_time": server_time or timezone.now(),
            "grant": {**package.content["grant"], "token": grant_token},
        }

    @staticmethod
    def record_download(package, *, now=None):
        now = now or timezone.now()
        OfflineExamPackage.objects.filter(pk=package.pk).update(
            first_downloaded_at=F("first_downloaded_at") if package.first_downloaded_at else now,
            last_downloaded_at=now,
            download_count=F("download_count") + 1,
        )
