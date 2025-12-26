from django.db import transaction
from django.contrib.auth.models import Group
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from academic.models import Teacher, Subject, Parent
from .models import CustomUser, Accountant, UserInvitation


class UserSerializer(serializers.ModelSerializer):
    username = serializers.SerializerMethodField(read_only=True)
    isAdmin = serializers.SerializerMethodField(read_only=True)
    isAccountant = serializers.SerializerMethodField(read_only=True)
    isTeacher = serializers.SerializerMethodField(read_only=True)
    isParent = serializers.SerializerMethodField(read_only=True)
    accountant_details = serializers.SerializerMethodField(read_only=True)
    teacher_details = serializers.SerializerMethodField(read_only=True)
    parent_details = serializers.SerializerMethodField(read_only=True)

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
            "accountant_details",
            "teacher_details",
            "parent_details",
        ]

    def get_isAdmin(self, obj):
        return obj.is_superuser

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

    def get_accountant_details(self, obj):
        """Return accountant details if the user is an accountant."""
        if obj.is_accountant and hasattr(obj, "accountant"):
            return AccountantSerializer(obj.accountant).data
        return None

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
            token = RefreshToken.for_user(obj)
            return str(token.access_token)
        except Exception:
            return None


class AccountantSerializer(serializers.ModelSerializer):
    payments = serializers.SerializerMethodField()
    send_invitation = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = Accountant
        fields = [
            "id",
            "username",
            "first_name",
            "middle_name",
            "last_name",
            "email",
            "phone_number",
            "empId",
            "address",
            "gender",
            "national_id",
            "tin_number",
            "date_of_birth",
            "salary",
            "unpaid_salary",
            "payments",
            "send_invitation",
        ]

    def get_payments(self, obj):
        """Lazy import to avoid circular import issue"""
        from finance.serializers import PaymentSerializer  # Import inside method

        if obj.user:
            payments = obj.user.payments.all()
            return PaymentSerializer(payments, many=True).data
        return []

    def validate_email(self, value):
        request = self.context.get("request", None)
        accountant_id = (
            self.instance.id if self.instance else None
        )  # Get accountant ID if updating

        if Accountant.objects.filter(email=value).exclude(id=accountant_id).exists():
            raise serializers.ValidationError(
                "A accountant with this email already exists."
            )

        return value

    def validate_phone_number(self, value):
        accountant_id = (
            self.instance.id if self.instance else None
        )  # Get accountant ID if updating

        if (
            Accountant.objects.filter(phone_number=value)
            .exclude(id=accountant_id)
            .exists()
        ):
            raise serializers.ValidationError(
                "A accountant with this phone number already exists."
            )

        return value

    @transaction.atomic
    def create(self, validated_data):
        """Creates an Accountant and optionally sends invitation."""
        send_invitation = validated_data.pop("send_invitation", False)

        accountant = Accountant.objects.create(**validated_data)

        # If send_invitation is True, create an invitation instead of auto-creating user
        if send_invitation:
            # Get the invited_by user from context (set by the view)
            invited_by = self.context.get('request').user if self.context.get('request') else None

            # Create invitation
            invitation = UserInvitation.objects.create(
                email=accountant.email,
                first_name=accountant.first_name,
                last_name=accountant.last_name,
                role='accountant',
                accountant_profile_id=accountant.id,
                invited_by=invited_by
            )

            # Send invitation email
            try:
                from core.email_utils import send_accountant_invitation
                send_accountant_invitation(invitation)
            except Exception as e:
                # Log the error but don't fail the accountant creation
                print(f"Failed to send invitation email: {str(e)}")

        return accountant


