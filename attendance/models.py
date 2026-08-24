from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError

from academic.models import Staff, Student, Teacher


# Create your models here.
class AttendanceStatus(models.Model):
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text='"Present" will not be saved but may show as an option for teachers.',
    )
    code = models.CharField(
        max_length=10,
        unique=True,
        help_text="Short code used on attendance reports. Example: 'A' might be the code for 'Absent'.",
    )
    excused = models.BooleanField(default=False)
    absent = models.BooleanField(
        default=False, help_text="Used for different types of absent statuses."
    )
    late = models.BooleanField(
        default=False, help_text="Used for tracking late statuses."
    )
    half = models.BooleanField(
        default=False,
        help_text="Indicates half-day attendance. Do not check absent, otherwise it will double count.",
    )

    class Meta:
        verbose_name_plural = "Attendance Statuses"

    def __str__(self):
        return self.name


class TeachersAttendance(models.Model):
    date = models.DateField(blank=True, null=True, validators=settings.DATE_VALIDATORS)
    teacher = models.ForeignKey(Teacher, blank=True, on_delete=models.CASCADE)
    time_in = models.TimeField(blank=True, null=True)
    time_out = models.TimeField(blank=True, null=True)
    status = models.ForeignKey(
        AttendanceStatus, blank=True, null=True, on_delete=models.CASCADE
    )
    notes = models.CharField(max_length=500, blank=True)

    class Meta:
        unique_together = (("teacher", "date", "status"),)
        ordering = ("-date", "teacher")

    def __str__(self):
        return f"{self.teacher} - {self.date} {self.status}"

    @property
    def edit(self):
        return f"Edit {self.teacher} - {self.date}"

class StudentAttendance(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField(validators=settings.DATE_VALIDATORS)
    ClassRoom = models.ForeignKey(
        "academic.ClassRoom", on_delete=models.CASCADE, blank=True, null=True, related_name='attendance_records'
    )
    term = models.ForeignKey(
        "administration.Term", on_delete=models.PROTECT, blank=True, null=True, related_name='attendance_records'
    )
    status = models.ForeignKey(
        AttendanceStatus, on_delete=models.PROTECT, related_name='student_attendance_records'
    )
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='marked_student_attendance'
    )
    notes = models.CharField(max_length=500, blank=True)
    time_in = models.TimeField(blank=True, null=True)
    time_out = models.TimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("student", "date"),)
        ordering = ("-date", "student")
        indexes = [
            models.Index(fields=["date", "ClassRoom"]),
            models.Index(fields=["student", "date"]),
            models.Index(fields=["term", "status"]),
        ]

    def __str__(self):
        return f"{self.student.full_name} - {self.date} {self.status}"

    @property
    def edit(self):
        return f"Edit {self.student.first_name or self.student.full_name} - {self.date}"

class AttendancePolicy(models.Model):
    singleton_key = models.BooleanField(default=True, unique=True, editable=False)
    device_attendance_enabled = models.BooleanField(default=False)
    student_late_after = models.TimeField(blank=True, null=True)
    staff_late_after = models.TimeField(blank=True, null=True)
    student_close_time = models.TimeField(blank=True, null=True)
    staff_close_time = models.TimeField(blank=True, null=True)
    device_duplicate_window_seconds = models.PositiveIntegerField(default=5)
    raw_scan_retention_days = models.PositiveIntegerField(
        blank=True, null=True, help_text="Raw scan retention. Blank disables automatic cleanup."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Attendance policies"

    def __str__(self):
        return "School attendance policy"


class StaffAttendance(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name="attendance_records")
    date = models.DateField(validators=settings.DATE_VALIDATORS)
    status = models.ForeignKey(AttendanceStatus, on_delete=models.PROTECT, related_name="staff_attendance_records")
    time_in = models.TimeField(blank=True, null=True)
    time_out = models.TimeField(blank=True, null=True)
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name="marked_staff_attendance", null=True, blank=True,
    )
    notes = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-date", "staff")
        constraints = [models.UniqueConstraint(fields=["staff", "date"], name="unique_staff_daily_attendance")]
        indexes = [models.Index(fields=["date", "status"]), models.Index(fields=["staff", "date"])]

    def __str__(self):
        return f"{self.staff} - {self.date} {self.status}"


