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
                "religion",
                "class_level",
                "gender",
            ]

            students_to_create = []
            not_created = []
            created_students = []
            new_parents_created = 0
            updated_students_info = []
            skipped_students = []

            for i, row in enumerate(
                sheet.iter_rows(min_row=2, values_only=True), start=2
            ):
                student_data = dict(zip(columns, row))

                # Normalize names
                first_name = (student_data["first_name"] or "").lower()
                middle_name = (student_data["middle_name"] or "").lower()
                last_name = (student_data["last_name"] or "").lower()

                try:
                    class_level = ClassLevel.objects.get(
                        name=student_data["class_level"]
                    )
                    parent_contact = student_data["parent_contact"]
                    parent = None
                    update_reasons = []

                    if parent_contact:
                        parent, parent_created = Parent.objects.get_or_create(
                            phone_number=parent_contact,
                            defaults={
                                "first_name": middle_name,
                                "last_name": last_name,
                                "email": f"parent_of_{first_name}_{middle_name}_{last_name}@hayatul.com",
                            },
                        )
                        if parent_created:
                            new_parents_created += 1

                    admission_number = student_data["admission_number"]
                    student_exists = Student.objects.filter(
                        admission_number=admission_number
                    ).first()

                    if student_exists:
                        # Track updates to existing students
                        updated = False

                        if not student_exists.parent_guardian and parent:
                            student_exists.parent_guardian = parent
                            update_reasons.append("parent added")
                            updated = True

                        existing_sibling = (
                            Student.objects.filter(parent_contact=parent_contact)
                            .exclude(id=student_exists.id)
                            .first()
                        )
                        if (
                            existing_sibling
                            and not student_exists.siblings.filter(
                                id=existing_sibling.id
                            ).exists()
                        ):
                            student_exists.siblings.add(existing_sibling)
                            existing_sibling.siblings.add(student_exists)
                            update_reasons.append("sibling added")
                            updated = True

                        if updated:
                            student_exists.save()
                            updated_students_info.append(
                                {
                                    "admission_number": admission_number,
                                    "full_name": f"{student_exists.first_name} {student_exists.last_name}",
                                    "reasons": update_reasons,
                                }
                            )
                        else:
                            skipped_students.append(
                                {
                                    "admission_number": admission_number,
                                    "full_name": f"{student_exists.first_name} {student_exists.last_name}",
                                    "reason": "Student already exists and no updates were needed.",
                                }
                            )
                        continue  # Skip creating duplicate

                    # Prepare new student
                    student = Student(
                        first_name=first_name,
                        middle_name=middle_name,
                        last_name=last_name,
                        admission_number=admission_number,
                        parent_contact=parent_contact,
                        religion=student_data["religion"],
                        class_level=class_level,
                        gender=student_data["gender"],
                        parent_guardian=parent,
                    )

                    existing_sibling = Student.objects.filter(
                        parent_contact=parent_contact
                    ).first()
                    students_to_create.append((student, existing_sibling))

                except Exception as e:
                    student_data["error"] = str(e)
                    not_created.append(student_data)

            # Save new students
            with transaction.atomic():
                for student, existing_sibling in students_to_create:
                    student.save()
                    created_students.append(student)

                    if (
                        existing_sibling
                        and not student.siblings.filter(id=existing_sibling.id).exists()
                    ):
                        student.siblings.add(existing_sibling)
                        existing_sibling.siblings.add(student)
                        updated_students_info.append(
                            {
                                "admission_number": student.admission_number,
                                "full_name": f"{student.first_name} {student.last_name}",
                                "reasons": ["sibling added"],
                            }
                        )

            return Response(
                {
                    "message": f"{len(created_students)} students successfully uploaded. {new_parents_created} parents created successfully. ",
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