class TeacherSerializer(serializers.ModelSerializer):
    # Explicitly declare user-related fields (these are properties on Teacher model)
    email = serializers.EmailField(required=True)
    first_name = serializers.CharField(required=True, max_length=100)
    middle_name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    last_name = serializers.CharField(required=True, max_length=100)
    phone_number = serializers.CharField(required=False, allow_blank=True, max_length=15)
    username = serializers.CharField(required=False, allow_blank=True, read_only=True)
    gender = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)

    subject_specialization = serializers.ListField(
        child=serializers.CharField(), write_only=True, required=True
    )
    subject_specialization_display = serializers.StringRelatedField(
        many=True, source="subject_specialization", read_only=True
    )
    payments = serializers.SerializerMethodField()
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
            "address",
            "gender",
            "national_id",
            "tin_number",
            "date_of_birth",
            "salary",
            "unpaid_salary",
            "payments",
            "send_invitation",
        ]

    def get_payments(self, obj):
        """Lazy import to avoid circular import issue"""
        from finance.serializers import PaymentSerializer  # Import inside method

        if obj.user:
            payments = obj.user.payments.all()
            return PaymentSerializer(payments, many=True).data
        return []

    def validate_email(self, value):
        request = self.context.get("request", None)
        teacher_id = (
            self.instance.id if self.instance else None
        )  # Get teacher ID if updating

        # Check if email already exists in CustomUser
        if CustomUser.objects.filter(email=value).exists():
            # If updating, check if it's the same user
            if self.instance and self.instance.user and self.instance.user.email == value:
                return value
            raise serializers.ValidationError(
                "A user with this email already exists."
            )

        return value

    def validate_phone_number(self, value):
        teacher_id = (
            self.instance.id if self.instance else None
        )  # Get teacher ID if updating

        # Check if phone number already exists in CustomUser
        if value and CustomUser.objects.filter(phone_number=value).exists():
            # If updating, check if it's the same user
            if self.instance and self.instance.user and self.instance.user.phone_number == value:
                return value
            raise serializers.ValidationError(
                "A user with this phone number already exists."
            )

        return value

    def validate_subject_specialization(self, value):
        """
        Validate that all subject names in the input exist in the database.
        Ensure it works for both create and update operations.
        """
        if not isinstance(value, list):
            raise serializers.ValidationError(
                "Subject specialization should be a list of subject names."
            )

        # Get existing subjects matching the provided names
        existing_subjects = Subject.objects.filter(name__in=value).distinct()

        # Extract names of found subjects
        existing_subject_names = set(existing_subjects.values_list("name", flat=True))

        # Identify missing subjects
        missing_subjects = set(value) - existing_subject_names

        if missing_subjects:
            raise serializers.ValidationError(
                f"The following subjects do not exist: {', '.join(missing_subjects)}"
            )

        return existing_subjects  # Return the queryset instead of a list of names

    @transaction.atomic
    def create(self, validated_data):
        from django.utils.crypto import get_random_string

        subject_specialization_data = validated_data.pop("subject_specialization")
        send_invitation = validated_data.pop("send_invitation", False)

        # Extract user fields (these are properties on Teacher, not actual fields)
        email = validated_data.pop('email', None)
        first_name = validated_data.pop('first_name', '')
        middle_name = validated_data.pop('middle_name', '')
        last_name = validated_data.pop('last_name', '')
        phone_number = validated_data.pop('phone_number', '')
        username = validated_data.pop('username', None)
        gender = validated_data.pop('gender', None)
        date_of_birth = validated_data.pop('date_of_birth', None)

        # Get empId for password generation
        empId = validated_data.get('empId')

        # Email is required for user creation
        if not email:
            raise serializers.ValidationError({"email": "Email is required to create a teacher."})

        # Check if a teacher with this email already exists
        existing_teacher = Teacher.objects.filter(user__email=email).first()
        if existing_teacher:
            raise serializers.ValidationError({
                "email": f"A teacher with email '{email}' already exists (Emp ID: {existing_teacher.empId})."
            })

        # Create or get CustomUser for the teacher
        user, created = CustomUser.objects.get_or_create(
            email=email,
            defaults={
                'first_name': first_name,
                'middle_name': middle_name,
                'last_name': last_name,
                'phone_number': phone_number,
                'is_teacher': True,
            }
        )

        if created:
            # Set default password for new users
            default_password = f"Complex.{empId[-4:] if empId and len(empId) >= 4 else '0000'}"
            user.set_password(default_password)
            user.save()

            # Add user to "teacher" group
            group, _ = Group.objects.get_or_create(name='teacher')
            user.groups.add(group)
        else:
            # Update existing user to ensure they're marked as teacher
            if not user.is_teacher:
                user.is_teacher = True
                user.save()

                # Add to teacher group
                group, _ = Group.objects.get_or_create(name='teacher')
                user.groups.add(group)

        # Create teacher with the linked user (only include Teacher model fields)
        teacher = Teacher.objects.create(user=user, **validated_data)
        # subject_specialization_data is already a queryset from validation
        teacher.subject_specialization.set(subject_specialization_data)

        # If send_invitation is True, create an invitation for user to set their own password
        if send_invitation:
            # Get the invited_by user from context (set by the view)
            invited_by = self.context.get('request').user if self.context.get('request') else None

            # Create invitation
            invitation = UserInvitation.objects.create(
                email=email,
                first_name=first_name,
                last_name=last_name,
                role='teacher',
                teacher_profile_id=teacher.id,
                invited_by=invited_by
            )

            # Send invitation email
            try:
                from core.email_utils import send_teacher_invitation
                send_teacher_invitation(invitation)
            except Exception as e:
                # Log the error but don't fail the teacher creation
                print(f"Failed to send invitation email: {str(e)}")

        return teacher

    @transaction.atomic
    def update(self, instance, validated_data):
        """Updates a Teacher and syncs changes to the associated CustomUser."""
        subject_specialization_data = validated_data.pop("subject_specialization", None)
        validated_data.pop("send_invitation", None)  # Remove send_invitation if present

        # Extract user fields (these are properties on Teacher, not actual fields)
        email = validated_data.pop("email", None)
        first_name = validated_data.pop("first_name", None)
        middle_name = validated_data.pop("middle_name", None)
        last_name = validated_data.pop("last_name", None)
        phone_number = validated_data.pop("phone_number", None)
        username = validated_data.pop("username", None)
        gender = validated_data.pop("gender", None)
        date_of_birth = validated_data.pop("date_of_birth", None)

        # Update Teacher instance (only actual Teacher model fields)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update subject specialization if provided
        if subject_specialization_data is not None:
            # subject_specialization_data is already a queryset from validation
            instance.subject_specialization.set(subject_specialization_data)

        # If the Teacher has an associated CustomUser, update it as well
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

        return instance


