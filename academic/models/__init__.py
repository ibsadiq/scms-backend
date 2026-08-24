from administration.models import AcademicYear, Term
from .choices import (
    CurriculumAuthority,
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
    ClassLevel,
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
    CurriculumSubject,
    Topic,
    CurriculumTopic,
    CurriculumGuidance,
    SubTopic,
    LearningObjective,
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
    AdmissionNumberSequence,
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
    AdmissionApplicationNumberSequence,
)

__all__ = [
    # Choices
    "CurriculumAuthority",
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
    "ClassLevel",
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
    "AdmissionNumberSequence",
    "NumberResetPolicy",
    "StudentAdmissionNumberPolicy",
    "AdmissionApplicationNumberPolicy",
    "AdmissionApplicationNumberSequence",
    # Curriculum
    "Curriculum",
    "CurriculumSubject",
    "Topic",
    "CurriculumTopic",
    "CurriculumGuidance",
    "SubTopic",
    "LearningObjective",
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
