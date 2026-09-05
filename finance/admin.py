from django.contrib import admin
from .models import FeeStructure, FeeTermSchedule, Payment, Receipt, StudentFeeAssignment

admin.site.register(Receipt)
admin.site.register(Payment)


class FeeTermScheduleInline(admin.TabularInline):
    model = FeeTermSchedule
    extra = 0
    fields = ("term", "amount", "due_date")


@admin.register(FeeStructure)
class FeeStructureAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "fee_type",
        "recurrence",
        "applicability",
        "logical_fee_key",
        "academic_year",
        "term",
        "amount",
        "due_date",
        "is_mandatory",
    )
    list_filter = ("fee_type", "recurrence", "applicability", "is_mandatory", "academic_year")
    search_fields = ("name", "logical_fee_key")
    inlines = [FeeTermScheduleInline]


@admin.register(FeeTermSchedule)
class FeeTermScheduleAdmin(admin.ModelAdmin):
    list_display = ("fee_structure", "term", "amount", "due_date")
    list_filter = ("term__academic_year", "term")
    search_fields = ("fee_structure__name", "term__name")


@admin.register(StudentFeeAssignment)
class StudentFeeAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "fee_structure",
        "term",
        "academic_year",
        "recurrence",
        "logical_fee_key",
        "amount_owed",
        "amount_paid",
        "due_date",
        "is_waived",
    )
    list_filter = ("recurrence", "is_waived", "academic_year", "term")
    readonly_fields = (
        "due_date",
        "amount_paid",
        "assigned_date",
        "last_payment_date",
        "logical_fee_key",
        "recurrence",
        "academic_year",
        "waived_date",
    )
    search_fields = (
        "student__first_name",
        "student__last_name",
        "student__admission_number",
        "logical_fee_key",
    )

