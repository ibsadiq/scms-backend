import datetime
import openpyxl
import re
from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import views
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import status, generics
from django.http import Http404
from django.shortcuts import get_object_or_404


def parse_date_of_birth(value):
    """
    Parses and validates a date_of_birth value from Excel/user input.
    Accepts:
      - None, blank/whitespace-only string -> (None, None)
      - datetime.date or datetime.datetime -> (date, None)
      - Strings in YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY format -> (date, None)
    Returns:
      - (datetime.date or None, None) on success
      - (None, error_message) on validation failure
    """
    if value is None:
        return None, None

    if isinstance(value, datetime.datetime):
        dob = value.date()
    elif isinstance(value, datetime.date):
        dob = value
    elif isinstance(value, str):
        val_str = value.strip()
        if not val_str:
            return None, None

        dob = None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                parsed = datetime.datetime.strptime(val_str, fmt)
                if parsed.year < 1900:
                    return None, "date_of_birth must be a valid date in YYYY-MM-DD or DD/MM/YYYY format."
                dob = parsed.date()
                break
            except ValueError:
                continue

        if dob is None:
            return None, "date_of_birth must be a valid date in YYYY-MM-DD or DD/MM/YYYY format."
    else:
        return None, "date_of_birth must be a valid date in YYYY-MM-DD or DD/MM/YYYY format."

    today = timezone.now().date()
    if dob > today:
        return None, "date_of_birth cannot be in the future."

    return dob, None


from academic.models import Student, ClassRoom, Parent
from academic.permissions import IsSchoolAdmin
from academic.services.academic_authority_service import AcademicAuthorityService
from academic.services.student_creation_service import StudentCreationService
from academic.services.parent_identity_service import ParentIdentityService
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
    max_page_size = 500


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
            workbook = openpyxl.load_workbook(file, data_only=True)
            sheet = workbook.active

            columns_12 = [
                "first_name",
                "middle_name",
                "last_name",
                "date_of_birth",
                "parent_contact",
                "parent_email",
                "parent_first_name",
                "parent_last_name",
                "religion",
                "classroom_id",
                "gender",
                "parent_address",
            ]
            columns_11_dob = columns_12[:11]

            columns_11_legacy = [
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
                "parent_address",
            ]
            columns_10_legacy = columns_11_legacy[:10]

            raw_header = [cell.value for cell in sheet[1] if cell.value is not None]
            cleaned_header = [str(v).strip().lower() for v in raw_header]

            if len(cleaned_header) >= 12 and (
                cleaned_header[:12] == columns_12
                or (cleaned_header[:11] == columns_11_dob and cleaned_header[11] in ("parent_address", "address"))
            ):
                columns = columns_12
            elif len(cleaned_header) >= 11 and cleaned_header[:11] == columns_11_dob:
                columns = columns_11_dob
            elif len(cleaned_header) >= 11 and (
                cleaned_header[:11] == columns_11_legacy
                or (cleaned_header[:10] == columns_10_legacy and cleaned_header[10] in ("parent_address", "address"))
            ):
                columns = columns_11_legacy
            elif len(cleaned_header) >= 10 and cleaned_header[:10] == columns_10_legacy:
                columns = columns_10_legacy
            else:
                return Response(
                    {
                        "error": "Invalid Students worksheet columns.",
                        "expected_columns": columns_12,
                        "actual_columns": raw_header[:12],
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            rows_to_create = []
            not_created = []
            created_students = []
            updated_students_info = []
            skipped_students = []

            for i, row in enumerate(
                sheet.iter_rows(min_row=2, values_only=True), start=2
            ):
                student_data = dict(zip(columns, row[:len(columns)]))
                if not any(value not in (None, "") for value in student_data.values()):
                    continue

                cleaned = {
                    key: value.strip() if isinstance(value, str) else value
                    for key, value in student_data.items()
                }
                errors = []
                for field in ("first_name", "last_name"):
                    if not cleaned.get(field):
                        errors.append(f"{field} is required")

                classroom = None
                classroom_id = cleaned.get("classroom_id")
                if not classroom_id:
                    errors.append("classroom_id is required")
                else:
                    try:
                        classroom = ClassRoom.objects.get(pk=classroom_id)
                    except (ClassRoom.DoesNotExist, TypeError, ValueError):
                        errors.append(f"classroom_id {classroom_id!r} does not exist")

                has_parent = any(
                    bool(str(cleaned.get(f) or "").strip())
                    for f in ("parent_contact", "parent_email", "parent_first_name", "parent_last_name", "parent_address")
                )

                if has_parent:
                    contact = ParentIdentityService.normalize_phone(cleaned.get("parent_contact"))
                    if not contact or not re.fullmatch(r"\+[1-9]\d{9,14}", contact):
                        errors.append("parent_contact must be a valid phone number, not an address")
                    else:
                        cleaned["parent_contact"] = contact

                    email = cleaned.get("parent_email")
                    if email:
                        try:
                            validate_email(email)
                        except DjangoValidationError:
                            errors.append("parent_email must contain one valid email address")

                    if not cleaned.get("parent_first_name"):
                        errors.append("parent_first_name is required when parent details are supplied")
                    if not cleaned.get("parent_last_name"):
                        errors.append("parent_last_name is required when parent details are supplied")
                else:
                    cleaned["parent_contact"] = None
                    cleaned["parent_email"] = None
                    cleaned["parent_first_name"] = ""
                    cleaned["parent_last_name"] = ""
                    cleaned["parent_address"] = ""

                gender = str(cleaned.get("gender") or "").title()
                religion = str(cleaned.get("religion") or "").title()
                if gender and gender not in {"Male", "Female", "Other"}:
                    errors.append("gender must be Male, Female, or Other")
                if religion and religion not in {"Islam", "Christian", "Other"}:
                    errors.append("religion must be Islam, Christian, or Other")
                cleaned["gender"] = gender or None
                cleaned["religion"] = religion or None

                dob, dob_error = parse_date_of_birth(cleaned.get("date_of_birth"))
                if dob_error:
                    errors.append(dob_error)
                else:
                    cleaned["date_of_birth"] = dob

                if errors:
                    not_created.append({"row": i, **student_data, "errors": errors})
                else:
                    cleaned["row"] = i
                    cleaned["classroom"] = classroom
                    rows_to_create.append(cleaned)

            if not_created:
                return Response(
                    {
                        "error": "No students were imported. Correct every invalid row and upload again.",
                        "not_created": not_created,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not rows_to_create:
                return Response(
                    {"error": "No student data rows were found."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                with transaction.atomic():
                    for student_data in rows_to_create:
                        student = StudentCreationService.create_student(
                            classroom=student_data["classroom"],
                            first_name=student_data["first_name"].title(),
                            last_name=student_data["last_name"].title(),
                            parent_phone=student_data.get("parent_contact") or None,
                            parent_email=student_data["parent_email"].lower() if student_data.get("parent_email") else None,
                            middle_name=(student_data.get("middle_name") or "").title(),
                            gender=student_data.get("gender"),
                            religion=student_data.get("religion"),
                            date_of_birth=student_data.get("date_of_birth"),
                            parent_first_name=(student_data.get("parent_first_name") or "").title(),
                            parent_last_name=(student_data.get("parent_last_name") or "").title(),
                            parent_address=student_data.get("parent_address") or "",
                            actor=request.user,
                            send_invitation=False,
                        )
                        created_students.append(student)
            except Exception as exc:
                return Response(
                    {
                        "error": "No students were imported because the batch could not be completed.",
                        "failed_row": student_data.get("row"),
                        "detail": str(exc),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

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
