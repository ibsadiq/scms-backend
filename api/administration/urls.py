from django.urls import path, include
from rest_framework.routers import DefaultRouter

from administration.views import (
    AcademicYearListCreateView,
    AcademicYearDetailView,
    TermListCreateView,
    TermDetailView,
    SchoolEventViewSet
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
    path('calender', include(router.urls)),
]
