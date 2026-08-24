"""
Admin API URLs for admission management.
Requires authentication and appropriate permissions.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from academic.views import (
    AdmissionSessionAdminViewSet,
    AdmissionFeeStructureAdminViewSet,
    AdmissionApplicationAdminViewSet,
    AdmissionDocumentAdminViewSet,
    AdmissionAssessmentAdminViewSet,
    AssessmentTemplateAdminViewSet,
    AssessmentCriterionAdminViewSet,
)
from academic.views.admission_admin import (
    StudentAdmissionNumberPolicyView,
    AdmissionApplicationNumberPolicyView,
)

# Create router
router = DefaultRouter()

# Register viewsets
router.register(
    r'sessions',
    AdmissionSessionAdminViewSet,
    basename='admin-admission-session'
)
router.register(
    r'fee-structures',
    AdmissionFeeStructureAdminViewSet,
    basename='admin-admission-fee-structure'
)
router.register(
    r'applications',
    AdmissionApplicationAdminViewSet,
    basename='admin-admission-application'
)
router.register(
    r'documents',
    AdmissionDocumentAdminViewSet,
    basename='admin-admission-document'
)
router.register(
    r'assessments',
    AdmissionAssessmentAdminViewSet,
    basename='admin-admission-assessment'
)
router.register(
    r'assessment-templates',
    AssessmentTemplateAdminViewSet,
    basename='admin-assessment-template'
)
router.register(
    r'assessment-criteria',
    AssessmentCriterionAdminViewSet,
    basename='admin-assessment-criterion'
)

urlpatterns = [
    path('numbering/student/', StudentAdmissionNumberPolicyView.as_view(), name='student-number-policy'),
    path('numbering/applications/', AdmissionApplicationNumberPolicyView.as_view(), name='application-number-policy'),
    path('', include(router.urls)),
]
