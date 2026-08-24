from datetime import date, timedelta

from django.utils import timezone

from academic.models import (
    AdmissionApplication, AdmissionFeeStructure, AdmissionSession,
    ClassLevel, ClassRoom, GradeLevel,
)
from administration.models import AcademicYear


def make_admissions_structure(*, year_name="2035/2036", year_start=date(2035, 9, 1)):
    year = AcademicYear.objects.create(
        name=year_name, start_date=year_start,
        end_date=date(year_start.year + 1, 7, 31), active_year=True,
    )
    grade = GradeLevel.objects.update_or_create(
        system_code="JSS_1",
        defaults={"section": "JSS", "default_name": "JSS 1", "sequence_order": 11},
    )[0]
    level = ClassLevel.objects.create(name=f"JSS 1 {year_start.year}", grade_level=grade)
    classroom = ClassRoom.objects.create(name=level, capacity=5)
    today = timezone.localdate()
    session = AdmissionSession.objects.create(
        academic_year=year, name=f"{year_name} Admissions",
        start_date=today - timedelta(days=1), end_date=today + timedelta(days=30),
        is_active=True, allow_public_applications=True,
    )
    fees = AdmissionFeeStructure.objects.create(
        admission_session=session, application_fee_required=False,
        acceptance_fee_required=False,
    )
    fees.grade_levels.add(grade)
    return year, grade, classroom, session


def make_application(session, grade, *, suffix="one", status="accepted"):
    return AdmissionApplication.objects.create(
        admission_session=session, applying_for_class=grade,
        status=status, first_name="Applicant", middle_name="Middle",
        last_name=suffix, gender="Male", date_of_birth=date(2018, 1, 1),
        state_of_origin="Lagos", lga="Ikeja", address="1 Test Street",
        city="Lagos", parent_first_name="Parent", parent_last_name=suffix,
        parent_email=f"parent-{suffix}@example.test",
        parent_phone=f"0807{abs(hash(suffix)) % 10000000:07d}"[:11],
    )
