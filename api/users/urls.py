from django.urls import path, include
from rest_framework.routers import DefaultRouter

from users.views import (
    MyTokenObtainPairView,
    getUserProfile,
    UserListView,
    UserDetailView,
    ParentListView,
    ParentDetailView,
    AccountantListView,
    AccountantDetailView,
    TeacherListView,
    TeacherDetailView,
    BulkUploadTeachersView,
    TeacherDashboardView,
    ParentDashboardView,
    UserInvitationListCreateView,
    UserInvitationDetailView,
    ValidateInvitationView,
    AcceptInvitationView,
    ResendInvitationView,
)


urlpatterns = [
    # JWT Token endpoint
    path("login/", MyTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("profile/", getUserProfile, name="users-profile"),
    path("users/", UserListView.as_view(), name="users-list"),
    path("users/<int:pk>/", UserDetailView.as_view(), name="user-detail"),
    # teacher URLs
    path("teachers/", TeacherListView.as_view(), name="teacher-list-create"),
    path(
        "teachers/bulk-upload/",
        BulkUploadTeachersView.as_view(),
        name="teacher-bulk-upload",
    ),
    path("teachers/<int:pk>/", TeacherDetailView.as_view(), name="accountant-detail"),
    # Accountant URLs
    path("accountants/", AccountantListView.as_view(), name="accountant-list-create"),
    path(
        "accountants/<int:pk>/",
        AccountantDetailView.as_view(),
        name="accountant-detail",
    ),
    # Parent URLs
    path("parents/", ParentListView.as_view(), name="parent-list-create"),
    path("parents/<int:pk>/", ParentDetailView.as_view(), name="parent-detail"),
    # Dashboard URLs
    path("teacher/dashboard/", TeacherDashboardView.as_view(), name="teacher-dashboard"),
    path("parent/dashboard/", ParentDashboardView.as_view(), name="parent-dashboard"),
    # Invitation URLs
    path("invitations/", UserInvitationListCreateView.as_view(), name="invitation-list-create"),
    path("invitations/<int:pk>/", UserInvitationDetailView.as_view(), name="invitation-detail"),
    path("invitations/validate/<str:token>/", ValidateInvitationView.as_view(), name="invitation-validate"),
    path("invitations/accept/", AcceptInvitationView.as_view(), name="invitation-accept"),
    path("invitations/<int:pk>/resend/", ResendInvitationView.as_view(), name="invitation-resend"),
]