class AttendanceEvent(models.Model):
    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        RFID = "RFID", "RFID"
        SYSTEM = "SYSTEM", "System"
        IMPORT = "IMPORT", "Import"

    class EventType(models.TextChoices):
        MARKED_PRESENT = "MARKED_PRESENT", "Marked present"
        MARKED_ABSENT = "MARKED_ABSENT", "Marked absent"
        MARKED_LATE = "MARKED_LATE", "Marked late"
        ENTRY = "ENTRY", "Entry"
        EXIT = "EXIT", "Exit"
        STATUS_CHANGED = "STATUS_CHANGED", "Status changed"
        MANUAL_CORRECTION = "MANUAL_CORRECTION", "Manual correction"

    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="attendance_events", null=True, blank=True)
    staff = models.ForeignKey(Staff, on_delete=models.PROTECT, related_name="attendance_events", null=True, blank=True)
    source = models.CharField(max_length=20, choices=Source.choices)
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    occurred_at = models.DateTimeField()
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name="performed_attendance_events", null=True, blank=True,
    )
    previous_state = models.JSONField(default=dict, blank=True)
    new_state = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-occurred_at", "-id")
        constraints = [models.CheckConstraint(
            condition=(models.Q(student__isnull=False, staff__isnull=True) | models.Q(student__isnull=True, staff__isnull=False)),
            name="attendance_event_exactly_one_subject",
        )]
        indexes = [
            models.Index(fields=["occurred_at", "source"]),
            models.Index(fields=["student", "occurred_at"]),
            models.Index(fields=["staff", "occurred_at"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Attendance events are immutable; create a correcting event instead.")
        super().save(*args, **kwargs)


class AttendanceDevice(models.Model):
    class Mode(models.TextChoices):
        ENTRY = "ENTRY", "Entry"
        EXIT = "EXIT", "Exit"
        BIDIRECTIONAL = "BIDIRECTIONAL", "Bidirectional"

    name = models.CharField(max_length=120)
    device_identifier = models.CharField(max_length=64, unique=True, db_index=True)
    mode = models.CharField(max_length=20, choices=Mode.choices)
    location = models.CharField(max_length=160, blank=True)
    secret_hash = models.CharField(max_length=255, editable=False)
    is_active = models.BooleanField(default=True, db_index=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    health_alert_state = models.CharField(max_length=10, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")
        indexes = [models.Index(fields=("is_active", "mode"))]

    def __str__(self):
        return self.name


class AttendanceScan(models.Model):
    class Direction(models.TextChoices):
        ENTRY = "ENTRY", "Entry"
        EXIT = "EXIT", "Exit"

    class Result(models.TextChoices):
        SUCCESS = "SUCCESS", "Success"
        UNKNOWN_CARD = "UNKNOWN_CARD", "Unknown card"
        REVOKED_CREDENTIAL = "REVOKED_CREDENTIAL", "Revoked credential"
        INACTIVE_CARD = "INACTIVE_CARD", "Inactive card"
        EXPIRED_CARD = "EXPIRED_CARD", "Expired card"
        INACTIVE_HOLDER = "INACTIVE_HOLDER", "Inactive holder"
        INACTIVE_DEVICE = "INACTIVE_DEVICE", "Inactive device"
        RFID_DISABLED = "RFID_DISABLED", "RFID disabled"
        DUPLICATE = "DUPLICATE", "Duplicate"
        INVALID_DIRECTION = "INVALID_DIRECTION", "Invalid direction"
        INVALID_TIMESTAMP = "INVALID_TIMESTAMP", "Invalid timestamp"
        ERROR = "ERROR", "Error"

    device = models.ForeignKey(AttendanceDevice, on_delete=models.PROTECT, related_name="scans")
    credential = models.ForeignKey(
        "idcards.RFIDCredential", on_delete=models.PROTECT, related_name="scans", null=True, blank=True
    )
    raw_uid = models.CharField(max_length=64)
    request_id = models.CharField(max_length=64)
    scanned_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)
    direction = models.CharField(max_length=10, choices=Direction.choices, blank=True)
    result = models.CharField(max_length=24, choices=Result.choices, default=Result.ERROR, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    processing_error = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-received_at", "-id")
        constraints = [
            models.UniqueConstraint(fields=("device", "request_id"), name="unique_device_scan_request")
        ]
        indexes = [
            models.Index(fields=("device", "scanned_at")),
            models.Index(fields=("result", "scanned_at")),
            models.Index(fields=("credential", "scanned_at")),
        ]

    @property
    def masked_uid(self):
        return f"********{self.raw_uid[-4:]}" if self.raw_uid else ""

    def __str__(self):
        return f"{self.device} {self.scanned_at} {self.result}"


class DeviceSecurityEvent(models.Model):
    class Severity(models.TextChoices):
        INFO = "INFO", "Info"
        WARNING = "WARNING", "Warning"
        CRITICAL = "CRITICAL", "Critical"

    class EventType(models.TextChoices):
        INVALID_SECRET = "INVALID_SECRET", "Invalid device secret"
        INVALID_SIGNATURE = "INVALID_SIGNATURE", "Invalid request signature"
        REPLAY_ATTEMPT = "REPLAY_ATTEMPT", "Replay attempt"
        RATE_LIMIT = "RATE_LIMIT", "Rate limit exceeded"
        DISABLED_DEVICE = "DISABLED_DEVICE", "Disabled device activity"
        DEVICE_STALE = "DEVICE_STALE", "Device stale"
        DEVICE_OFFLINE = "DEVICE_OFFLINE", "Device offline"

    device = models.ForeignKey(
        AttendanceDevice, on_delete=models.PROTECT, related_name="security_events", null=True, blank=True
    )
    event_type = models.CharField(max_length=24, choices=EventType.choices, db_index=True)
    severity = models.CharField(max_length=10, choices=Severity.choices, db_index=True)
    request_id = models.CharField(max_length=64, blank=True)
    fingerprint = models.CharField(max_length=64, blank=True)
    details = models.JSONField(default=dict, blank=True)
    occurrence_count = models.PositiveIntegerField(default=1)
    first_occurred_at = models.DateTimeField(auto_now_add=True)
    last_occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-last_occurred_at", "-id")
        indexes = [
            models.Index(fields=("device", "last_occurred_at")),
            models.Index(fields=("event_type", "last_occurred_at")),
        ]

    def __str__(self):
        return f"{self.event_type} ({self.severity})"


class StudentTermAttendanceSummary(models.Model):
    class Source(models.TextChoices):
        SSYNC = "SSYNC", "SSync daily attendance"
        MANUAL = "MANUAL", "Manual"
        IMPORTED = "IMPORTED", "Imported"

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="term_attendance_summaries"
    )
    term = models.ForeignKey(
        "administration.Term", on_delete=models.CASCADE, related_name="student_attendance_summaries"
    )
    school_days = models.PositiveIntegerField(default=0)
    days_present = models.PositiveIntegerField(default=0)
    days_absent = models.PositiveIntegerField(default=0)
    times_late = models.PositiveIntegerField(default=0)
    source = models.CharField(max_length=20, choices=Source.choices)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="entered_term_attendance_summaries",
        null=True,
        blank=True,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-term__start_date", "student__admission_number")
        constraints = [
            models.UniqueConstraint(fields=["student", "term"], name="unique_student_term_attendance_summary"),
            models.CheckConstraint(condition=models.Q(days_present__lte=models.F("school_days")), name="summary_present_lte_school_days"),
            models.CheckConstraint(condition=models.Q(days_absent__lte=models.F("school_days")), name="summary_absent_lte_school_days"),
            models.CheckConstraint(
                condition=models.Q(days_present__lte=models.F("school_days") - models.F("days_absent")),
                name="summary_classified_days_lte_school_days",
            ),
        ]
        indexes = [models.Index(fields=["term", "source"]), models.Index(fields=["student", "term"])]

    def clean(self):
        errors = {}
        counts = {
            "school_days": self.school_days,
            "days_present": self.days_present,
            "days_absent": self.days_absent,
            "times_late": self.times_late,
        }
        for field, value in counts.items():
            if value is not None and value < 0:
                errors[field] = "Attendance counts cannot be negative."
        if self.school_days is not None:
            if self.days_present is not None and self.days_present > self.school_days:
                errors["days_present"] = "Days present cannot exceed school days."
            if self.days_absent is not None and self.days_absent > self.school_days:
                errors["days_absent"] = "Days absent cannot exceed school days."
            if None not in (self.days_present, self.days_absent) and self.days_present + self.days_absent > self.school_days:
                errors["days_absent"] = "Present and absent days combined cannot exceed school days."
        if errors:
            raise ValidationError(errors)

    @property
    def attendance_percentage(self):
        return round((self.days_present / self.school_days) * 100, 1) if self.school_days else 0.0

    def __str__(self):
        return f"{self.student} - {self.term} ({self.source})"


class PeriodAttendance(models.Model):
    student = models.ForeignKey(Student, blank=True, on_delete=models.CASCADE)
    date = models.DateField(blank=True, null=True, validators=settings.DATE_VALIDATORS)
    period = (
        models.IntegerField()
    )  # e.g., 1 for the first period, 2 for the second period, etc.
    status = models.ForeignKey(
        AttendanceStatus, blank=True, null=True, on_delete=models.CASCADE
    )
    reason_for_absence = models.CharField(max_length=500, blank=True, null=True)
    notes = models.CharField(max_length=500, blank=True)

    class Meta:
        unique_together = (("student", "date", "period"),)
        ordering = ("date", "student", "period")

    def __str__(self):
        return f"{self.student.first_name or self.student.full_name} - {self.date} Period {self.period} {self.status}"

    @property
    def edit(self):
        return f"Edit {self.student.first_name or self.student.full_name} - {self.date} Period {self.period}"
