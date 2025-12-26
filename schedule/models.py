from django.db import models
from django.core.exceptions import ValidationError

from academic.models import ClassRoom, Teacher, AllocatedSubject


class Period(models.Model):
    """
    Represents a timetable period/schedule entry.
    Defines when a subject is taught to a classroom.
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

    day_of_week = models.CharField(
        max_length=10,
        choices=DAYS_OF_WEEK,
        help_text="Day of the week"
    )
    start_time = models.TimeField(help_text="Start time of the class")
    end_time = models.TimeField(help_text="End time of the class")
    classroom = models.ForeignKey(
        ClassRoom,
        on_delete=models.CASCADE,
        related_name='periods',
        help_text="Classroom this period is for"
    )
    subject = models.ForeignKey(
        AllocatedSubject,
        on_delete=models.CASCADE,
        related_name='periods',
        help_text="Subject being taught"
    )
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='periods',
        help_text="Teacher assigned to teach this session"
    )

    # Additional fields
    room_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Physical room where class takes place"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this period is currently active"
    )
    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Additional notes about this period"
    )

    class Meta:
        unique_together = ("day_of_week", "start_time", "classroom")
        ordering = ['day_of_week', 'start_time']
        verbose_name = "Period"
        verbose_name_plural = "Periods"
        indexes = [
            models.Index(fields=['classroom', 'day_of_week', 'start_time']),
            models.Index(fields=['teacher', 'day_of_week', 'start_time']),
        ]

    def __str__(self):
        return f"{self.classroom} - {self.subject} ({self.day_of_week} {self.start_time}-{self.end_time})"

    def clean(self):
        """
        Validate period to prevent conflicts.
        Checks for:
        1. Time validity (end_time > start_time)
        2. Classroom conflicts (same classroom, same day, overlapping times)
        3. Teacher conflicts (same teacher, same day, overlapping times)
        """
        super().clean()

        # 1. Validate time order
        if self.start_time and self.end_time:
            if self.end_time <= self.start_time:
                raise ValidationError({
                    'end_time': 'End time must be after start time.'
                })

        # 2. Check for classroom conflicts
        if self.classroom and self.day_of_week and self.start_time and self.end_time and self.is_active:
            classroom_conflicts = Period.objects.filter(
                classroom=self.classroom,
                day_of_week=self.day_of_week,
                is_active=True
            ).exclude(pk=self.pk if self.pk else None)

            for period in classroom_conflicts:
                # Check if times overlap
                # Overlap occurs if: start_time < other.end_time AND end_time > other.start_time
                if (self.start_time < period.end_time and self.end_time > period.start_time):
                    raise ValidationError({
                        '__all__': f'Classroom conflict: {self.classroom} is already scheduled for '
                                 f'{self.day_of_week} from {period.start_time.strftime("%H:%M")} to '
                                 f'{period.end_time.strftime("%H:%M")} (Subject: {period.subject}).'
                    })

        # 3. Check for teacher conflicts
        if self.teacher and self.day_of_week and self.start_time and self.end_time and self.is_active:
            teacher_conflicts = Period.objects.filter(
                teacher=self.teacher,
                day_of_week=self.day_of_week,
                is_active=True
            ).exclude(pk=self.pk if self.pk else None)

            for period in teacher_conflicts:
                # Check if times overlap
                if (self.start_time < period.end_time and self.end_time > period.start_time):
                    raise ValidationError({
                        '__all__': f'Teacher conflict: {self.teacher} is already scheduled for '
                                 f'{self.day_of_week} from {period.start_time.strftime("%H:%M")} to '
                                 f'{period.end_time.strftime("%H:%M")} '
                                 f'(Classroom: {period.classroom}, Subject: {period.subject}).'
                    })

    def save(self, *args, **kwargs):
        """Run validation before saving"""
        self.full_clean()
        super().save(*args, **kwargs)
