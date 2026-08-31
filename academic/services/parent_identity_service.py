import re

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction

from academic.models import Parent
from users.models import CustomUser


class ParentIdentityService:
    """Authoritative Parent/CustomUser identity resolution and synchronization."""

    @staticmethod
    def normalize_phone(value):
        if value is None:
            return None
        phone = re.sub(r"[\s()\-.]", "", str(value).strip())
        if not phone:
            return None
        if phone.startswith("00"):
            phone = "+" + phone[2:]
        if phone.startswith("0") and len(phone) == 11:
            return "+234" + phone[1:]
        if phone.startswith("234") and len(phone) == 13:
            return "+" + phone
        return phone

    @classmethod
    def phone_variants(cls, value):
        phone = cls.normalize_phone(value)
        if not phone:
            return []
        variants = {phone}
        if phone.startswith("+234"):
            variants.update({"0" + phone[4:], phone[1:]})
        return list(variants)

    @classmethod
    def _match(cls, queryset, *, phone, email, label):
        phone_matches = list(queryset.filter(phone_number__in=cls.phone_variants(phone)).order_by("pk")[:2]) if phone else []
        email_matches = list(queryset.filter(email__iexact=email).order_by("pk")[:2]) if email else []
        matches = {obj.pk: obj for obj in phone_matches + email_matches}
        if len(matches) > 1:
            raise ValidationError(f"Phone and email resolve to different existing {label} records.")
        return next(iter(matches.values()), None)

    @classmethod
    @transaction.atomic
    def resolve_parent(cls, *, phone_number, email=None, **profile):
        phone = cls.normalize_phone(phone_number)
        email = email.strip().lower() if email else None
        if not phone and not email:
            raise ValidationError("A phone number or email is required for parent identity resolution.")
        parent = cls._match(Parent.objects.select_for_update(), phone=phone, email=email, label="parent")
        user = cls._match(CustomUser.objects.select_for_update(), phone=phone, email=email, label="user")
        if parent:
            if user and parent.user_id and parent.user_id != user.pk:
                raise ValidationError("Parent and user identifiers resolve to different identities.")
            if not parent.user_id:
                parent.user = user or cls._create_user(phone=phone, email=email, **profile)
                parent.save(update_fields=["user"])
            cls._ensure_parent_role(parent.user)
            return parent
        if user and Parent.objects.filter(user=user).exists():
            raise ValidationError("A parent profile for this user already exists.")
        user = user or cls._create_user(phone=phone, email=email, **profile)
        cls._ensure_parent_role(user)
        return Parent.objects.create(
            user=user, phone_number=phone, email=email,
            first_name=profile.get("first_name", ""), middle_name=profile.get("middle_name", ""),
            last_name=profile.get("last_name", ""), occupation=profile.get("occupation", ""),
            parent_type=profile.get("parent_type", ""), address=profile.get("address", ""),
        )

    @classmethod
    def _create_user(cls, *, phone, email, **profile):
        user = CustomUser(
            email=email or f"parent_{(phone or 'unknown').replace('+', '')}@ssyncportal.local",
            phone_number=phone, first_name=profile.get("first_name", "") or "",
            middle_name=profile.get("middle_name", "") or "", last_name=profile.get("last_name", "") or "",
            is_parent=True, is_active=True,
        )
        user.set_unusable_password()
        user.save()
        cls._ensure_parent_role(user)
        return user

    @staticmethod
    def _ensure_parent_role(user):
        if not user.is_parent:
            user.is_parent = True
            user.save(update_fields=["is_parent"])
        group, _ = Group.objects.get_or_create(name="parent")
        user.groups.add(group)

    @classmethod
    @transaction.atomic
    def sync_user(cls, parent):
        if not parent.user_id:
            return None
        user = CustomUser.objects.select_for_update().get(pk=parent.user_id)
        phone = cls.normalize_phone(parent.phone_number)
        email = parent.email.strip().lower() if parent.email else user.email
        others = CustomUser.objects.exclude(pk=user.pk)
        if email and others.filter(email__iexact=email).exists():
            raise ValidationError("Another user already uses this email address.")
        if phone and others.filter(phone_number__in=cls.phone_variants(phone)).exists():
            raise ValidationError("Another user already uses this phone number.")
        user.email, user.phone_number = email, phone
        user.first_name, user.middle_name, user.last_name = parent.first_name or "", parent.middle_name or "", parent.last_name or ""
        user.is_parent = True
        user.save(update_fields=["email", "phone_number", "first_name", "middle_name", "last_name", "is_parent"])
        cls._ensure_parent_role(user)
        return user
