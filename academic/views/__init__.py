from .structure import (
    DepartmentListCreateView,
    DepartmentDetailView,
    SchoolSectionListView,
    SchoolSectionDetailView,
    GradeLevelListCreateView,
    GradeLevelDetailView,
    ClassYearListCreateView,
    ClassYearDetailView,
    ReasonLeftListCreateView,
    ReasonLeftDetailView,
    StreamListCreateView,
    StreamDetailView,
    ClassRoomView,
    ClassRoomDetailView,
    BulkUploadClassRoomsView,
    BulkUploadSubjectsView,
)

from .staff import (
    SubjectListView,
    SubjectDetailView,
    StaffViewSet,
    StaffFilter,
)

from .student import (
    StudentClassListCreateView,
    StudentClassDetailView,
    BulkUploadStudentClassView,
    BulkUploadStudentsProfileView,
)

from .teacher import (
    TeacherMyClassesView,
    ClassroomStudentsView,
    BulkMarkAttendanceView,
    TeacherMyScheduleView,
)

from .allocation import (
    AllocatedSubjectViewSet,
    AllocatedSubjectFilter,
)

from .admission_admin import (
    AdmissionSessionAdminViewSet,
    AdmissionFeeStructureAdminViewSet,
    AdmissionApplicationAdminViewSet,
    AdmissionDocumentAdminViewSet,
    AdmissionAssessmentAdminViewSet,
    AssessmentTemplateAdminViewSet,
    AssessmentCriterionAdminViewSet,
)

from .admission_public import (
    PublicAdmissionSessionViewSet,
    PublicAdmissionFeeStructureViewSet,
    PublicAdmissionApplicationViewSet,
    PublicAdmissionDocumentViewSet,
    PublicGradeLevelViewSet,
)

from .promotions import (
    PromotionRuleViewSet,
    StudentPromotionViewSet,
)

from .class_advancement import (
    ClassAdvancementViewSet,
    StreamAssignmentViewSet,
    StudentEnrollmentViewSet,
)

from .student_portal import (
    StudentAuthViewSet,
    StudentPortalViewSet,
)

from .curriculum import (
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
)

from .scheme_and_lesson import (
    SchemeOfWorkViewSet,
    SchemeOfWorkItemViewSet,
    LessonPlanViewSet,
    LessonPlanMaterialViewSet,
    LessonDeliveryViewSet,
)

__all__ = [
    # Structure
    "DepartmentListCreateView",
    "DepartmentDetailView",
    "SchoolSectionListView",
    "SchoolSectionDetailView",
    "GradeLevelListCreateView",
    "GradeLevelDetailView",
    "ClassYearListCreateView",
    "ClassYearDetailView",
    "ReasonLeftListCreateView",
    "ReasonLeftDetailView",
    "StreamListCreateView",
    "StreamDetailView",
    "ClassRoomView",
    "ClassRoomDetailView",
    "BulkUploadClassRoomsView",
    "BulkUploadSubjectsView",
    # Staff
    "SubjectListView",
    "SubjectDetailView",
    "StaffViewSet",
    "StaffFilter",
    # Student
    "StudentClassListCreateView",
    "StudentClassDetailView",
    "BulkUploadStudentClassView",
    "BulkUploadStudentsProfileView",
    # Teacher
    "TeacherMyClassesView",
    "ClassroomStudentsView",
    "BulkMarkAttendanceView",
    "TeacherMyScheduleView",
    # Allocation
    "AllocatedSubjectViewSet",
    "AllocatedSubjectFilter",
    # Admission Admin
    "AdmissionSessionAdminViewSet",
    "AdmissionFeeStructureAdminViewSet",
    "AdmissionApplicationAdminViewSet",
    "AdmissionDocumentAdminViewSet",
    "AdmissionAssessmentAdminViewSet",
    "AssessmentTemplateAdminViewSet",
    "AssessmentCriterionAdminViewSet",
    # Admission Public
    "PublicAdmissionSessionViewSet",
    "PublicAdmissionFeeStructureViewSet",
    "PublicAdmissionApplicationViewSet",
    "PublicAdmissionDocumentViewSet",
    "PublicGradeLevelViewSet",
    # Promotions
    "PromotionRuleViewSet",
    "StudentPromotionViewSet",
    # Class Advancement
    "ClassAdvancementViewSet",
    "StreamAssignmentViewSet",
    "StudentEnrollmentViewSet",
    # Student Portal
    "StudentAuthViewSet",
    "StudentPortalViewSet",
    # Curriculum
    "CurriculumViewSet",
    "CurriculumSubjectViewSet",
    "CurriculumTopicViewSet",
    "TopicViewSet",
    "SubTopicViewSet",
    "LearningObjectiveViewSet",
    "PublishedSchemeViewSet",
    "PublishedSchemeEntryViewSet",
    "CurriculumResourceViewSet",
    "CurriculumAssignmentViewSet",
    # Scheme and Lesson
    "SchemeOfWorkViewSet",
    "SchemeOfWorkItemViewSet",
    "LessonPlanViewSet",
    "LessonPlanMaterialViewSet",
    "LessonDeliveryViewSet",
]
