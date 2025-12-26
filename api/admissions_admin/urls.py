"""
Admin API URLs for admission management.
Requires authentication and appropriate permissions.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from academic.views_admission_admin import (
    AdmissionSessionAdminViewSet,
    AdmissionFeeStructureAdminViewSet,
    AdmissionApplicationAdminViewSet,
    AdmissionDocumentAdminViewSet,
    AdmissionAssessmentAdminViewSet,
    AssessmentTemplateAdminViewSet,
    AssessmentCriterionAdminViewSet,
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
    path('', include(router.urls)),
]
