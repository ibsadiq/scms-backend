from django.contrib import admin
from .models import FeeStructure, Payment, Receipt, StudentFeeAssignment

admin.site.register(Receipt)
admin.site.register(Payment)


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
        "is_mandatory",
    )
    list_filter = ("fee_type", "recurrence", "applicability", "is_mandatory", "academic_year")
    search_fields = ("name", "logical_fee_key")


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
        "is_waived",
    )
    list_filter = ("recurrence", "is_waived", "academic_year", "term")
    search_fields = (
        "student__first_name",
        "student__last_name",
        "student__admission_number",
        "logical_fee_key",
    )

