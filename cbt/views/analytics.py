from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied

from academic.models import AllocatedSubject
from academic.services.academic_authority_service import AcademicAuthorityService
from cbt.models import (
    CBTExam,
    CBTExamStatus,
)
from cbt.permissions import CanManageCBTExam
from cbt.services import CBTActorService, CBTAnalyticsService
from cbt.serializers.invigilation import InvigilationExamListSerializer


class CBTAnalyticsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only ViewSet for Post-Examination CBT Performance Analytics.
    """
    queryset = CBTExam.objects.filter(
        status__in=[CBTExamStatus.READY, CBTExamStatus.PUBLISHED, CBTExamStatus.CLOSED]
    ).select_related(
        "session",
        "subject",
        "classroom",
        "classroom__grade_level",
    ).prefetch_related(
        "exam_questions__question_version__question",
        "attempts__grade",
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

    def retrieve(self, request, *args, **kwargs):
        exam = self.get_object()

        summary = CBTAnalyticsService.get_exam_summary(exam)
        score_dist = CBTAnalyticsService.get_score_distribution(exam)
        questions_perf = CBTAnalyticsService.get_question_performance(exam)
        aggregations = CBTAnalyticsService.get_type_and_difficulty_performance(exam)
        candidates_perf = CBTAnalyticsService.get_candidate_performance(exam)

        return Response({
            "exam": {
                "id": exam.id,
                "title": exam.title,
                "subject_name": exam.subject.name if exam.subject else "",
                "classroom_name": exam.classroom.name if exam.classroom else "",
                "session_name": exam.session.name if exam.session else "",
                "status": exam.status,
                "duration_minutes": exam.duration_minutes,
            },
            "summary": summary,
            "score_distribution": score_dist,
            "questions": questions_perf,
            "aggregations": aggregations,
            "candidates": candidates_perf,
        })
