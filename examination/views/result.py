from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import F, Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from api.jobs.throttles import BackgroundJobCreateThrottle
from academic.models import AllocatedSubject, ClassRoom, Student
from academic.services.academic_authority_service import AcademicAuthorityService
from administration.models import Term, AcademicYear
from ..models import TermResult, AnnualResult, ReportCard
from ..serializers.result import (
    TermResultSerializer, TermResultListSerializer, HomeroomRemarksSerializer, AdminRemarksSerializer,
    AnnualResultSerializer, AnnualResultListSerializer, ReportCardSerializer, ResultAuditLogSerializer
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
from django.db import connection, transaction
from django.http import HttpResponse
from api.jobs.serializers import BackgroundJobSerializer
from api.jobs.services import BackgroundJobService


def _get_schema_name(request):
    if hasattr(request, "tenant") and request.tenant and request.tenant.schema_name != "public":
        return request.tenant.schema_name
    return connection.schema_name


def _can_compute_for_classroom(user, classroom):
    if AcademicAuthorityService.is_school_admin(user):
        return True
    teacher = getattr(user, "teacher", None)
    if not teacher or not classroom:
        return False
    return bool(
        classroom.class_teacher_id == teacher.id
        or AllocatedSubject.objects.filter(teacher_name=teacher, class_room=classroom).exists()
    )


def _require_compute_scope(user, classroom):
    if not _can_compute_for_classroom(user, classroom):
        raise PermissionDenied("You are not authorized to compute results for this classroom.")


def _term_results_for_user(user):
    if not user.is_authenticated:
        return TermResult.objects.none()

    if AcademicAuthorityService.is_school_admin(user):
        return TermResult.objects.all()

    role = getattr(user, "active_role", None)
    if not role:
        if getattr(user, "is_teacher", False):
            role = "teacher"
        elif getattr(user, "is_parent", False):
            role = "parent"
        elif getattr(user, "is_student", False):
            role = "student"
        elif getattr(user, "is_accountant", False):
            role = "accountant"

    if role == "teacher" or getattr(user, "is_teacher", False):
        teacher = getattr(user, "teacher", None)
        if teacher:
            return TermResult.objects.filter(
                Q(classroom__class_teacher=teacher) | Q(subject_results__teacher=teacher)
            ).distinct()
        return TermResult.objects.none()

    if role == "parent" or getattr(user, "is_parent", False):
        parent = getattr(user, "parent", None)
        if parent:
            return TermResult.objects.filter(
                Q(student__parent_guardian=parent) | Q(student__parent_guardian__user=user),
                is_published=True
            ).distinct()
        return TermResult.objects.filter(student__parent_guardian__user=user, is_published=True).distinct()

    if role == "student" or getattr(user, "is_student", False):
        student = getattr(user, "student_profile", None) or getattr(user, "student", None)
        if not student:
            from academic.models import Student
            student = Student.objects.filter(user=user).first()
        if student:
            return TermResult.objects.filter(student=student, is_published=True).distinct()
        return TermResult.objects.filter(student__user=user, is_published=True).distinct()

    return TermResult.objects.none()


class TermResultViewSet(viewsets.ModelViewSet):
    def get_serializer_class(self):
        if self.action == 'list':
            return TermResultListSerializer
        return TermResultSerializer

    def get_queryset(self):
        qs = _term_results_for_user(self.request.user).select_related(
            "student", "term", "academic_year", "classroom", "grading_scheme"
        )
        if self.action != 'list':
            qs = qs.prefetch_related("subject_results")
        
        p = self.request.query_params
        student_param = p.get("student") or p.get("student_id")
        if student_param:
            from academic.models import Student
            st = Student.objects.filter(id=student_param).first()
            if not st and str(student_param).isdigit():
                st = Student.objects.filter(user_id=student_param).first()
            if st:
                qs = qs.filter(student=st)
            else:
                qs = qs.filter(student_id=student_param)
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
            _require_compute_scope(request.user, student.classroom)
            result = ResultComputationService.compute_student_term_result(
                student=student, term=term, academic_year=academic_year, user=request.user
            )
        except (Student.DoesNotExist, Term.DoesNotExist, AcademicYear.DoesNotExist) as e:
            return Response({"detail": "Invalid student, term, or academic year."}, status=status.HTTP_404_NOT_FOUND)
        except DjangoValidationError as e:
            return Response({"detail": e.messages if hasattr(e, "messages") else str(e)},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(TermResultSerializer(result).data, status=status.HTTP_201_CREATED)

    @action(
        detail=False,
        methods=["post"],
        url_path="compute-class",
        throttle_classes=[BackgroundJobCreateThrottle],
    )
    def compute_class(self, request):
        try:
            classroom = ClassRoom.objects.get(id=request.data.get("classroom"))
            term = Term.objects.get(id=request.data.get("term"))
            academic_year = AcademicYear.objects.get(id=request.data.get("academic_year"))
        except (ClassRoom.DoesNotExist, Term.DoesNotExist, AcademicYear.DoesNotExist):
            return Response({"detail": "Invalid classroom, term, or academic year."}, status=status.HTTP_404_NOT_FOUND)

        _require_compute_scope(request.user, classroom)

        use_async = request.data.get("async", False) or request.data.get("use_celery", False)
        if use_async:
            job = BackgroundJobService.create_and_dispatch(
                task=compute_class_results_task,
                job_type="EXAMINATION_CLASS_RESULT_COMPUTATION",
                created_by=request.user,
                task_kwargs={
                    "classroom_id": classroom.id,
                    "term_id": term.id,
                    "academic_year_id": academic_year.id,
                    "user_id": request.user.id,
                },
            )
            return Response(
                BackgroundJobSerializer(job).data,
                status=status.HTTP_202_ACCEPTED
            )

        summary = ResultComputationService.compute_classroom_term_results(
            classroom=classroom,
            term=term,
            academic_year=academic_year,
            user=request.user,
        )
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
        
        if not request.user.is_admin:
            teacher = getattr(request.user, "teacher", None)
            if not teacher or not ClassRoom.objects.filter(id=classroom_id, class_teacher=teacher).exists():
                return Response({"detail": "Only the homeroom teacher of this classroom or an administrator can lock results."}, status=status.HTTP_403_FORBIDDEN)

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
        
        with transaction.atomic():
            latest_report_card = ReportCard.objects.select_for_update().filter(term_result=result).order_by('-version').first()
            if regenerate or not latest_report_card:
                next_version = (latest_report_card.version + 1) if latest_report_card else 1
                report_card = ReportCard.objects.create(
                    term_result=result,
                    version=next_version,
                    status=ReportCardStatus.PENDING
                )
            else:
                report_card = latest_report_card
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
    def get_serializer_class(self):
        if self.action == 'list':
            return AnnualResultListSerializer
        return AnnualResultSerializer

    def get_queryset(self):
        user = self.request.user
        qs = AnnualResult.objects.select_related("student", "academic_year", "classroom")
        if self.action != 'list':
            qs = qs.prefetch_related("subjects")
        if not user.is_authenticated:
            return qs.none()
        if AcademicAuthorityService.is_school_admin(user):
            pass
        elif user.is_teacher and hasattr(user, "teacher"):
            teacher = user.teacher
            qs = qs.filter(
                Q(classroom__class_teacher=teacher)
                | Q(
                    student__term_results__academic_year=F("academic_year"),
                    student__term_results__subject_results__teacher=teacher,
                )
            ).distinct()
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
            _require_compute_scope(request.user, student.classroom)
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

        _require_compute_scope(request.user, classroom)

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
        student_id = p.get("student") or p.get("student_id")
        if student_id:
            from academic.models import Student
            st = Student.objects.filter(id=student_id).first()
            if not st and str(student_id).isdigit():
                st = Student.objects.filter(user_id=student_id).first()
            if st:
                qs = qs.filter(term_result__student=st)
            else:
                qs = qs.filter(term_result__student_id=student_id)
        if p.get("admin_approved"):
            is_approved = p["admin_approved"].lower() in ("true", "1")
            qs = qs.filter(term_result__admin_approved=is_approved)
        return qs

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        if not request.user or not request.user.is_authenticated:
            token = request.query_params.get("token") or request.query_params.get("access_token")
            if token:
                from rest_framework_simplejwt.tokens import AccessToken
                from django.contrib.auth import get_user_model
                try:
                    validated = AccessToken(token)
                    user_id = validated.get("user_id")
                    user = get_user_model().objects.get(id=user_id)
                    request.user = user
                except Exception:
                    pass

        if not request.user or not request.user.is_authenticated:
            return Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED)

        report_card = self.get_object()

        # Check if PDF file exists on storage or auto-generate on-the-fly if missing
        pdf_exists = False
        if report_card.pdf_file:
            try:
                pdf_exists = report_card.pdf_file.storage.exists(report_card.pdf_file.name)
            except Exception:
                pdf_exists = False

        if not pdf_exists:
            try:
                from examination.services.report_card_generator import ReportCardGenerator
                generator = ReportCardGenerator(report_card.term_result, generated_by=request.user)
                report_card = generator.generate_pdf(regenerate=True, allow_unpublished=True)
            except Exception as gen_err:
                return Response(
                    {"detail": f"Report card PDF not available and generation failed: {str(gen_err)}"},
                    status=status.HTTP_404_NOT_FOUND
                )

        report_card.increment_download_count()
        
        student_name = report_card.term_result.student.full_name if report_card.term_result and report_card.term_result.student else "Student"
        term_name = report_card.term_result.term.name if report_card.term_result and report_card.term_result.term else "Term"
        filename = f"Report_Card_{student_name}_{term_name}.pdf".replace(" ", "_")
        
        try:
            # If the storage provides an absolute HTTP URL (like Cloudinary or S3),
            # it is much better and more reliable to redirect the user to download it
            # directly from the CDN rather than proxying it through Django and hitting 401s.
            url = report_card.pdf_file.url
            if url.startswith('http://') or url.startswith('https://'):
                from django.http import HttpResponseRedirect
                return HttpResponseRedirect(url)
            
            # Local file storage fallback
            pdf_file = report_card.pdf_file.open("rb")
            response = HttpResponse(pdf_file.read(), content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response
        except Exception as e:
            return Response({"detail": f"Failed to retrieve PDF file: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ResultAuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing examination and result audit logs across the school.
    """
    from examination.models import ResultAuditLog
    from examination.serializers.result import ResultAuditLogSerializer
    from examination.filters import ResultAuditLogFilter
    from examination.permissions import IsAdmin
    from django_filters.rest_framework import DjangoFilterBackend
    from rest_framework.filters import SearchFilter, OrderingFilter

    queryset = ResultAuditLog.objects.select_related(
        "performed_by",
        "term_result",
        "term_result__student",
        "term_result__classroom",
        "term_result__term"
    ).all()
    serializer_class = ResultAuditLogSerializer
    permission_classes = [IsAdmin]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ResultAuditLogFilter
    search_fields = [
        "notes",
        "term_result__student__first_name",
        "term_result__student__last_name",
        "term_result__student__admission_number",
        "performed_by__first_name",
        "performed_by__last_name",
        "performed_by__email",
    ]
    ordering_fields = ["timestamp"]
    ordering = ["-timestamp"]
