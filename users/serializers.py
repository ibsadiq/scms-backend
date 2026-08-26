from django.db import transaction
from django.contrib.auth.models import Group
from rest_framework import serializers


class RoleChoiceSerializer(serializers.Serializer):
    role = serializers.ChoiceField(
        choices=["admin", "teacher", "parent", "student", "accountant", "staff", "inspector"]
    )


TENANT_ROLE_CHOICES = ["admin", "teacher", "parent", "student", "accountant", "staff"]


class RoleStateSerializer(serializers.Serializer):
    available_roles = serializers.ListField(
        child=serializers.ChoiceField(choices=TENANT_ROLE_CHOICES), required=False
    )
    active_role = serializers.ChoiceField(choices=TENANT_ROLE_CHOICES, allow_null=True)
    available_roles_display = serializers.ListField(required=False)
    message = serializers.CharField(required=False)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    frontend_url = serializers.URLField(required=False)


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)


class SuccessMessageSerializer(serializers.Serializer):
    success = serializers.BooleanField(required=False)
    message = serializers.CharField()


class BulkTeacherUploadRequestSerializer(serializers.Serializer):
    file = serializers.FileField()


class BulkTeacherUploadResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    not_created = serializers.ListField(child=serializers.JSONField())


class TeacherDashboardStatsSerializer(serializers.Serializer):
    totalClasses = serializers.IntegerField()
    totalStudents = serializers.IntegerField()
    todaysClasses = serializers.IntegerField()
    pendingGrades = serializers.IntegerField()


class TeacherScheduleItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    subject_name = serializers.CharField()
    classroom_name = serializers.CharField()
    start_time = serializers.CharField()
    end_time = serializers.CharField()
    status = serializers.ChoiceField(choices=("completed", "ongoing", "upcoming"))


class TeacherClassItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    subject = serializers.CharField()
    student_count = serializers.IntegerField()


class TeacherActivitySerializer(serializers.Serializer):
    id = serializers.CharField()
    type = serializers.CharField()
    icon = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()
    time = serializers.CharField()


class TeacherAssessmentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    type = serializers.CharField()
    subject = serializers.CharField()
    classroom = serializers.CharField()
    date = serializers.DateField()


class HomeroomStudentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    name = serializers.CharField()
    classroom_id = serializers.IntegerField(allow_null=True)
    classroom_name = serializers.CharField()
    parent_id = serializers.IntegerField(allow_null=True)
    parent_name = serializers.CharField()


class HomeroomClassSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class TeacherDashboardSerializer(serializers.Serializer):
    stats = TeacherDashboardStatsSerializer()
    todaysSchedule = TeacherScheduleItemSerializer(many=True)
    myClasses = TeacherClassItemSerializer(many=True)
    recentActivities = TeacherActivitySerializer(many=True)
    upcomingAssessments = TeacherAssessmentSerializer(many=True)
    homeroomStudents = HomeroomStudentSerializer(many=True)
    homeroomClasses = HomeroomClassSerializer(many=True)


class ParentChildPerformanceSerializer(serializers.Serializer):
    average_grade = serializers.CharField()
    position = serializers.CharField()


class ParentChildAttendanceSerializer(serializers.Serializer):
    rate = serializers.IntegerField()
    present = serializers.IntegerField()
    absent = serializers.IntegerField()
    late = serializers.IntegerField()
    total = serializers.IntegerField()


class ParentChildFeeSummarySerializer(serializers.Serializer):
    total = serializers.FloatField()
    paid = serializers.FloatField()
    balance = serializers.FloatField()
    status = serializers.ChoiceField(choices=("Paid", "Partial", "Unpaid"))


class ParentHomeroomTeacherSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()


class ParentDashboardChildSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    admission_number = serializers.CharField()
    class_name = serializers.CharField()
    homeroom_teacher = ParentHomeroomTeacherSerializer(allow_null=True)
    status = serializers.ChoiceField(choices=("active", "inactive"))
    performance = ParentChildPerformanceSerializer()
    attendance = ParentChildAttendanceSerializer()
    fees = ParentChildFeeSummarySerializer()


class ParentSchoolAdminSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.EmailField()
    role_label = serializers.CharField()


class ParentEventSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    event_type = serializers.CharField()
    date = serializers.CharField()
    start_date = serializers.DateField()
    end_date = serializers.DateField(allow_null=True)
    description = serializers.CharField()


class ParentRecentPaymentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    receipt_number = serializers.CharField()
    child_name = serializers.CharField()
    fee_type = serializers.CharField()
    amount = serializers.FloatField()
    date = serializers.DateField()
    formatted_date = serializers.CharField()
    status = serializers.CharField()
    paid_through = serializers.CharField()


class ParentDashboardSerializer(serializers.Serializer):
    children = ParentDashboardChildSerializer(many=True)
    school_admins = ParentSchoolAdminSerializer(many=True)
    upcomingEvents = ParentEventSerializer(many=True)
    recentPayments = ParentRecentPaymentSerializer(many=True)


class ParentChildSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    full_name = serializers.CharField()
    admission_number = serializers.CharField()
    class_name = serializers.CharField()
    classroom_name = serializers.CharField()
    gender = serializers.CharField()
    date_of_birth = serializers.DateField(allow_null=True)
    status = serializers.ChoiceField(choices=("active", "inactive"))
from academic.models import Teacher, Subject, Parent
from .models import CustomUser, UserInvitation
from .tokens import tenant_refresh_token_for_user


class UserSerializer(serializers.ModelSerializer):
    username = serializers.SerializerMethodField(read_only=True)
    isAdmin = serializers.SerializerMethodField(read_only=True)
    isAccountant = serializers.SerializerMethodField(read_only=True)
    isTeacher = serializers.SerializerMethodField(read_only=True)
    isParent = serializers.SerializerMethodField(read_only=True)
    teacher_details = serializers.SerializerMethodField(read_only=True)
    parent_details = serializers.SerializerMethodField(read_only=True)
    isStudent        = serializers.SerializerMethodField(read_only=True)
    isInspector      = serializers.SerializerMethodField(read_only=True)
    inspector_details = serializers.SerializerMethodField(read_only=True)
    active_role = serializers.ChoiceField(
        source="get_effective_role",
        choices=TENANT_ROLE_CHOICES,
        allow_null=True,
        read_only=True,
    )
    available_roles = serializers.ListField(
        source="get_available_roles",
        child=serializers.ChoiceField(choices=TENANT_ROLE_CHOICES),
        read_only=True,
    )

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "email",
            "username",
            "first_name",
            "middle_name",
            "last_name",
            "isAdmin",
            "isAccountant",
            "isTeacher",
            "isParent",
            "isStudent",
            "teacher_details",
            "parent_details",
            "isInspector",
            "inspector_details",
            "active_role",
            "available_roles",
        ]

    def get_isStudent(self, obj):
        return obj.is_student

    def get_isInspector(self, obj):
        return obj.is_inspector

    def get_inspector_details(self, obj):
        """Return inspector profile if the user is an inspector."""
        if obj.is_inspector and hasattr(obj, 'inspector_profile'):
            from tenants.serializers import InspectorSerializer
            return InspectorSerializer(obj.inspector_profile).data
        return None

    def get_isAdmin(self, obj):
        return obj.is_admin

    def get_isAccountant(self, obj):
        return obj.is_accountant

    def get_isTeacher(self, obj):
        return obj.is_teacher

    def get_isParent(self, obj):
        return obj.is_parent

    def get_username(self, obj):
        if obj.first_name and obj.last_name:
            return f"{obj.first_name} {obj.last_name}"
        return obj.email or "Unknown User"

    def get_teacher_details(self, obj):
        """Return teacher details if the user is a teacher."""
        if obj.is_teacher and hasattr(obj, "teacher"):
            return TeacherSerializer(obj.teacher).data
        return None

    def get_parent_details(self, obj):
        """Return parent details if the user is a parent."""
        if obj.is_parent and hasattr(obj, "parent"):
            return ParentSerializer(obj.parent).data
        return None


