import openpyxl
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import views
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import status, generics
from django.http import Http404
from django.shortcuts import get_object_or_404


from academic.models import Student, ClassRoom, Parent
from academic.permissions import IsSchoolAdmin
from academic.services.academic_authority_service import AcademicAuthorityService
from academic.services.student_creation_service import StudentCreationService
from .access import student_queryset_for_user
from .filters import StudentFilter
from .permissions import SISStudentPermission
from .serializers import (
    ScopedStudentReadSerializer,
    StudentSerializer,
    StudentsMedicalHistorySerializer,
    StudentsPreviousAcademicHistorySerializer,
    TeacherStudentReadSerializer,
    BulkUploadFileSerializer,
    BulkStudentUploadResponseSerializer,
)
from drf_spectacular.utils import extend_schema


class StudentPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class StudentListView(generics.ListCreateAPIView):
    queryset = Student.objects.all().select_related(
        'classroom',
        'classroom__grade_level',
        'classroom__stream',
        'parent_guardian',
        'reason_left'
    ).prefetch_related('siblings__classroom')
    serializer_class = StudentSerializer
    permission_classes = [SISStudentPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_class = StudentFilter
    pagination_class = StudentPagination

    def get_queryset(self):
        return student_queryset_for_user(self.request.user, super().get_queryset())

    def get_serializer_class(self):
        user = getattr(self.request, "user", None) if getattr(self, "request", None) else None
        if getattr(self, "request", None) and self.request.method == "GET":
            if user and AcademicAuthorityService.is_school_admin(user):
                from .serializers import StudentListSerializer
                return StudentListSerializer
            if user and getattr(user, "teacher", None):
                return TeacherStudentReadSerializer
            return ScopedStudentReadSerializer

        if user and AcademicAuthorityService.is_school_admin(user):
            return StudentSerializer
        if user and getattr(user, "teacher", None):
            return TeacherStudentReadSerializer
        return ScopedStudentReadSerializer


    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        student = serializer.save()
        return Response(
            self.get_serializer(student).data, status=status.HTTP_201_CREATED
        )


class StudentDetailView(views.APIView):
    permission_classes = [SISStudentPermission]
    serializer_class = StudentSerializer

    def get_object(self, request, pk):
        try:
            return student_queryset_for_user(
                request.user,
                Student.objects.select_related(
                    "classroom", "classroom__grade_level", "classroom__stream",
                    "parent_guardian", "class_of_year", "reason_left",
                ).prefetch_related("siblings__classroom"),
            ).get(pk=pk)
        except Student.DoesNotExist:
            raise Http404

    def serialize_student(self, request, student, **kwargs):
        if AcademicAuthorityService.is_school_admin(request.user):
            serializer_class = StudentSerializer
        elif getattr(request.user, "teacher", None):
            serializer_class = TeacherStudentReadSerializer
        else:
            serializer_class = ScopedStudentReadSerializer
        return serializer_class(student, context={"request": request}, **kwargs)

    def get(self, request, pk, format=None):
        student = self.get_object(request, pk)
        serializer = self.serialize_student(request, student)
        return Response(serializer.data)

    def put(self, request, pk, format=None):
        student = self.get_object(request, pk)
        serializer = StudentSerializer(student, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk, format=None):
        student = self.get_object(request, pk)
        serializer = StudentSerializer(student, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, format=None):
        student = self.get_object(request, pk)
        student.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class StudentPortalAccessView(APIView):
    permission_classes = [IsSchoolAdmin]

    def patch(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        enabled = request.data.get("enabled")
        if not isinstance(enabled, bool):
            return Response(
                {"enabled": "This field must be a boolean."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if enabled and not student.is_active:
            return Response(
                {"detail": "Portal access cannot be enabled for an inactive student."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if enabled and not student.phone_number:
            return Response(
                {"detail": "Add the student's phone number before enabling portal access."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        Student.objects.filter(pk=student.pk).update(can_login=enabled)
        student.can_login = enabled
        return Response({
            "id": student.pk,
            "can_login": student.can_login,
            "portal_account_created": bool(student.user_id),
        })


class BulkUploadStudentsView(APIView):
    """
    API View to handle bulk uploading of students from an Excel file.
    """
    permission_classes = [IsSchoolAdmin]

    @extend_schema(
        request=BulkUploadFileSerializer,
        responses={201: BulkStudentUploadResponseSerializer},
    )
    def post(self, request, *args, **kwargs):
        file = request.FILES.get("file")
        if not file:
            return Response(
                {"error": "No file provided."}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            workbook = openpyxl.load_workbook(file)
            sheet = workbook.active

            columns = [
                "first_name",
                "middle_name",
                "last_name",
                "parent_contact",
                "parent_email",
                "parent_first_name",
                "parent_last_name",
                "religion",
                "classroom_id",
                "gender",
            ]

            students_to_create = []
            not_created = []
            created_students = []
            updated_students_info = []
            skipped_students = []

            for i, row in enumerate(
                sheet.iter_rows(min_row=2, values_only=True), start=2
            ):
                student_data = dict(zip(columns, row))

                # Normalize names
                first_name = (student_data.get("first_name") or "").lower()
                middle_name = (student_data.get("middle_name") or "").lower()
                last_name = (student_data.get("last_name") or "").lower()
                parent_contact = student_data.get("parent_contact")

                try:
                    # Prepare new student via canonical service
                    classroom_id = student_data.get("classroom_id")
                    if not classroom_id:
                        raise ValueError("classroom_id is required")

                    classroom = ClassRoom.objects.get(pk=classroom_id)

                    # Transaction boundary per row managed by create_student atomic block
                    student = StudentCreationService.create_student(
                        classroom=classroom,
                        first_name=first_name.title(),
                        last_name=last_name.title(),
                        parent_phone=parent_contact,
                        parent_email=student_data.get("parent_email"),
                        middle_name=middle_name.title(),
                        gender=student_data.get("gender"),
                        religion=student_data.get("religion"),
                        parent_first_name=student_data.get("parent_first_name"),
                        parent_last_name=student_data.get("parent_last_name"),
                    )

                    created_students.append(student)

                    # Manage siblings
                    if parent_contact:
                        existing_sibling = Student.objects.filter(
                            parent_contact=parent_contact
                        ).exclude(id=student.id).first()

                        if existing_sibling and not student.siblings.filter(id=existing_sibling.id).exists():
                            student.siblings.add(existing_sibling)
                            existing_sibling.siblings.add(student)
                            updated_students_info.append(
                                {
                                    "admission_number": student.admission_number,
                                    "full_name": f"{student.first_name} {student.last_name}",
                                    "reasons": ["sibling added"],
                                }
                            )

                except Exception as e:
                    student_data["error"] = str(e)
                    not_created.append(student_data)

            return Response(
                {
                    "message": f"{len(created_students)} students successfully uploaded.",
                    "updated_students": updated_students_info,
                    "skipped_students": skipped_students,
                    "not_created": not_created,
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


"""
class StudentHealthRecordViewSet(viewsets.ModelViewSet):
    queryset = StudentHealthRecord.objects.all()
    serializer_class = StudentHealthRecordSerializer

class GradeScaleViewSet(viewsets.ModelViewSet):
    queryset = GradeScale.objects.all()
    serializer_class = GradeScaleSerializer

class GradeScaleRuleViewSet(viewsets.ModelViewSet):
    queryset = GradeScaleRule.objects.all()
    serializer_class = GradeScaleRuleSerializer

class SchoolYearViewSet(viewsets.ModelViewSet):
    queryset = SchoolYear.objects.all()
    serializer_class = SchoolYearSerializer

class MessageToStudentViewSet(viewsets.ModelViewSet):
    queryset = MessageToStudent.objects.all()
    serializer_class = MessageToStudentSerializer
"""

from academic.models import StudentsMedicalHistory, StudentsPreviousAcademicHistory

class StudentMedicalHistoryView(views.APIView):
    permission_classes = [SISStudentPermission]
    serializer_class = StudentsMedicalHistorySerializer

    def get_student(self, request, pk):
        return get_object_or_404(student_queryset_for_user(request.user), pk=pk)

    def get(self, request, pk):
        self.get_student(request, pk)
        records = StudentsMedicalHistory.objects.filter(student_id=pk)
        return Response(StudentsMedicalHistorySerializer(records, many=True).data)

    def post(self, request, pk):
        self.get_student(request, pk)
        data = request.data.copy()
        data['student'] = pk
        serializer = StudentsMedicalHistorySerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class StudentAcademicHistoryView(views.APIView):
    permission_classes = [SISStudentPermission]
    serializer_class = StudentsPreviousAcademicHistorySerializer

    def get_student(self, request, pk):
        return get_object_or_404(student_queryset_for_user(request.user), pk=pk)

    def get(self, request, pk):
        self.get_student(request, pk)
        records = StudentsPreviousAcademicHistory.objects.filter(student_id=pk)
        return Response(StudentsPreviousAcademicHistorySerializer(records, many=True).data)

    def post(self, request, pk):
        self.get_student(request, pk)
        data = request.data.copy()
        data['student'] = pk
        serializer = StudentsPreviousAcademicHistorySerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
