"""
Public API URLs for admission portal.
No authentication required.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from academic.views_admission_public import (
    PublicAdmissionSessionViewSet,
    PublicAdmissionFeeStructureViewSet,
    PublicAdmissionApplicationViewSet,
    PublicAdmissionDocumentViewSet,
    PublicClassLevelViewSet,
)

# Create router
router = DefaultRouter()

# Register viewsets
router.register(
    r'sessions',
    PublicAdmissionSessionViewSet,
    basename='public-admission-session'
)
router.register(
    r'fee-structures',
    PublicAdmissionFeeStructureViewSet,
    basename='public-admission-fee-structure'
)
router.register(
    r'applications',
    PublicAdmissionApplicationViewSet,
    basename='public-admission-application'
)
router.register(
    r'classes',
    PublicClassLevelViewSet,
    basename='public-admission-class'
)

urlpatterns = [
    # Document endpoints with tracking token
    path(
        'applications/<str:tracking_token>/documents/',
        PublicAdmissionDocumentViewSet.as_view({
            'get': 'list',
            'post': 'create'
        }),
        name='public-admission-documents'
    ),
    path(
        'documents/<int:pk>/',
        PublicAdmissionDocumentViewSet.as_view({
            'delete': 'destroy'
        }),
        name='public-admission-document-detail'
    ),

    # Include router URLs
    path('', include(router.urls)),
]
