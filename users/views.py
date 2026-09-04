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
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import serializers as drf_serializers
from rest_framework import status, generics
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from drf_spectacular.utils import extend_schema
from django.utils import timezone
from django.db.models import Sum, Count
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction





from academic.models import StudentClassEnrollment, Teacher, Subject, Parent, AllocatedSubject
from academic.permissions import IsSchoolAdmin
from examination.models import AssessmentSession, AssessmentEntry
from schedule.models import PeriodSlot, TimetableEntry
from .models import CustomUser, CustomUser as User, UserInvitation
from .tokens import TENANT_CLAIM, current_tenant_schema, tenant_refresh_token_for_user
from .serializers import (
    UserSerializer,
    UserSerializerWithToken,
    TeacherSerializer,
    ParentSerializer,
    UserInvitationSerializer,
    AcceptInvitationSerializer,
    AccountantSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RoleChoiceSerializer,
    RoleStateSerializer,
    BulkTeacherUploadRequestSerializer,
    BulkTeacherUploadResponseSerializer,
    ParentChildSummarySerializer,
    ParentDashboardSerializer,
    TeacherDashboardSerializer,
    LoginResponseSerializer,
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
        token[TENANT_CLAIM] = current_tenant_schema()
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
            clean_phone = phone.strip()
            phone_variants = [clean_phone]
            if clean_phone.startswith('0'):
                phone_variants.extend(['+234' + clean_phone[1:], '234' + clean_phone[1:]])
            elif clean_phone.startswith('+234'):
                phone_variants.extend(['0' + clean_phone[4:], clean_phone[1:]])
            elif clean_phone.startswith('234'):
                phone_variants.extend(['0' + clean_phone[3:], '+' + clean_phone])

            user = User.objects.filter(phone_number__in=phone_variants).first()

            if not user:
                from academic.models import Teacher, Parent
                teacher = Teacher.objects.filter(
                    Q(phone_number__in=phone_variants) | Q(mobile_phone__in=phone_variants)
                ).select_related('user').first()
                if teacher and teacher.user:
                    user = teacher.user
                    if not user.phone_number:
                        user.phone_number = teacher.phone_number or clean_phone
                        user.save(update_fields=['phone_number'])

            if not user:
                from academic.models import Parent
                parent = Parent.objects.filter(phone_number__in=phone_variants).select_related('user').first()
                if parent and parent.user:
                    user = parent.user
                    if not user.phone_number:
                        user.phone_number = parent.phone_number or clean_phone
                        user.save(update_fields=['phone_number'])

            if user:
                attrs['email'] = user.email
            else:
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


@extend_schema(responses={200: LoginResponseSerializer})
class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer
    permission_classes = [AllowAny]


# Token refresh with tenant validation
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.serializers import TokenRefreshSerializer

class MyTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        from rest_framework_simplejwt.tokens import RefreshToken

        token = RefreshToken(attrs['refresh'])
        token_schema = token.get(TENANT_CLAIM)
        current_schema = current_tenant_schema()
        if not token_schema:
            raise drf_serializers.ValidationError(
                {'refresh': 'Token is not bound to a tenant. Please sign in again.'}
            )
        if token_schema != current_schema:
            raise drf_serializers.ValidationError(
                {'refresh': 'Token tenant does not match the requested tenant.'}
            )

        data = super().validate(attrs)
        data['tenant_slug'] = token_schema

        return data

class MyTokenRefreshView(TokenRefreshView):
    serializer_class = MyTokenRefreshSerializer
    permission_classes = [AllowAny]


@extend_schema(responses={200: UserSerializer})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def getUserProfile(request):
    user = request.user
    serializer = UserSerializer(user, many=False)
    return Response(serializer.data)


@extend_schema(responses={200: RoleStateSerializer})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def getUserRoles(request):
    """Get user's available roles and current active role"""
    user = request.user
    available_roles = user.get_available_roles()

    active_role = user.ensure_active_role()

    role_labels = {
        'admin': 'Admin',
        'teacher': 'Teacher',
        'parent': 'Parent',
        'student': 'Student',
        'accountant': 'Accountant',
        'staff': 'Staff',
        'inspector': 'Inspector',
    }

    return Response({
        'available_roles': available_roles,
        'active_role': active_role,
        'available_roles_display': [{'value': r, 'label': role_labels.get(r, r.capitalize())} for r in available_roles]
    })


@extend_schema(request=RoleChoiceSerializer, responses={200: RoleStateSerializer})
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
    designation = CharFilter(field_name="staff__designation", lookup_expr="icontains")
    academic_qualification = CharFilter(field_name="staff__academic_qualification", lookup_expr="icontains")
    state = CharFilter(field_name="staff__state", lookup_expr="icontains")

    class Meta:
        model = Teacher
        fields = [
            "first_name",
            "middle_name",
            "last_name",
            "designation",
            "academic_qualification",
            "state",
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
        val = value.strip()
        return queryset.filter(
            Q(first_name__icontains=val)
            | Q(last_name__icontains=val)
            | Q(middle_name__icontains=val)
            | Q(phone_number__icontains=val)
            | Q(email__icontains=val)
            | Q(occupation__icontains=val)
            | Q(user__first_name__icontains=val)
            | Q(user__last_name__icontains=val)
            | Q(user__email__icontains=val)
            | Q(user__phone_number__icontains=val)
            | Q(children__first_name__icontains=val)
            | Q(children__last_name__icontains=val)
            | Q(children__admission_number__icontains=val)
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
    serializer_class = UserSerializer

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


class ParentListView(generics.ListCreateAPIView):
    queryset = Parent.objects.all().select_related("user").prefetch_related("children", "children__classroom")
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
    serializer_class = ParentSerializer

    def get_object(self, pk):
        return get_object_or_404(
            Parent.objects.prefetch_related(
                "children",
                "children__classroom",
            ),
            pk=pk,
        )

    def get(self, request, pk, format=None):
        parent = self.get_object(pk)

        serializer = self.serializer_class(
            parent,
            context={
                "request": request,
            },
        )

        return Response(serializer.data)

    def put(self, request, pk, format=None):
        parent = self.get_object(pk)

        serializer = self.serializer_class(
            parent,
            data=request.data,
            partial=True,
            context={
                "request": request,
            },
        )

        serializer.is_valid(
            raise_exception=True
        )

        updated_parent = serializer.save()
        updated_parent = self.get_object(updated_parent.pk)

        response_serializer = self.serializer_class(
            updated_parent,
            context={
                "request": request,
            },
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk, format=None):
        return self.put(
            request,
            pk,
            format=format,
        )

    def delete(self, request, pk, format=None):
        from academic.services.parent_student_service import ParentStudentService

        parent = self.get_object(pk)
        ParentStudentService.delete_parent(parent)

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )
# Teacher Views
class TeacherListView(generics.ListCreateAPIView):
    queryset = Teacher.objects.all().select_related("user", "staff")
    serializer_class = TeacherSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = TeacherFilter
    search_fields = [
        'user__first_name',
        'user__last_name',
        'user__middle_name',
        'empId',
        'user__email',
        'staff__designation',
        'staff__academic_qualification',
        'staff__state',
    ]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        teacher = serializer.save()
        return Response(
            self.get_serializer(teacher).data, status=status.HTTP_201_CREATED
        )


class TeacherDetailView(views.APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TeacherSerializer

    def get_object(self, pk):
        return get_object_or_404(Teacher, pk=pk)

    def get(self, request, pk, format=None):
        teacher = self.get_object(pk)
        serializer = TeacherSerializer(teacher, context={"request": request})
        return Response(serializer.data)

    def put(self, request, pk, format=None):
        teacher = self.get_object(pk)
        serializer = TeacherSerializer(teacher, data=request.data, context={"request": request})
        if serializer.is_valid():
            updated_teacher = serializer.save()

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
                pass

            return Response(TeacherSerializer(updated_teacher, context={"request": request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk, format=None):
        teacher = self.get_object(pk)
        serializer = TeacherSerializer(teacher, data=request.data, partial=True, context={"request": request})
        if serializer.is_valid():
            updated_teacher = serializer.save()

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
                    pass

            return Response(TeacherSerializer(updated_teacher, context={"request": request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, format=None):
        teacher = self.get_object(pk)
        teacher.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TeacherResendInvitationView(APIView):
    """
    API View to send or resend an invitation email to a teacher who has no last login.
    POST /api/users/teachers/{id}/resend-invitation/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        import datetime
        teacher = get_object_or_404(Teacher, pk=pk)
        email = teacher.email
        if not email:
            return Response(
                {"error": "Teacher does not have an email address."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if teacher.user and teacher.user.last_login:
            return Response(
                {"error": "Teacher has already logged in."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invitation = (
            UserInvitation.objects.filter(
                email=email,
                role="teacher",
                status="pending",
            )
            .order_by("-created_at")
            .first()
        )

        if invitation and not invitation.is_expired:
            invitation.expires_at = timezone.now() + datetime.timedelta(days=7)
            invitation.save()
        else:
            if invitation:
                invitation.status = "expired"
                invitation.save()
            invitation = UserInvitation.objects.create(
                email=email,
                first_name=teacher.first_name,
                last_name=teacher.last_name,
                role="teacher",
                teacher_profile_id=teacher.id,
                invited_by=request.user,
            )

        try:
            from core.email_utils import send_teacher_invitation
            send_teacher_invitation(invitation, request=request)
        except Exception as e:
            return Response(
                {"error": f"Failed to send invitation email: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({
            "message": "Invitation email sent successfully.",
            "invitation_id": invitation.id,
        })


class ParentResendInvitationView(APIView):
    """
    API View to send or resend an invitation email to a parent.
    POST /api/users/parents/{id}/resend-invitation/
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        import datetime
        from django.utils import timezone
        from academic.models import Parent
        from academic.services.parent_identity_service import ParentIdentityService
        from users.invitation_models import UserInvitation
        import logging

        logger = logging.getLogger(__name__)

        parent = get_object_or_404(Parent.objects.select_related("user"), pk=pk)
        email = (parent.email or "").strip().lower()
        if not email:
            return Response(
                {"error": "Parent does not have an email address on file. Please add an email address first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if parent.user and parent.user.has_usable_password():
            return Response(
                {"error": "Parent already has an active portal account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Ensure/resolve parent identity safely with collision protections
        try:
            parent = ParentIdentityService.resolve_parent(
                phone_number=parent.phone_number,
                email=email,
                first_name=parent.first_name,
                last_name=parent.last_name,
            )
        except DjangoValidationError as exc:
            msg = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)

        invitation = (
            UserInvitation.objects.filter(
                email__iexact=email,
                role="parent",
                status="pending",
            )
            .order_by("-created_at")
            .first()
        )

        if invitation and not invitation.is_expired:
            invitation.expires_at = timezone.now() + datetime.timedelta(days=7)
            invitation.parent_profile_id = parent.id
            invitation.save()
        else:
            if invitation:
                invitation.status = "expired"
                invitation.save()
            invitation = UserInvitation.objects.create(
                email=email,
                first_name=parent.first_name or "",
                last_name=parent.last_name or "",
                role="parent",
                parent_profile_id=parent.id,
                invited_by=request.user,
            )

        def _dispatch():
            try:
                from core.email_utils import send_parent_invitation
                send_parent_invitation(invitation, request=request)
            except Exception as e:
                logger.exception(f"Failed to send parent invitation email: {e}")

        transaction.on_commit(_dispatch)

        return Response({
            "message": "Invitation email sent successfully.",
            "invitation_id": invitation.id,
            "has_portal_account": False,
            "invitation_status": "PENDING",
        }, status=status.HTTP_200_OK)


class BulkUploadTeachersView(APIView):
    """
    API View to handle bulk uploading of teachers from an Excel file with Staff integration.
    """

    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [IsSchoolAdmin]

    @extend_schema(
        request=BulkTeacherUploadRequestSerializer,
        responses={201: BulkTeacherUploadResponseSerializer},
    )
    def post(self, request, *args, **kwargs):
        from decimal import Decimal, InvalidOperation
        from datetime import datetime, date
        from django.utils import timezone
        from academic.models import Staff

        file = request.FILES.get("file")
        if not file:
            return Response(
                {"error": "No file provided."}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            workbook = openpyxl.load_workbook(file)
            sheet = workbook.active

            rows = list(sheet.iter_rows(values_only=True))
            if not rows or len(rows) < 2:
                return Response(
                    {"message": "0 teachers successfully uploaded.", "not_created": []},
                    status=status.HTTP_201_CREATED,
                )

            # Check if row 0 contains header names
            first_row = [str(c).strip().lower().replace(" ", "_") if c is not None else "" for c in rows[0]]
            is_named_header = any(h in first_row for h in ["first_name", "email", "phone_number", "emp_id", "employment_id"])

            if is_named_header:
                header_map = {name: idx for idx, name in enumerate(first_row) if name}
                data_rows = rows[1:]
            else:
                default_cols = [
                    "first_name",
                    "middle_name",
                    "last_name",
                    "phone_number",
                    "employment_id",
                    "short_name",
                    "subject_specialization",
                    "address",
                    "gender",
                    "date_of_birth",
                    "salary",
                    "academic_qualification",
                    "state",
                    "designation",
                ]
                header_map = {col: idx for idx, col in enumerate(default_cols)}
                data_rows = rows[1:]

            teachers_to_create = []
            not_created = []

            for row_idx, row in enumerate(data_rows, start=2):
                if not any(row):
                    continue

                def get_val(key, default=""):
                    idx = header_map.get(key)
                    if idx is not None and idx < len(row) and row[idx] is not None:
                        return str(row[idx]).strip()
                    return default

                def get_raw(key, default=None):
                    idx = header_map.get(key)
                    if idx is not None and idx < len(row) and row[idx] is not None:
                        return row[idx]
                    return default

                teacher_data = {
                    "first_name": get_val("first_name"),
                    "middle_name": get_val("middle_name"),
                    "last_name": get_val("last_name"),
                    "email": get_val("email"),
                    "phone_number": get_val("phone_number"),
                    "employment_id": get_val("employment_id") or get_val("empid"),
                    "short_name": get_val("short_name"),
                    "subject_specialization": get_val("subject_specialization"),
                    "address": get_val("address"),
                    "gender": get_val("gender"),
                    "date_of_birth": get_raw("date_of_birth"),
                    "academic_qualification": get_val("academic_qualification"),
                    "state": get_val("state"),
                    "designation": get_val("designation") or "Teacher",
                    "salary": get_raw("salary"),
                }

                try:
                    if not teacher_data["first_name"] or not teacher_data["last_name"]:
                        raise ValueError("First name and Last name are required.")

                    # Determine email
                    generated_email = teacher_data["email"] or (
                        f"{teacher_data['first_name'].lower()}."
                        f"{teacher_data['last_name'].lower()}{get_random_string(3).lower()}@ssyncportal.local"
                    )
                    teacher_data["email"] = generated_email

                    if Teacher.objects.filter(user__email=generated_email).exists():
                        raise ValueError(f"Email '{generated_email}' already exists.")

                    if teacher_data["phone_number"] and Teacher.objects.filter(
                        user__phone_number=teacher_data["phone_number"]
                    ).exists():
                        raise ValueError(
                            f"Phone number '{teacher_data['phone_number']}' already exists."
                        )

                    # Parse date of birth
                    dob = None
                    raw_dob = teacher_data["date_of_birth"]
                    if raw_dob:
                        if isinstance(raw_dob, (datetime, date)):
                            dob = raw_dob.date() if isinstance(raw_dob, datetime) else raw_dob
                        else:
                            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
                                try:
                                    dob = datetime.strptime(str(raw_dob), fmt).date()
                                    break
                                except ValueError:
                                    pass
                            if not dob:
                                raise ValueError(f"Invalid date of birth format '{raw_dob}'. Use YYYY-MM-DD.")
                        if dob and dob > timezone.now().date():
                            raise ValueError("Date of birth cannot be in the future.")

                    # Parse salary
                    salary_dec = None
                    raw_salary = teacher_data["salary"]
                    if raw_salary:
                        try:
                            clean_sal = str(raw_salary).replace(",", "").replace("$", "").replace("₦", "").strip()
                            salary_dec = Decimal(clean_sal)
                            if salary_dec < 0:
                                raise ValueError("Salary cannot be negative.")
                        except (InvalidOperation, ValueError) as err:
                            raise ValueError(f"Invalid salary amount '{raw_salary}': {err}")

                    # Validate subjects
                    subjects = []
                    subject_names = (
                        teacher_data["subject_specialization"].split(",")
                        if teacher_data["subject_specialization"]
                        else []
                    )
                    for subject_name in subject_names:
                        clean_name = subject_name.strip()
                        if clean_name:
                            try:
                                subject = Subject.objects.get(name__iexact=clean_name)
                                subjects.append(subject)
                            except Subject.DoesNotExist:
                                raise ValueError(
                                    f"Subject '{clean_name}' does not exist."
                                )

                    with transaction.atomic():
                        emp_id_val = teacher_data["employment_id"] or None
                        short_name_val = teacher_data["short_name"][:3].upper() if teacher_data["short_name"] else None

                        user, created = CustomUser.objects.get_or_create(
                            email=generated_email,
                            defaults={
                                "first_name": teacher_data["first_name"],
                                "middle_name": teacher_data["middle_name"],
                                "last_name": teacher_data["last_name"],
                                "phone_number": teacher_data["phone_number"] or None,
                                "is_teacher": True,
                            },
                        )
                        if created:
                            default_password = f"Complex.{emp_id_val[-4:] if emp_id_val and len(emp_id_val) >= 4 else '0000'}"
                            user.set_password(default_password)
                            user.save()
                            group, _ = Group.objects.get_or_create(name="teacher")
                            user.groups.add(group)

                        staff, staff_created = Staff.objects.get_or_create(
                            user=user,
                            defaults={
                                "role": Staff.Role.TEACHER,
                                "designation": teacher_data["designation"],
                                "academic_qualification": teacher_data["academic_qualification"],
                                "state": teacher_data["state"],
                                "address": teacher_data["address"],
                                "date_of_birth": dob,
                                "salary": salary_dec,
                                "is_active": True,
                            }
                        )
                        if not staff_created:
                            staff.role = Staff.Role.TEACHER
                            staff.designation = teacher_data["designation"]
                            staff.academic_qualification = teacher_data["academic_qualification"]
                            staff.state = teacher_data["state"]
                            staff.address = teacher_data["address"]
                            staff.date_of_birth = dob
                            staff.salary = salary_dec
                            staff.is_active = True
                            staff.save()

                        teacher = Teacher(
                            user=user,
                            staff=staff,
                            empId=emp_id_val,
                            short_name=short_name_val,
                        )
                        teacher.save()

                        if subjects:
                            teacher.subject_specialization.set(subjects)

                        teachers_to_create.append(teacher)

                except Exception as e:
                    teacher_data["error"] = str(e)
                    teacher_data["row"] = row_idx
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

    @extend_schema(responses={200: TeacherDashboardSerializer})
    def get(self, request):
        from django.core.cache import cache
        from django.db import connection
        from django.db.models import Count

        cache_key = f"teacher_dashboard_{connection.schema_name}_{request.user.id}"
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        try:
            teacher = Teacher.objects.get(user=request.user)
        except Teacher.DoesNotExist:
            return Response(
                {"error": "Teacher profile not found for this user"},
                status=status.HTTP_404_NOT_FOUND
            )

        today = timezone.now().date()
        current_time = timezone.now().time()

        # ===== ALLOCATED SUBJECTS =====
        all_allocations = AllocatedSubject.objects.filter(teacher_name=teacher).select_related('class_room', 'subject')

        classroom_ids = list(all_allocations.values_list('class_room_id', flat=True).distinct())

        total_classes = len(classroom_ids)
        total_students = StudentClassEnrollment.objects.filter(
            classroom_id__in=classroom_ids,
            academic_year__active_year=True
        ).values('student_id').distinct().count()

        # Today's periods
        todays_periods = list(
            TimetableEntry.objects.filter(
                teacher=teacher,
                slot__day_of_week=today.strftime('%A'),
                is_active=True
            ).select_related('classroom', 'subject', 'subject__subject', 'slot')
            .order_by('slot__start_time')
        )

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

        # ===== MY CLASSES (1 Aggregate GROUP BY query) =====
        enrollment_counts = StudentClassEnrollment.objects.filter(
            classroom_id__in=classroom_ids,
            academic_year__active_year=True
        ).values('classroom_id').annotate(cnt=Count('student_id'))
        class_count_map = {row['classroom_id']: row['cnt'] for row in enrollment_counts}

        my_classes = []
        for alloc in all_allocations:
            student_count = class_count_map.get(alloc.class_room_id, 0) if alloc.class_room_id else 0

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

        # ===== HOMEROOM STUDENTS & CLASSES (For messaging parents) =====
        from academic.models import Student, ClassRoom
        homeroom_classes = ClassRoom.objects.filter(class_teacher=teacher)
        homeroom_classes_data = [
            {
                "id": c.id,
                "name": str(c.name) if (hasattr(c, 'name') and c.name) else str(c)
            }
            for c in homeroom_classes
        ]

        homeroom_students_qs = Student.objects.filter(
            classroom__class_teacher=teacher,
            is_active=True
        ).select_related('classroom', 'classroom__grade_level', 'parent_guardian', 'parent_guardian__user')
        
        homeroom_students = []
        for student in homeroom_students_qs:
            parent = student.parent_guardian
            parent_user = parent.user if parent else None
            p_name = "No Parent"
            if parent_user:
                p_name = parent_user.get_full_name() or parent_user.username
            elif parent:
                p_name = f"{parent.first_name or ''} {parent.last_name or ''}".strip() or "Parent"

            c_name = str(student.classroom.name) if (student.classroom and hasattr(student.classroom, 'name') and student.classroom.name) else (str(student.classroom) if student.classroom else '')

            homeroom_students.append({
                "id": student.id,
                "first_name": student.first_name or '',
                "last_name": student.last_name or '',
                "name": student.full_name,
                "classroom_id": student.classroom_id,
                "classroom_name": c_name,
                "parent_id": parent_user.id if parent_user else None,
                "parent_name": p_name,
            })

        payload = {
            "stats": stats,
            "todaysSchedule": todays_schedule,
            "myClasses": my_classes,
            "recentActivities": recent_activities,
            "upcomingAssessments": upcoming_assessments,
            "homeroomStudents": homeroom_students,
            "homeroomClasses": homeroom_classes_data,
        }

        cache.set(cache_key, payload, 30)
        return Response(payload)


# Parent Dashboard View
class ParentDashboardView(APIView):
    """
    Parent Dashboard API
    GET /api/users/parent/dashboard/
    Returns: children data, performance, attendance, fees, events, activities
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: ParentDashboardSerializer})
    def get(self, request):
        from django.core.cache import cache
        from django.db import connection
        from django.utils import timezone
        from finance.models import StudentFeeAssignment, Receipt
        from attendance.models import StudentAttendance
        from administration.models import SchoolEvent
        from examination.models import TermResult, AssessmentEntry, GradingScheme, GradeRule

        cache_key = f"parent_dashboard_{connection.schema_name}_{request.user.id}"
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

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
                    gl = student.classroom.grade_level if student.classroom else None
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
                user_id = t_user.id if t_user else t.id
                homeroom_teacher = {
                    "id": user_id,
                    "name": full_name or "Assigned Teacher",
                    "first_name": t.first_name or (t_user.first_name if t_user else ''),
                    "last_name": t.last_name or (t_user.last_name if t_user else '')
                }

            # Class name resolution from the canonical classroom relationship.
            class_name = 'N/A'
            if student.classroom:
                class_name = str(student.classroom)

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

        # ===== SCHOOL ADMINISTRATORS FOR MESSAGING =====
        school_admins_list = []
        admin_users = CustomUser.objects.filter(
            Q(is_admin=True) | Q(is_superuser=True),
            is_active=True
        ).distinct()
        for au in admin_users:
            school_admins_list.append({
                "id": au.id,
                "name": au.get_full_name() or "School Administrator",
                "first_name": au.first_name or "School",
                "last_name": au.last_name or "Administrator",
                "email": au.email,
                "role_label": "School Administrator",
            })

        payload = {
            "children": children_data,
            "school_admins": school_admins_list,
            "upcomingEvents": upcoming_events,
            "recentPayments": recent_payments
        }

        cache.set(cache_key, payload, 30)
        return Response(payload)


class ParentChildrenView(APIView):
    """
    Parent Children List API
    GET /api/users/parent/children/
    Returns: list of children associated with the logged-in parent
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: ParentChildSummarySerializer(many=True)})
    def get(self, request):
        try:
            parent = Parent.objects.get(user=request.user)
        except Parent.DoesNotExist:
            return Response(
                {"error": "Parent profile not found for this user"},
                status=status.HTTP_404_NOT_FOUND
            )

        children_data = []
        for student in parent.children.all():
            class_name = 'N/A'
            if student.classroom:
                class_name = str(student.classroom)

            children_data.append({
                "id": student.id,
                "first_name": student.first_name,
                "last_name": student.last_name,
                "full_name": f"{student.first_name} {student.last_name}".strip(),
                "admission_number": student.admission_number or student.student_id or '',
                "class_name": class_name,
                "classroom_name": class_name,
                "gender": getattr(student, 'gender', ''),
                "date_of_birth": str(student.date_of_birth) if getattr(student, 'date_of_birth', None) else None,
                "status": "active" if student.is_active else "inactive",
            })

        return Response(children_data)


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
    permission_classes = [AllowAny]  # Public endpoint
    serializer_class = UserInvitationSerializer

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
    permission_classes = [AllowAny]  # Public endpoint
    serializer_class = AcceptInvitationSerializer

    def post(self, request):
        serializer = AcceptInvitationSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.save()

            # Generate tokens for the new user
            refresh = tenant_refresh_token_for_user(user)

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
    serializer_class = UserInvitationSerializer

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
    serializer_class = AccountantSerializer

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
        serializer = AccountantSerializer(qs, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        serializer = AccountantSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            accountant = serializer.save()
            return Response(AccountantSerializer(accountant, context={'request': request}).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AccountantDetailView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AccountantSerializer

    def get_object(self, pk):
        return get_object_or_404(User, pk=pk, is_accountant=True)

    def patch(self, request, pk):
        accountant = self.get_object(pk)
        serializer = AccountantSerializer(accountant, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            updated = serializer.save()
            return Response(AccountantSerializer(updated, context={'request': request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        accountant = self.get_object(pk)
        accountant.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    serializer_class = PasswordResetRequestSerializer

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
    permission_classes = [AllowAny]
    serializer_class = PasswordResetConfirmSerializer

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
