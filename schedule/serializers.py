from rest_framework import serializers
from django.utils import timezone

from .models import PeriodSlot, TeacherAvailability, TimetableEntry, Room
from academic.models import AllocatedSubject, ClassRoom, Teacher, Term


class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = ["id", "name", "code", "capacity", "is_active"]
        read_only_fields = ["id"]


class PeriodSlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = PeriodSlot
        fields = [
            "id", "term", "day_of_week", "period_number",
            "label", "start_time", "end_time", "is_break",
        ]
        read_only_fields = ["id"]

    def validate(self, data):
        start = data.get("start_time")
        end = data.get("end_time")
        if start and end and end <= start:
            raise serializers.ValidationError({"end_time": "End time must be after start time."})
        return data


class TeacherAvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherAvailability
        fields = ["id", "term", "teacher", "slot", "is_available"]
        read_only_fields = ["id"]


class TimetableEntryListSerializer(serializers.ModelSerializer):
    day_of_week = serializers.CharField(source="slot.day_of_week", read_only=True)
    period_number = serializers.IntegerField(source="slot.period_number", read_only=True)
    start_time = serializers.TimeField(source="slot.start_time", read_only=True)
    end_time = serializers.TimeField(source="slot.end_time", read_only=True)
    is_break = serializers.BooleanField(source="slot.is_break", read_only=True)

    teacher_name = serializers.SerializerMethodField()
    subject_name = serializers.SerializerMethodField()
    classroom_name = serializers.SerializerMethodField()
    room_name = serializers.CharField(source="room.name", read_only=True, default=None)
    display_label = serializers.SerializerMethodField()

    class Meta:
        model = TimetableEntry
        fields = [
            "id", "term", "slot",
            "day_of_week", "period_number", "start_time", "end_time", "is_break",
            "classroom", "classroom_name",
            "subject", "subject_name",
            "activity_label", "is_free_period", "display_label",
            "teacher", "teacher_name",
            "room", "room_name",
            "is_active", "notes",
        ]
        read_only_fields = ["id"]

    def get_teacher_name(self, obj):
        return f"{obj.teacher.first_name} {obj.teacher.last_name}" if obj.teacher else None

    def get_subject_name(self, obj):
        return obj.subject.subject.name if obj.subject and obj.subject.subject_id else None

    def get_classroom_name(self, obj):
        return str(obj.classroom) if obj.classroom_id else None

    def get_display_label(self, obj):
        """What the frontend grid actually renders in the cell."""
        if obj.is_free_period:
            return "Free"
        if obj.activity_label:
            return obj.activity_label
        return self.get_subject_name(obj)


class TimetableEntryWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimetableEntry
        fields = [
            "id", "term", "slot", "classroom", "subject",
            "activity_label", "is_free_period",
            "teacher", "room", "is_active", "notes",
        ]
        read_only_fields = ["id"]

    def validate(self, data):
        subject = data.get("subject") or getattr(self.instance, "subject", None)
        activity_label = data.get("activity_label", getattr(self.instance, "activity_label", ""))
        is_free_period = data.get("is_free_period", getattr(self.instance, "is_free_period", False))
        teacher = data.get("teacher") or getattr(self.instance, "teacher", None)

        filled = [bool(subject), bool(activity_label), is_free_period]
        if sum(filled) == 0:
            raise serializers.ValidationError("Provide a subject, an activity_label, or mark this as a free period.")
        if sum(filled) > 1:
            raise serializers.ValidationError("An entry can only be one of: subject, activity, or free period.")

        if subject and teacher:
            allocated_teacher_id = subject.teacher_name_id
            if allocated_teacher_id and allocated_teacher_id != teacher.id:
                raise serializers.ValidationError({
                    "teacher": f"{teacher} is not the allocated teacher for {subject}."
                })

        slot = data.get("slot") or getattr(self.instance, "slot", None)
        if slot and slot.is_break and (subject or teacher or activity_label):
            raise serializers.ValidationError({"slot": "Cannot assign a subject/activity/teacher to a break slot."})

        # Weekly/daily caps — only meaningful when a real subject is set
        if subject and slot:
            classroom = data.get("classroom") or getattr(self.instance, "classroom", None)
            term = data.get("term") or getattr(self.instance, "term", None)
            if classroom and term:
                existing = TimetableEntry.objects.filter(
                    subject=subject, classroom=classroom, term=term, is_active=True
                ).exclude(pk=getattr(self.instance, "pk", None))

                weekly_count = existing.count() + 1
                if weekly_count > subject.weekly_periods:
                    raise serializers.ValidationError({
                        "subject": f"{subject} already has {existing.count()} periods/week scheduled "
                                   f"for {classroom} (max {subject.weekly_periods})."
                    })

                daily_count = existing.filter(slot__day_of_week=slot.day_of_week).count() + 1
                if daily_count > subject.max_daily_periods:
                    raise serializers.ValidationError({
                        "subject": f"{subject} already has {daily_count - 1} periods on "
                                   f"{slot.day_of_week} for {classroom} (max {subject.max_daily_periods}/day)."
                    })

        return data

    def _run_model_validation(self, instance):
        try:
            instance.full_clean()
        except Exception as e:
            if hasattr(e, "message_dict"):
                raise serializers.ValidationError(e.message_dict)
            raise serializers.ValidationError({"non_field_errors": e.messages if hasattr(e, "messages") else [str(e)]})

    def create(self, validated_data):
        instance = TimetableEntry(**validated_data)
        self._run_model_validation(instance)
        instance.save()
        return instance

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        self._run_model_validation(instance)
        instance.save()
        return instance


class BulkActivitySerializer(serializers.Serializer):
    """
    Apply the same activity (or free period) to a given slot across
    every classroom in the school in one call — e.g. Friday's Extra-Moral
    Lesson, or a school-wide Assembly slot.
    """
    term = serializers.PrimaryKeyRelatedField(queryset=Term.objects.all())
    slot = serializers.PrimaryKeyRelatedField(queryset=PeriodSlot.objects.all())
    activity_label = serializers.CharField(required=False, allow_blank=True, default="")
    is_free_period = serializers.BooleanField(default=False)
    teacher = serializers.PrimaryKeyRelatedField(queryset=Teacher.objects.all(), required=False, allow_null=True)
    room = serializers.PrimaryKeyRelatedField(queryset=Room.objects.all(), required=False, allow_null=True)
    overwrite = serializers.BooleanField(default=False)

    def validate(self, data):
        if not data.get("activity_label") and not data.get("is_free_period"):
            raise serializers.ValidationError("Provide activity_label or set is_free_period=True.")
        if data.get("activity_label") and data.get("is_free_period"):
            raise serializers.ValidationError("Cannot set both activity_label and is_free_period.")
        return data

class BulkCopyTimetableSerializer(serializers.Serializer):
    """
    For the 'copy timetable to another class' UI feature.
    """
    source_classroom = serializers.PrimaryKeyRelatedField(queryset=ClassRoom.objects.all())
    target_classroom = serializers.PrimaryKeyRelatedField(queryset=ClassRoom.objects.all())
    term = serializers.PrimaryKeyRelatedField(queryset=TimetableEntry._meta.get_field("term").related_model.objects.all())
    overwrite = serializers.BooleanField(default=False)

    def validate(self, data):
        if data["source_classroom"] == data["target_classroom"]:
            raise serializers.ValidationError("Source and target classroom must differ.")
        return data