import logging

from django.core.exceptions import ValidationError
from django.db import transaction

from academic.models import Student, ClassRoom
from administration.models import AcademicYear
from academic.services.parent_identity_service import ParentIdentityService
from academic.services.enrollment_service import EnrollmentService
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
        parent_phone,
        parent_email,
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
        actor=None,
    ):
        """
        Creates a student, resolves parent identity, and enrolls the student
        into the specified classroom for the current active academic year.
        """
        if not classroom:
            raise ValidationError("Classroom is required for direct student creation.")
            
        academic_year = AcademicYear.objects.select_for_update().filter(active_year=True).first()
        if not academic_year:
            raise ValidationError("An active academic year is required to enroll the student.")
            
        # Lock the classroom to ensure we have the most up-to-date capacity info
        classroom = ClassRoom.objects.select_for_update().select_related("name").filter(pk=classroom.pk).first()
        
        parent = ParentIdentityService.resolve_parent(
            phone_number=parent_phone,
            email=parent_email,
            first_name=parent_first_name or first_name,
            last_name=parent_last_name or last_name,
        )

        student_kwargs = {
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
            "parent_contact": parent_phone,
            "phone_number": student_phone,
            "parent_guardian": parent,
            "class_level": classroom.name, # Sync class level
            "can_login": False,
        }
        
        if admission_date:
            student_kwargs["admission_date"] = admission_date
        if image:
            student_kwargs["image"] = image

        student = Student(**student_kwargs)
        student.save() # This triggers AdmissionNumberService.allocate() if no admission number is provided.
        
        EnrollmentService.enroll(
            student=student, 
            classroom=classroom, 
            academic_year=academic_year,
            notes="Direct Admin Creation"
        )

        transaction.on_commit(
            lambda: cls._issue_parent_invitation(parent=parent, actor=actor)
        )
        
        return student

    @staticmethod
    def _issue_parent_invitation(*, parent, actor=None):
        if not parent.email or (parent.user and parent.user.has_usable_password()):
            return

        try:
            invitation, created = UserInvitation.objects.get_or_create(
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
            if created:
                from core.email_utils import send_parent_invitation

                send_parent_invitation(invitation)
        except Exception:
            logger.exception(
                "Failed to issue parent invitation for directly created student parent %s",
                parent.pk,
            )
