from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from academic.models import ClassRoom, Student
from administration.models import Term, AcademicYear
from ..models import TermResult, AnnualResult, ReportCard
from ..serializers.result import (
    TermResultSerializer, HomeroomRemarksSerializer, AdminRemarksSerializer,
    AnnualResultSerializer, ReportCardSerializer, ResultAuditLogSerializer
)
from ..permissions import (
    IsAdmin, CanComputeResults, CanHomeroomApprove, CanApproveResults, CanPublishResults,
    CanLockResults, CanGenerateReports, CanAddHomeroomRemarks,
    CanViewOwnStudentResult, IsHomeroomTeacherOfClass,
)
from ..services.result_computation_service import ResultComputationService
from ..services.promotion_service import PromotionService
from ..services.report_card_generator import ReportCardGenerator
from ..tasks import generate_report_card_task, generate_bulk_report_cards_task, compute_class_results_task
from ..models import ReportCardStatus
from django.db import connection
from django.http import HttpResponse


def _get_schema_name(request):
    if hasattr(request, "tenant") and request.tenant and request.tenant.schema_name != "public":
        return request.tenant.schema_name
    return connection.schema_name


def _term_results_for_user(user):
    if not user.is_authenticated:
        return TermResult.objects.none()
    if user.is_admin:
        return TermResult.objects.all()
    if user.is_teacher and user.active_role == "teacher" and hasattr(user, "teacher"):
        teacher = user.teacher
        return TermResult.objects.filter(
            Q(classroom__class_teacher=teacher) | Q(subject_results__teacher=teacher)
        ).distinct()
    if user.is_parent and user.active_role == "parent" and hasattr(user, "parent"):
        return TermResult.objects.filter(student__parent_guardian=user.parent, is_published=True)
    if user.is_student and user.active_role == "student" and hasattr(user, "student_profile"):
        return TermResult.objects.filter(student=user.student_profile, is_published=True)
    return TermResult.objects.none()


