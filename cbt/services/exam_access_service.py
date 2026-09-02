from dataclasses import dataclass
from enum import StrEnum

from django.utils import timezone

from academic.models import StudentClassEnrollment

from cbt.models import (
    AttemptGrant, AttemptGrantStatus, CBTExamStatus, ExamAttemptStatus,
    PublishedExamRevision,
)


class ExamAccessState(StrEnum):
    AVAILABLE = "AVAILABLE"
    NOT_YET_OPEN = "NOT_YET_OPEN"
    CLOSED = "CLOSED"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    ACTIVE_ATTEMPT = "ACTIVE_ATTEMPT"
    ALREADY_SUBMITTED = "ALREADY_SUBMITTED"
    EXPIRED_ATTEMPT = "EXPIRED_ATTEMPT"
    NO_PUBLISHED_REVISION = "NO_PUBLISHED_REVISION"
    UNPUBLISHED = "UNPUBLISHED"
    GRANT_REVOKED = "GRANT_REVOKED"


@dataclass(frozen=True)
class ExamAccessDecision:
    state: ExamAccessState
    message: str
    server_time: object
    enrollment: object = None
    published_revision: object = None
    attempt: object = None
    can_start: bool = False
    can_resume: bool = False


class CBTExamAccessService:
    """Authoritative, student-safe start/resume eligibility resolver.

    Availability uses a half-open interval: available_from is inclusive and
    available_until is exclusive. Resume is governed by attempt expiry, not by
    whether the window still permits a new start.
    """

    MESSAGES = {
        ExamAccessState.AVAILABLE: "This exam is available.",
        ExamAccessState.NOT_YET_OPEN: "This exam is not open yet.",
        ExamAccessState.CLOSED: "This exam is closed for new attempts.",
        ExamAccessState.NOT_ELIGIBLE: "You are not eligible for this exam.",
        ExamAccessState.ACTIVE_ATTEMPT: "You may resume your active attempt.",
        ExamAccessState.ALREADY_SUBMITTED: "This exam has already been submitted.",
        ExamAccessState.EXPIRED_ATTEMPT: "Your attempt has expired.",
        ExamAccessState.NO_PUBLISHED_REVISION: "This exam is not ready for delivery.",
        ExamAccessState.UNPUBLISHED: "This exam is not available.",
        ExamAccessState.GRANT_REVOKED: "Your attempt authorization has been revoked.",
    }

    @staticmethod
    def evaluate(*, student, exam, now=None, attempt=None, revision=None):
        now = now or timezone.now()
        if attempt is None:
            attempt = exam.attempts.filter(student=student).order_by("-started_at").first()

        if attempt is not None:
            if attempt.status == ExamAttemptStatus.IN_PROGRESS:
                grant_status = None
                if attempt.attempt_grant_id:
                    grant_status = AttemptGrant.objects.filter(
                        pk=attempt.attempt_grant_id
                    ).values_list("status", flat=True).first()
                if grant_status == AttemptGrantStatus.REVOKED:
                    return CBTExamAccessService._decision(
                        ExamAccessState.GRANT_REVOKED, now, attempt=attempt,
                        revision=attempt.published_revision,
                    )
                if now < attempt.expires_at:
                    return CBTExamAccessService._decision(
                        ExamAccessState.ACTIVE_ATTEMPT, now, attempt=attempt,
                        revision=attempt.published_revision, can_resume=True,
                    )
                return CBTExamAccessService._decision(
                    ExamAccessState.EXPIRED_ATTEMPT, now, attempt=attempt,
                    revision=attempt.published_revision,
                )
            if attempt.status == ExamAttemptStatus.SUBMITTED:
                return CBTExamAccessService._decision(
                    ExamAccessState.ALREADY_SUBMITTED, now, attempt=attempt,
                    revision=attempt.published_revision,
                )
            return CBTExamAccessService._decision(
                ExamAccessState.EXPIRED_ATTEMPT, now, attempt=attempt,
                revision=attempt.published_revision,
            )

        if exam.status != CBTExamStatus.PUBLISHED:
            return CBTExamAccessService._decision(ExamAccessState.UNPUBLISHED, now)

        enrollment = StudentClassEnrollment.objects.filter(
            student=student,
            academic_year=exam.session.academic_year,
            classroom=exam.classroom,
            is_active=True,
        ).first()
        if enrollment is None:
            return CBTExamAccessService._decision(ExamAccessState.NOT_ELIGIBLE, now)

        if revision is None:
            revision = PublishedExamRevision.objects.filter(
                exam=exam,
                status=PublishedExamRevision.Status.FINALIZED,
            ).order_by("-revision_number").first()
        if revision is None:
            return CBTExamAccessService._decision(
                ExamAccessState.NO_PUBLISHED_REVISION, now, enrollment=enrollment
            )

        if exam.available_from is not None and now < exam.available_from:
            return CBTExamAccessService._decision(
                ExamAccessState.NOT_YET_OPEN, now, enrollment=enrollment, revision=revision
            )
        if exam.available_until is not None and now >= exam.available_until:
            return CBTExamAccessService._decision(
                ExamAccessState.CLOSED, now, enrollment=enrollment, revision=revision
            )
        return CBTExamAccessService._decision(
            ExamAccessState.AVAILABLE,
            now,
            enrollment=enrollment,
            revision=revision,
            can_start=True,
        )

    @staticmethod
    def _decision(state, now, *, enrollment=None, revision=None, attempt=None,
                  can_start=False, can_resume=False):
        return ExamAccessDecision(
            state=state,
            message=CBTExamAccessService.MESSAGES[state],
            server_time=now,
            enrollment=enrollment,
            published_revision=revision,
            attempt=attempt,
            can_start=can_start,
            can_resume=can_resume,
        )
