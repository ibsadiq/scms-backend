from django.urls import path
from .views import (
    debug,
    OnboardingCheckView,
    Step1CreateTenantView,
    Step2CreateAdminUserView,
    Step3ConfigureSettingsView,
    SkipToCompleteOnboardingView,
    TenantOnboarding,
)

app_name = 'tenants'

urlpatterns = [
    # Debug endpoint
    path('debug/', debug, name='debug'),

    # Onboarding flow endpoints
    path('onboarding/check/', OnboardingCheckView.as_view(), name='onboarding-check'),
    path('onboarding/step1/create-tenant/', Step1CreateTenantView.as_view(), name='onboarding-step1'),
    path('onboarding/step2/create-admin/', Step2CreateAdminUserView.as_view(), name='onboarding-step2'),
    path('onboarding/step3/configure-settings/', Step3ConfigureSettingsView.as_view(), name='onboarding-step3'),
    path('onboarding/skip-to-complete/', SkipToCompleteOnboardingView.as_view(), name='onboarding-skip'),

    # Legacy endpoint (backward compatibility)
    path('onboarding/', TenantOnboarding.as_view(), name='onboarding-legacy'),
]
