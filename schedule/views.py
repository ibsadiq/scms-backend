from django.db import transaction
from django.core.management import call_command
from django.core.management.base import CommandError
from io import StringIO

from rest_framework import viewsets, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action

from .models import PeriodSlot, TimetableEntry, Room, TeacherAvailability
from .serializers import (
    PeriodSlotSerializer, RoomSerializer, TeacherAvailabilitySerializer,
    TimetableEntryListSerializer, TimetableEntryWriteSerializer,
    BulkCopyTimetableSerializer, BulkActivitySerializer,
)
from academic.models import ClassRoom


def is_user_admin(user):
    if not user or not user.is_authenticated:
        return False
    return bool(
        getattr(user, "is_admin", False) or
        getattr(user, "is_staff", False) or
        getattr(user, "is_superuser", False)
    )


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Admins (and homeroom-equivalent staff, if you want to extend this) can
    write. Everyone authenticated can read — actual row-level scoping for
    teachers/parents happens in get_queryset, not here.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return is_user_admin(request.user)


class RoomViewSet(viewsets.ModelViewSet):
    queryset = Room.objects.filter(is_active=True)
    serializer_class = RoomSerializer
    permission_classes = [IsAdminOrReadOnly]
    pagination_class = None


class PeriodSlotViewSet(viewsets.ModelViewSet):
    queryset = PeriodSlot.objects.all()
    serializer_class = PeriodSlotSerializer
    permission_classes = [IsAdminOrReadOnly]
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        term = self.request.query_params.get("term")
        if term:
            qs = qs.filter(term_id=term)
        return qs


class TeacherAvailabilityViewSet(viewsets.ModelViewSet):
    queryset = TeacherAvailability.objects.all()
    serializer_class = TeacherAvailabilitySerializer
    permission_classes = [IsAdminOrReadOnly]
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        if not getattr(self.request.user, "is_admin", False):
            qs = qs.filter(teacher__user=self.request.user)
        return qs


