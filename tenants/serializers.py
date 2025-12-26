from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from .models import SchoolSettings, OnboardingStep

User = get_user_model()


class OnboardingCheckSerializer(serializers.Serializer):
    """Serializer to check onboarding status"""
    onboarding_completed = serializers.BooleanField(read_only=True)
    onboarding_step = serializers.IntegerField(read_only=True)
    onboarding_step_label = serializers.CharField(read_only=True)
    needs_onboarding = serializers.BooleanField(read_only=True)
    school_name = serializers.CharField(read_only=True)
    tenant_id = serializers.IntegerField(read_only=True)


class TenantCreateSerializer(serializers.Serializer):
    school_name = serializers.CharField(max_length=255)
    primary_color = serializers.CharField(max_length=20, default="#047857")
    secondary_color = serializers.CharField(max_length=20, required=False, allow_blank=True)
    address = serializers.CharField(max_length=255, required=False, allow_blank=True)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    contact_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)

    def create(self, validated_data):
        # Get or create the single school settings instance
        school = SchoolSettings.get_settings()

        # Update with provided data
        school.school_name = validated_data["school_name"]
        school.primary_color = validated_data.get("primary_color", "#047857")
        school.secondary_color = validated_data.get("secondary_color", "")
        school.address = validated_data.get("address", "")
        school.contact_email = validated_data.get("contact_email", "")
        school.contact_phone = validated_data.get("contact_phone", "")
        school.onboarding_step = OnboardingStep.SCHOOL_INFO
        school.save()

        return school



class AdminUserCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)
    first_name = serializers.CharField()
    last_name = serializers.CharField()

    def validate(self, data):
        if data["password"] != data["confirm_password"]:
            raise serializers.ValidationError("Passwords do not match")
        return data

    def create(self, validated_data):
        validated_data.pop("confirm_password")

        return User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            is_staff=True,
            is_superuser=True
        )


class TenantSettingsUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating school branding (Step 3)"""
    class Meta:
        model = SchoolSettings
        fields = [
            "school_name",
            "logo",
            "primary_color",
            "secondary_color",
            "address",
            "contact_email",
            "contact_phone",
        ]


class CompleteOnboardingSerializer(serializers.Serializer):
    """Final step: Mark onboarding as complete"""
    confirm = serializers.BooleanField(required=True)

    def validate_confirm(self, value):
        if not value:
            raise serializers.ValidationError("You must confirm to complete onboarding")
        return value

    def save(self, **kwargs):
        school = self.context.get("school") or SchoolSettings.get_settings()

        if school.onboarding_step != OnboardingStep.COMPLETED:
            raise serializers.ValidationError("Onboarding steps not completed")

        school.complete_onboarding()
        return school


class TenantSerializer(serializers.ModelSerializer):
    """Serializer for school settings (backward compatible with Tenant name)"""
    needs_onboarding = serializers.BooleanField(read_only=True)
    admin_email = serializers.EmailField(source="admin_user.email", read_only=True)
    onboarding_step_label = serializers.CharField(
        source="get_onboarding_step_display",
        read_only=True
    )

    class Meta:
        model = SchoolSettings
        fields = [
            "id",
            "school_name",
            "logo",
            "primary_color",
            "secondary_color",
            "address",
            "contact_email",
            "contact_phone",
            "onboarding_step",
            "onboarding_step_label",
            "onboarding_completed",
            "needs_onboarding",
            "admin_email",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
