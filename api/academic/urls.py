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
    GradeLevelListCreateView,
    GradeLevelDetailView,
    SchoolSectionListView,
    SchoolSectionDetailView,
    ClassYearListCreateView,
    ClassYearDetailView,
    ReasonLeftListCreateView,
    ReasonLeftDetailView,
    StreamListCreateView,
    StreamDetailView,
    StudentClassListCreateView,
    StudentClassDetailView,
    BulkUploadStudentClassView,
    BulkUploadStudentsProfileView,
    TeacherMyClassesView,
    ClassroomStudentsView,
    TeacherMyScheduleView,
    AllocatedSubjectViewSet,
    PromotionRuleViewSet,
    StudentPromotionViewSet,
    ClassAdvancementViewSet,
    StreamAssignmentViewSet,
    StudentEnrollmentViewSet,
    StudentAuthViewSet,
    StudentPortalViewSet,
    CurriculumViewSet,
    CurriculumSubjectViewSet,
    CurriculumTopicViewSet,
    TopicViewSet,
    SubTopicViewSet,
    LearningObjectiveViewSet,
    PublishedSchemeViewSet,
    PublishedSchemeEntryViewSet,
    CurriculumResourceViewSet,
    CurriculumAssignmentViewSet,
    SchemeOfWorkViewSet,
    SchemeOfWorkItemViewSet,
    LessonPlanViewSet,
    LessonPlanMaterialViewSet,
    LessonDeliveryViewSet,
    StaffViewSet,
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

# Phase F3.2: Curriculum, Scheme of Work, and Lesson Plans
router.register(r'curricula', CurriculumViewSet, basename='curriculum')
router.register(r'curriculum-subjects', CurriculumSubjectViewSet, basename='curriculum-subject')
router.register(r'curriculum-topics', CurriculumTopicViewSet, basename='curriculum-topic')
router.register(r'topics', TopicViewSet, basename='topic')
router.register(r'subtopics', SubTopicViewSet, basename='subtopic')
router.register(r'learning-objectives', LearningObjectiveViewSet, basename='learning-objective')
router.register(r'published-schemes', PublishedSchemeViewSet, basename='published-scheme')
router.register(r'published-scheme-entries', PublishedSchemeEntryViewSet, basename='published-scheme-entry')
router.register(r'curriculum-resources', CurriculumResourceViewSet, basename='curriculum-resource')
router.register(r'curriculum-assignments', CurriculumAssignmentViewSet, basename='curriculum-assignment')
router.register(r'schemes-of-work', SchemeOfWorkViewSet, basename='scheme-of-work')
router.register(r'scheme-of-work-items', SchemeOfWorkItemViewSet, basename='scheme-of-work-item')
router.register(r'lesson-plans', LessonPlanViewSet, basename='lesson-plan')
router.register(r'lesson-plan-materials', LessonPlanMaterialViewSet, basename='lesson-plan-material')
router.register(r'lesson-deliveries', LessonDeliveryViewSet, basename='lesson-delivery')

# Phase F3.3: Canonical Staff Read Endpoint
router.register(r'staff', StaffViewSet, basename='staff')

# AllocatedSubject management
router.register(r'allocated-subjects', AllocatedSubjectViewSet, basename='allocated-subjects')

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
    # SchoolSection URLs
    path(
        "school-sections/",
        SchoolSectionListView.as_view(),
        name="school-section-list",
    ),
    path(
        "school-sections/<int:pk>/",
        SchoolSectionDetailView.as_view(),
        name="school-section-detail",
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
    path(
        "students/bulk-upload/",
        BulkUploadStudentsProfileView.as_view(),
        name="student-profile-bulk-upload",
    ),
    # Teacher-specific URLs
    path(
        "teachers/my-classes/",
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
    # Examination/Assessment URLs are registered directly in school/urls.py
]
