from django.db import transaction
from django.db.models import Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from .messaging_policy import MessagingPolicy
from .models import DirectMessage
from .serializers import DirectMessageCreateSerializer, DirectMessageSerializer


class DirectMessageCreateThrottle(UserRateThrottle):
    scope = "direct_message_create"


def _display_name(user):
    name = " ".join(filter(None, (user.first_name, user.last_name))).strip()
    if name:
        return name
    labels = {
        "admin": "School Administrator", "teacher": "Teacher",
        "parent": "Parent", "student": "Student", "accountant": "Accountant",
        "staff": "Staff",
    }
    return labels[_role(user)]


def _role(user):
    if MessagingPolicy.is_admin(user):
        return "admin"
    for flag, role in (
        ("is_teacher", "teacher"), ("is_parent", "parent"),
        ("is_student", "student"), ("is_accountant", "accountant"),
    ):
        if getattr(user, flag, False):
            return role
    return "staff"


class DirectMessageViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """Immutable two-party direct messages with policy-scoped discovery."""

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        return DirectMessageCreateSerializer if self.action == "create" else DirectMessageSerializer

    def get_queryset(self):
        user = self.request.user
        return DirectMessage.objects.filter(
            Q(sender=user) | Q(recipient=user)
        ).select_related(
            "sender", "recipient", "student", "parent_message"
        ).order_by("-created_at", "-pk")

    def get_throttles(self):
        return [DirectMessageCreateThrottle()] if self.action == "create" else []

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = serializer.save(sender=request.user)
        return Response(
            DirectMessageSerializer(message, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        message = self.get_object()
        if message.recipient_id != request.user.pk:
            raise PermissionDenied("Only the recipient may mark this message as read.")
        if not message.is_read:
            message.is_read = True
            message.save(update_fields=("is_read",))
        return Response({"status": "Message marked as read"})

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        count = DirectMessage.objects.filter(
            recipient=request.user, is_read=False,
        ).count()
        return Response({"unread_count": count})

    @action(detail=False, methods=["get"])
    def recipients(self, request):
        contacts = MessagingPolicy.allowed_recipient_queryset(request.user)
        return Response([{
            "user_id": user.pk,
            "display_name": _display_name(user),
            "role": _role(user),
            "relationship": "school_admin" if MessagingPolicy.is_admin(user) else "authorized_contact",
        } for user in contacts.order_by("first_name", "last_name", "pk")])

    @action(detail=False, methods=["get"])
    def classroom_parents(self, request):
        if not (
            MessagingPolicy.is_admin(request.user)
            or getattr(request.user, "teacher", None)
        ):
            raise PermissionDenied("Family contact enumeration is unavailable.")
        students = MessagingPolicy.classroom_family_students(
            request.user, request.query_params.get("classroom_id"),
        )
        rows = []
        for student in students:
            parent = student.parent_guardian
            parent_user = parent.user if parent else None
            if not parent_user:
                continue
            rows.append({
                "student_id": student.pk,
                "student_name": student.full_name,
                "classroom": str(student.classroom) if student.classroom else "",
                "parent_user_id": parent_user.pk,
                "parent_name": _display_name(parent_user),
            })
        return Response(rows)

    @action(detail=False, methods=["get"])
    def school_admins(self, request):
        return Response([{
            "user_id": admin.pk,
            "display_name": _display_name(admin),
            "role": "admin",
        } for admin in MessagingPolicy.admin_queryset().order_by(
            "first_name", "last_name", "pk"
        )])