class TimetableEntryViewSet(viewsets.ModelViewSet):
    queryset = TimetableEntry.objects.select_related(
        "slot", "classroom", "subject", "subject__subject", "teacher", "room"
    ).order_by("slot__day_of_week", "slot__period_number")
    permission_classes = [IsAdminOrReadOnly]
    pagination_class = None

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return TimetableEntryWriteSerializer
        return TimetableEntryListSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        term = self.request.query_params.get("term")
        if term:
            qs = qs.filter(term_id=term)

        classroom_id = self.request.query_params.get("classroom")
        if classroom_id:
            qs = qs.filter(classroom_id=classroom_id)

        teacher_id = self.request.query_params.get("teacher")
        if teacher_id:
            qs = qs.filter(teacher_id=teacher_id)

        if not getattr(user, "is_admin", False):
            if getattr(user, "is_teacher", False):
                qs = qs.filter(teacher__user=user)
            elif hasattr(user, "student_profile") and user.student_profile:
                qs = qs.filter(classroom=user.student_profile.classroom)
            elif hasattr(user, "parent") and user.parent:
                child_classrooms = user.parent.children.values_list("classroom", flat=True)
                qs = qs.filter(classroom__in=child_classrooms)
            else:
                qs = qs.none()

        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        instance = serializer.instance
        return Response(
            TimetableEntryListSerializer(instance).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(TimetableEntryListSerializer(serializer.instance).data)

    @action(detail=False, methods=["get"])
    def by_classroom(self, request):
        classroom_id = request.query_params.get("classroom")
        if not classroom_id:
            return Response({"error": "classroom parameter is required"}, status=400)
        qs = self.get_queryset().filter(classroom_id=classroom_id)
        return Response(TimetableEntryListSerializer(qs, many=True).data)

    @action(detail=False, methods=["get"])
    def by_teacher(self, request):
        teacher_id = request.query_params.get("teacher")
        if not teacher_id:
            return Response({"error": "teacher parameter is required"}, status=400)
        qs = self.get_queryset().filter(teacher_id=teacher_id)
        return Response(TimetableEntryListSerializer(qs, many=True).data)

    @action(detail=False, methods=["get"])
    def my_timetable(self, request):
        """
        Resolves from request.user by default — admins can pass ?teacher=id
        explicitly to look someone up.
        """
        user = request.user
        qs = self.get_queryset()

        teacher_id = request.query_params.get("teacher")
        if teacher_id and getattr(user, "is_admin", False):
            qs = qs.filter(teacher_id=teacher_id)
        elif getattr(user, "is_teacher", False):
            qs = qs.filter(teacher__user=user)
        else:
            return Response({"error": "No timetable available for this user."}, status=403)

        return Response(TimetableEntryListSerializer(qs, many=True).data)

    @action(detail=False, methods=["post"])
    def swap(self, request):
        """
        Atomically swap content between two timetable entries without triggering unique constraint errors or null constraint violations.
        """
        entry_a_id = request.data.get("entry_a")
        entry_b_id = request.data.get("entry_b")
        if not entry_a_id or not entry_b_id:
            return Response({"error": "entry_a and entry_b are required"}, status=400)

        with transaction.atomic():
            from django.shortcuts import get_object_or_404
            entry_a = get_object_or_404(TimetableEntry, id=entry_a_id)
            entry_b = get_object_or_404(TimetableEntry, id=entry_b_id)

            # Swap content attributes between entry_a and entry_b
            (
                entry_a.subject, entry_b.subject,
                entry_a.activity_label, entry_b.activity_label,
                entry_a.is_free_period, entry_b.is_free_period,
                entry_a.teacher, entry_b.teacher,
                entry_a.room, entry_b.room,
                entry_a.notes, entry_b.notes,
                entry_a.is_active, entry_b.is_active,
            ) = (
                entry_b.subject, entry_a.subject,
                entry_b.activity_label, entry_a.activity_label,
                entry_b.is_free_period, entry_a.is_free_period,
                entry_b.teacher, entry_a.teacher,
                entry_b.room, entry_a.room,
                entry_b.notes, entry_a.notes,
                entry_b.is_active, entry_a.is_active,
            )

            entry_a.save()
            entry_b.save()

        return Response({
            "status": "success",
            "message": "Slots swapped successfully",
            "entry_a": TimetableEntryListSerializer(entry_a).data,
            "entry_b": TimetableEntryListSerializer(entry_b).data,
        })

    @action(detail=False, methods=["post"])
    def bulk_copy(self, request):
        """
        Copies every entry from source_classroom to target_classroom for a
        given term, in one atomic transaction.
        """
        serializer = BulkCopyTimetableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        source_entries = TimetableEntry.objects.filter(
            classroom=data["source_classroom"], term=data["term"], is_active=True
        ).select_related("slot")

        created, skipped = [], []

        with transaction.atomic():
            if data["overwrite"]:
                TimetableEntry.objects.filter(
                    classroom=data["target_classroom"], term=data["term"]
                ).update(is_active=False)

            for entry in source_entries:
                new_entry = TimetableEntry(
                    term=data["term"],
                    slot=entry.slot,
                    classroom=data["target_classroom"],
                    subject=entry.subject,
                    activity_label=entry.activity_label,
                    is_free_period=entry.is_free_period,
                    teacher=entry.teacher,
                    room=entry.room,
                    notes=entry.notes,
                )
                try:
                    new_entry.full_clean()
                    new_entry.save()
                    created.append(new_entry.id)
                except Exception as e:
                    skipped.append({"slot": str(entry.slot), "reason": str(e)})

        return Response({
            "created_count": len(created),
            "skipped": skipped,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=False, methods=["post"])
    def bulk_activity(self, request):
        """
        Apply an activity or free period to a slot across every classroom
        that doesn't already have an active entry there (or all, if
        overwrite=True). E.g. Friday's Extra-Moral Lesson, school-wide Assembly.
        """
        serializer = BulkActivitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        all_classrooms = ClassRoom.objects.all()
        created, skipped = [], []

        with transaction.atomic():
            if data["overwrite"]:
                TimetableEntry.objects.filter(
                    term=data["term"], slot=data["slot"]
                ).update(is_active=False)

            for classroom in all_classrooms:
                if not data["overwrite"]:
                    exists = TimetableEntry.objects.filter(
                        term=data["term"], slot=data["slot"], classroom=classroom, is_active=True
                    ).exists()
                    if exists:
                        skipped.append({"classroom": str(classroom), "reason": "already has an active entry"})
                        continue

                entry = TimetableEntry(
                    term=data["term"], slot=data["slot"], classroom=classroom,
                    activity_label=data.get("activity_label", ""),
                    is_free_period=data["is_free_period"],
                    teacher=data.get("teacher"), room=data.get("room"),
                )
                try:
                    entry.full_clean()
                    entry.save()
                    created.append(entry.id)
                except Exception as e:
                    skipped.append({"classroom": str(classroom), "reason": str(e)})

        return Response({
            "created_count": len(created),
            "skipped": skipped,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class GenerateTimetableView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        if not is_user_admin(request.user):
            return Response({"error": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

        term_id = request.data.get("term")
        if not term_id:
            return Response({"error": "term is required"}, status=400)

        dry_run = bool(request.data.get("dry_run", False))
        max_backtracks = request.data.get("max_backtracks", 5000)

        try:
            max_backtracks = int(max_backtracks)
        except (TypeError, ValueError):
            return Response({"error": "max_backtracks must be an integer"}, status=400)

        command_args = ["--term", str(term_id), "--max-backtracks", str(max_backtracks)]
        if dry_run:
            command_args.append("--dry-run")

        output = StringIO()
        try:
            call_command("generate_timetable", *command_args, stdout=output)
            return Response({
                "status": "success",
                "dry_run": dry_run,
                "message": output.getvalue(),
            })
        except CommandError as e:
            return Response({"status": "error", "message": str(e)}, status=400)
        except Exception as e:
            return Response({"status": "error", "message": str(e)}, status=500)