class UserSerializerWithToken(UserSerializer):
    token = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = CustomUser
        fields = UserSerializer.Meta.fields + ["token"]

    def get_token(self, obj):
        try:
            token = tenant_refresh_token_for_user(obj)
            return str(token.access_token)
        except Exception:
            return None


class LoginResponseSerializer(UserSerializer):
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)
    token = serializers.CharField(read_only=True, allow_null=True)
    tenant_slug = serializers.CharField(read_only=True)
    isSuperAdmin = serializers.BooleanField(read_only=True)

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + [
            "access",
            "refresh",
            "token",
            "tenant_slug",
            "isSuperAdmin",
        ]


class TeacherSerializer(serializers.ModelSerializer):
    # Explicitly declare user-related fields
    email = serializers.EmailField(required=True)
    first_name = serializers.CharField(required=True, max_length=100)
    middle_name = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    last_name = serializers.CharField(required=True, max_length=100)
    phone_number = serializers.CharField(required=False, allow_blank=True, max_length=15, default="")
    username = serializers.CharField(required=False, allow_blank=True, read_only=True)
    gender = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    # Canonical Staff employment fields
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    academic_qualification = serializers.CharField(required=False, allow_blank=True, max_length=255, default="")
    state = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    address = serializers.CharField(required=False, allow_blank=True, max_length=255, default="")
    designation = serializers.CharField(required=False, allow_blank=True, max_length=255, default="")
    salary = serializers.DecimalField(required=False, allow_null=True, max_digits=12, decimal_places=2)

    subject_specialization = serializers.ListField(
        child=serializers.CharField(), write_only=True, required=True
    )
    subject_specialization_display = serializers.StringRelatedField(
        many=True, source="subject_specialization", read_only=True
    )
    send_invitation = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = Teacher
        fields = [
            "id",
            "username",
            "first_name",
            "middle_name",
            "last_name",
            "email",
            "phone_number",
            "empId",
            "short_name",
            "subject_specialization",
            "subject_specialization_display",
            "gender",
            "national_id",
            "tin_number",
            "date_of_birth",
            "academic_qualification",
            "state",
            "address",
            "designation",
            "salary",
            "image",
            "send_invitation",
        ]

    def validate_date_of_birth(self, value):
        from django.utils import timezone
        if value and value > timezone.now().date():
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        return value

    def validate_salary(self, value):
        from academic.permissions import can_view_staff_salary
        request = self.context.get("request")
        if not request or not can_view_staff_salary(getattr(request, "user", None)):
            raise serializers.ValidationError("You do not have permission to modify salary.")
        if value is not None and value < 0:
            raise serializers.ValidationError("Salary cannot be negative.")
        return value

    def validate_email(self, value):
        request = self.context.get("request", None)
        teacher_id = (
            self.instance.id if self.instance else None
        )

        existing_user = CustomUser.objects.filter(email=value).first()
        if existing_user:
            if self.instance and self.instance.user and self.instance.user.email == value:
                return value
            if not self.instance and not Teacher.objects.filter(user=existing_user).exists():
                return value
            raise serializers.ValidationError(
                "A user with this email already exists."
            )

        return value

    def validate_phone_number(self, value):
        teacher_id = (
            self.instance.id if self.instance else None
        )

        if value and CustomUser.objects.filter(phone_number=value).exists():
            if self.instance and self.instance.user and self.instance.user.phone_number == value:
                return value
            existing_user = CustomUser.objects.filter(phone_number=value).first()
            if (
                not self.instance
                and existing_user
                and existing_user.email == self.initial_data.get("email")
                and not Teacher.objects.filter(user=existing_user).exists()
            ):
                return value
            raise serializers.ValidationError(
                "A user with this phone number already exists."
            )

        return value

    def validate_subject_specialization(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError(
                "Subject specialization should be a list of subject names or IDs."
            )

        subject_names = [v for v in value if isinstance(v, str)]
        subject_ids = [int(v) for v in value if str(v).isdigit()]

        existing_subjects = Subject.objects.none()

        if subject_names:
            existing_subjects = existing_subjects | Subject.objects.filter(name__in=subject_names)

        if subject_ids:
            existing_subjects = existing_subjects | Subject.objects.filter(id__in=subject_ids)

        existing_subjects = existing_subjects.distinct()

        found_count = existing_subjects.count()
        requested_count = len(value)

        if found_count != requested_count:
            found_names = set(existing_subjects.values_list("name", flat=True))
            found_ids = set(existing_subjects.values_list("id", flat=True))
            missing = []
            for v in value:
                if isinstance(v, str) and v not in found_names:
                    missing.append(str(v))
                elif str(v).isdigit() and int(v) not in found_ids:
                    missing.append(str(v))
            raise serializers.ValidationError(
                f"The following subjects do not exist: {', '.join(missing)}"
            )

        return existing_subjects

    def to_representation(self, instance):
        data = super().to_representation(instance)
        staff = instance.staff
        if staff:
            data["date_of_birth"] = staff.date_of_birth
            data["academic_qualification"] = staff.academic_qualification
            data["state"] = staff.state
            data["address"] = staff.address
            data["designation"] = staff.designation
            data["salary"] = staff.salary

        from academic.permissions import can_view_staff_salary
        request = self.context.get("request")
        if not request or not can_view_staff_salary(getattr(request, "user", None), instance.user):
            data.pop("salary", None)
        return data

    @transaction.atomic
    def create(self, validated_data):
        from academic.models import Staff

        subject_specialization_data = validated_data.pop("subject_specialization")
        send_invitation = validated_data.pop("send_invitation", False)

        # Extract user fields
        email = validated_data.pop("email", None)
        first_name = validated_data.pop("first_name", "")
        middle_name = validated_data.pop("middle_name", "")
        last_name = validated_data.pop("last_name", "")
        phone_number = validated_data.pop("phone_number", "")
        username = validated_data.pop("username", None)
        gender = validated_data.pop("gender", None)

        # Extract canonical Staff fields
        has_date_of_birth = "date_of_birth" in validated_data
        has_salary = "salary" in validated_data
        date_of_birth = validated_data.pop("date_of_birth", None)
        academic_qualification = validated_data.pop("academic_qualification", "")
        state = validated_data.pop("state", "")
        address = validated_data.pop("address", "")
        designation = validated_data.pop("designation", "")
        salary = validated_data.pop("salary", None)

        empId = validated_data.get("empId")
        image = validated_data.get("image")

        if not email:
            raise serializers.ValidationError({"email": "Email is required to create a teacher."})

        existing_teacher = Teacher.objects.filter(user__email=email).first()
        if existing_teacher:
            raise serializers.ValidationError({
                "email": f"A teacher with email '{email}' already exists (Emp ID: {existing_teacher.empId})."
            })

        user, created = CustomUser.objects.get_or_create(
            email=email,
            defaults={
                "first_name": first_name,
                "middle_name": middle_name,
                "last_name": last_name,
                "phone_number": phone_number,
                "is_teacher": True,
            }
        )

        if created:
            default_password = f"Complex.{empId[-4:] if empId and len(empId) >= 4 else '0000'}"
            user.set_password(default_password)
            user.save()

            group, _ = Group.objects.get_or_create(name="teacher")
            user.groups.add(group)
        else:
            if not user.is_teacher:
                user.is_teacher = True
                user.save(update_fields=["is_teacher"])

                group, _ = Group.objects.get_or_create(name="teacher")
                user.groups.add(group)

        # Create or update Staff record as canonical employee
        staff = Staff.objects.filter(user=user).first()
        if not staff:
            staff = Staff(
                user=user,
                role=Staff.Role.TEACHER,
                designation=designation or "Teacher",
                academic_qualification=academic_qualification,
                state=state,
                address=address,
                date_of_birth=date_of_birth,
                salary=salary,
                image=image,
                is_active=True,
            )
            staff.save()
        else:
            if has_date_of_birth:
                staff.date_of_birth = date_of_birth
            if academic_qualification:
                staff.academic_qualification = academic_qualification
            if state:
                staff.state = state
            if address:
                staff.address = address
            if designation:
                staff.designation = designation
            if salary is not None:
                staff.salary = salary
            if image:
                staff.image = image
            staff.save()

        teacher = Teacher.objects.create(
            user=user,
            staff=staff,
            **validated_data
        )
        teacher.subject_specialization.set(subject_specialization_data)

        if send_invitation:
            invited_by = self.context.get("request").user if self.context.get("request") else None

            invitation = UserInvitation.objects.create(
                email=email,
                first_name=first_name,
                last_name=last_name,
                role="teacher",
                teacher_profile_id=teacher.id,
                invited_by=invited_by
            )

            try:
                from core.email_utils import send_teacher_invitation
                send_teacher_invitation(invitation)
            except Exception as e:
                print(f"Failed to send invitation email: {str(e)}")

        return teacher

    @transaction.atomic
    def update(self, instance, validated_data):
        from academic.models import Staff
        from academic.permissions import can_view_staff_salary

        subject_specialization_data = validated_data.pop("subject_specialization", None)
        validated_data.pop("send_invitation", None)

        email = validated_data.pop("email", None)
        first_name = validated_data.pop("first_name", None)
        middle_name = validated_data.pop("middle_name", None)
        last_name = validated_data.pop("last_name", None)
        phone_number = validated_data.pop("phone_number", None)
        username = validated_data.pop("username", None)
        gender = validated_data.pop("gender", None)

        has_date_of_birth = "date_of_birth" in validated_data
        has_salary = "salary" in validated_data
        date_of_birth = validated_data.pop("date_of_birth", None)
        academic_qualification = validated_data.pop("academic_qualification", None)
        state = validated_data.pop("state", None)
        address = validated_data.pop("address", None)
        designation = validated_data.pop("designation", None)
        salary = validated_data.pop("salary", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if subject_specialization_data is not None:
            instance.subject_specialization.set(subject_specialization_data)

        if instance.user:
            user = instance.user
            if email is not None:
                user.email = email
            if first_name is not None:
                user.first_name = first_name
            if middle_name is not None:
                user.middle_name = middle_name
            if last_name is not None:
                user.last_name = last_name
            if phone_number is not None:
                user.phone_number = phone_number
            user.save()

        # Update canonical Staff
        staff = instance.staff
        if not staff and instance.user:
            staff = Staff.objects.filter(user=instance.user).first()
            if not staff:
                staff = Staff(
                    user=instance.user,
                    staff_id=instance.teacher_id or f"STF-{instance.id}",
                    role=Staff.Role.TEACHER,
                    is_active=not instance.inactive,
                )
                staff.save()
            instance.staff = staff
            instance.save(update_fields=["staff"])

        if staff:
            if has_date_of_birth:
                staff.date_of_birth = date_of_birth
            if academic_qualification is not None:
                staff.academic_qualification = academic_qualification
            if state is not None:
                staff.state = state
            if address is not None:
                staff.address = address
            if designation is not None:
                staff.designation = designation

            request = self.context.get("request")
            if has_salary:
                staff.salary = salary

            if "image" in validated_data and validated_data["image"]:
                staff.image = validated_data["image"]
            staff.save()

        return instance


class ParentSerializer(serializers.ModelSerializer):
    children_details = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()
    parent_type = serializers.SerializerMethodField()
    send_invitation = serializers.BooleanField(write_only=True, required=False, default=False)
    students = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
        allow_empty=True
    )

    class Meta:
        model = Parent
        fields = [
            "id",
            "first_name",
            "middle_name",
            "last_name",
            "email",
            "phone_number",
            "address",
            "gender",
            "parent_type",
            "national_id",
            "occupation",
            "single_parent",
            "alt_email",
            "image",
            "inactive",
            "children_details",
            "children",
            "send_invitation",
            "students",
        ]

    def get_parent_type(self, obj):
        if obj.parent_type:
            return obj.parent_type
        if obj.gender == "Male":
            return "Father"
        if obj.gender == "Female":
            return "Mother"
        return "Guardian"

    def get_children_details(self, obj):
        """Returns a list of children associated with the parent."""
        return [
            {
                "id": child.id,
                "first_name": child.first_name,
                "last_name": child.last_name,
                "classroom_name": str(child.classroom) if child.classroom else None,
                "admission_number": getattr(child, "admission_number", None),
            }
            for child in obj.children.all()
        ]

    def get_children(self, obj):
        return self.get_children_details(obj)

    def validate_email(self, value):
        """Ensure email uniqueness among parents."""
        if Parent.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "A parent with this email already exists."
            )
        return value

    def validate_phone_number(self, value):
        """Ensure phone number uniqueness among parents."""
        if Parent.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError(
                "A parent with this phone number already exists."
            )
        return value

    @transaction.atomic
    def create(self, validated_data):
        """Creates a Parent and optionally sends invitation."""
        send_invitation = validated_data.pop("send_invitation", False)
        student_ids = validated_data.pop("students", None)

        parent = Parent(**validated_data)
        parent.save()  # This triggers the model's save() where user is created if not send_invitation

        # Associate students with parent
        if student_ids is not None:
            from academic.models import Student
            Student.objects.filter(id__in=student_ids).update(parent_guardian=parent)

        # If send_invitation is True, create an invitation instead of auto-creating user
        if send_invitation:
            # Get the invited_by user from context (set by the view)
            invited_by = self.context.get('request').user if self.context.get('request') else None

            # Create invitation
            invitation = UserInvitation.objects.create(
                email=parent.email,
                first_name=parent.first_name,
                last_name=parent.last_name,
                role='parent',
                parent_profile_id=parent.id,
                invited_by=invited_by
            )

            # Send invitation email
            try:
                from core.email_utils import send_parent_invitation
                send_parent_invitation(invitation)
            except Exception as e:
                # Log the error but don't fail the parent creation
                print(f"Failed to send invitation email: {str(e)}")

        return parent

    @transaction.atomic
    def update(self, instance, validated_data):
        """Updates a Parent and syncs changes to the associated CustomUser."""
        student_ids = validated_data.pop("students", None)
        email = validated_data.get("email", instance.email)
        first_name = validated_data.get("first_name", instance.first_name)
        last_name = validated_data.get("last_name", instance.last_name)

        # Update Parent
        parent = super().update(instance, validated_data)

        # Update student linkages
        if student_ids is not None:
            from academic.models import Student
            Student.objects.filter(parent_guardian=parent).exclude(id__in=student_ids).update(parent_guardian=None)
            Student.objects.filter(id__in=student_ids).update(parent_guardian=parent)

        # If the Parent has an associated CustomUser, update it as well
        if hasattr(parent, "user") and parent.user:
            user = parent.user
            user.email = email
            user.first_name = first_name
            user.last_name = last_name
            user.save()

        return parent


