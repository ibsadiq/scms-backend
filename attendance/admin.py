from django.contrib import admin

from .models import *

admin.site.register(AttendanceStatus)
admin.site.register(TeachersAttendance)
@admin.register(StudentAttendance)
class StudentAttendanceAdmin(admin.ModelAdmin):
    """Daily rows are immutable from admin; attendance services own mutations."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
admin.site.register(PeriodAttendance)
admin.site.register(AttendancePolicy)
@admin.register(StaffAttendance)
class StaffAttendanceAdmin(StudentAttendanceAdmin):
    pass


@admin.register(AttendanceEvent)
class AttendanceEventAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "event_type", "source", "student", "staff", "performed_by")
    list_filter = ("source", "event_type")
    readonly_fields = tuple(field.name for field in AttendanceEvent._meta.fields)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StudentTermAttendanceSummary)
class StudentTermAttendanceSummaryAdmin(admin.ModelAdmin):
    list_display = ("student", "term", "source", "school_days", "days_present", "days_absent", "times_late", "entered_by")
    list_filter = ("source", "term")
    search_fields = ("student__first_name", "student__last_name", "student__admission_number")


admin.site.register(AttendanceDevice)


@admin.register(AttendanceScan)
class AttendanceScanAdmin(admin.ModelAdmin):
    list_display = ("device", "masked_uid", "scanned_at", "direction", "result")
    list_filter = ("result", "direction", "device")
    readonly_fields = ("raw_uid", "request_id", "received_at", "processed_at")


@admin.register(DeviceSecurityEvent)
class DeviceSecurityEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "severity", "device", "occurrence_count", "last_occurred_at")
    list_filter = ("event_type", "severity")
    readonly_fields = tuple(field.name for field in DeviceSecurityEvent._meta.fields)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
