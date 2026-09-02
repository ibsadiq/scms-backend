from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.http import FileResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from ..models import AssessmentSession, AssessmentEntry, MarkedScript
from ..serializers.assessments import AssessmentSessionSerializer, AssessmentEntrySerializer, MarkedScriptSerializer
from ..permissions import IsAdmin, CanEnterScores, CanUploadMarkedScript, CanViewMarkedScript
from ..services.assessment_service import AssessmentService


class AssessmentSessionViewSet(viewsets.ModelViewSet):
    serializer_class = AssessmentSessionSerializer
    queryset = AssessmentSession.objects.prefetch_related("classrooms")

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAdmin()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        # Allow admins to create without teacher profile
        if getattr(self.request.user, "is_admin", False):
            serializer.save(created_by=None)
        else:
            teacher = getattr(self.request.user, "teacher", None)
            serializer.save(created_by=teacher)


class AssessmentEntryViewSet(viewsets.ModelViewSet):
    serializer_class = AssessmentEntrySerializer
    permission_classes = [CanEnterScores]
    queryset = AssessmentEntry.objects.select_related("component", "student", "subject", "entered_by")

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        if user.is_admin:
            return qs
        if hasattr(user, "teacher"):
            return qs.filter(entered_by=user.teacher)
        return qs.none()

    def perform_create(self, serializer):
        # Allow admins to create without teacher profile
        if self.request.user.is_admin:
            serializer.save(entered_by=None)
        else:
            serializer.save(entered_by=self.request.user.teacher)

    @action(detail=False, methods=["post"], url_path="bulk-upload")
    def bulk_upload(self, request):
        try:
            # Allow admins to bulk upload without teacher profile
            teacher = getattr(request.user, "teacher", None) if not request.user.is_admin else None
            entries = AssessmentService.bulk_record_scores(
                entries=request.data.get("entries", []),
                teacher=teacher,
            )
        except DjangoValidationError as e:
            return Response(e.message_dict if hasattr(e, "message_dict") else {"detail": str(e)},
                             status=status.HTTP_400_BAD_REQUEST)
        return Response(
            AssessmentEntrySerializer(entries, many=True).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="bulk-update")
    def bulk_update(self, request):
        # Same underlying service — update_or_create makes create/update the same path
        return self.bulk_upload(request)