class UserInvitationSerializer(serializers.ModelSerializer):
    invited_by_name = serializers.SerializerMethodField(read_only=True)
    days_until_expiry = serializers.ReadOnlyField()
    is_expired = serializers.ReadOnlyField()

    class Meta:
        model = UserInvitation
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "role",
            "token",
            "status",
            "teacher_profile_id",
            "parent_profile_id",
            "accountant_profile_id",
            "created_at",
            "expires_at",
            "accepted_at",
            "invited_by",
            "invited_by_name",
            "days_until_expiry",
            "is_expired",
        ]
        read_only_fields = ["token", "created_at", "accepted_at", "status"]

    def get_invited_by_name(self, obj):
        if obj.invited_by:
            return f"{obj.invited_by.first_name} {obj.invited_by.last_name}".strip() or obj.invited_by.email
        return None

    def validate_email(self, value):
        """Check if email is already in use"""
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "A user with this email already exists."
            )

        # Check if there's already a pending invitation
        if UserInvitation.objects.filter(
            email=value,
            status='pending'
        ).exists():
            raise serializers.ValidationError(
                "A pending invitation already exists for this email."
            )

        return value


class AcceptInvitationSerializer(serializers.Serializer):
    """Serializer for accepting an invitation and setting up account"""
    token = serializers.CharField(required=True)
    password = serializers.CharField(required=True, write_only=True, min_length=8)
    password_confirm = serializers.CharField(required=True, write_only=True)

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({
                "password_confirm": "Passwords do not match."
            })
        return data

    def validate_token(self, value):
        """Validate that the token exists and is valid"""
        try:
            invitation = UserInvitation.objects.get(token=value)
            if not invitation.is_valid():
                raise serializers.ValidationError(
                    "This invitation has expired or has already been used."
                )
            self.context['invitation'] = invitation
            return value
        except UserInvitation.DoesNotExist:
            raise serializers.ValidationError("Invalid invitation token.")

    @transaction.atomic
    def save(self):
        """Create user account and link to profile based on role"""
        invitation = self.context['invitation']
        password = self.validated_data['password']

        # Check if user already exists (in case it was created automatically by Teacher/Parent/Accountant)
        try:
            user = CustomUser.objects.get(email=invitation.email)
            # User exists, just update their password and activate if needed
            user.first_name = invitation.first_name
            user.last_name = invitation.last_name
            user.is_active = True
        except CustomUser.DoesNotExist:
            # Create new CustomUser
            user = CustomUser.objects.create(
                email=invitation.email,
                first_name=invitation.first_name,
                last_name=invitation.last_name,
                is_active=True,
            )

        user.set_password(password)

        # Set role flags and assign to group
        if invitation.role == 'teacher':
            user.is_teacher = True
            group, _ = Group.objects.get_or_create(name='teacher')
            user.groups.add(group)

            # Link to teacher profile if exists
            if invitation.teacher_profile_id:
                try:
                    teacher = Teacher.objects.get(id=invitation.teacher_profile_id)
                    teacher.user = user
                    teacher.save()
                except Teacher.DoesNotExist:
                    pass

        elif invitation.role == 'parent':
            user.is_parent = True
            group, _ = Group.objects.get_or_create(name='parent')
            user.groups.add(group)

            # Link to parent profile if exists
            if invitation.parent_profile_id:
                try:
                    parent = Parent.objects.get(id=invitation.parent_profile_id)
                    parent.user = user
                    parent.save()
                except Parent.DoesNotExist:
                    pass

        elif invitation.role == 'accountant':
            user.is_accountant = True
            group, _ = Group.objects.get_or_create(name='accountant')
            user.groups.add(group)

        user.save()

        # Mark invitation as accepted
        invitation.mark_as_accepted()

        return user


