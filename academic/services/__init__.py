"""
Academic Services Module
"""

from .promotion_service import PromotionService
from .class_advancement_service import ClassAdvancementService
from .curriculum_service import CurriculumService
from .scheme_of_work_service import SchemeOfWorkService
from .lesson_plan_service import LessonPlanService
from .lesson_delivery_service import LessonDeliveryService
from .academic_approval_policy_service import AcademicApprovalPolicyService
from .academic_leadership_service import AcademicLeadershipService
from .academic_authority_service import AcademicAuthorityService
from .staff_identity_service import StaffIdentityService

__all__ = [
    "PromotionService",
    "ClassAdvancementService",
    "CurriculumService",
    "SchemeOfWorkService",
    "LessonPlanService",
    "LessonDeliveryService",
    "AcademicApprovalPolicyService",
    "AcademicLeadershipService",
    "AcademicAuthorityService",
    "StaffIdentityService",
]
from .admission_enrollment_service import AdmissionEnrollmentService
