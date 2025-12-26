from django.http import JsonResponse
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from .models import SchoolSettings, Tenant, OnboardingStep
from .serializers import (
    OnboardingCheckSerializer,
    TenantCreateSerializer,
    AdminUserCreateSerializer,
    TenantSettingsUpdateSerializer,
    CompleteOnboardingSerializer,
    TenantSerializer
)

from django.conf import settings

User = get_user_model()


def debug(request):
    """Debug view to check school settings"""
    try:
        school = SchoolSettings.get_settings()
        return JsonResponse({
            "school_name": school.school_name,
            "primary_color": school.primary_color,
            "onboarding_completed": school.onboarding_completed,
        })
    except Exception as e:
        return JsonResponse({"error": str(e)})


class OnboardingCheckView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        """
        Check onboarding status for single school setup.

        Returns school settings and onboarding status.
        """
        # Check if school settings exist
        if not SchoolSettings.objects.exists():
            # Fresh installation - no school setup yet
            return Response({
                "school_id": None,
                "school_name": None,
                "onboarding_step": OnboardingStep.SCHOOL_INFO,
                "onboarding_step_label": "School Information",
                "onboarding_completed": False,
                "needs_onboarding": True,
                "message": "Welcome! Please complete school setup."
            })

        # Get existing school settings
        school = SchoolSettings.get_settings()

        return Response({
            "school_id": school.id,
            "school_name": school.school_name,
            "onboarding_step": school.onboarding_step,
            "onboarding_step_label": school.get_onboarding_step_display(),
            "onboarding_completed": school.onboarding_completed,
            "needs_onboarding": school.needs_onboarding,
        })



class Step1CreateTenantView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = TenantCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        school = serializer.save()

        if not school.can_advance_to(OnboardingStep.SCHOOL_INFO):
            return Response({"error": "Invalid onboarding step"}, status=400)

        school.onboarding_step = OnboardingStep.ADMIN
        school.save(update_fields=["onboarding_step"])

        return Response({
            "message": "School information saved",
            "next_step": OnboardingStep.ADMIN,
        }, status=201)




class Step2CreateAdminUserView(APIView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        school = SchoolSettings.get_settings()

        if not school.can_advance_to(OnboardingStep.ADMIN):
            return Response({"error": "Complete step 1 first"}, status=400)

        serializer = AdminUserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        admin = serializer.save()
        school.admin_user = admin
        school.onboarding_step = OnboardingStep.BRANDING
        school.save(update_fields=["admin_user", "onboarding_step"])

        refresh = RefreshToken.for_user(admin)

        return Response({
            "message": "Admin created",
            "tokens": {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            "next_step": OnboardingStep.BRANDING,
        }, status=201)



class Step3ConfigureSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        school = SchoolSettings.get_settings()

        if not school.can_advance_to(OnboardingStep.BRANDING):
            return Response({"error": "Complete previous steps first"}, status=400)

        serializer = TenantSettingsUpdateSerializer(
            school, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # ✅ ONLY place onboarding is completed
        school.complete_onboarding()

        return Response({
            "message": "Onboarding completed",
            "next_step": OnboardingStep.COMPLETED,
        })



class SkipToCompleteOnboardingView(APIView):
    """
    Skip optional steps and complete onboarding directly.
    This allows completing steps 3 and 4 in one call.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        school = SchoolSettings.get_settings()

        if school.onboarding_completed:
            return Response({
                "error": "Onboarding already completed"
            }, status=status.HTTP_400_BAD_REQUEST)

        if not school.admin_user:
            return Response({
                "error": "Admin user must be created first"
            }, status=status.HTTP_400_BAD_REQUEST)

        # Mark onboarding as complete
        school.complete_onboarding()

        return Response({
            "message": "Onboarding completed successfully!",
            "school": TenantSerializer(school).data,
            "redirect_to": "login"
        }, status=status.HTTP_200_OK)


# Legacy view for backward compatibility
class TenantOnboarding(APIView):
    """
    DEPRECATED: Use the step-by-step onboarding flow instead.
    This view is kept for backward compatibility.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        school_name = request.data.get("school_name")
        primary_color = request.data.get("primary_color", "#0F52BA")
        secondary_color = request.data.get("secondary_color", "#BA770F")

        if not school_name:
            return Response({"error": "school_name required"}, status=400)

        # Create/update school settings
        school = SchoolSettings.get_settings()
        school.school_name = school_name
        school.primary_color = primary_color
        school.secondary_color = secondary_color
        school.save()

        return Response({
            "message": "School settings created successfully",
            "school_id": school.id,
            "school_name": school.school_name
        })
