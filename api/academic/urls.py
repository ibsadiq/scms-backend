from django.urls import path, include
from rest_framework.routers import DefaultRouter
from academic.views import (
    SubjectListView,
    SubjectDetailView,
    BulkUploadSubjectsView,
    ClassRoomView,
    ClassRoomDetailView,
    BulkUploadClassRoomsView,
    DepartmentListCreateView,
    DepartmentDetailView,
    ClassLevelListCreateView,
    ClassLevelDetailView,
    GradeLevelListCreateView,
    GradeLevelDetailView,
    ClassYearListCreateView,
    ClassYearDetailView,
    ReasonLeftListCreateView,
    ReasonLeftDetailView,
    StreamListCreateView,
    StreamDetailView,
    StudentClassListCreateView,
    StudentClassDetailView,
    BulkUploadStudentClassView,
)
from academic.teacher_views import (
    TeacherMyClassesView,
    ClassroomStudentsView,
    TeacherMyScheduleView,
)
from academic.views_promotions import (
    PromotionRuleViewSet,
    StudentPromotionViewSet
)
from academic.views_class_advancement import (
    ClassAdvancementViewSet,
    StreamAssignmentViewSet,
    StudentEnrollmentViewSet
)
from academic.views_student_portal import (
    StudentAuthViewSet,
    StudentPortalViewSet
)

# Router for promotion and class advancement endpoints (Phase 2.1 & 2.2)
router = DefaultRouter()
router.register(r'promotion-rules', PromotionRuleViewSet, basename='promotion-rules')
router.register(r'promotions', StudentPromotionViewSet, basename='promotions')
router.register(r'class-advancement', ClassAdvancementViewSet, basename='class-advancement')
router.register(r'stream-assignments', StreamAssignmentViewSet, basename='stream-assignments')
router.register(r'enrollments', StudentEnrollmentViewSet, basename='enrollments')

# Phase 1.6: Student Portal
router.register(r'students/auth', StudentAuthViewSet, basename='student-auth')
router.register(r'students/portal', StudentPortalViewSet, basename='student-portal')

urlpatterns = [
    # Promotion endpoints (Phase 2.1)
    path('', include(router.urls)),

    # Department URLs
    path(
        "departments/",
        DepartmentListCreateView.as_view(),
        name="department-list-create",
    ),
    path(
        "departments/<int:pk>/",
        DepartmentDetailView.as_view(),
        name="department-detail",
    ),
    # ClassLevel URLs
    path(
        "class-levels/",
        ClassLevelListCreateView.as_view(),
        name="class-level-list-create",
    ),
    path(
        "class-levels/<int:pk>/",
        ClassLevelDetailView.as_view(),
        name="class-level-detail",
    ),
    # GradeLevel URLs
    path(
        "grade-levels/",
        GradeLevelListCreateView.as_view(),
        name="grade-level-list-create",
    ),
    path(
        "grade-levels/<int:pk>/",
        GradeLevelDetailView.as_view(),
        name="grade-level-detail",
    ),
    # ClassYear URLs
    path(
        "class-years/", ClassYearListCreateView.as_view(), name="class-year-list-create"
    ),
    path(
        "class-years/<int:pk>/", ClassYearDetailView.as_view(), name="class-year-detail"
    ),
    # ReasonLeft URLs
    path(
        "reasons-left/",
        ReasonLeftListCreateView.as_view(),
        name="reason-left-list-create",
    ),
    path(
        "reasons-left/<int:pk>/",
        ReasonLeftDetailView.as_view(),
        name="reason-left-detail",
    ),
    # Stream URLs
    path(
        "streams/",
        StreamListCreateView.as_view(),
        name="stream-list-create",
    ),
    path(
        "streams/<int:pk>/",
        StreamDetailView.as_view(),
        name="stream-detail",
    ),
    path("subjects/", SubjectListView.as_view(), name="subject-list"),
    path("subjects/<int:id>/", SubjectDetailView.as_view(), name="subject-detail"),
    path(
        "subjects/bulk-upload/",
        BulkUploadSubjectsView.as_view(),
        name="subject-bulk-upload",
    ),
    path("classrooms/", ClassRoomView.as_view(), name="classroom-list"),
    path('classrooms/<int:pk>/', ClassRoomDetailView.as_view(), name='classroom-detail'),

    path(
        "classrooms/bulk-upload/",
        BulkUploadClassRoomsView.as_view(),
        name="bulk-upload-classrooms",
    ),
    # StudentClass URLs
    path(
        "student-classes/",
        StudentClassListCreateView.as_view(),
        name="student-class-list-create",
    ),
    path(
        "student-classes/<int:pk>/",
        StudentClassDetailView.as_view(),
        name="student-class-detail",
    ),
    path(
        "student-classes/bulk-upload/",
        BulkUploadStudentClassView.as_view(),
        name="student-class-bulk-upload",
    ),
    # Teacher-specific URLs
    path(
        "allocated-subjects/my-classes/",
        TeacherMyClassesView.as_view(),
        name="teacher-my-classes"
    ),
    path(
        "classrooms/<int:classroom_id>/students/",
        ClassroomStudentsView.as_view(),
        name="classroom-students"
    ),
    path(
        "timetable/my-schedule/",
        TeacherMyScheduleView.as_view(),
        name="teacher-my-schedule"
    ),
    # Examination/Assessment URLs (includes assessments, marks, results, grade-scales)
    path("", include("api.examination.urls")),
]
