import logging

from django.core.exceptions import ValidationError
from django.db import transaction

from academic.models import (
    AcademicYear,
    AdmissionApplication,
    AdmissionStatus,
    ClassRoom,
    Student,
)
from academic.services.enrollment_service import EnrollmentService
from academic.services.numbering_service import NumberingService
from academic.services.parent_identity_service import ParentIdentityService
from users.models import UserInvitation


logger = logging.getLogger(__name__)


class AdmissionEnrollmentService:
    @classmethod
    @transaction.atomic
    def enroll(
        cls,
        *,
        application,
        classroom,
        actor,
    ):
        application = (
            AdmissionApplication.objects
            .select_for_update()
            .get(pk=application.pk)
        )

        if (
            application.enrolled_student_id
            or application.status == AdmissionStatus.ENROLLED
        ):
            raise ValidationError(
                "This application has already been enrolled."
            )

        if application.status != AdmissionStatus.ACCEPTED:
            raise ValidationError(
                "Only an accepted application can be enrolled."
            )

        academic_year = (
            AcademicYear.objects
            .select_for_update()
            .filter(active_year=True)
            .first()
        )

        if not academic_year:
            raise ValidationError(
                "An active academic year is required for enrollment."
            )

        classroom = (
            ClassRoom.objects
            .select_for_update()
            .select_related("grade_level")
            .filter(pk=classroom.pk)
            .first()
        )

        if (
            not classroom
            or classroom.grade_level_id
            != application.applying_for_class_id
        ):
            raise ValidationError(
                "The classroom must match the application's "
                "accepted grade level."
            )

        parent = ParentIdentityService.resolve_parent(
            phone_number=application.parent_phone,
            email=application.parent_email,
            first_name=application.parent_first_name,
            last_name=application.parent_last_name,
            occupation=application.parent_occupation,
            parent_type=application.parent_relationship.title(),
            address=application.address,
        )

        admission_number = (
            NumberingService.generate_student_admission_number(
                academic_year=academic_year,
                grade_level=classroom.grade_level,
                year=academic_year.start_date.year,
            )
        )

        student = Student.objects.create(
            admission_number=admission_number,
            first_name=application.first_name,
            middle_name=application.middle_name,
            last_name=application.last_name,
            date_of_birth=application.date_of_birth,
            gender=application.gender,
            religion=application.religion,
            blood_group=application.blood_group,
            region=application.state_of_origin,
            city=application.city,
            street=application.address,
            parent_contact=application.parent_phone,
            parent_guardian=parent,
            can_login=False,
        )

        EnrollmentService.enroll(
            student=student,
            classroom=classroom,
            academic_year=academic_year,
            notes=(
                f"Converted from "
                f"{application.application_number}"
            ),
        )

        application.enrolled_student = student
        application.status = AdmissionStatus.ENROLLED

        application.save(
            update_fields=(
                "enrolled_student",
                "status",
                "enrolled_at",
                "updated_at",
            )
        )

        transaction.on_commit(
            lambda: cls._issue_parent_invitation(
                application,
                parent,
                actor,
            )
        )

        return student

    @staticmethod
    def _issue_parent_invitation(
        application,
        parent,
        actor,
    ):
        try:
            invitation, _ = (
                UserInvitation.objects.get_or_create(
                    email=application.parent_email,
                    role="parent",
                    status="pending",
                    defaults={
                        "first_name": (
                            application.parent_first_name
                        ),
                        "last_name": (
                            application.parent_last_name
                        ),
                        "parent_profile_id": parent.pk,
                        "invited_by": actor,
                    },
                )
            )

            from core.email_utils import send_parent_invitation

            send_parent_invitation(invitation)

        except Exception:
            logger.exception(
                "Failed to issue parent invitation for "
                "admission application %s",
                application.pk,
            )