class TermResultViewSet(viewsets.ModelViewSet):
    serializer_class = TermResultSerializer

    def get_queryset(self):
        qs = _term_results_for_user(self.request.user).select_related(
            "student", "term", "academic_year", "classroom", "grading_scheme"
        ).prefetch_related("subject_results")

        p = self.request.query_params
        if p.get("student"):
            qs = qs.filter(student_id=p["student"])
        if p.get("term"):
            qs = qs.filter(term_id=p["term"])
        if p.get("classroom"):
            qs = qs.filter(classroom_id=p["classroom"])
        if p.get("academic_year"):
            qs = qs.filter(academic_year_id=p["academic_year"])
        if p.get("admin_approved"):
            is_approved = p["admin_approved"].lower() in ("true", "1")
            qs = qs.filter(admin_approved=is_approved)
        if p.get("homeroom_approved"):
            is_hr_approved = p["homeroom_approved"].lower() in ("true", "1")
            qs = qs.filter(homeroom_approved=is_hr_approved)
        return qs

    def get_permissions(self):
        action_permissions = {
            "compute": [CanComputeResults],
            "compute_class": [CanComputeResults],
            "homeroom_approve": [CanHomeroomApprove],
            "approve": [CanApproveResults],
            "publish": [CanPublishResults],
            "bulk_publish": [CanPublishResults],
            "unpublish": [IsAdmin],
            "lock": [CanLockResults],
            "bulk_lock": [CanLockResults],
            "unlock": [IsAdmin],
            "bulk_unlock": [IsAdmin],
            "generate_report": [CanGenerateReports],
            "homeroom_remarks": [CanAddHomeroomRemarks],
            "admin_remarks": [IsAdmin],
            "create": [IsAdmin],
            "update": [IsAdmin],
            "partial_update": [IsAdmin],
            "destroy": [IsAdmin],
            "retrieve": [CanViewOwnStudentResult],
        }
        classes = action_permissions.get(self.action)
        if classes:
            return [cls() for cls in classes]

        from rest_framework.permissions import IsAuthenticated
        return [IsAuthenticated()]
  

    @action(detail=False, methods=["post"], url_path="compute")
    def compute(self, request):
        try:
            student = Student.objects.get(id=request.data.get("student"))
            term = Term.objects.get(id=request.data.get("term"))
            academic_year = AcademicYear.objects.get(id=request.data.get("academic_year"))
            result = ResultComputationService.compute_student_term_result(
                student=student, term=term, academic_year=academic_year, user=request.user
            )
        except (Student.DoesNotExist, Term.DoesNotExist, AcademicYear.DoesNotExist) as e:
            return Response({"detail": "Invalid student, term, or academic year."}, status=status.HTTP_404_NOT_FOUND)
        except DjangoValidationError as e:
            return Response({"detail": e.messages if hasattr(e, "messages") else str(e)},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(TermResultSerializer(result).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="compute-class")
    def compute_class(self, request):
        try:
            classroom = ClassRoom.objects.get(id=request.data.get("classroom"))
            term = Term.objects.get(id=request.data.get("term"))
            academic_year = AcademicYear.objects.get(id=request.data.get("academic_year"))
        except (ClassRoom.DoesNotExist, Term.DoesNotExist, AcademicYear.DoesNotExist):
            return Response({"detail": "Invalid classroom, term, or academic year."}, status=status.HTTP_404_NOT_FOUND)

        use_async = request.data.get("async", False) or request.data.get("use_celery", False)
        if use_async:
            task = compute_class_results_task.delay(
                schema_name=_get_schema_name(request),
                classroom_id=classroom.id,
                term_id=term.id,
                academic_year_id=academic_year.id,
                user_id=request.user.id,
            )
            return Response(
                {"detail": "Class result computation scheduled via Celery.", "task_id": task.id},
                status=status.HTTP_202_ACCEPTED
            )

        summary = {"computed": 0, "failed": 0, "errors": []}
        for student in classroom.students.filter(is_active=True):
            try:
                ResultComputationService.compute_student_term_result(
                    student=student, term=term, academic_year=academic_year, user=request.user
                )
                summary["computed"] += 1
            except DjangoValidationError as e:
                summary["failed"] += 1
                summary["errors"].append({"student": student.full_name, "error": str(e)})
        return Response(summary)

    @action(detail=True, methods=["post"])
    def homeroom_approve(self, request, pk=None):
        result = self.get_object()
        self.check_object_permissions(request, result)
        try:
            remarks = request.data.get("remarks") or request.data.get("class_teacher_remarks")
            if remarks:
                result.class_teacher_remarks = remarks
                result.save(update_fields=["class_teacher_remarks"])
            result.homeroom_approve(request.user)
        except DjangoValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TermResultSerializer(result).data)

    @action(detail=True, methods=["post"], url_path="homeroom-approve")
    def homeroom_approve_hyphen(self, request, pk=None):
        return self.homeroom_approve(request, pk=pk)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        result = self.get_object()
        self.check_object_permissions(request, result)
        try:
            remarks = request.data.get("remarks") or request.data.get("principal_remarks") or request.data.get("admin_remarks")
            if remarks:
                result.principal_remarks = remarks
                result.save(update_fields=["principal_remarks"])
            result.approve(request.user)
        except DjangoValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TermResultSerializer(result).data)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        result = self.get_object()
        self.check_object_permissions(request, result)
        try:
            result.publish(published_by=request.user)
        except DjangoValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TermResultSerializer(result).data)
    
    @action(detail=True, methods=["post"])
    def unpublish(self, request, pk=None):
        result = self.get_object()
        self.check_object_permissions(request, result)
        result.unpublish(user=request.user)
        return Response(TermResultSerializer(result).data)

    @action(detail=True, methods=["post"])
    def lock(self, request, pk=None):
        result = self.get_object()
        self.check_object_permissions(request, result)
        result.lock(request.user)
        return Response(TermResultSerializer(result).data)

    @action(detail=False, methods=["post"], url_path="bulk-lock")
    def bulk_lock(self, request):
        term_id = request.data.get("term")
        classroom_id = request.data.get("classroom")
        academic_year_id = request.data.get("academic_year")

        if not term_id or not classroom_id or not academic_year_id:
            return Response({"detail": "term, classroom, and academic_year are required."}, status=status.HTTP_400_BAD_REQUEST)
        
        results = TermResult.objects.filter(
            term_id=term_id,
            classroom_id=classroom_id,
            academic_year_id=academic_year_id,
            is_locked=False
        )

        count = 0
        for result in results:
            try:
                result.lock(request.user)
                count += 1
            except DjangoValidationError:
                continue

        return Response({"detail": f"{count} results successfully locked."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def unlock(self, request, pk=None):
        result = self.get_object()
        result.unlock(user=request.user, reason=request.data.get("reason", ""))
        return Response(TermResultSerializer(result).data)

    @action(detail=False, methods=["post"], url_path="bulk-unlock")
    def bulk_unlock(self, request):
        term_id = request.data.get("term")
        classroom_id = request.data.get("classroom")
        academic_year_id = request.data.get("academic_year")

        if not term_id or not classroom_id or not academic_year_id:
            return Response({"detail": "term, classroom, and academic_year are required."}, status=status.HTTP_400_BAD_REQUEST)

        results = TermResult.objects.filter(
            term_id=term_id,
            classroom_id=classroom_id,
            academic_year_id=academic_year_id,
            is_locked=True
        )

        count = 0
        for result in results:
            try:
                result.unlock(user=request.user, reason="Bulk unlock")
                count += 1
            except DjangoValidationError:
                continue

        return Response({"detail": f"{count} results successfully unlocked."}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="bulk-publish")
    def bulk_publish(self, request):
        """Bulk publish only results with both homeroom and admin approvals"""
        term_id = request.data.get("term")
        classroom_id = request.data.get("classroom")
        academic_year_id = request.data.get("academic_year")

        if not term_id or not classroom_id or not academic_year_id:
            return Response({"detail": "term, classroom, and academic_year are required."}, status=status.HTTP_400_BAD_REQUEST)

        # Only publish results that have both approvals and are not already published
        results = TermResult.objects.filter(
            term_id=term_id,
            classroom_id=classroom_id,
            academic_year_id=academic_year_id,
            homeroom_approved=True,
            admin_approved=True,
            is_published=False,
            is_locked=True, 
        )

        count = 0
        skipped = 0
        errors = []
        for result in results:
            try:
                result.publish(published_by=request.user)
                count += 1
            except DjangoValidationError as e:
                errors.append({"student": result.student.full_name, "error": str(e)})
                skipped += 1

        # Count results that don't meet approval criteria
        total_results = TermResult.objects.filter(
            term_id=term_id,
            classroom_id=classroom_id,
            academic_year_id=academic_year_id
        ).count()
        not_ready = total_results - count - skipped

        response_data = {
            "detail": f"{count} results successfully published.",
            "published_count": count,
            "skipped_count": skipped,
            "not_ready_count": not_ready,
            "errors": errors if errors else None
        }
        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="generate-report")
    def generate_report(self, request, pk=None):
        result = self.get_object()
        allow_unpublished = request.data.get("allow_unpublished", False) and request.user.is_admin
        regenerate = request.data.get("regenerate", False)
        
        report_card, _ = ReportCard.objects.get_or_create(
            term_result=result,
            defaults={'status': ReportCardStatus.PENDING}
        )
        if regenerate:
            report_card.status = ReportCardStatus.PENDING
            report_card.save(update_fields=['status'])
            
        generate_report_card_task.delay(
            schema_name=_get_schema_name(request),
            term_result_id=result.id,
            user_id=request.user.id,
            regenerate=regenerate,
            allow_unpublished=allow_unpublished,
        )
        return Response(ReportCardSerializer(report_card, context={"request": request}).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["post"], url_path="bulk-generate-report")
    def bulk_generate_report(self, request):
        term_id = request.data.get("term")
        classroom_id = request.data.get("classroom")
        regenerate = request.data.get("regenerate", False)
        
        if not term_id or not classroom_id:
            return Response({"detail": "term and classroom are required."}, status=status.HTTP_400_BAD_REQUEST)
            
        generate_bulk_report_cards_task.delay(
            schema_name=_get_schema_name(request),
            term_id=term_id,
            classroom_id=classroom_id,
            user_id=request.user.id,
            regenerate=regenerate,
        )
        
        return Response({"detail": "Bulk report card generation has been scheduled."}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post", "patch"])
    def homeroom_remarks(self, request, pk=None):
        result = self.get_object()
        self.check_object_permissions(request, result)
        data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data or {})
        if "remarks" in data and "class_teacher_remarks" not in data:
            data["class_teacher_remarks"] = data["remarks"]
        serializer = HomeroomRemarksSerializer(result, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(TermResultSerializer(result).data)

    @action(detail=True, methods=["post", "patch"], url_path="homeroom-remarks")
    def homeroom_remarks_hyphen(self, request, pk=None):
        return self.homeroom_remarks(request, pk=pk)

    @action(detail=True, methods=["patch"], url_path="admin-remarks")
    def admin_remarks(self, request, pk=None):
        result = self.get_object()
        serializer = AdminRemarksSerializer(result, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="audit-logs")
    def audit_logs(self, request, pk=None):
        result = self.get_object()
        logs = result.audit_logs.select_related("performed_by").all()
        return Response(ResultAuditLogSerializer(logs, many=True).data)


class AnnualResultViewSet(viewsets.ModelViewSet):
    serializer_class = AnnualResultSerializer

    def get_queryset(self):
        user = self.request.user
        qs = AnnualResult.objects.select_related("student", "academic_year", "classroom").prefetch_related("subjects")
        if not user.is_authenticated:
            return qs.none()
        if user.is_admin or (user.is_teacher and hasattr(user, "teacher")):
            pass
        elif user.is_parent and user.active_role == "parent" and hasattr(user, "parent"):
            qs = qs.filter(student__parent_guardian=user.parent, is_published=True)
        elif user.is_student and user.active_role == "student" and hasattr(user, "student_profile"):
            qs = qs.filter(student=user.student_profile, is_published=True)
        else:
            return qs.none()

        p = self.request.query_params
        if p.get("student"):
            qs = qs.filter(student_id=p["student"])
        if p.get("classroom"):
            qs = qs.filter(classroom_id=p["classroom"])
        if p.get("academic_year"):
            qs = qs.filter(academic_year_id=p["academic_year"])
        return qs

    def get_permissions(self):
        if self.action in ("compute", "compute_class"):
            return [CanComputeResults()]
        
        from rest_framework.permissions import IsAuthenticated
        return [IsAuthenticated()]

    @action(detail=False, methods=["post"])
    def compute(self, request):
        try:
            student = Student.objects.get(id=request.data.get("student"))
            academic_year = AcademicYear.objects.get(id=request.data.get("academic_year"))
        except (Student.DoesNotExist, AcademicYear.DoesNotExist):
            return Response({"detail": "Invalid student or academic year."}, status=status.HTTP_404_NOT_FOUND)

        try:
            annual_result = PromotionService.compute_annual_result(
                student=student, academic_year=academic_year, user=request.user
            )
        except DjangoValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AnnualResultSerializer(annual_result).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="compute-class")
    def compute_class(self, request):
        try:
            classroom = ClassRoom.objects.get(id=request.data.get("classroom"))
            academic_year = AcademicYear.objects.get(id=request.data.get("academic_year"))
        except (ClassRoom.DoesNotExist, AcademicYear.DoesNotExist):
            return Response({"detail": "Invalid classroom or academic year."}, status=status.HTTP_404_NOT_FOUND)

        summary = {"computed": 0, "failed": 0, "errors": []}
        for student in classroom.students.filter(is_active=True):
            try:
                PromotionService.compute_annual_result(
                    student=student, academic_year=academic_year, user=request.user
                )
                summary["computed"] += 1
            except DjangoValidationError as e:
                summary["failed"] += 1
                summary["errors"].append({"student": student.id, "error": str(e)})

        return Response(
            {"detail": f"Computed {summary['computed']} annual results. {summary['failed']} failed."},
            status=status.HTTP_200_OK
        )



class ReportCardViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ReportCardSerializer

    def get_queryset(self):
        qs = ReportCard.objects.filter(
            term_result__in=_term_results_for_user(self.request.user)
        ).select_related("term_result__student", "term_result__term", "term_result__classroom", "generated_by")

        p = self.request.query_params
        if p.get("term"):
            qs = qs.filter(term_result__term_id=p["term"])
        if p.get("classroom"):
            qs = qs.filter(term_result__classroom_id=p["classroom"])
        if p.get("student"):
            qs = qs.filter(term_result__student_id=p["student"])
        if p.get("admin_approved"):
            is_approved = p["admin_approved"].lower() in ("true", "1")
            qs = qs.filter(term_result__admin_approved=is_approved)
        return qs

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        report_card = self.get_object()
        if not report_card.pdf_file:
            return Response({"detail": "Report card PDF not available."}, status=status.HTTP_404_NOT_FOUND)
        
        report_card.increment_download_count()
        
        student_name = report_card.term_result.student.full_name if report_card.term_result and report_card.term_result.student else "Student"
        term_name = report_card.term_result.term.name if report_card.term_result and report_card.term_result.term else "Term"
        filename = f"Report_Card_{student_name}_{term_name}.pdf".replace(" ", "_")
        
        try:
            pdf_file = report_card.pdf_file.open("rb")
            response = HttpResponse(pdf_file.read(), content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response
        except Exception as e:
            return Response({"detail": f"Failed to retrieve PDF file: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)