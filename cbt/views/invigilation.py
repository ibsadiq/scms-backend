from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotFound, PermissionDenied
from django.shortcuts import get_object_or_404

from academic.models import AllocatedSubject
from academic.services.academic_authority_service import AcademicAuthorityService
from cbt.models import (
    CBTExam,
    CBTExamStatus,
    ExamAttempt,
)
from cbt.serializers import (
    InvigilationExamListSerializer,
    MonitoredAttemptListSerializer,
    MonitoredAttemptDetailSerializer,
)
from cbt.permissions import CanManageCBTExam
from cbt.services.cbt_actor_service import CBTActorService


class CBTInvigilationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only ViewSet for Staff/Invigilator Live Attempt Monitoring.
    """
    queryset = CBTExam.objects.filter(
        status__in=[CBTExamStatus.READY, CBTExamStatus.PUBLISHED, CBTExamStatus.CLOSED]
    ).select_related(
        "session",
        "subject",
        "classroom",
        "classroom__grade_level",
    ).prefetch_related(
        "attempts__student",
        "attempts__attempt_questions__answer",
    )
    serializer_class = InvigilationExamListSerializer
    permission_classes = [IsAuthenticated, CanManageCBTExam]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        if not AcademicAuthorityService.is_school_admin(user):
            try:
                teacher = CBTActorService.resolve_teacher(user)
            except Exception:
                return CBTExam.objects.none()

            allocated_pairs = set(
                AllocatedSubject.objects.filter(
                    teacher_name=teacher
                ).values_list("subject_id", "class_room_id")
            )

            created_ids = list(qs.filter(created_by=teacher).values_list("id", flat=True))

            authorized_ids = []
            for exam in qs:
                if exam.id in created_ids:
                    authorized_ids.append(exam.id)
                elif (exam.subject_id, exam.classroom_id) in allocated_pairs:
                    authorized_ids.append(exam.id)
                else:
                    section = (
                        exam.classroom.grade_level.section
                        if (exam.classroom and hasattr(exam.classroom, "grade_level") and exam.classroom.grade_level)
                        else None
                    )
                    academic_year = exam.session.academic_year if exam.session else None
                    if AcademicAuthorityService.can_approve(
                        actor=user,
                        workflow="CBT_PUBLISH",
                        subject=exam.subject,
                        section=section,
                        academic_year=academic_year,
                        creator=exam.created_by,
                    ):
                        authorized_ids.append(exam.id)

            return qs.filter(id__in=authorized_ids)

        return qs

    @action(detail=True, methods=["get"], url_path="attempts")
    def attempts(self, request, pk=None):
        """
        List all candidate attempts for a specific CBT exam.
        """
        exam = self.get_object()
        attempts_qs = (
            ExamAttempt.objects.filter(cbt_exam=exam)
            .select_related("student", "grade")
            .prefetch_related("attempt_questions__answer")
            .order_by("student__first_name", "student__last_name")
        )
        serializer = MonitoredAttemptListSerializer(attempts_qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path=r"attempts/(?P<attempt_public_id>[0-9a-f-]+)")
    def attempt_detail(self, request, attempt_public_id=None):
        """
        Get deep telemetry for a single candidate attempt.
        """
        attempt = get_object_or_404(
            ExamAttempt.objects.select_related(
                "cbt_exam__subject",
                "cbt_exam__classroom",
                "student",
                "grade",
            ).prefetch_related(
                "attempt_questions__answer",
                "answer_events",
            ),
            public_id=attempt_public_id,
        )

        # Validate staff has access to this exam
        exam = attempt.cbt_exam
        accessible_exam_ids = set(self.get_queryset().values_list("id", flat=True))
        if exam.id not in accessible_exam_ids:
            raise PermissionDenied("You are not authorized to monitor this attempt.")

        serializer = MonitoredAttemptDetailSerializer(attempt)
        return Response(serializer.data)