class ParentSerializer(serializers.ModelSerializer):
    children_details = serializers.SerializerMethodField()
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
            "date_of_birth",
            "parent_type",
            "national_id",
            "occupation",
            "single_parent",
            "alt_email",
            "image",
            "inactive",
            "children_details",
            "send_invitation",
            "students",
        ]

    def get_children_details(self, obj):
        """Returns a list of children associated with the parent."""
        return [
            {
                "id": child.id,
                "first_name": child.first_name,
                "last_name": child.last_name,
            }
            for child in obj.children.all()
        ]

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
        student_ids = validated_data.pop("students", [])

        parent = Parent(**validated_data)
        parent.save()  # This triggers the model's save() where user is created if not send_invitation

        # Associate students with parent
        if student_ids:
            from sis.models import Student
            students = Student.objects.filter(id__in=student_ids)
            for student in students:
                student.guardian = parent
                student.save()

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
        email = validated_data.get("email", instance.email)
        first_name = validated_data.get("first_name", instance.first_name)
        last_name = validated_data.get("last_name", instance.last_name)

        # Update Parent
        parent = super().update(instance, validated_data)

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

            # Link to accountant profile if exists
            if invitation.accountant_profile_id:
                try:
                    accountant = Accountant.objects.get(id=invitation.accountant_profile_id)
                    accountant.user = user
                    accountant.save()
                except Accountant.DoesNotExist:
                    pass

        user.save()

        # Mark invitation as accepted
        invitation.mark_as_accepted()

        return user
