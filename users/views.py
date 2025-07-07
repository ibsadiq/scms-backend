import openpyxl
from django.db.models import Q
from django.contrib.auth.models import Group
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import FilterSet, CharFilter, DjangoFilterBackend
from rest_framework import viewsets, views
from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from academic.models import Teacher, Subject, Parent
from .models import CustomUser as User, Accountant
from .serializers import (
    UserSerializer,
    UserSerializerWithToken,
    AccountantSerializer,
    TeacherSerializer,
    ParentSerializer,
)


# Custom Token View
class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        user_data = UserSerializerWithToken(self.user).data
        data.update(user_data)
        return data


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def getUserProfile(request):
    user = request.user
    serializer = UserSerializer(user, many=False)
    return Response(serializer.data)


class UserFilter(FilterSet):
    first_name = CharFilter(field_name="first_name", lookup_expr="icontains")
    middle_name = CharFilter(field_name="middle_name", lookup_expr="icontains")
    last_name = CharFilter(field_name="last_name", lookup_expr="icontains")

    class Meta:
        model = User
        fields = [
            "first_name",
            "middle_name",
            "last_name",
        ]


class TeacherFilter(FilterSet):
    first_name = CharFilter(field_name="first_name", lookup_expr="icontains")
    middle_name = CharFilter(field_name="middle_name", lookup_expr="icontains")
    last_name = CharFilter(field_name="last_name", lookup_expr="icontains")

    class Meta:
        model = Teacher
        fields = [
            "first_name",
            "middle_name",
            "last_name",
        ]


class ParentFilter(FilterSet):
    first_name = CharFilter(field_name="first_name", lookup_expr="icontains")
    middle_name = CharFilter(field_name="middle_name", lookup_expr="icontains")
    last_name = CharFilter(field_name="last_name", lookup_expr="icontains")

    class Meta:
        model = Parent
        fields = [
            "first_name",
            "middle_name",
            "last_name",
        ]


class UserListView(generics.ListCreateAPIView):
    serializer_class = UserSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = UserFilter

    def get_queryset(self):
        return User.objects.filter(is_parent=False)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(self.get_serializer(user).data, status=status.HTTP_201_CREATED)


class UserDetailView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return User.objects.get(pk=pk)
        except User.DoesNotExist:
            raise Http404

    def get(self, request, pk, format=None):
        user = self.get_object(pk)
        print(user)
        serializer = UserSerializer(user)
        return Response(serializer.data)

    def put(self, request, pk, format=None):
        user = self.get_object(pk)
        serializer = UserSerializer(user, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, format=None):
        user = self.get_object(pk)
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AccountantListView(APIView):
    """
    API View for handling single and listing accountants.
    """

    def get(self, request, format=None):
        accountants = Accountant.objects.all()
        serializer = AccountantSerializer(accountants, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, format=None):
        serializer = AccountantSerializer(data=request.data)
        if serializer.is_valid():
            accountant = serializer.save()
            return Response(
                AccountantSerializer(accountant).data, status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AccountantDetailView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(Accountant, pk=pk)

    def get(self, request, pk, format=None):
        accountant = self.get_object(pk)
        serializer = AccountantSerializer(accountant)
        return Response(serializer.data)

    def put(self, request, pk, format=None):
        accountant = self.get_object(pk)
        serializer = AccountantSerializer(accountant, data=request.data)
        if serializer.is_valid():
            updated_accountant = serializer.save()

            # Update the linked CustomUser when accountant details change
            email = updated_accountant.email
            first_name = updated_accountant.first_name
            last_name = updated_accountant.last_name

            try:
                user = User.objects.get(email=accountant.email)
                user.email = email
                user.first_name = first_name
                user.last_name = last_name
                user.save()
            except User.DoesNotExist:
                pass  # If user does not exist, no update is needed

            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, format=None):
        accountant = self.get_object(pk)
        accountant.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ParentListView(generics.ListCreateAPIView):
    queryset = Parent.objects.all()
    serializer_class = ParentSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ParentFilter

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        parent = serializer.save()
        return Response(
            self.get_serializer(parent).data, status=status.HTTP_201_CREATED
        )


class ParentDetailView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(Parent, pk=pk)

    def get(self, request, pk, format=None):
        parent = self.get_object(pk)
        serializer = ParentSerializer(parent)
        return Response(serializer.data)

    def put(self, request, pk, format=None):
        parent = self.get_object(pk)
        serializer = ParentSerializer(parent, data=request.data)
        if serializer.is_valid():
            updated_parent = serializer.save()

            # Update the linked CustomUser when parent details change
            email = updated_parent.email
            first_name = updated_parent.first_name
            last_name = updated_parent.last_name

            try:
                user = User.objects.get(email=parent.email)
                user.email = email
                user.first_name = first_name
                user.last_name = last_name
                user.save()
            except User.DoesNotExist:
                pass  # If user does not exist, no update is needed

            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, format=None):
        parent = self.get_object(pk)
        parent.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# Teacher Views
