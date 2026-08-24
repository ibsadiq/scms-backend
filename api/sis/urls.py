from django.urls import path
from sis.views import (
    StudentListView,
    StudentDetailView,
    BulkUploadStudentsView,
    StudentMedicalHistoryView,
    StudentAcademicHistoryView,
    StudentPortalAccessView,
)
from academic.views import StudentPortalViewSet

student_dashboard_view = StudentPortalViewSet.as_view({'get': 'dashboard'})
student_profile_view = StudentPortalViewSet.as_view({'get': 'profile', 'put': 'update_profile', 'patch': 'update_profile'})

urlpatterns = [
    path("students/", StudentListView.as_view(), name="students-list"),
    path("students/<int:pk>/", StudentDetailView.as_view(), name="student-detail"),
    path("students/<int:pk>/portal-access/", StudentPortalAccessView.as_view(), name="student-portal-access"),
    path("students/<int:pk>/medical-history/", StudentMedicalHistoryView.as_view(), name="student-medical-history"),
    path("students/<int:pk>/academic-history/", StudentAcademicHistoryView.as_view(), name="student-academic-history"),
    path("students/bulk-upload/", BulkUploadStudentsView.as_view()),
    path("students/portal/dashboard/", student_dashboard_view, name="sis-student-portal-dashboard"),
    path("students/portal/profile/", student_profile_view, name="sis-student-portal-profile"),
]
