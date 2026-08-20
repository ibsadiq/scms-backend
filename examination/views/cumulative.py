from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from ..models import CumulativeResult, AcademicTranscript, ResultAmendmentRequest
from ..serializers.result import (
    CumulativeResultSerializer, AcademicTranscriptSerializer, ResultAmendmentRequestSerializer
)
from ..services.cumulative_result_service import CumulativeResultService
from ..services.transcript_service import TranscriptService
from ..services.amendment_service import AmendmentService
from ..permissions import IsAdmin, CanComputeResults
from academic.models import Student
from administration.models import AcademicYear

class CumulativeResultViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CumulativeResultSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = CumulativeResult.objects.select_related("student", "academic_year", "grading_scheme").prefetch_related("subjects__subject")
        user = self.request.user
        
        # Access control
        if not (getattr(user, "is_admin", False) or getattr(user, "is_superuser", False) or getattr(user, "is_staff", False)):
            if getattr(user, "is_parent", False):
                parent = getattr(user, "parent", None)
                if parent:
                    qs = qs.filter(student__parent_guardian=parent, lifecycle_state="PUBLISHED")
            elif getattr(user, "is_student", False):
                student = getattr(user, "student_profile", None) or getattr(user, "student", None)
                if student:
                    qs = qs.filter(student=student, lifecycle_state="PUBLISHED")
        
        p = self.request.query_params
        if p.get("student_id"):
            qs = qs.filter(student_id=p["student_id"])
        if p.get("academic_year_id"):
            qs = qs.filter(academic_year_id=p["academic_year_id"])
            
        return qs

    @action(detail=False, methods=["post"], permission_classes=[CanComputeResults])
    def compute(self, request):
        student_id = request.data.get("student_id")
        year_id = request.data.get("target_academic_year_id")
        
        if not student_id or not year_id:
            return Response({"error": "student_id and target_academic_year_id are required."}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            student = Student.objects.get(id=student_id)
            year = AcademicYear.objects.get(id=year_id)
            result = CumulativeResultService.compute_cumulative_result(student, year, request.user)
            if not result:
                return Response({"error": "Could not compute cumulative result (no valid annual results found)."}, status=status.HTTP_400_BAD_REQUEST)
                
            return Response(CumulativeResultSerializer(result).data)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AcademicTranscriptViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AcademicTranscriptSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = AcademicTranscript.objects.select_related("student")
        user = self.request.user
        
        if not (getattr(user, "is_admin", False) or getattr(user, "is_superuser", False) or getattr(user, "is_staff", False)):
            if getattr(user, "is_parent", False):
                parent = getattr(user, "parent", None)
                if parent:
                    qs = qs.filter(student__parent_guardian=parent)
            elif getattr(user, "is_student", False):
                student = getattr(user, "student_profile", None) or getattr(user, "student", None)
                if student:
                    qs = qs.filter(student=student)
                    
        p = self.request.query_params
        if p.get("student_id"):
            qs = qs.filter(student_id=p["student_id"])
            
        return qs

    @action(detail=False, methods=["post"], permission_classes=[IsAdmin])
    def generate(self, request):
        student_id = request.data.get("student_id")
        if not student_id:
            return Response({"error": "student_id is required."}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            student = Student.objects.get(id=student_id)
            transcript = TranscriptService.generate_transcript(student, request.user)
            return Response(AcademicTranscriptSerializer(transcript).data)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ResultAmendmentViewSet(viewsets.ModelViewSet):
    serializer_class = ResultAmendmentRequestSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        qs = ResultAmendmentRequest.objects.all()
        user = self.request.user
        if not getattr(user, "is_admin", False):
            qs = qs.filter(requested_by=user)
        return qs

    @action(detail=True, methods=["post"], permission_classes=[IsAdmin])
    def resolve(self, request, pk=None):
        amendment = self.get_object()
        action_status = request.data.get("status")
        notes = request.data.get("notes", "")
        
        if action_status not in [ResultAmendmentRequest.Status.APPROVED, ResultAmendmentRequest.Status.REJECTED]:
            return Response({"error": "status must be APPROVED or REJECTED"}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            resolved = AmendmentService.resolve_amendment(amendment, request.user, action_status, notes)
            return Response(ResultAmendmentRequestSerializer(resolved).data)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
