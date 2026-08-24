from django.core.exceptions import ValidationError
from django.db.models import Q
from academic.models import Parent
from users.models import CustomUser


class ParentIdentityService:
    @classmethod
    def resolve_parent(
        cls,
        *,
        phone_number,
        email=None,
        first_name="",
        last_name="",
        occupation="",
        parent_type="",
        address=""
    ):
        """
        Resolves or creates a parent record deterministically.
        It searches existing Parents and Users by phone and email.
        Raises ValidationError if conflicting records exist.
        """
        if not phone_number and not email:
            raise ValidationError("A phone number or email is required for parent identity resolution.")

        query = Q()
        if phone_number:
            query |= Q(phone_number=phone_number)
        if email:
            query |= Q(email__iexact=email)

        matches = list(Parent.objects.select_for_update().filter(query).order_by("pk"))
        if len({parent.pk for parent in matches}) > 1:
            raise ValidationError(
                "Parent email and phone resolve to different existing parent records."
            )
        if matches:
            return matches[0]

        users = list(CustomUser.objects.filter(query).order_by("pk"))
        if len({user.pk for user in users}) > 1:
            raise ValidationError(
                "Parent email and phone resolve to different existing user accounts."
            )
        user = users[0] if users else None
        
        if user and not user.is_parent:
            user.is_parent = True
            user.save(update_fields=("is_parent",))
            
        if not user:
            # Require at least phone or email for custom user creation.
            if not email:
                raise ValidationError("Parent email is required to create a new user account.")
            
            user = CustomUser(
                email=email,
                phone_number=phone_number,
                first_name=first_name,
                last_name=last_name,
                is_parent=True,
                is_active=True,
            )
            user.set_unusable_password()
            user.save()
            
        return Parent.objects.create(
            user=user,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone_number=phone_number,
            occupation=occupation,
            parent_type=parent_type,
            address=address,
        )
