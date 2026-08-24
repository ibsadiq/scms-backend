from dataclasses import dataclass
from typing import Callable

from django.core.exceptions import ValidationError

from idcards.models import HolderType
from .branding import BrandingResolver


@dataclass(frozen=True)
class DynamicField:
    key: str
    label: str
    value_type: str
    holder_types: tuple[str, ...]
    resolver: Callable


def _text(value):
    return "" if value is None else str(value)


class DynamicFieldRegistry:
    BOTH = (HolderType.STUDENT, HolderType.STAFF)
    FIELDS = (
        DynamicField("student.full_name", "Student Name", "text", (HolderType.STUDENT,), lambda c: c["student"].full_name),
        DynamicField("student.student_id", "Student ID", "text", (HolderType.STUDENT,), lambda c: c["student"].student_id),
        DynamicField("student.admission_number", "Admission Number", "text", (HolderType.STUDENT,), lambda c: c["student"].admission_number),
        DynamicField("student.classroom", "Classroom", "text", (HolderType.STUDENT,), lambda c: _text(c["student"].classroom)),
        DynamicField("student.class_level", "Class Level", "text", (HolderType.STUDENT,), lambda c: _text(c["student"].class_level)),
        DynamicField("student.photo", "Student Photo", "image", (HolderType.STUDENT,), lambda c: c["student"].image.url if c["student"].image else ""),
        DynamicField("staff.full_name", "Staff Name", "text", (HolderType.STAFF,), lambda c: c["staff"].full_name),
        DynamicField("staff.staff_id", "Staff ID", "text", (HolderType.STAFF,), lambda c: c["staff"].staff_id),
        DynamicField("staff.role", "Staff Role", "text", (HolderType.STAFF,), lambda c: c["staff"].get_role_display()),
        DynamicField("staff.designation", "Designation", "text", (HolderType.STAFF,), lambda c: c["staff"].designation),
        DynamicField("staff.department", "Department", "text", (HolderType.STAFF,), lambda c: _text(c["staff"].department)),
        DynamicField("staff.photo", "Staff Photo", "image", (HolderType.STAFF,), lambda c: c["staff"].image.url if c["staff"].image else ""),
        *(DynamicField(f"school.{key}", f"School {key.title()}", "image" if key == "logo" else "text", (HolderType.STUDENT, HolderType.STAFF), lambda c, k=key: c["school"].get(k, "")) for key in ("name", "logo", "motto", "address", "phone", "email")),
        DynamicField("card.card_number", "Card Number", "text", BOTH, lambda c: c["card"].card_number),
        DynamicField("card.issued_at", "Issue Date", "date", BOTH, lambda c: c["card"].issued_at.date().isoformat()),
        DynamicField("card.expires_at", "Expiry Date", "date", BOTH, lambda c: c["card"].expires_at.date().isoformat() if c["card"].expires_at else ""),
        DynamicField("card.verification_token", "Verification Token", "text", BOTH, lambda c: str(c["card"].verification_token)),
    )
    BY_KEY = {field.key: field for field in FIELDS}

    @classmethod
    def available(cls, holder_type):
        if holder_type not in HolderType.values:
            raise ValidationError("Unknown holder type.")
        return [
            {"key": field.key, "label": field.label, "type": field.value_type}
            for field in cls.FIELDS if holder_type in field.holder_types
        ]

    @classmethod
    def require(cls, key, holder_type):
        field = cls.BY_KEY.get(key)
        if not field or holder_type not in field.holder_types:
            raise ValidationError(f"Dynamic field '{key}' is not available for {holder_type} cards.")
        return field

    @classmethod
    def resolve(cls, keys, card):
        context = {"student": card.student, "staff": card.staff, "card": card, "school": BrandingResolver.resolve()}
        return {key: cls.require(key, card.holder_type).resolver(context) for key in keys}
