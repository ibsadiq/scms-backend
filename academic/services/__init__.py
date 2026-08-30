"""
Academic Services Module
"""

from .promotion_service import PromotionService
from .class_advancement_service import ClassAdvancementService
from .curriculum_service import CurriculumService
from .scheme_of_work_service import SchemeOfWorkService
from .lesson_plan_service import LessonPlanService
from .lesson_delivery_service import LessonDeliveryService
from .published_scheme_adoption_service import PublishedSchemeAdoptionService
from .academic_approval_policy_service import AcademicApprovalPolicyService
from .academic_leadership_service import AcademicLeadershipService
from .academic_authority_service import AcademicAuthorityService
from .numbering_service import NumberingService
from .staff_identity_service import StaffIdentityService
from .curriculum_publishing_service import (
    CurriculumResourceService,
    PublishedSchemeService,
)
from .curriculum_v2_validator import (
    ValidationReport,
    ValidationIssue,
    Severity,
    validate_v2,
    make_topic_key as make_curriculum_topic_key,
)
from .admission_enrollment_service import AdmissionEnrollmentService

__all__ = [
    "PromotionService",
    "ClassAdvancementService",
    "CurriculumService",
    "SchemeOfWorkService",
    "LessonPlanService",
    "LessonDeliveryService",
    "PublishedSchemeAdoptionService",
    "AcademicApprovalPolicyService",
    "AcademicLeadershipService",
    "AcademicAuthorityService",
    "StaffIdentityService",
    "PublishedSchemeService",
    "CurriculumResourceService",
    "AdmissionEnrollmentService",
    "NumberingService",
    # V2 Curriculum Validator
    "ValidationReport",
    "ValidationIssue",
    "Severity",
    "validate_v2",
    "make_curriculum_topic_key",
]
