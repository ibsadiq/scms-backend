from dataclasses import dataclass
from typing import Callable

from django.core.exceptions import ValidationError
from django.utils import timezone

from administration.models import AcademicYear
from idcards.models import HolderType
from .branding import BrandingResolver


@dataclass(frozen=True)
class DynamicField:
    key: str
    label: str
    group: str
    value_type: str
    holder_types: tuple[str, ...]
    example_value: str
    max_expected_length: int
    sensitivity: str  # "public", "internal", "confidential"
    resolver: Callable


def _text(value):
    return "" if value is None else str(value)


class AcademicContextResolver:
    """Canonical resolver for the active academic year and term."""

    @classmethod
    def resolve(cls):
        active_year = AcademicYear.objects.filter(active_year=True).first()
        year_name = active_year.name if active_year else ""
        term_name = ""
        if active_year:
            today = timezone.now().date()
            current_term = active_year.terms.filter(start_date__lte=today, end_date__gte=today).first()
            if not current_term:
                current_term = active_year.terms.order_by("start_date").first()
            if current_term:
                term_name = current_term.name
        return {"current_year": year_name, "current_term": term_name}


class DynamicFieldRegistry:
    BOTH = (HolderType.STUDENT, HolderType.STAFF)

    FIELDS = (
        # Student fields
        DynamicField(
            "student.full_name", "Student Name", "student", "text", (HolderType.STUDENT,),
            "Jane Doe", 50, "public", lambda c: c["student"].full_name if c.get("student") else "",
        ),
        DynamicField(
            "student.first_name", "First Name", "student", "text", (HolderType.STUDENT,),
            "Jane", 30, "public", lambda c: (c["student"].first_name or "").title() if c.get("student") else "",
        ),
        DynamicField(
            "student.middle_name", "Middle Name", "student", "text", (HolderType.STUDENT,),
            "Anne", 30, "public", lambda c: (c["student"].middle_name or "").title() if c.get("student") else "",
        ),
        DynamicField(
            "student.last_name", "Last Name", "student", "text", (HolderType.STUDENT,),
            "Doe", 30, "public", lambda c: (c["student"].last_name or "").title() if c.get("student") else "",
        ),
        DynamicField(
            "student.student_id", "Student ID", "student", "text", (HolderType.STUDENT,),
            "STU-A7K9X2M4", 20, "public", lambda c: c["student"].student_id if c.get("student") else "",
        ),
        DynamicField(
            "student.admission_number", "Admission Number", "student", "text", (HolderType.STUDENT,),
            "ADM-2024-001", 30, "public", lambda c: c["student"].admission_number if c.get("student") else "",
        ),
        DynamicField(
            "student.classroom", "Classroom", "student", "text", (HolderType.STUDENT,),
            "Grade 10A", 30, "public", lambda c: _text(c["student"].classroom) if c.get("student") else "",
        ),
        DynamicField(
            "student.class_level", "Class Level", "student", "text", (HolderType.STUDENT,),
            "SS2", 20, "public", lambda c: _text(c["student"].grade_level) if c.get("student") else "",
        ),
        DynamicField(
            "student.date_of_birth", "Date of Birth", "student", "date", (HolderType.STUDENT,),
            "2008-05-14", 10, "internal",
            lambda c: (c["student"].date_of_birth.isoformat() if c.get("student") and c["student"].date_of_birth else ""),
        ),
        DynamicField(
            "student.gender", "Gender", "student", "text", (HolderType.STUDENT,),
            "Female", 10, "public",
            lambda c: (c["student"].get_gender_display() if c.get("student") and hasattr(c["student"], "get_gender_display") and c["student"].gender else (_text(c["student"].gender) if c.get("student") else "")),
        ),
        DynamicField(
            "student.admission_date", "Admission Date", "student", "date", (HolderType.STUDENT,),
            "2022-09-01", 10, "public",
            lambda c: (c["student"].admission_date.date().isoformat() if c.get("student") and c["student"].admission_date else ""),
        ),
        DynamicField(
            "student.photo", "Student Photo", "student", "image", (HolderType.STUDENT,),
            "", 0, "public", lambda c: c["student"].image.url if c.get("student") and c["student"].image else "",
        ),

        # Staff fields
        DynamicField(
            "staff.full_name", "Staff Name", "staff", "text", (HolderType.STAFF,),
            "Dr. Robert Smith", 50, "public", lambda c: c["staff"].full_name if c.get("staff") else "",
        ),
        DynamicField(
            "staff.first_name", "First Name", "staff", "text", (HolderType.STAFF,),
            "Robert", 30, "public", lambda c: (c["staff"].user.first_name if c.get("staff") and c["staff"].user else ""),
        ),
        DynamicField(
            "staff.last_name", "Last Name", "staff", "text", (HolderType.STAFF,),
            "Smith", 30, "public", lambda c: (c["staff"].user.last_name if c.get("staff") and c["staff"].user else ""),
        ),
        DynamicField(
            "staff.staff_id", "Staff ID", "staff", "text", (HolderType.STAFF,),
            "STF-9X2M4K7A", 20, "public", lambda c: c["staff"].staff_id if c.get("staff") else "",
        ),
        DynamicField(
            "staff.role", "Staff Role", "staff", "text", (HolderType.STAFF,),
            "Teacher", 30, "public", lambda c: c["staff"].get_role_display() if c.get("staff") else "",
        ),
        DynamicField(
            "staff.job_title", "Job Title", "staff", "text", (HolderType.STAFF,),
            "Head of Sciences", 50, "public", lambda c: (c["staff"].designation or "") if c.get("staff") else "",
        ),
        DynamicField(
            "staff.designation", "Designation", "staff", "text", (HolderType.STAFF,),
            "Head of Sciences", 50, "public", lambda c: (c["staff"].designation or "") if c.get("staff") else "",
        ),
        DynamicField(
            "staff.department", "Department", "staff", "text", (HolderType.STAFF,),
            "Science Department", 40, "public", lambda c: _text(c["staff"].department) if c.get("staff") else "",
        ),
        DynamicField(
            "staff.photo", "Staff Photo", "staff", "image", (HolderType.STAFF,),
            "", 0, "public", lambda c: c["staff"].image.url if c.get("staff") and c["staff"].image else "",
        ),

        # School fields
        DynamicField(
            "school.name", "School Name", "school", "text", BOTH,
            "Springfield Academy", 60, "public", lambda c: c["school"].get("name", ""),
        ),
        DynamicField(
            "school.logo", "School Logo", "school", "image", BOTH,
            "", 0, "public", lambda c: c["school"].get("logo", ""),
        ),
        DynamicField(
            "school.motto", "School Motto", "school", "text", BOTH,
            "Excellence & Integrity", 80, "public", lambda c: c["school"].get("motto", ""),
        ),
        DynamicField(
            "school.address", "School Address", "school", "text", BOTH,
            "123 Education Way, Lagos", 100, "public", lambda c: c["school"].get("address", ""),
        ),
        DynamicField(
            "school.phone", "School Phone", "school", "text", BOTH,
            "+234 801 234 5678", 25, "public", lambda c: c["school"].get("phone", ""),
        ),
        DynamicField(
            "school.email", "School Email", "school", "text", BOTH,
            "info@springfield.edu", 50, "public", lambda c: c["school"].get("email", ""),
        ),

        # Academic fields
        DynamicField(
            "academic.current_year", "Academic Year", "academic", "text", BOTH,
            "2025/2026", 20, "public", lambda c: c["academic"].get("current_year", ""),
        ),
        DynamicField(
            "academic.current_term", "Current Term", "academic", "text", BOTH,
            "First Term", 20, "public", lambda c: c["academic"].get("current_term", ""),
        ),

        # Card fields
        DynamicField(
            "card.card_number", "Card Number", "card", "text", BOTH,
            "IDC-2026-0001", 20, "public", lambda c: c["card"].card_number if c.get("card") else "",
        ),
        DynamicField(
            "card.issued_at", "Issue Date", "card", "date", BOTH,
            "2026-08-24", 10, "public",
            lambda c: (c["card"].issued_at.date().isoformat() if c.get("card") and c["card"].issued_at else ""),
        ),
        DynamicField(
            "card.expires_at", "Expiry Date", "card", "date", BOTH,
            "2027-08-24", 10, "public",
            lambda c: (c["card"].expires_at.date().isoformat() if c.get("card") and c["card"].expires_at else ""),
        ),
        DynamicField(
            "card.holder_type", "Holder Type", "card", "text", BOTH,
            "Student", 15, "public",
            lambda c: (c["card"].get_holder_type_display() if c.get("card") and hasattr(c["card"], "get_holder_type_display") else str(c["card"].holder_type if c.get("card") else "")),
        ),
        DynamicField(
            "card.status", "Card Status", "card", "text", BOTH,
            "ACTIVE", 15, "public",
            lambda c: getattr(c["card"], "effective_status", c["card"].status) if c.get("card") else "ACTIVE",
        ),
    )

    INTERNAL_FIELDS = (
        DynamicField(
            "card.verification_token", "Verification Token", "card", "text", BOTH,
            "VT-SAMPLE-TOKEN", 32, "confidential",
            lambda c: getattr(c["card"], "verification_token", "") if c.get("card") else "",
        ),
    )

    ALL_FIELDS = FIELDS + INTERNAL_FIELDS
    BY_KEY = {field.key: field for field in ALL_FIELDS}

    @classmethod
    def available(cls, holder_type):
        if holder_type not in HolderType.values:
            raise ValidationError("Unknown holder type.")
        return [
            {
                "key": field.key,
                "label": field.label,
                "group": field.group,
                "type": field.value_type,
                "example_value": field.example_value,
                "max_expected_length": field.max_expected_length,
                "sensitivity": field.sensitivity,
            }
            for field in cls.FIELDS
            if holder_type in field.holder_types
        ]

    @classmethod
    def require(cls, key, holder_type):
        field = cls.BY_KEY.get(key)
        if not field or holder_type not in field.holder_types:
            raise ValidationError(f"Dynamic field '{key}' is not available for {holder_type} cards.")
        return field

    @classmethod
    def resolve(cls, keys, card):
        context = {
            "student": getattr(card, "student", None),
            "staff": getattr(card, "staff", None),
            "card": card,
            "school": BrandingResolver.resolve(),
            "academic": AcademicContextResolver.resolve(),
        }
        return {key: cls.require(key, card.holder_type).resolver(context) for key in keys}