class MarkedScriptViewSet(viewsets.ModelViewSet):
    serializer_class = MarkedScriptSerializer
    queryset = MarkedScript.objects.select_related("student", "subject", "exam", "uploaded_by")

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy", "bulk_upload", "toggle_visibility"):
            return [CanUploadMarkedScript()]
        return [CanViewMarkedScript()]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

        role = getattr(user, "active_role", None)
        if not role:
            if getattr(user, "is_teacher", False):
                role = "teacher"
            elif getattr(user, "is_parent", False):
                role = "parent"
            elif getattr(user, "is_student", False):
                role = "student"

        if hasattr(user, "teacher") and not getattr(user, "is_admin", False) and role == "teacher":
            qs = qs.filter(uploaded_by=user.teacher)
        elif role == "student" or getattr(user, "is_student", False):
            student = getattr(user, "student_profile", None) or getattr(user, "student", None)
            if not student:
                from academic.models import Student
                student = Student.objects.filter(user=user).first()
            if student:
                qs = qs.filter(student=student, visible_to_student=True)
            else:
                qs = qs.filter(student__user=user, visible_to_student=True)
        elif role == "parent" or getattr(user, "is_parent", False):
            parent = getattr(user, "parent", None)
            if parent:
                qs = qs.filter(Q(student__parent_guardian=parent) | Q(student__parent_guardian__user=user), visible_to_parent=True).distinct()
            else:
                qs = qs.filter(student__parent_guardian__user=user, visible_to_parent=True).distinct()
        elif not user.is_authenticated:
            return qs.none()
        elif not getattr(user, "is_admin", False) and not getattr(user, "is_staff", False):
            return qs.none()

        # Query param filtering
        params = self.request.query_params
        exam_id = params.get("exam") or params.get("exam_id")
        student_id = params.get("student") or params.get("student_id")
        subject_id = params.get("subject") or params.get("subject_id")
        classroom_id = params.get("classroom") or params.get("classroom_id")
        academic_year_id = params.get("academic_year") or params.get("academic_year_id")
        term_id = params.get("term") or params.get("term_id")

        if exam_id:
            qs = qs.filter(exam_id=exam_id)
        if student_id:
            from academic.models import Student
            st = Student.objects.filter(id=student_id).first()
            if not st and str(student_id).isdigit():
                st = Student.objects.filter(user_id=student_id).first()
            if st:
                qs = qs.filter(student=st)
            else:
                qs = qs.filter(student_id=student_id)
        if subject_id:
            qs = qs.filter(subject_id=subject_id)
        if classroom_id:
            qs = qs.filter(
                Q(student__classroom_id=classroom_id) |
                Q(student__student_classes__classroom_id=classroom_id) |
                Q(exam__classrooms__id=classroom_id)
            ).distinct()
        if academic_year_id:
            qs = qs.filter(
                Q(assessment_entry__component__scheme__academic_year_id=academic_year_id) |
                Q(student__student_classes__academic_year_id=academic_year_id)
            ).distinct()
        if term_id:
            qs = qs.filter(
                Q(assessment_entry__student__academic_year__terms__id=term_id) |
                Q(student__student_classes__academic_year__terms__id=term_id)
            ).distinct()

        return qs

    def perform_create(self, serializer):
        teacher = getattr(self.request.user, "teacher", None)
        serializer.save(uploaded_by=teacher)

    @action(detail=True, methods=["post", "patch"], url_path="toggle_visibility")
    def toggle_visibility(self, request, pk=None):
        script = self.get_object()
        if "visible_to_student" in request.data:
            val = str(request.data["visible_to_student"]).lower() in ("true", "1")
            script.visible_to_student = val
        if "visible_to_parent" in request.data:
            val = str(request.data["visible_to_parent"]).lower() in ("true", "1")
            script.visible_to_parent = val
        script.save()
        return Response(self.get_serializer(script).data)

    @action(detail=False, methods=["post"], url_path="bulk_upload")
    def bulk_upload(self, request):
        files = request.FILES.getlist("files")
        student_ids = request.data.getlist("student_ids")
        exam_id = request.data.get("exam_id") or request.data.get("exam")
        subject_id = request.data.get("subject_id") or request.data.get("subject")
        visible_to_student = str(request.data.get("visible_to_student", "false")).lower() in ("true", "1")
        visible_to_parent = str(request.data.get("visible_to_parent", "false")).lower() in ("true", "1")
        notes = request.data.get("notes", "")

        if not files or not student_ids:
            return Response({"detail": "No files or student_ids provided."}, status=status.HTTP_400_BAD_REQUEST)

        if not exam_id or not subject_id:
            return Response({"detail": "exam_id and subject_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        created_scripts = []
        errors = []
        teacher = getattr(request.user, "teacher", None)

        for idx, (file_obj, student_id) in enumerate(zip(files, student_ids)):
            try:
                from academic.models import Student, Subject
                from examination.models import AssessmentSession

                exam = AssessmentSession.objects.get(id=exam_id)
                subject = Subject.objects.get(id=subject_id)
                student = Student.objects.get(id=student_id)

                script = MarkedScript.objects.filter(exam=exam, student=student, subject=subject).first()
                if not script:
                    script = MarkedScript(exam=exam, student=student, subject=subject)

                if getattr(student, "classroom", None):
                    script.classroom = student.classroom

                script.script_file = file_obj
                script.uploaded_by = teacher
                script.notes = notes
                script.visible_to_student = visible_to_student
                script.visible_to_parent = visible_to_parent
                script.save()

                created_scripts.append({
                    "id": script.id,
                    "student_id": student.id,
                    "student_name": student.full_name,
                    "file_name": script.file_name,
                })
            except Exception as e:
                errors.append({"file_index": idx, "student_id": student_id, "error": str(e)})

        response_data = {
            "message": f"Uploaded {len(created_scripts)} of {len(files)} files successfully",
            "created": len(created_scripts),
            "scripts": created_scripts,
            "errors": errors,
        }
        return Response(response_data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, pk=None):
        script = self.get_object()
        if not script.script_file:
            return Response({"detail": "No file associated with this marked script."}, status=status.HTTP_404_NOT_FOUND)

        try:
            filename = script.file_name or f"marked_script_{script.id}.pdf"
            response = FileResponse(script.script_file.open("rb"))
            response["Content-Disposition"] = f'inline; filename="{filename}"'
            return response
        except Exception as e:
            return Response({"detail": f"Could not read script file: {str(e)}"}, status=status.HTTP_404_NOT_FOUND)
