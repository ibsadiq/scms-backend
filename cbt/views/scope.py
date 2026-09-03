from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from cbt.services.cbt_academic_scope_service import CBTAcademicScopeService


class CBTAuthoringScopeView(APIView):
    """
    GET /api/cbt/authoring-scope/
    Returns the server-authoritative subject and classroom scope for CBT authoring.
    For teachers, subjects reflect teaching allocations and classrooms are mapped per subject.
    For admins, all school subjects and classrooms are returned.
    Students and parents are forbidden.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        # Block non-staff (e.g., student / parent roles without staff/teacher/admin profiles)
        is_admin = CBTAcademicScopeService.is_admin_scope(user)
        is_teacher = getattr(user, "is_teacher", False) or hasattr(user, "teacher")

        if not is_admin and not is_teacher:
            return Response(
                {"detail": "You do not have permission to access CBT authoring scopes."},
                status=status.HTTP_403_FORBIDDEN,
            )

        session_id = request.query_params.get("session")
        session = None
        if session_id:
            from examination.models import AssessmentSession
            session = AssessmentSession.objects.filter(pk=session_id).first()

        payload = CBTAcademicScopeService.get_authoring_scope_payload(user, session=session)
        return Response(payload, status=status.HTTP_200_OK)
