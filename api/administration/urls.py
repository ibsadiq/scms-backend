from django.urls import path, include
from rest_framework.routers import DefaultRouter

from administration.views import (
    AcademicYearListCreateView,
    AcademicYearDetailView,
    TermListCreateView,
    TermDetailView,
    SchoolEventViewSet,
    SchoolEventBulkUploadView,
    SchoolEventTemplateDownloadView
)


router = DefaultRouter()
router.register(r'school-events', SchoolEventViewSet, basename='school-events')



urlpatterns = [
    # AcademicYear URLs
    path(
        "academic-years/",
        AcademicYearListCreateView.as_view(),
        name="academic-year-list-create",
    ),
    path(
        "academic-years/<int:pk>/",
        AcademicYearDetailView.as_view(),
        name="academic-year-detail",
    ),
    # Term URLs
    path("terms/", TermListCreateView.as_view(), name="term-list-create"),
    path("terms/<int:pk>/", TermDetailView.as_view(), name="term-detail"),
    path('school-events', include(router.urls)),
    path('school-events/bulk-upload/', SchoolEventBulkUploadView.as_view(), name='school-events-bulk-upload'),
    path('school-events/template-download/', SchoolEventTemplateDownloadView.as_view(), name='school-events-template-download'),
]
