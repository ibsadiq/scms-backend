from django.db import transaction
from .numbering_service import NumberingService
from ..models import AdmissionApplication, AdmissionStatus


class AdmissionApplicationService:
    @classmethod
    @transaction.atomic
    def create(cls, *, validated_data):
        admission_session = validated_data["admission_session"]
        grade_level = validated_data["applying_for_class"]

        application_number = (
            NumberingService.generate_application_number(
                academic_year=admission_session.academic_year,
                grade_level=grade_level,
            )
        )

        return AdmissionApplication.objects.create(
            application_number=application_number,
            status=AdmissionStatus.DRAFT,
            **validated_data,
        )