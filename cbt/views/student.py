import logging
import hashlib
import mimetypes

from rest_framework import viewsets, status, views
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.http import FileResponse
from django.db.models import Max

from academic.models import StudentClassEnrollment
from cbt.models import (
    CBTExam,
    CBTExamStatus,
    ExamAttempt,
    AttemptQuestion,
    AttemptGrantSource,
    OfflineExamPackage,
    PublishedExamMedia,
)
from cbt.serializers import (
    StudentAvailableExamSerializer,
    ExamAttemptSerializer,
    ExamAttemptListSerializer,
    AnswerSaveSerializer,
    FlagQuestionSerializer,
    SubmissionSerializer,
    AttemptQuestionSerializer,
    AttemptGrantStudentSerializer,
    OfflinePackageRequestSerializer,
    OfflineAttemptStartSerializer,
    OfflineSyncSerializer,
    OfflineSubmitSerializer,
)
from cbt.permissions import (
    CanTakeCBTExam,
    CanAccessOwnAttempt,
)
from cbt.services import (
    CBTActorService,
    ExamAttemptService,
    StudentAnswerService,
    AttemptGradingService,
    AttemptGrantService,
    OfflinePackageService,
    OfflinePackageError,
    OfflineSyncService,
    OfflineSyncError,
)
from django.utils import timezone


logger = logging.getLogger(__name__)


def _offline_sync_state(attempt, *, event_results=None):
    questions = attempt.attempt_questions.select_related(
        "published_question", "answer"
    ).prefetch_related(
        "answer__selected_options__published_choice",
        "answer__blank_responses__published_blank",
        "answer__matching_responses__published_left_item",
        "answer__matching_responses__published_right_item",
    ).annotate(last_answer_revision=Max("answer_events__server_revision"))
    answers = []
    for question in questions:
        safe = AttemptQuestionSerializer(question).data
        answers.append({
            "question_id": str(question.published_question.public_id),
            "response": safe["student_response"],
            "last_server_revision": question.last_answer_revision,
        })
    return {
        "protocol_version": OfflineSyncService.PROTOCOL_VERSION,
        "server_time": timezone.now(),
        "attempt": {
            "public_id": str(attempt.public_id),
            "status": attempt.status,
            "revision": attempt.revision,
            "submitted_revision": attempt.submitted_revision,
            "expires_at": attempt.expires_at,
            "start_source": attempt.start_source,
        },
        "events": event_results or [],
        "answers": answers,
    }


def _offline_error_response(exc):
    return Response(
        {"code": exc.sync_code, "detail": "Offline reconciliation was rejected."},
        status=status.HTTP_400_BAD_REQUEST,
    )


class OfflineAttemptStartView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = OfflineAttemptStartSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"code": "INVALID_PAYLOAD", "detail": "Offline start payload is invalid."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        student = CBTActorService.resolve_student(request.user)
        try:
            attempt = OfflineSyncService.bootstrap(
                student=student, **serializer.validated_data
            )
            return Response(_offline_sync_state(attempt), status=status.HTTP_200_OK)
        except OfflineSyncError as exc:
            return _offline_error_response(exc)


class OfflineAttemptSyncView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, attempt_public_id):
        serializer = OfflineSyncSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"code": "INVALID_PAYLOAD", "detail": "Offline sync payload is invalid."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        student = CBTActorService.resolve_student(request.user)
        try:
            result = OfflineSyncService.sync(
                student=student,
                attempt_id=attempt_public_id,
                **serializer.validated_data,
            )
            return Response(
                _offline_sync_state(result.attempt, event_results=result.events),
                status=status.HTTP_200_OK,
            )
        except OfflineSyncError as exc:
            return _offline_error_response(exc)


