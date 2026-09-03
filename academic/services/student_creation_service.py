import logging

from django.core.exceptions import ValidationError
from django.db import transaction

from academic.models import Student, ClassRoom
from administration.models import AcademicYear
from academic.services.parent_identity_service import ParentIdentityService
from academic.services.enrollment_service import EnrollmentService
from academic.services.numbering_service import NumberingService
from users.models import UserInvitation


logger = logging.getLogger(__name__)


class StudentCreationService:
    @classmethod
    @transaction.atomic
    def create_student(
        cls,
        *,
        classroom,
        first_name,
        last_name,
        parent_phone=None,
        parent_email=None,
        student_phone=None,
        middle_name="",
        gender=None,
        religion=None,
        date_of_birth=None,
        region="",
        city="",
        street="",
        blood_group="",
        admission_date=None,
        image=None,
        parent_first_name="",
        parent_last_name="",
        parent_address="",
        actor=None,
        send_invitation=False,
    ):
        """
        Creates a student, resolves parent identity, generates the
        admission number, and enrolls the student into the specified
        classroom for the active academic year.
        """
        if not classroom:
            raise ValidationError(
                "Classroom is required for direct student creation."
            )

        academic_year = (
            AcademicYear.objects
            .select_for_update()
            .filter(active_year=True)
            .first()
        )

        if not academic_year:
            raise ValidationError(
                "An active academic year is required "
                "to enroll the student."
            )

        classroom = (
            ClassRoom.objects
            .select_for_update()
            .select_related("grade_level")
            .filter(pk=classroom.pk)
            .first()
        )

        if not classroom:
            raise ValidationError(
                "The selected classroom does not exist."
            )

        if not classroom.grade_level:
            raise ValidationError(
                "The selected classroom has no grade level configured."
            )

        parent_fields_present = any(
            bool(str(val).strip())
            for val in [parent_phone, parent_email, parent_first_name, parent_last_name, parent_address]
            if val is not None
        )

        parent = None
        if parent_fields_present:
            norm_phone = ParentIdentityService.normalize_phone(parent_phone) if parent_phone else None
            clean_email = parent_email.strip().lower() if parent_email else None
            if not norm_phone and not clean_email:
                raise ValidationError("A valid phone number or email is required when parent information is provided.")

            parent = ParentIdentityService.resolve_parent(
                phone_number=norm_phone,
                email=clean_email,
                first_name=parent_first_name or "",
                last_name=parent_last_name or "",
                address=parent_address or street or "",
            )

        if send_invitation:
            if not parent:
                raise ValidationError("A parent or guardian is required when sending an invitation.")
            if not parent.email:
                raise ValidationError("A valid parent email address is required to send an invitation.")

        admission_number = (
            NumberingService.generate_student_admission_number(
                academic_year=academic_year,
                grade_level=classroom.grade_level,
            )
        )

        if not date_of_birth:
            date_of_birth = None

        student_kwargs = {
            "admission_number": admission_number,
            "first_name": first_name,
            "middle_name": middle_name,
            "last_name": last_name,
            "gender": gender,
            "religion": religion,
            "date_of_birth": date_of_birth,
            "region": region,
            "city": city,
            "street": street,
            "blood_group": blood_group,
            "parent_contact": parent.phone_number if parent else None,
            "phone_number": student_phone,
            "parent_guardian": parent,
            "can_login": False,
        }

        if admission_date:
            student_kwargs["admission_date"] = admission_date

        if image:
            student_kwargs["image"] = image

        student = Student.objects.create(
            **student_kwargs
        )

        EnrollmentService.enroll(
            student=student,
            classroom=classroom,
            academic_year=academic_year,
            notes="Direct Admin Creation",
        )

        if send_invitation:
            transaction.on_commit(
                lambda: cls._issue_parent_invitation(
                    parent=parent,
                    actor=actor,
                )
            )

        return student

    @staticmethod
    def _issue_parent_invitation(
        *,
        parent,
        actor=None,
    ):
        if (
            not parent.email
            or (
                parent.user
                and parent.user.has_usable_password()
            )
        ):
            return

        try:
            invitation, created = (
                UserInvitation.objects.get_or_create(
                    email=parent.email,
                    role="parent",
                    status="pending",
                    defaults={
                        "first_name": parent.first_name or "",
                        "last_name": parent.last_name or "",
                        "parent_profile_id": parent.pk,
                        "invited_by": actor,
                    },
                )
            )

            if created:
                from core.email_utils import (
                    send_parent_invitation
                )

                send_parent_invitation(invitation)

        except Exception:
            logger.exception(
                "Failed to issue parent invitation for "
                "directly created student parent %s",
                parent.pk,
            )