class TeacherListView(generics.ListCreateAPIView):
    queryset = Teacher.objects.all()
    serializer_class = TeacherSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = TeacherFilter

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        teacher = serializer.save()
        return Response(
            self.get_serializer(teacher).data, status=status.HTTP_201_CREATED
        )


class TeacherDetailView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(Teacher, pk=pk)

    def get(self, request, pk, format=None):
        teacher = self.get_object(pk)
        serializer = TeacherSerializer(teacher)
        return Response(serializer.data)

    def put(self, request, pk, format=None):
        teacher = self.get_object(pk)
        serializer = TeacherSerializer(teacher, data=request.data)
        if serializer.is_valid():
            updated_teacher = serializer.save()

            # Update the linked CustomUser when teacher details change
            email = updated_teacher.email
            first_name = updated_teacher.first_name
            last_name = updated_teacher.last_name

            try:
                user = User.objects.get(email=teacher.email)
                user.email = email
                user.first_name = first_name
                user.last_name = last_name
                user.save()
            except User.DoesNotExist:
                pass  # If user does not exist, no update is needed

            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, format=None):
        teacher = self.get_object(pk)
        teacher.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BulkUploadTeachersView(APIView):
    """
    API View to handle bulk uploading of teachers from an Excel file.
    """

    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        file = request.FILES.get("file")
        if not file:
            return Response(
                {"error": "No file provided."}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Load the Excel file
            workbook = openpyxl.load_workbook(file)
            sheet = workbook.active  # Assuming data is in the first sheet

            # Expected columns in the Excel file
            columns = [
                "first_name",
                "middle_name",
                "last_name",
                "phone_number",
                "employment_id",
                "short_name",
                "subject_specialization",  # Should match subject names as a comma-separated string
                "address",
                "gender",
                "date_of_birth",
                "salary",
            ]

            teachers_to_create = []
            not_created = []

            for i, row in enumerate(
                sheet.iter_rows(min_row=2, values_only=True), start=2
            ):
                # Map row data to the expected columns
                teacher_data = dict(zip(columns, row))

                try:
                    # Generate email based on first_name and last_name
                    generated_email = (
                        f"{teacher_data['first_name'].lower()}."
                        f"{teacher_data['last_name'].lower()}@hayatul.com"
                    )
                    teacher_data["email"] = generated_email

                    # Check for duplicate email
                    if Teacher.objects.filter(email=generated_email).exists():
                        raise ValueError(f"Email '{generated_email}' already exists.")

                    # Check for duplicate phone number
                    if Teacher.objects.filter(
                        phone_number=teacher_data["phone_number"]
                    ).exists():
                        raise ValueError(
                            f"Phone number '{teacher_data['phone_number']}' already exists."
                        )

                    # Validate subject specialization
                    subjects = []
                    subject_names = (
                        teacher_data["subject_specialization"].lower().split(",")
                        if teacher_data["subject_specialization"].lower()
                        else []
                    )
                    for subject_name in subject_names:
                        try:
                            subject = Subject.objects.get(name=subject_name.strip())
                            subjects.append(subject)
                        except Subject.DoesNotExist:
                            raise ValueError(
                                f"Subject '{subject_name.strip()}' does not exist."
                            )

                    # Create Teacher object
                    teacher = Teacher(
                        first_name=teacher_data["first_name"].lower(),
                        middle_name=teacher_data["middle_name"].lower(),
                        last_name=teacher_data["last_name"].lower(),
                        email=generated_email,
                        short_name=teacher_data["short_name"].upper(),
                        phone_number=teacher_data["phone_number"],
                        empId=teacher_data["employment_id"],
                        address=teacher_data["address"].lower(),
                        gender=teacher_data["gender"],
                        date_of_birth=teacher_data["date_of_birth"],
                        salary=teacher_data["salary"],
                    )
                    teacher.save()

                    # Assign subjects
                    if subjects:
                        teacher.subject_specialization.set(subjects)

                    # Create corresponding user
                    if not teacher.username:
                        teacher.username = f"{teacher.first_name.lower()}{teacher.last_name.lower()}{get_random_string(4)}"
                    teacher.save()

                    user, created = User.objects.get_or_create(
                        email=teacher.email,
                        defaults={
                            "first_name": teacher.first_name,
                            "last_name": teacher.last_name,
                            "is_teacher": True,
                        },
                    )
                    if created:
                        default_password = f"Complex.{teacher.empId[-4:] if teacher.empId and len(teacher.empId) >= 4 else '0000'}"
                        user.set_password(default_password)
                        user.save()

                        # Add to "teacher" group
                        group, _ = Group.objects.get_or_create(name="teacher")
                        user.groups.add(group)

                    teachers_to_create.append(teacher)

                except Exception as e:
                    # Add row data and error message to the not_created list
                    teacher_data["error"] = str(e)
                    not_created.append(teacher_data)

            return Response(
                {
                    "message": f"{len(teachers_to_create)} teachers successfully uploaded.",
                    "not_created": not_created,
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