class OfflineAttemptSubmitView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, attempt_public_id):
        serializer = OfflineSubmitSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"code": "INVALID_PAYLOAD", "detail": "Offline submission payload is invalid."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        student = CBTActorService.resolve_student(request.user)
        values = dict(serializer.validated_data)
        submission_id = values.pop("submission_id")
        client_submitted_at = values.pop("client_submitted_at", None)
        try:
            result, submission = OfflineSyncService.sync_and_submit(
                student=student,
                attempt_id=attempt_public_id,
                submission_id=submission_id,
                client_submitted_at=client_submitted_at,
                **values,
            )
            if submission.finalized_now:
                try:
                    AttemptGradingService.grade_attempt(attempt=submission.attempt)
                except Exception as exc:
                    logger.exception(
                        "CBT offline grading failed for attempt %s",
                        submission.attempt.pk,
                    )
                    AttemptGradingService.record_failure(
                        attempt=submission.attempt, error=exc
                    )
                    return Response(
                        {
                            "code": "GRADING_FAILED",
                            "detail": "The attempt was submitted but grading is pending recovery.",
                            "submission_outcome": submission.outcome,
                        },
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )
            payload = _offline_sync_state(
                submission.attempt, event_results=result.events
            )
            payload["submission_outcome"] = submission.outcome
            return Response(payload, status=status.HTTP_200_OK)
        except OfflineSyncError as exc:
            return _offline_error_response(exc)
        except DjangoValidationError:
            return Response(
                {"code": "ATTEMPT_EXPIRED", "detail": "Offline submission was rejected."},
                status=status.HTTP_400_BAD_REQUEST,
            )


class StudentExamViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Student view for listing and starting eligible published CBT exams.
    """
    serializer_class = StudentAvailableExamSerializer
    permission_classes = [IsAuthenticated, CanTakeCBTExam]

    def get_queryset(self):
        user = self.request.user
        try:
            student = CBTActorService.resolve_student(user)
        except DjangoValidationError:
            return CBTExam.objects.none()

        # Find classrooms where student is actively enrolled
        enrollments = StudentClassEnrollment.objects.filter(
            student=student,
            is_active=True,
        ).select_related("classroom", "academic_year")

        active_classroom_ids = enrollments.values_list("classroom_id", flat=True)
        active_year_ids = enrollments.values_list("academic_year_id", flat=True)

        return CBTExam.objects.filter(
            status=CBTExamStatus.PUBLISHED,
            classroom_id__in=active_classroom_ids,
            session__academic_year_id__in=active_year_ids,
        ).select_related("subject", "classroom__grade_level", "session").prefetch_related("attempts")

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        exam = self.get_object()
        student = CBTActorService.resolve_student(request.user)

        try:
            attempt = ExamAttemptService.start_attempt(
                exam=exam,
                student=student,
            )
            serializer = ExamAttemptSerializer(attempt, context={"request": request})
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except DjangoValidationError as exc:
            msg = getattr(exc, "message_dict", None) or getattr(exc, "messages", str(exc))
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="grant")
    def grant(self, request, pk=None):
        exam = self.get_object()
        student = CBTActorService.resolve_student(request.user)
        now = timezone.now()
        try:
            grant = AttemptGrantService.issue(
                student=student,
                exam=exam,
                now=now,
                source=AttemptGrantSource.OFFLINE_PREPARATION,
            )
            payload = AttemptGrantStudentSerializer(grant).data
            payload["grant_token"] = AttemptGrantService.sign(grant)
            payload["server_time"] = now
            return Response(payload, status=status.HTTP_200_OK)
        except DjangoValidationError as exc:
            msg = getattr(exc, "message_dict", None) or getattr(exc, "messages", str(exc))
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="offline-package")
    def offline_package(self, request, pk=None):
        exam = self.get_object()
        student = CBTActorService.resolve_student(request.user)
        serializer = OfflinePackageRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"code": "INVALID_GRANT", "detail": "Grant token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        now = timezone.now()
        try:
            package = OfflinePackageService.issue(
                student=student,
                exam=exam,
                grant_token=serializer.validated_data["grant_token"],
                now=now,
            )
            payload = OfflinePackageService.response_payload(
                package=package,
                grant_token=serializer.validated_data["grant_token"],
                server_time=now,
            )
            OfflinePackageService.record_download(package, now=now)
            return Response(payload, status=status.HTTP_200_OK)
        except OfflinePackageError as exc:
            return Response(
                {"code": exc.package_code, "detail": exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )


class StudentAttemptViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Student viewset for retrieving active/submitted attempts and submitting.
    """
    serializer_class = ExamAttemptSerializer
    permission_classes = [IsAuthenticated, CanAccessOwnAttempt]

    def get_queryset(self):
        user = self.request.user
        try:
            student = CBTActorService.resolve_student(user)
        except DjangoValidationError:
            return ExamAttempt.objects.none()

        return ExamAttempt.objects.filter(student=student).select_related(
            "cbt_exam__subject",
            "cbt_exam__classroom__grade_level",
            "published_revision",
            "attempt_grant",
        ).prefetch_related(
            "attempt_questions__exam_question__question_version__question",
            "attempt_questions__option_order__question_option",
            "attempt_questions__answer",
            "attempt_questions__published_question",
        )

    def retrieve(self, request, *args, **kwargs):
        attempt = self.get_object()
        # Auto-refresh expired attempt
        attempt = ExamAttemptService.refresh_status(attempt=attempt)
        serializer = self.get_serializer(attempt)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        attempt = self.get_object()
        submission_serializer = SubmissionSerializer(data=request.data)
        submission_serializer.is_valid(raise_exception=True)
        try:
            submission = ExamAttemptService.submit(
                attempt=attempt,
                submission_id=submission_serializer.validated_data.get("submission_id"),
            )
            attempt = submission.attempt

            if attempt.status != "SUBMITTED":
                return Response(
                    {
                        "detail": "This exam attempt has expired and was not submitted.",
                        "submission_outcome": submission.outcome,
                        "attempt": ExamAttemptSerializer(attempt, context={"request": request}).data,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Trigger automatic grading for objective questions
            existing_grade = getattr(attempt, "grade", None)
            should_grade = (
                submission.finalized_now
                or existing_grade is None
                or existing_grade.status == "FAILED"
            )
            if should_grade:
                try:
                    AttemptGradingService.grade_attempt(attempt=attempt)
                except Exception as exc:
                    logger.exception("CBT grading failed for attempt %s", attempt.pk)
                    AttemptGradingService.record_failure(attempt=attempt, error=exc)
                    return Response(
                        {
                            "detail": (
                                "The exam was submitted, but grading could not be completed. "
                                "School staff have been notified."
                            ),
                            "grading_status": "FAILED",
                            "submission_outcome": submission.outcome,
                        },
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

            serializer = ExamAttemptSerializer(attempt, context={"request": request})
            return Response(
                {
                    "detail": "Exam attempt successfully submitted.",
                    "submission_outcome": submission.outcome,
                    "attempt": serializer.data,
                },
                status=status.HTTP_200_OK,
            )
        except DjangoValidationError as exc:
            msg = getattr(exc, "message_dict", None) or getattr(exc, "messages", str(exc))
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)


class AttemptQuestionViewSet(viewsets.GenericViewSet):
    """
    Endpoints for student answering, clearing, and flagging attempt questions.
    """
    queryset = AttemptQuestion.objects.all().select_related(
        "attempt__student",
        "exam_question__question_version__question",
        "published_question",
    )
    permission_classes = [IsAuthenticated, CanAccessOwnAttempt]
    serializer_class = AttemptQuestionSerializer

    @action(detail=True, methods=["put", "patch", "delete"], url_path="answer")
    def answer(self, request, pk=None):
        attempt_question = self.get_object()
        student = CBTActorService.resolve_student(request.user)

        if request.method == "DELETE":
            serializer = AnswerSaveSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            result = serializer.clear_answer(attempt_question, student=student)
            output_serializer = AttemptQuestionSerializer(
                attempt_question, context={"request": request}
            )
            return Response(
                {
                    "detail": "Answer cleared successfully.",
                    "sync": {
                        "event_id": str(result.event.event_id),
                        "outcome": result.outcome,
                        "attempt_revision": result.event.server_revision,
                        "client_sequence": result.event.client_sequence,
                    },
                    "question": output_serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        serializer = AnswerSaveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = serializer.save_answer(attempt_question, student=student)
            output_serializer = AttemptQuestionSerializer(
                attempt_question, context={"request": request}
            )
            return Response(
                {
                    "detail": "Answer saved successfully.",
                    "sync": {
                        "event_id": str(result.event.event_id),
                        "outcome": result.outcome,
                        "attempt_revision": result.event.server_revision,
                        "client_sequence": result.event.client_sequence,
                    },
                    "question": output_serializer.data,
                },
                status=status.HTTP_200_OK,
            )
        except DjangoValidationError as exc:
            msg = getattr(exc, "message_dict", None) or getattr(exc, "messages", str(exc))
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["patch"], url_path="flag")
    def flag(self, request, pk=None):
        attempt_question = self.get_object()
        serializer = FlagQuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        serializer.save_flag(attempt_question)
        output_serializer = AttemptQuestionSerializer(
            attempt_question, context={"request": request}
        )
        return Response(
            {
                "detail": f"Question {'flagged' if attempt_question.is_flagged else 'unflagged'} successfully.",
                "question": output_serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class OfflineMediaDownloadView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, media_public_id):
        student = CBTActorService.resolve_student(request.user)
        token = request.headers.get("X-CBT-Grant-Token", "")
        if not token:
            return Response(
                {"code": "INVALID_GRANT", "detail": "Grant token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        now = timezone.now()
        try:
            verified = AttemptGrantService.verify_token(
                token,
                now=now,
                expected_student=student,
                allow_before_valid_from=True,
            )
        except DjangoValidationError as exc:
            message = " ".join(getattr(exc, "messages", [])).casefold()
            code = "GRANT_REVOKED" if "revoked" in message else "INVALID_GRANT"
            return Response(
                {"code": code, "detail": "Grant authorization is invalid."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        grant = verified.grant
        package_exists = OfflineExamPackage.objects.filter(
            attempt_grant=grant,
            student=student,
            published_revision=grant.published_revision,
        ).exists()
        if not package_exists:
            return Response(
                {"code": "PACKAGE_NOT_AVAILABLE", "detail": "Offline package is unavailable."},
                status=status.HTTP_404_NOT_FOUND,
            )
        media = get_object_or_404(
            PublishedExamMedia.objects.select_related(
                "published_question__revision", "source_attachment"
            ),
            public_id=media_public_id,
            published_question__revision=grant.published_revision,
        )
        file_obj = media.source_attachment.file
        digest = hashlib.sha256()
        size = 0
        try:
            file_obj.open("rb")
            for chunk in file_obj.chunks():
                digest.update(chunk)
                size += len(chunk)
            if digest.hexdigest() != media.content_sha256 or size != media.size_bytes:
                file_obj.close()
                return Response(
                    {"code": "MEDIA_INTEGRITY_ERROR", "detail": "Media integrity verification failed."},
                    status=status.HTTP_409_CONFLICT,
                )
            file_obj.seek(0)
        except Exception:
            try:
                file_obj.close()
            except Exception:
                pass
            return Response(
                {"code": "MEDIA_INTEGRITY_ERROR", "detail": "Media is unavailable."},
                status=status.HTTP_409_CONFLICT,
            )
        content_type = mimetypes.guess_type(media.filename)[0] or "application/octet-stream"
        return FileResponse(
            file_obj,
            content_type=content_type,
            as_attachment=False,
            filename=media.filename,
        )
