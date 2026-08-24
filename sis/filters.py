from django.db.models import Q
from django_filters.rest_framework import (
    CharFilter,
    FilterSet,
    NumberFilter,
)
from rest_framework.exceptions import ValidationError

from academic.models import Student


class StudentFilter(FilterSet):
    first_name = CharFilter(field_name="first_name", lookup_expr="icontains")
    middle_name = CharFilter(field_name="middle_name", lookup_expr="icontains")
    last_name = CharFilter(field_name="last_name", lookup_expr="icontains")
    admission_number = CharFilter(field_name="admission_number", lookup_expr="icontains")
    status = CharFilter(method="filter_status")
    id = NumberFilter(field_name="id")
    student = NumberFilter(field_name="id")
    classroom = NumberFilter(field_name="classroom_id")
    grade_level = NumberFilter(field_name="class_level__grade_level_id")
    class_level = NumberFilter(field_name="class_level_id")
    admission_date__year = NumberFilter(field_name="admission_date", lookup_expr="year")
    admission_date__month = NumberFilter(field_name="admission_date", lookup_expr="month")
    search = CharFilter(method="filter_search")

    class Meta:
        model = Student
        fields = (
            "first_name",
            "middle_name",
            "last_name",
            "admission_number",
            "status",
            "id",
            "student",
            "classroom",
            "grade_level",
            "class_level",
            "search",
            "admission_date__year",
            "admission_date__month",
        )

    def filter_status(self, queryset, name, value):
        normalized = (value or "").strip().lower()
        mappings = {
            "active": Q(graduation_date__isnull=True, date_dismissed__isnull=True, is_active=True),
            "inactive": Q(graduation_date__isnull=True, date_dismissed__isnull=True, is_active=False),
            "graduated": Q(graduation_date__isnull=False),
            "withdrawn": Q(graduation_date__isnull=True, date_dismissed__isnull=False),
        }
        if normalized not in mappings:
            raise ValidationError({"status": "Use active, inactive, graduated, or withdrawn."})
        return queryset.filter(mappings[normalized])

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(first_name__icontains=value)
            | Q(middle_name__icontains=value)
            | Q(last_name__icontains=value)
            | Q(admission_number__icontains=value)
            | Q(user__email__icontains=value)
            | Q(phone_number__icontains=value)
            | Q(parent_contact__icontains=value)
        ).distinct()
