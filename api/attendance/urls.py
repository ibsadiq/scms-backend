from django.urls import path, include
from rest_framework.routers import DefaultRouter
from attendance.views import (
    TeacherAttendanceListView,
    TeacherAttendanceDetailView,
    PeriodAttendanceListView,
    PeriodAttendanceDetailView,
)
from attendance.views_student import StudentAttendanceViewSet
from academic.teacher_views import BulkMarkAttendanceView

# Router for ViewSet-based endpoints
router = DefaultRouter()
router.register(r'student-attendance', StudentAttendanceViewSet, basename='student-attendance')

urlpatterns = [
    # ViewSet routes (includes summary endpoint)
    path('', include(router.urls)),

    # Legacy class-based views
    path(
        "teacher-attendance/",
        TeacherAttendanceListView.as_view(),
        name="teacher-attendance-list",
    ),
    path(
        "teacher-attendance/<int:pk>/",
        TeacherAttendanceDetailView.as_view(),
        name="teacher-attendance-detail",
    ),
    path(
        "period-attendance/",
        PeriodAttendanceListView.as_view(),
        name="period-attendance-list",
    ),
    path(
        "period-attendance/<int:pk>/",
        PeriodAttendanceDetailView.as_view(),
        name="period-attendance-detail",
    ),
    # Bulk attendance marking for teachers
    path(
        "student-attendance/bulk-mark/",
        BulkMarkAttendanceView.as_view(),
        name="bulk-mark-attendance"
    ),
]
