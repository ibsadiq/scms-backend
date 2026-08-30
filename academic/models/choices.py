from django.db import models
from django.utils.translation import gettext_lazy as _


class CurriculumAuthority(models.TextChoices):
    NERDC = "NERDC", "NERDC"
    STATE = "STATE", "State Ministry / Education Authority"
    SCHOOL = "SCHOOL", "School"
    OTHER = "OTHER", "Other"


class PublishedSchemeEntryType(models.TextChoices):
    INSTRUCTION = "INSTRUCTION", _("Instruction")
    REVISION = "REVISION", _("Revision")
    ASSESSMENT = "ASSESSMENT", _("Assessment")
    EXAMINATION = "EXAMINATION", _("Examination")
    BREAK = "BREAK", _("Break")
    PREPARATION = "PREPARATION", _("Preparation")
    CLOSING = "CLOSING", _("Closing")
    OTHER = "OTHER", _("Other")


class CurriculumResourceType(models.TextChoices):
    PRESCRIBED_TEXT = "PRESCRIBED_TEXT", _("Prescribed Text")
    RECOMMENDED_TEXT = "RECOMMENDED_TEXT", _("Recommended Text")
    REFERENCE = "REFERENCE", _("Reference")
    INSTRUCTIONAL_NOTE = "INSTRUCTIONAL_NOTE", _("Instructional Note")
    EVALUATION = "EVALUATION", _("Evaluation")
    ASSIGNMENT = "ASSIGNMENT", _("Assignment")
    PRACTICAL = "PRACTICAL", _("Practical")
    EXAMPLE = "EXAMPLE", _("Example")
    OTHER = "OTHER", _("Other")


class SectionType(models.TextChoices):
    PRE_PRIMARY = "PRE_PRIMARY", _("Pre-Primary Education")
    PRIMARY = "PRIMARY", _("Primary Education")
    JUNIOR_SECONDARY = "JSS", _("Junior Secondary School")
    SENIOR_SECONDARY = "SSS", _("Senior Secondary School")


class StandardClassCode(models.TextChoices):
    # 1. Pre-Primary
    CRECHE = "CRECHE", _("Creche/Playgroup")
    PRE_NURSERY = "PRE_NURSERY", _("Pre-Nursery")
    NURSERY_1 = "NURSERY_1", _("Nursery 1")
    NURSERY_2 = "NURSERY_2", _("Nursery 2")
    NURSERY_3 = "NURSERY_3", _("Nursery 3")

    # 2. Primary (Basic)
    BASIC_1 = "BASIC_1", _("Basic 1 (Primary 1)")
    BASIC_2 = "BASIC_2", _("Basic 2 (Primary 2)")
    BASIC_3 = "BASIC_3", _("Basic 3 (Primary 3)")
    BASIC_4 = "BASIC_4", _("Basic 4 (Primary 4)")
    BASIC_5 = "BASIC_5", _("Basic 5 (Primary 5)")
    BASIC_6 = "BASIC_6", _("Basic 6 (Primary 6)")

    # 3. Junior Secondary
    JSS_1 = "JSS_1", _("JSS 1 (Basic 7)")
    JSS_2 = "JSS_2", _("JSS 2 (Basic 8)")
    JSS_3 = "JSS_3", _("JSS 3 (Basic 9)")

    # 4. Senior Secondary
    SS_1 = "SS_1", _("SS 1")
    SS_2 = "SS_2", _("SS 2")
    SS_3 = "SS_3", _("SS 3")


class AcademicLeadershipRole(models.TextChoices):
    HOD = "HOD", _("Head of Department")
    HEAD_TEACHER = "HEAD_TEACHER", _("Head Teacher")


class AcademicWorkflow(models.TextChoices):
    SCHEME_OF_WORK = "SCHEME_OF_WORK", _("Scheme of Work")
    LESSON_PLAN = "LESSON_PLAN", _("Lesson Plan")
    QUESTION_BANK = "QUESTION_BANK", _("Question Bank")
    CBT_PUBLISH = "CBT_PUBLISH", _("CBT Publish")


class ApprovalRoute(models.TextChoices):
    ADMIN_ONLY = "ADMIN_ONLY", _("Admin / Principal Only")
    ACADEMIC_LEADER_OR_ADMIN = (
        "ACADEMIC_LEADER_OR_ADMIN",
        _("Academic Leader (HOD / Head Teacher) or Admin"),
    )


class SchemeOfWorkStatus(models.TextChoices):
    DRAFT = "DRAFT", _("Draft")
    SUBMITTED = "SUBMITTED", _("Submitted")
    APPROVED = "APPROVED", _("Approved")
    REJECTED = "REJECTED", _("Rejected")


class LessonPlanStatus(models.TextChoices):
    DRAFT = "DRAFT", _("Draft")
    SUBMITTED = "SUBMITTED", _("Submitted")
    APPROVED = "APPROVED", _("Approved")
    REJECTED = "REJECTED", _("Rejected")


class LessonDeliveryStatus(models.TextChoices):
    COMPLETED = "COMPLETED", "Completed"
    PARTIAL = "PARTIAL", "Partially Completed"
    NOT_TAUGHT = "NOT_TAUGHT", "Not Taught"
    RESCHEDULED = "RESCHEDULED", "Rescheduled"


class AdmissionStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    SUBMITTED = "submitted", _("Submitted")
    UNDER_REVIEW = "under_review", _("Under Review")
    DOCUMENTS_PENDING = "documents_pending", _("Documents Pending")
    EXAM_SCHEDULED = "exam_scheduled", _("Exam Scheduled")
    EXAM_COMPLETED = "exam_completed", _("Exam Completed")
    INTERVIEW_SCHEDULED = "interview_scheduled", _("Interview Scheduled")
    APPROVED = "approved", _("Approved")
    REJECTED = "rejected", _("Rejected")
    ACCEPTED = "accepted", _("Accepted")
    ENROLLED = "enrolled", _("Enrolled")
    WITHDRAWN = "withdrawn", _("Withdrawn")


class AssessmentType(models.TextChoices):
    ENTRANCE_EXAM = "entrance_exam", _("Entrance Examination")
    INTERVIEW = "interview", _("Interview")
    APTITUDE_TEST = "aptitude_test", _("Aptitude Test")
    SCREENING = "screening", _("Screening Test")
    ORAL_TEST = "oral_test", _("Oral Test")
    PRACTICAL = "practical", _("Practical Assessment")
    PSYCHOMETRIC = "psychometric", _("Psychometric Test")
    PORTFOLIO_REVIEW = "portfolio_review", _("Portfolio Review")
