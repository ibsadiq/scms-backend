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
    def _phone_matches(cls, phone_a, phone_b):
        if not phone_a or not phone_b:
            return False
        variants_a = set(cls.phone_variants(phone_a))
        variants_b = set(cls.phone_variants(phone_b))
        return bool(variants_a & variants_b)

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

        # 1. Resolve candidate Parent and User records
        parent_candidate = cls._match(Parent.objects.select_for_update(), phone=phone, email=email, label="parent")
        user_candidate = cls._match(CustomUser.objects.select_for_update(), phone=phone, email=email, label="user") if (phone or email) else None

        # 2. Cross-identifier consistency validations
        if user_candidate:
            if user_candidate.phone_number and phone and not cls._phone_matches(user_candidate.phone_number, phone):
                raise ValidationError("Parent and user identifiers resolve to different identities.")
            if user_candidate.email and email and user_candidate.email.strip().lower() != email:
                raise ValidationError("Parent and user identifiers resolve to different identities.")

        if parent_candidate:
            if user_candidate:
                if parent_candidate.user_id and parent_candidate.user_id != user_candidate.pk:
                    raise ValidationError("Parent and user identifiers resolve to different identities.")
                if Parent.objects.filter(user=user_candidate).exclude(pk=parent_candidate.pk).exists():
                    raise ValidationError("Parent and user identifiers resolve to different identities.")
                if parent_candidate.email and user_candidate.email and parent_candidate.email.strip().lower() != user_candidate.email.strip().lower():
                    raise ValidationError("Parent and user identifiers resolve to different identities.")
                if parent_candidate.phone_number and user_candidate.phone_number and not cls._phone_matches(parent_candidate.phone_number, user_candidate.phone_number):
                    raise ValidationError("Parent and user identifiers resolve to different identities.")

            if parent_candidate.phone_number and phone and not cls._phone_matches(parent_candidate.phone_number, phone):
                raise ValidationError("Parent and user identifiers resolve to different identities.")
            if parent_candidate.email and email and parent_candidate.email.strip().lower() != email:
                raise ValidationError("Parent and user identifiers resolve to different identities.")
            if parent_candidate.user:
                if parent_candidate.user.phone_number and phone and not cls._phone_matches(parent_candidate.user.phone_number, phone):
                    raise ValidationError("Parent and user identifiers resolve to different identities.")
                if parent_candidate.user.email and email and parent_candidate.user.email.strip().lower() != email:
                    raise ValidationError("Parent and user identifiers resolve to different identities.")

            if not parent_candidate.user_id and email:
                parent_candidate.user = user_candidate or cls._create_user(phone=phone, email=email, **profile)
                update_fields = ["user"]
                if not parent_candidate.email:
                    parent_candidate.email = email
                    update_fields.append("email")
                parent_candidate.save(update_fields=update_fields)
            elif not parent_candidate.email and email:
                parent_candidate.email = email
                parent_candidate.save(update_fields=["email"])

            if parent_candidate.user:
                cls._ensure_parent_role(parent_candidate.user)
            return parent_candidate

        if user_candidate and Parent.objects.filter(user=user_candidate).exists():
            raise ValidationError("A parent profile for this user already exists.")

        user = user_candidate
        if not user and email:
            user = cls._create_user(phone=phone, email=email, **profile)
        if user:
            cls._ensure_parent_role(user)

        return Parent.objects.create(
            user=user, phone_number=phone, email=email,
            first_name=profile.get("first_name", ""), middle_name=profile.get("middle_name", ""),
            last_name=profile.get("last_name", ""), occupation=profile.get("occupation", ""),
            parent_type=profile.get("parent_type", ""), address=profile.get("address", ""),
        )

    @classmethod
    def _create_user(cls, *, phone, email, **profile):
        if not email:
            return None
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise ValidationError("A user with this email address already exists.")
        if phone and CustomUser.objects.filter(phone_number__in=cls.phone_variants(phone)).exists():
            raise ValidationError("A user with this phone number already exists.")
        user = CustomUser(
            email=email,
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
