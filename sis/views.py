import openpyxl
from django.db import transaction
from django_filters.rest_framework import FilterSet, CharFilter, DjangoFilterBackend
from rest_framework import views
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import status, generics
from django.http import Http404


from academic.models import Student, ClassLevel, Parent
from .serializers import StudentSerializer

# Students filter


class StudentFilter(FilterSet):
    first_name = CharFilter(field_name="first_name", lookup_expr="icontains")
    middle_name = CharFilter(field_name="middle_name", lookup_expr="icontains")
    last_name = CharFilter(field_name="last_name", lookup_expr="icontains")
    class_level = CharFilter(method="filter_by_class_level")

    class Meta:
        model = Student
        fields = ["first_name", "middle_name", "last_name", "class_level"]

    def filter_by_class_level(self, queryset, name, value):
        return queryset.filter(class_level__name__icontains=value)


class StudentListView(generics.ListCreateAPIView):
    queryset = Student.objects.all()
    serializer_class = StudentSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = StudentFilter

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        student = serializer.save()
        return Response(
            self.get_serializer(student).data, status=status.HTTP_201_CREATED
        )


class StudentDetailView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return Student.objects.get(pk=pk)
        except Student.DoesNotExist:
            raise Http404

    def get(self, request, pk, format=None):
        student = self.get_object(pk)
        serializer = StudentSerializer(student)
        return Response(serializer.data)

    def put(self, request, pk, format=None):
        student = self.get_object(pk)
        serializer = StudentSerializer(student, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, format=None):
        student = self.get_object(pk)
        student.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BulkUploadStudentsView(APIView):
    """
    API View to handle bulk uploading of students from an Excel file.
    """

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
                "admission_number",
                "parent_contact",
                "region",
                "city",
                "class_level",
                "gender",
                "date_of_birth",
            ]

            students_to_create = []
            sibling_relationships = []
            not_created = []

            for i, row in enumerate(
                sheet.iter_rows(min_row=2, values_only=True), start=2
            ):
                student_data = dict(zip(columns, row))

                # Normalize name fields
                first_name = (
                    student_data["first_name"].lower()
                    if student_data["first_name"]
                    else ""
                )
                middle_name = (
                    student_data["middle_name"].lower()
                    if student_data["middle_name"]
                    else ""
                )
                last_name = (
                    student_data["last_name"].lower()
                    if student_data["last_name"]
                    else ""
                )

                try:
                    try:
                        class_level = ClassLevel.objects.get(
                            name=student_data["class_level"]
                        )
                    except ClassLevel.DoesNotExist:
                        raise ValueError(
                            f"Class level '{student_data['class_level']}' does not exist."
                        )

                    parent_contact = student_data["parent_contact"]
                    parent = None
                    if parent_contact:
                        parent, _ = Parent.objects.get_or_create(
                            phone_number=parent_contact,
                            defaults={
                                "first_name": middle_name,
                                "last_name": last_name,
                                "email": f"parent_of_{first_name}_{last_name}@hayatul.com",
                            },
                        )

                    if Student.objects.filter(
                        admission_number=student_data["admission_number"]
                    ).exists():
                        raise ValueError(
                            f"Admission number '{student_data['admission_number']}' already exists."
                        )

                    existing_sibling = Student.objects.filter(
                        parent_contact=parent_contact
                    ).first()

                    student = Student(
                        first_name=first_name,
                        middle_name=middle_name,
                        last_name=last_name,
                        admission_number=student_data["admission_number"],
                        parent_contact=parent_contact,
                        region=student_data["region"],
                        city=student_data["city"],
                        class_level=class_level,
                        gender=student_data["gender"],
                        date_of_birth=student_data["date_of_birth"],
                        parent_guardian=parent,
                    )

                    students_to_create.append((student, existing_sibling))

                except Exception as e:
                    student_data["error"] = str(e)
                    not_created.append(student_data)

            created_students = []

            # Save each student individually to allow ID generation
            with transaction.atomic():
                for student, existing_sibling in students_to_create:
                    student.save()
                    created_students.append(student)

                    if existing_sibling:
                        student.siblings.add(existing_sibling)
                        existing_sibling.siblings.add(student)

            return Response(
                {
                    "message": f"{len(created_students)} students successfully uploaded.",
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
