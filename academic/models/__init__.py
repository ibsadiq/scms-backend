from administration.models import AcademicYear, Term
from .choices import (
    CurriculumAuthority,
    CurriculumResourceType,
    PublishedSchemeEntryType,
    SectionType,
    StandardClassCode,
    AcademicLeadershipRole,
    AcademicWorkflow,
    ApprovalRoute,
    SchemeOfWorkStatus,
    LessonPlanStatus,
    LessonDeliveryStatus,
    AdmissionStatus,
    AssessmentType,
)

from .structure import (
    Department,
    SchoolSection,
    GradeLevel,
    ClassYear,
    ReasonLeft,
    Stream,
    ClassRoom,
    Dormitory,
    DormitoryAllocation,
)

from .staff import (
    Staff,
    Subject,
    Teacher,
    AllocatedSubject,
    MessageToTeacher,
)

from .curriculum import (
    Curriculum,
    CurriculumSource,
    CurriculumImportBatch,
    SourceType,
    ImportBatchStatus,
    CurriculumSubject,
    Topic,
    CurriculumTopic,
    CurriculumGuidance,
    SubTopic,
    LearningObjective,
    PublishedScheme,
    PublishedSchemeEntry,
    CurriculumResource,
    CurriculumAssignment,
)

from .scheme_and_lesson import (
    SchemeOfWork,
    SchemeOfWorkItem,
    LessonPlan,
    LessonDelivery,
    LessonPlanMaterial,
)

from .leadership import (
    AcademicLeadershipAssignment,
    AcademicApprovalPolicy,
)

from .student import (
    Parent,
    Student,
    StudentsMedicalHistory,
    StudentsPreviousAcademicHistory,
    StudentFile,
    StudentHealthRecord,
    MessageToParent,
    PromotionRule,
    StudentPromotion,
    StudentClassEnrollment,
)

from .admission import (
    AdmissionSession,
    AdmissionFeeStructure,
    AdmissionApplication,
    AdmissionDocument,
    AdmissionAssessment,
    AssessmentCriterion,
    AssessmentTemplate,
    AssessmentTemplateCriterion,
)
from .numbering import (
    NumberResetPolicy,
    StudentAdmissionNumberPolicy,
    AdmissionApplicationNumberPolicy,
    NumberSequence,
    NumberSequenceType,
    NUMBER_PATTERN_TOKEN_RE,
)

__all__ = [
    # Choices
    "CurriculumAuthority",
    "CurriculumResourceType",
    "PublishedSchemeEntryType",
    "SectionType",
    "StandardClassCode",
    "AcademicLeadershipRole",
    "AcademicWorkflow",
    "ApprovalRoute",
    "SchemeOfWorkStatus",
    "LessonPlanStatus",
    "LessonDeliveryStatus",
    "AdmissionStatus",
    "AssessmentType",
    # Structure
    "Department",
    "SchoolSection",
    "GradeLevel",
    "ClassYear",
    "ReasonLeft",
    "Stream",
    "ClassRoom",
    "Dormitory",
    "DormitoryAllocation",
    # Staff
    "Staff",
    "Subject",
    "Teacher",
    "AllocatedSubject",
    "MessageToTeacher",
    "NumberResetPolicy",
    "StudentAdmissionNumberPolicy",
    "AdmissionApplicationNumberPolicy",
    "NumberSequence",
    "NumberSequenceType",
    "NUMBER_PATTERN_TOKEN_RE",
    # Curriculum
    "Curriculum",
    "CurriculumSource",
    "CurriculumImportBatch",
    "SourceType",
    "ImportBatchStatus",
    "CurriculumSubject",
    "Topic",
    "CurriculumTopic",
    "CurriculumGuidance",
    "SubTopic",
    "LearningObjective",
    "PublishedScheme",
    "PublishedSchemeEntry",
    "CurriculumResource",
    # Scheme & Lesson
    "SchemeOfWork",
    "SchemeOfWorkItem",
    "LessonPlan",
    "LessonDelivery",
    "LessonPlanMaterial",
    # Leadership
    "AcademicLeadershipAssignment",
    "AcademicApprovalPolicy",
    # Student
    "Parent",
    "Student",
    "StudentsMedicalHistory",
    "StudentsPreviousAcademicHistory",
    "StudentFile",
    "StudentHealthRecord",
    "MessageToParent",
    "PromotionRule",
    "StudentPromotion",
    "StudentClassEnrollment",
    # Admission
    "AdmissionSession",
    "AdmissionFeeStructure",
    "AdmissionApplication",
    "AdmissionDocument",
    "AdmissionAssessment",
    "AssessmentCriterion",
    "AssessmentTemplate",
    "AssessmentTemplateCriterion",
]