class AccountantSerializer(serializers.ModelSerializer):
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    academic_qualification = serializers.CharField(required=False, allow_blank=True, max_length=255, default="")
    state = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    address = serializers.CharField(required=False, allow_blank=True, max_length=255, default="")
    designation = serializers.CharField(required=False, allow_blank=True, max_length=255, default="Accountant")
    salary = serializers.DecimalField(required=False, allow_null=True, max_digits=12, decimal_places=2)
    staff_id = serializers.CharField(read_only=True)
    image = serializers.ImageField(required=False, allow_null=True)
    gender = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    empId = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    national_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    tin_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = CustomUser
        fields = [
            'id',
            'staff_id',
            'first_name',
            'middle_name',
            'last_name',
            'email',
            'phone_number',
            'gender',
            'empId',
            'national_id',
            'tin_number',
            'date_of_birth',
            'academic_qualification',
            'state',
            'address',
            'designation',
            'salary',
            'image',
            'is_active',
        ]
        read_only_fields = ['id', 'staff_id']

    def validate_date_of_birth(self, value):
        from django.utils import timezone
        if value and value > timezone.now().date():
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        return value

    def validate_salary(self, value):
        from academic.permissions import can_view_staff_salary
        request = self.context.get("request")
        if not request or not can_view_staff_salary(getattr(request, "user", None)):
            raise serializers.ValidationError("You do not have permission to modify salary.")
        if value is not None and value < 0:
            raise serializers.ValidationError("Salary cannot be negative.")
        return value

    def validate_email(self, value):
        qs = CustomUser.objects.filter(email=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_phone_number(self, value):
        if not value:
            return value
        qs = CustomUser.objects.filter(phone_number=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A user with this phone number already exists.")
        return value

    def to_representation(self, instance):
        data = super().to_representation(instance)
        staff = getattr(instance, "staff_profile", None)
        if not staff:
            from academic.models import Staff
            staff = Staff.objects.filter(user=instance).first()

        if staff:
            data["staff_id"] = staff.staff_id
            data["date_of_birth"] = staff.date_of_birth
            data["academic_qualification"] = staff.academic_qualification
            data["state"] = staff.state
            data["address"] = staff.address
            data["designation"] = staff.designation or "Accountant"
            data["salary"] = staff.salary
            if staff.image:
                request = self.context.get("request")
                try:
                    data["image"] = request.build_absolute_uri(staff.image.url) if request else staff.image.url
                except Exception:
                    data["image"] = None

        from academic.permissions import can_view_staff_salary
        request = self.context.get("request")
        if not request or not can_view_staff_salary(getattr(request, "user", None), instance):
            data.pop("salary", None)
        return data

    @transaction.atomic
    def create(self, validated_data):
        from academic.models import Staff

        has_date_of_birth = 'date_of_birth' in validated_data
        has_salary = 'salary' in validated_data
        date_of_birth = validated_data.pop('date_of_birth', None)
        academic_qualification = validated_data.pop('academic_qualification', '')
        state = validated_data.pop('state', '')
        address = validated_data.pop('address', '')
        designation = validated_data.pop('designation', 'Accountant')
        salary = validated_data.pop('salary', None)
        image = validated_data.pop('image', None)
        validated_data.pop('gender', None)
        validated_data.pop('empId', None)
        validated_data.pop('national_id', None)
        validated_data.pop('tin_number', None)

        user = CustomUser(
            email=validated_data['email'],
            first_name=validated_data.get('first_name', ''),
            middle_name=validated_data.get('middle_name', ''),
            last_name=validated_data.get('last_name', ''),
            phone_number=validated_data.get('phone_number') or None,
            is_accountant=True,
        )
        user.set_unusable_password()
        user.save()
        group, _ = Group.objects.get_or_create(name='accountant')
        user.groups.add(group)

        Staff.objects.create(
            user=user,
            role=Staff.Role.ACCOUNTANT,
            designation=designation or 'Accountant',
            academic_qualification=academic_qualification,
            state=state,
            address=address,
            date_of_birth=date_of_birth,
            salary=salary,
            image=image,
            is_active=True,
        )
        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        from academic.models import Staff
        from academic.permissions import can_view_staff_salary

        has_date_of_birth = 'date_of_birth' in validated_data
        has_salary = 'salary' in validated_data
        date_of_birth = validated_data.pop('date_of_birth', None)
        academic_qualification = validated_data.pop('academic_qualification', None)
        state = validated_data.pop('state', None)
        address = validated_data.pop('address', None)
        designation = validated_data.pop('designation', None)
        salary = validated_data.pop('salary', None)
        image = validated_data.pop('image', None)
        validated_data.pop('gender', None)
        validated_data.pop('empId', None)
        validated_data.pop('national_id', None)
        validated_data.pop('tin_number', None)

        for field in ['first_name', 'middle_name', 'last_name', 'email', 'phone_number', 'is_active']:
            if field in validated_data:
                setattr(instance, field, validated_data[field])
        instance.save()

        staff = getattr(instance, "staff_profile", None)
        if not staff:
            staff = Staff.objects.filter(user=instance).first()
            if not staff:
                staff = Staff(user=instance, role=Staff.Role.ACCOUNTANT)
                staff.save()

        if staff:
            if has_date_of_birth:
                staff.date_of_birth = date_of_birth
            if academic_qualification is not None:
                staff.academic_qualification = academic_qualification
            if state is not None:
                staff.state = state
            if address is not None:
                staff.address = address
            if designation is not None:
                staff.designation = designation
            if image is not None:
                staff.image = image

            request = self.context.get('request')
            if has_salary:
                staff.salary = salary
            staff.save()

        return instance
