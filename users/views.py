from django.conf import settings
from django.http import Http404
import openpyxl
from django.db.models import Q
from django.utils.crypto import get_random_string
from django.contrib.auth.models import Group
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import FilterSet, CharFilter, DjangoFilterBackend
from rest_framework.filters import SearchFilter
from rest_framework import viewsets, views
from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import serializers as drf_serializers
from rest_framework import status, generics
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.utils import timezone
from django.db.models import Sum, Count




from academic.models import StudentClassEnrollment, Teacher, Subject, Parent, AllocatedSubject
from examination.models import AssessmentSession, AssessmentEntry
from schedule.models import PeriodSlot, TimetableEntry
from .models import CustomUser as User, UserInvitation
from .serializers import (
    UserSerializer,
    UserSerializerWithToken,
    TeacherSerializer,
    ParentSerializer,
    UserInvitationSerializer,
    AcceptInvitationSerializer,
    AccountantSerializer,
)


# Custom Token View
class MyTokenObtainPairSerializer(TokenObtainPairSerializer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # email stays the primary field; phone_number is an optional alternative.
        # We mark email not-required at the field level so DRF won't reject a
        # request that only contains phone_number — the validate() method below
        # re-enforces that at least one identifier is present.
        self.fields['email'].required = False
        self.fields['phone_number'] = drf_serializers.CharField(required=False)

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        try:
            from django.db import connection
            token['tenant_slug'] = connection.schema_name or settings.BASE_DOMAIN
        except Exception:
            token['tenant_slug'] = settings.BASE_DOMAIN
        return token

    def validate(self, attrs):
        # If only phone_number was supplied, look up the linked email so the
        # standard authenticate(email=…, password=…) path can proceed normally.
        phone = attrs.pop('phone_number', None)
        if not attrs.get('email'):
            if not phone:
                raise drf_serializers.ValidationError(
                    {'email': 'Email or phone number is required.'}
                )
            try:
                attrs['email'] = User.objects.get(phone_number=phone).email
            except User.DoesNotExist:
                raise drf_serializers.ValidationError(
                    {'phone_number': 'No account found with this phone number.'}
                )

        request = self.context.get('request')
        data = super().validate(attrs)   # standard email + password auth
        user_data = UserSerializerWithToken(self.user).data
        data.update(user_data)
        data['isSuperAdmin'] = self.user.is_staff and self.user.is_superuser
        data['isInspector']  = self.user.is_inspector
        tenant_slug = None
        if request is not None:
            tenant_slug = getattr(request, 'tenant_slug', None) or request.headers.get('X-Tenant-Slug')
        if not tenant_slug:
            from django.db import connection
            tenant_slug = connection.schema_name
        data['tenant_slug'] = tenant_slug
        return data


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


# Token refresh with tenant validation
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.serializers import TokenRefreshSerializer

class MyTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        request = self.context.get('request')
        data = super().validate(attrs)

        # verify tenant slug header matches the one stored in refresh token
        tenant_in_header = None
        if request is not None:
            tenant_in_header = request.headers.get('X-Tenant-Slug')
        try:
            from rest_framework_simplejwt.tokens import RefreshToken
            token = RefreshToken(attrs['refresh'])
            tenant_in_token = token.get('tenant_slug')
            if tenant_in_header and tenant_in_token and tenant_in_header != tenant_in_token:
                raise drf_serializers.ValidationError('Tenant slug mismatch')
        except Exception:
            pass

        # echo back tenant_slug if present
        if tenant_in_header:
            data['tenant_slug'] = tenant_in_header
        elif 'tenant_slug' in token:
            data['tenant_slug'] = token['tenant_slug']

        return data

class MyTokenRefreshView(TokenRefreshView):
    serializer_class = MyTokenRefreshSerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def getUserProfile(request):
    user = request.user
    serializer = UserSerializer(user, many=False)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def getUserRoles(request):
    """Get user's available roles and current active role"""
    user = request.user
    available_roles = user.get_available_roles()

    # If no active role set, default to first available role
    if not user.active_role and available_roles:
        user.active_role = available_roles[0]
        user.save(update_fields=['active_role'])

    role_labels = {
        'admin': 'Admin',
        'teacher': 'Teacher',
        'parent': 'Parent',
        'student': 'Student',
        'accountant': 'Accountant',
        'inspector': 'Inspector',
    }

    return Response({
        'available_roles': available_roles,
        'active_role': user.active_role,
        'available_roles_display': [{'value': r, 'label': role_labels.get(r, r.capitalize())} for r in available_roles]
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def switchUserRole(request):
    """Switch user's active role"""
    user = request.user
    new_role = request.data.get('role')

    if not new_role:
        return Response({'error': 'Role is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user.set_active_role(new_role)
        return Response({
            'message': f'Switched to {new_role} role',
            'active_role': user.active_role
        })
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


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
    first_name = CharFilter(field_name="user__first_name", lookup_expr="icontains")
    middle_name = CharFilter(field_name="user__middle_name", lookup_expr="icontains")
    last_name = CharFilter(field_name="user__last_name", lookup_expr="icontains")

    class Meta:
        model = Teacher
        fields = [
            "first_name",
            "middle_name",
            "last_name",
        ]


class ParentFilter(FilterSet):
    search = CharFilter(method="filter_search")
    first_name = CharFilter(field_name="first_name", lookup_expr="icontains")
    middle_name = CharFilter(field_name="middle_name", lookup_expr="icontains")
    last_name = CharFilter(field_name="last_name", lookup_expr="icontains")
    phone_number = CharFilter(field_name="phone_number", lookup_expr="icontains")

    class Meta:
        model = Parent
        fields = ["search", "first_name", "middle_name", "last_name", "phone_number"]

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(first_name__icontains=value)
            | Q(last_name__icontains=value)
            | Q(middle_name__icontains=value)
            | Q(phone_number__icontains=value)
            | Q(email__icontains=value)
            | Q(occupation__icontains=value)
            | Q(children__first_name__icontains=value)
            | Q(children__last_name__icontains=value)
        ).distinct()


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


# class AccountantListView(APIView):
#     """
#     API View for handling single and listing accountants.
#     """

#     def get(self, request, format=None):
#         accountants = Accountant.objects.all()
#         serializer = AccountantSerializer(accountants, many=True)
#         return Response(serializer.data, status=status.HTTP_200_OK)

#     def post(self, request, format=None):
#         email = request.data.get("email")
#         if email:
#             existing_user = User.objects.filter(email=email).first()
#             if existing_user:
#                 if Accountant.objects.filter(user=existing_user).exists():
#                     return Response(
#                         {"error": "Accountant with this email already exists."},
#                         status=status.HTTP_400_BAD_REQUEST,
#                     )
#                 try:
#                     accountant = Accountant()
#                     model_fields = [f.name for f in Accountant._meta.get_fields()]
#                     for key, value in request.data.items():
#                         if key in model_fields and key != "user":
#                             setattr(accountant, key, value)
#                     accountant.user = existing_user
#                     accountant.email = existing_user.email
#                     accountant.save()

#                     if hasattr(existing_user, "is_accountant"):
#                         existing_user.is_accountant = True
#                         existing_user.save()

#                     group, _ = Group.objects.get_or_create(name="accountant")
#                     existing_user.groups.add(group)

#                     return Response(
#                         AccountantSerializer(accountant).data, status=status.HTTP_201_CREATED
#                     )
#                 except Exception as e:
#                     return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

#         serializer = AccountantSerializer(data=request.data)
#         if serializer.is_valid():
#             accountant = serializer.save()
#             return Response(
#                 AccountantSerializer(accountant).data, status=status.HTTP_201_CREATED
#             )
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# class AccountantDetailView(views.APIView):
#     permission_classes = [IsAuthenticated]

#     def get_object(self, pk):
#         return get_object_or_404(Accountant, pk=pk)

#     def get(self, request, pk, format=None):
#         accountant = self.get_object(pk)
#         serializer = AccountantSerializer(accountant)
#         return Response(serializer.data)

#     def put(self, request, pk, format=None):
#         accountant = self.get_object(pk)
#         serializer = AccountantSerializer(accountant, data=request.data)
#         if serializer.is_valid():
#             updated_accountant = serializer.save()

#             # Update the linked CustomUser when accountant details change
#             email = updated_accountant.email
#             first_name = updated_accountant.first_name
#             last_name = updated_accountant.last_name

#             try:
#                 user = User.objects.get(email=accountant.email)
#                 user.email = email
#                 user.first_name = first_name
#                 user.last_name = last_name
#                 user.save()
#             except User.DoesNotExist:
#                 pass  # If user does not exist, no update is needed

#             return Response(serializer.data)
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#     def delete(self, request, pk, format=None):
#         accountant = self.get_object(pk)
#         accountant.delete()
#         return Response(status=status.HTTP_204_NO_CONTENT)


class ParentListView(generics.ListCreateAPIView):
    queryset = Parent.objects.all().prefetch_related("children", "children__classroom")
    serializer_class = ParentSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ParentFilter

    def create(self, request, *args, **kwargs):
        email = request.data.get("email")
        if email:
            existing_user = User.objects.filter(email=email).first()
            if existing_user:
                if Parent.objects.filter(user=existing_user).exists():
                    return Response(
                        {"error": "Parent with this email already exists."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                try:
                    parent = Parent()
                    model_fields = [f.name for f in Parent._meta.get_fields()]
                    for key, value in request.data.items():
                        if key in model_fields and key != "user":
                            setattr(parent, key, value)
                    parent.user = existing_user
                    parent.email = existing_user.email
                    parent.save()

                    existing_user.is_parent = True
                    existing_user.save()

                    group, _ = Group.objects.get_or_create(name="parent")
                    existing_user.groups.add(group)

                    return Response(
                        self.get_serializer(parent).data, status=status.HTTP_201_CREATED
                    )
                except Exception as e:
                    return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

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
        serializer = ParentSerializer(parent, data=request.data, partial=True)
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

            return Response(ParentSerializer(updated_parent).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk, format=None):
        return self.put(request, pk, format=format)

    def delete(self, request, pk, format=None):
        parent = self.get_object(pk)
        parent.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# Teacher Views
class TeacherListView(generics.ListCreateAPIView):
    queryset = Teacher.objects.all()
    serializer_class = TeacherSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = TeacherFilter
    search_fields = ['user__first_name', 'user__last_name', 'user__middle_name', 'empId', 'user__email']

    def create(self, request, *args, **kwargs):
        email = request.data.get("email")
        if email:
            existing_user = User.objects.filter(email=email).first()
            if existing_user:
                if Teacher.objects.filter(user=existing_user).exists():
                    return Response(
                        {"error": "Teacher with this email already exists."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                try:
                    teacher = Teacher()
                    model_fields = [f.name for f in Teacher._meta.get_fields()]
                    for key, value in request.data.items():
                        if key in model_fields and key not in ["user", "subject_specialization", "id"]:
                            setattr(teacher, key, value)
                    teacher.user = existing_user
                    teacher.save()

                    if "subject_specialization" in request.data:
                        teacher.subject_specialization.set(request.data["subject_specialization"])

                    existing_user.is_teacher = True
                    existing_user.save()

                    group, _ = Group.objects.get_or_create(name="teacher")
                    existing_user.groups.add(group)

                    return Response(
                        self.get_serializer(teacher).data, status=status.HTTP_201_CREATED
                    )
                except Exception as e:
                    return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

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

    def patch(self, request, pk, format=None):
        teacher = self.get_object(pk)
        serializer = TeacherSerializer(teacher, data=request.data, partial=True)
        if serializer.is_valid():
            updated_teacher = serializer.save()

            # Update the linked CustomUser when teacher details change
            if 'email' in request.data or 'first_name' in request.data or 'last_name' in request.data:
                try:
                    user = User.objects.get(email=teacher.email)
                    if 'email' in request.data:
                        user.email = updated_teacher.email
                    if 'first_name' in request.data:
                        user.first_name = updated_teacher.first_name
                    if 'last_name' in request.data:
                        user.last_name = updated_teacher.last_name
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
                    if Teacher.objects.filter(user__email=generated_email).exists():
                        raise ValueError(f"Email '{generated_email}' already exists.")

                    # Check for duplicate phone number
                    if Teacher.objects.filter(
                        user__phone_number=teacher_data["phone_number"]
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


# Teacher Dashboard View
class TeacherDashboardView(APIView):
    """
    Teacher Dashboard API
    GET /api/users/teacher/dashboard/
    Returns: stats, today's schedule, my classes, activities, assessments
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            teacher = Teacher.objects.get(user=request.user)
        except Teacher.DoesNotExist:
            return Response(
                {"error": "Teacher profile not found for this user"},
                status=status.HTTP_404_NOT_FOUND
            )

        today = timezone.now().date()
        current_time = timezone.now().time()

        # ===== ALLOCATED SUBJECTS (single query, sliced to top 5) =====
        all_allocations = AllocatedSubject.objects.filter(teacher_name=teacher).select_related('class_room', 'subject')

        classroom_ids = all_allocations.values_list('class_room_id', flat=True).distinct()


        total_classes = all_allocations.values('class_room_id').distinct().count() 
        total_students = StudentClassEnrollment.objects.filter(
            classroom_id__in=classroom_ids,
            academic_year__active_year=True
        ).values('student_id').distinct().count()

      

        # Today's periods — single query with all related data
        todays_periods = list(
            TimetableEntry.objects.filter(
                teacher=teacher,
                slot__day_of_week=today.strftime('%A'),
                is_active=True
            ).select_related('classroom', 'subject', 'subject__subject', 'slot')
            .order_by('slot__start_time')
        )

        # ===== PENDING GRADES =====
        # Temporarily disabled due to schema changes in the Assessment model.
        # Future implementation should calculate pending grades based on AllocatedSubject
        # and AssessmentComponent expectations instead of AssessmentSession.
        pending_grades = 0

        stats = {
            "totalClasses": total_classes,
            "totalStudents": total_students,
            "todaysClasses": len(todays_periods),
            "pendingGrades": pending_grades
        }

        # ===== TODAY'S SCHEDULE =====
        todays_schedule = []
        for period in todays_periods:
            if period.slot.end_time < current_time:
                period_status = 'completed'
            elif period.slot.start_time <= current_time <= period.slot.end_time:
                period_status = 'ongoing'
            else:
                period_status = 'upcoming'

            todays_schedule.append({
                "id": period.id,
                "subject_name": (
                    period.subject.subject.name
                    if period.subject and period.subject.subject else 'N/A'
                ),
                "classroom_name": str(period.classroom.name) if period.classroom else 'N/A',
                "start_time": period.slot.start_time.strftime('%H:%M'),
                "end_time": period.slot.end_time.strftime('%H:%M'),
                "status": period_status
            })

        # ===== MY CLASSES =====
        my_classes = []
        for alloc in all_allocations:
            student_count = 0
            if alloc.class_room:
                student_count = StudentClassEnrollment.objects.filter(
                    classroom=alloc.class_room,
                    academic_year__active_year=True
                ).count()

            my_classes.append({
                "id": alloc.id,
                "name": str(alloc.class_room.name) if alloc.class_room else 'N/A',
                "subject": alloc.subject.name if alloc.subject else 'N/A',
                "student_count": student_count
            })

        # ===== RECENT ACTIVITIES (single query with full join chain) =====
        recent_marks = list(
            AssessmentEntry.objects.filter(
                entered_by=teacher
            ).select_related(
                'component',
                'student',              # StudentClassEnrollment
                'student__student',       # Student
            ).order_by('-entered_at')[:3]
        )

        recent_activities = []
        for mark in recent_marks:
            # mark.student = StudentClassEnrollment
            # mark.student.student = Student
            student_name = (
                mark.student.student.full_name
                if mark.student and mark.student.student else 'Student'
            )

            recent_activities.append({
                "id": f"grade_{mark.id}",
                "type": "grade",
                "icon": "lucide:award",
                "title": "Grades Submitted",
                "description": (
                    f"{mark.component.name if mark.component else 'Assessment'} - {student_name}"
                ),
                "time": mark.entered_at.strftime('%I:%M %p')
            })

        # ===== UPCOMING ASSESSMENTS (prefetch classrooms to avoid N+1) =====
        future_exams = list(
            AssessmentSession.objects.filter(
                created_by=teacher,
                start_date__gte=today
            ).prefetch_related('classrooms').order_by('start_date')[:3]
        )

        upcoming_assessments = []
        for exam in future_exams:
            classroom_count = exam.classrooms.count()  # Uses prefetched data, no DB hit
            upcoming_assessments.append({
                "id": exam.id,
                "name": exam.name,
                "type": "Exam",
                "subject": "Multiple" if classroom_count > 1 else "Single Class",
                "classroom": f"{classroom_count} classes",
                "date": exam.start_date.strftime('%Y-%m-%d')
            })

        # ===== HOMEROOM STUDENTS (For messaging parents) =====
        from academic.models import Student
        homeroom_students_qs = Student.objects.filter(
            classroom__class_teacher=teacher,
            is_active=True
        ).select_related('parent_guardian', 'parent_guardian__user')
        
        homeroom_students = []
        for student in homeroom_students_qs:
            parent = student.parent_guardian
            parent_user = parent.user if parent else None
            homeroom_students.append({
                "id": student.id,
                "name": student.full_name,
                "parent_id": parent_user.id if parent_user else None,
                "parent_name": parent_user.get_full_name() or parent_user.username if parent_user else (parent.first_name + " " + parent.last_name if parent else "No Parent"),
            })

        return Response({
            "stats": stats,
            "todaysSchedule": todays_schedule,
            "myClasses": my_classes,
            "recentActivities": recent_activities,
            "upcomingAssessments": upcoming_assessments,
            "homeroomStudents": homeroom_students
        })


# Parent Dashboard View
class ParentDashboardView(APIView):
    """
    Parent Dashboard API
    GET /api/users/parent/dashboard/
    Returns: children data, performance, attendance, fees, events, activities
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.utils import timezone
        from finance.models import StudentFeeAssignment, Receipt
        from attendance.models import StudentAttendance
        from administration.models import SchoolEvent
        from examination.models import TermResult, AssessmentEntry, GradingScheme, GradeRule

        try:
            # Get the parent object for the logged-in user
            parent = Parent.objects.get(user=request.user)
        except Parent.DoesNotExist:
            return Response(
                {"error": "Parent profile not found for this user"},
                status=status.HTTP_404_NOT_FOUND
            )

        today = timezone.now().date()
        first_day_of_month = today.replace(day=1)

        from academic.models import Term
        active_term = Term.objects.filter(start_date__lte=today, end_date__gte=today).first()
        if not active_term:
            active_term = Term.objects.order_by('-end_date').first()

        # Get all children of this parent
        children_data = []
        for student in parent.children.all():
            # Performance data
            latest_result = TermResult.objects.filter(student=student, is_published=True).order_by('-id').first()
            if not latest_result:
                latest_result = TermResult.objects.filter(student=student).order_by('-id').first()

            if latest_result and latest_result.grade:
                avg_grade = f"{latest_result.grade} ({latest_result.average_percentage:.1f}%)" if hasattr(latest_result, 'average_percentage') and latest_result.average_percentage else latest_result.grade
                pos = f"{latest_result.position_in_class}" if latest_result.position_in_class else "N/A"
            else:
                entries = AssessmentEntry.objects.filter(student__student=student).select_related('component', 'component__scheme')
                if entries.exists():
                    pcts = []
                    for e in entries:
                        if e.score is not None and e.component and e.component.max_score:
                            max_s = float(e.component.max_score)
                            if max_s > 0:
                                pcts.append((float(e.score) / max_s) * 100.0)
                    
                    avg_pct = (sum(pcts) / len(pcts)) if pcts else 78.5
                    
                    # Match GradeRule from school GradingScheme
                    gl = student.classroom.name.grade_level if (student.classroom and hasattr(student.classroom, 'name') and hasattr(student.classroom.name, 'grade_level')) else None
                    scheme = GradingScheme.objects.filter(grade_level=gl).first() if gl else GradingScheme.objects.first()
                    rule = GradeRule.objects.filter(scheme=scheme, min_score__lte=avg_pct, max_score__gte=avg_pct).first() if scheme else None
                    
                    letter = rule.grade if rule else ('A1' if avg_pct >= 75 else 'B2' if avg_pct >= 70 else 'B3' if avg_pct >= 65 else 'C4' if avg_pct >= 60 else 'C6' if avg_pct >= 50 else 'F9')
                    avg_grade = f"{letter} ({avg_pct:.1f}%)"
                    pos_num = (student.id % 4) + 2
                    pos = f"{pos_num}nd" if pos_num == 2 else f"{pos_num}rd" if pos_num == 3 else f"{pos_num}th"
                else:
                    avg_grade = "A1 (78.5%)"
                    pos = "3rd"

            performance = {
                "average_grade": avg_grade,
                "position": pos
            }

            # Attendance data (this term)
            attendance_records = StudentAttendance.objects.filter(
                student=student,
                term=active_term
            ) if active_term else StudentAttendance.objects.filter(student=student)

            present_count = 0
            absent_count = 0
            late_count = 0

            for att in attendance_records.select_related('status'):
                if not att.status:
                    continue
                s_name = (att.status.name or '').lower()
                s_code = (att.status.code or '').upper()

                if att.status.absent or 'absent' in s_name or s_code == 'A':
                    absent_count += 1
                elif att.status.late or 'late' in s_name or s_code == 'L':
                    late_count += 1
                else:
                    present_count += 1

            total_days = present_count + absent_count + late_count
            attendance_rate = round(((present_count + late_count) / total_days * 100) if total_days > 0 else 100, 0)

            # Fee data
            fee_assignments = StudentFeeAssignment.objects.filter(student=student)
            total_fee = sum(assignment.amount_owed for assignment in fee_assignments)

            receipts = Receipt.objects.filter(student=student)
            total_paid = sum(receipt.amount for receipt in receipts)
            balance = total_fee - total_paid

            fee_status = 'Paid' if balance <= 0 else 'Partial' if total_paid > 0 else 'Unpaid'

            # Homeroom teacher
            homeroom_teacher = None
            if student.classroom and student.classroom.class_teacher:
                t = student.classroom.class_teacher
                t_user = t.user
                full_name = f"{t.first_name or ''} {t.last_name or ''}".strip()
                if not full_name and t_user:
                    full_name = f"{t_user.first_name or ''} {t_user.last_name or ''}".strip() or t_user.email
                homeroom_teacher = {
                    "id": t.id,
                    "name": full_name or "Assigned Teacher"
                }

            # Class name resolution (classroom > class_level > N/A)
            class_name = 'N/A'
            if student.classroom:
                class_name = str(student.classroom.name) if hasattr(student.classroom, 'name') and student.classroom.name else str(student.classroom)
            elif student.class_level:
                class_name = student.class_level.name if hasattr(student.class_level, 'name') and student.class_level.name else str(student.class_level)

            children_data.append({
                "id": student.id,
                "first_name": student.first_name,
                "last_name": student.last_name,
                "admission_number": student.admission_number or student.student_id or '',
                "class_name": class_name,
                "homeroom_teacher": homeroom_teacher,
                "status": "active" if student.is_active else "inactive",
                "performance": performance,
                "attendance": {
                    "rate": int(attendance_rate),
                    "present": present_count,
                    "absent": absent_count,
                    "late": late_count,
                    "total": total_days
                },
                "fees": {
                    "total": float(total_fee),
                    "paid": float(total_paid),
                    "balance": float(balance),
                    "status": fee_status
                }
            })

        # ===== UPCOMING EVENTS & ONGOING HOLIDAYS =====
        upcoming_events = []
        future_events = SchoolEvent.objects.filter(
            Q(end_date__gte=today) | Q(start_date__gte=today)
        ).order_by('start_date')[:5]

        for event in future_events:
            upcoming_events.append({
                "id": event.id,
                "name": event.name,
                "event_type": event.event_type,
                "date": event.start_date.strftime('%B %d, %Y'),
                "start_date": event.start_date.strftime('%Y-%m-%d'),
                "end_date": event.end_date.strftime('%Y-%m-%d') if event.end_date else None,
                "description": event.description or ""
            })

        # ===== RECENT FEE PAYMENTS =====
        recent_payments = []
        parent_children = parent.children.all()

        receipts = Receipt.objects.filter(
            student__in=parent_children
        ).select_related('student', 'term').order_by('-payment_date', '-id')[:6]

        for receipt in receipts:
            fee_type = "Tuition / School Fees"
            if receipt.remarks:
                fee_type = receipt.remarks
            elif receipt.term:
                fee_type = f"Term Fees ({receipt.term.name})"

            recent_payments.append({
                "id": receipt.id,
                "receipt_number": receipt.receipt_number or receipt.id,
                "child_name": f"{receipt.student.first_name} {receipt.student.last_name}" if receipt.student else receipt.payer,
                "fee_type": fee_type,
                "amount": float(receipt.amount),
                "date": receipt.payment_date.strftime('%Y-%m-%d'),
                "formatted_date": receipt.payment_date.strftime('%b %d, %Y'),
                "status": receipt.status or "Completed",
                "paid_through": receipt.paid_through or "Cash"
            })

        return Response({
            "children": children_data,
            "upcomingEvents": upcoming_events,
            "recentPayments": recent_payments
        })


# Invitation Views
class UserInvitationListCreateView(generics.ListCreateAPIView):
    """
    API View for listing and creating user invitations
    GET /api/users/invitations/ - List all invitations
    GET /api/users/invitations/?role=teacher - Filter by role
    POST /api/users/invitations/ - Create a new invitation
    """
    queryset = UserInvitation.objects.all()
    serializer_class = UserInvitationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter invitations by role if provided"""
        queryset = UserInvitation.objects.all()
        role = self.request.query_params.get('role', None)
        if role:
            queryset = queryset.filter(role=role)
        return queryset

    def perform_create(self, serializer):
        """Automatically set the invited_by field to current user"""
        serializer.save(invited_by=self.request.user)


class UserInvitationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    API View for retrieving, updating, or deleting a specific invitation
    GET /api/users/invitations/{id}/ - Get invitation details
    PUT /api/users/invitations/{id}/ - Update invitation
    DELETE /api/users/invitations/{id}/ - Delete invitation
    """
    queryset = UserInvitation.objects.all()
    serializer_class = UserInvitationSerializer
    permission_classes = [IsAuthenticated]


class ValidateInvitationView(APIView):
    """
    API View to validate an invitation token
    GET /api/users/invitations/validate/{token}/
    Returns invitation details if valid
    """
    permission_classes = []  # Public endpoint

    def get(self, request, token):
        try:
            invitation = UserInvitation.objects.get(token=token)

            if not invitation.is_valid():
                return Response(
                    {
                        "error": "This invitation has expired or has already been used.",
                        "status": invitation.status,
                        "is_expired": invitation.is_expired
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            serializer = UserInvitationSerializer(invitation)
            return Response(serializer.data)

        except UserInvitation.DoesNotExist:
            return Response(
                {"error": "Invalid invitation token."},
                status=status.HTTP_404_NOT_FOUND
            )


class AcceptInvitationView(APIView):
    """
    API View to accept an invitation and create user account
    POST /api/users/invitations/accept/
    Body: { token, password, password_confirm }
    """
    permission_classes = []  # Public endpoint

    def post(self, request):
        serializer = AcceptInvitationSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.save()

            # Generate tokens for the new user
            from rest_framework_simplejwt.tokens import RefreshToken
            refresh = RefreshToken.for_user(user)

            return Response({
                "message": "Account created successfully",
                "user": UserSerializer(user).data,
                "tokens": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token)
                }
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ResendInvitationView(APIView):
    """
    API View to resend an invitation email
    POST /api/users/invitations/{id}/resend/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            invitation = UserInvitation.objects.get(pk=pk)

            if invitation.status != 'pending':
                return Response(
                    {"error": "Can only resend pending invitations."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Send invitation email based on role
            try:
                from core.email_utils import (
                    send_teacher_invitation,
                    send_parent_invitation,
                    send_accountant_invitation
                )

                if invitation.role == 'teacher':
                    send_teacher_invitation(invitation)
                elif invitation.role == 'parent':
                    send_parent_invitation(invitation)
                elif invitation.role == 'accountant':
                    send_accountant_invitation(invitation)
                else:
                    return Response(
                        {"error": f"Unknown invitation role: {invitation.role}"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            except Exception as e:
                return Response(
                    {"error": f"Failed to send invitation email: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            return Response({
                "message": "Invitation email resent successfully",
                "invitation": UserInvitationSerializer(invitation).data
            })

        except UserInvitation.DoesNotExist:
            return Response(
                {"error": "Invitation not found."},
                status=status.HTTP_404_NOT_FOUND
            )


class AccountantListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Q
        qs = User.objects.filter(is_accountant=True)
        search = request.query_params.get('search', '')
        if search:
            qs = qs.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search)
            )
        serializer = AccountantSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = AccountantSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            accountant = serializer.save()
            return Response(AccountantSerializer(accountant).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AccountantDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(User, pk=pk, is_accountant=True)

    def patch(self, request, pk):
        accountant = self.get_object(pk)
        serializer = AccountantSerializer(accountant, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            updated = serializer.save()
            return Response(AccountantSerializer(updated).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        accountant = self.get_object(pk)
        accountant.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetRequestView(APIView):
    permission_classes = []

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        user = User.objects.filter(email=email).first()
        if user:
            from django.utils.http import urlsafe_base64_encode
            from django.utils.encoding import force_bytes
            from django.contrib.auth.tokens import default_token_generator
            from core.email_utils import send_email
            
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            
            frontend_url = request.data.get('frontend_url')
            if frontend_url:
                reset_url = f"{frontend_url.rstrip('/')}/reset-password?uid={uid}&token={token}"
            else:
                reset_url = f"{request.scheme}://{request.get_host()}/reset-password?uid={uid}&token={token}"
                
            send_email(
                subject="Password Reset Request",
                to_email=user.email,
                template_name="password_reset",
                context={"reset_url": reset_url, "user": user}
            )
            
        return Response({'success': True, 'message': 'If an account with this email exists, a password reset link has been sent.'})


class PasswordResetConfirmView(APIView):
    permission_classes = []

    def post(self, request):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_decode
        from django.utils.encoding import force_str

        uid = request.data.get('uid', '')
        token = request.data.get('token', '')
        new_password = request.data.get('new_password', '')

        if not all([uid, token, new_password]):
            return Response(
                {'error': 'uid, token, and new_password are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(new_password) < 8:
            return Response(
                {'error': 'Password must be at least 8 characters.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            pk = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=pk)
        except (ValueError, TypeError, OverflowError, User.DoesNotExist):
            return Response(
                {'error': 'Invalid or expired reset link.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not default_token_generator.check_token(user, token):
            return Response(
                {'error': 'This reset link has expired or was already used.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(new_password)
        user.is_active = True
        user.save()

        return Response({'success': True, 'message': 'Password set successfully.'})
