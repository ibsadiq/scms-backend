from django.db import models
from django.core.exceptions import ValidationError

from academic.models import ClassRoom, Teacher, AllocatedSubject, Term


class Room(models.Model):
    """
    Physical room a class can be held in. Replaces the old free-text room_number.
    """
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, blank=True, null=True)
    capacity = models.PositiveIntegerField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class PeriodSlot(models.Model):
    """
    Defines the school's daily time grid for a given term — e.g. 'Period 3 on
    Tuesday runs 9:40-10:20'. This is shared infrastructure, not tied to any
    one class or subject. TimetableEntry references this instead of storing
    its own start/end time.
    """
    DAYS_OF_WEEK = [
        ("Monday", "Monday"),
        ("Tuesday", "Tuesday"),
        ("Wednesday", "Wednesday"),
        ("Thursday", "Thursday"),
        ("Friday", "Friday"),
        ("Saturday", "Saturday"),
        ("Sunday", "Sunday"),
    ]

    term = models.ForeignKey(
        Term, on_delete=models.CASCADE, related_name='period_slots'
    )
    day_of_week = models.CharField(max_length=10, choices=DAYS_OF_WEEK)
    period_number = models.PositiveSmallIntegerField(
        help_text="Ordinal position in the day, e.g. 1, 2, 3. Breaks get a number too so ordering stays correct."
    )
    label = models.CharField(
        max_length=50,
        blank=True,
        help_text="Optional display label, e.g. 'Period 1' or 'Break'. Defaults to period_number if blank."
    )
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_break = models.BooleanField(
        default=False,
        help_text="Break periods are excluded from subject/teacher assignment."
    )

    class Meta:
        unique_together = ("term", "day_of_week", "period_number")
        ordering = ['term', 'day_of_week', 'period_number']
        indexes = [
            models.Index(fields=['term', 'day_of_week']),
        ]

    def __str__(self):
        return f"{self.term} - {self.day_of_week} P{self.period_number} ({self.start_time}-{self.end_time})"

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({'end_time': 'End time must be after start time.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class TeacherAvailability(models.Model):
    """
    Optional per-teacher constraint used by the auto-generation algorithm and
    by conflict checks (e.g. a teacher who only works mornings, or is on
    leave for a given slot).
    """
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name='teacher_availabilities')
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name='availabilities')
    slot = models.ForeignKey(PeriodSlot, on_delete=models.CASCADE, related_name='teacher_availabilities')
    is_available = models.BooleanField(default=True)

    class Meta:
        unique_together = ("teacher", "slot")
        indexes = [
            models.Index(fields=['teacher', 'term']),
        ]

    def __str__(self):
        return f"{self.teacher} - {self.slot} ({'available' if self.is_available else 'unavailable'})"


class TimetableEntry(models.Model):
    """
    A single assignment: this class has this subject (or activity, or is
    free) during this slot, optionally with a teacher and room.
    """
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name='timetable_entries')
    slot = models.ForeignKey(PeriodSlot, on_delete=models.PROTECT, null=True, blank=True, related_name='timetable_entries')
    classroom = models.ForeignKey(ClassRoom, on_delete=models.CASCADE, related_name='timetable_entries')

    subject = models.ForeignKey(
        AllocatedSubject, on_delete=models.PROTECT, null=True, blank=True,
        related_name='timetable_entries',
        help_text="Leave blank for free periods or non-subject activities."
    )
    activity_label = models.CharField(
        max_length=100, blank=True,
        help_text="e.g. 'Assembly', 'Extra-Moral Lesson', 'Library Period'. Used when subject is blank and this isn't a free period."
    )
    is_free_period = models.BooleanField(
        default=False,
        help_text="Explicitly marks this slot as free for this classroom."
    )

    teacher = models.ForeignKey(
        Teacher, on_delete=models.SET_NULL, null=True, blank=True, related_name='timetable_entries'
    )
    room = models.ForeignKey(
        Room, on_delete=models.SET_NULL, null=True, blank=True, related_name='timetable_entries'
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ("term", "slot", "classroom")
        ordering = ['slot__day_of_week', 'slot__period_number']
        indexes = [
            models.Index(fields=['classroom', 'term']),
            models.Index(fields=['teacher', 'term']),
            models.Index(fields=['room', 'term']),
        ]

    def __str__(self):
        if self.is_free_period:
            return f"{self.classroom} - Free ({self.slot})"
        if self.activity_label:
            return f"{self.classroom} - {self.activity_label} ({self.slot})"
        return f"{self.classroom} - {self.subject} ({self.slot})"

    def clean(self):
        super().clean()

        if not self.slot_id:
            return

        # Exactly one of: real subject / named activity / free period
        filled = [bool(self.subject_id), bool(self.activity_label), self.is_free_period]
        if sum(filled) == 0:
            raise ValidationError('Provide a subject, an activity_label, or mark this as a free period.')
        if sum(filled) > 1:
            raise ValidationError('An entry can only be one of: subject, activity, or free period — not a combination.')

        if self.slot.is_break and (self.subject_id or self.teacher_id or self.activity_label):
            raise ValidationError({'slot': 'Cannot assign a subject/activity/teacher to a break slot.'})

        # Teacher conflict: same teacher, same term, same slot, different classroom
        if self.teacher_id and self.is_active:
            conflict = TimetableEntry.objects.filter(
                term=self.term, slot=self.slot, teacher_id=self.teacher_id, is_active=True,
            ).exclude(pk=self.pk).exclude(classroom=self.classroom)
            existing = conflict.select_related('classroom').first()
            if existing:
                raise ValidationError({
                    '__all__': f'Teacher conflict: {self.teacher} is already engaged with '
                               f'{existing.classroom} during {self.slot}.'
                })

        # Room conflict: same room, same term, same slot, different classroom
        if self.room_id and self.is_active:
            conflict = TimetableEntry.objects.filter(
                term=self.term, slot=self.slot, room_id=self.room_id, is_active=True,
            ).exclude(pk=self.pk).exclude(classroom=self.classroom)
            existing = conflict.select_related('classroom').first()
            if existing:
                raise ValidationError({
                    '__all__': f'Room conflict: {self.room} is already booked by '
                               f'{existing.classroom} during {self.slot}.'
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)