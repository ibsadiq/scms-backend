import django_filters
from .models import ResultAuditLog

class ResultAuditLogFilter(django_filters.FilterSet):
    start_date = django_filters.DateFilter(field_name='timestamp', lookup_expr='date__gte')
    end_date = django_filters.DateFilter(field_name='timestamp', lookup_expr='date__lte')
    date = django_filters.DateFilter(field_name='timestamp', lookup_expr='date')
    action = django_filters.CharFilter(field_name='action', lookup_expr='exact')
    performed_by = django_filters.NumberFilter(field_name='performed_by_id', lookup_expr='exact')
    student = django_filters.NumberFilter(field_name='term_result__student_id', lookup_expr='exact')
    classroom = django_filters.NumberFilter(field_name='term_result__classroom_id', lookup_expr='exact')
    term = django_filters.NumberFilter(field_name='term_result__term_id', lookup_expr='exact')
    academic_year = django_filters.NumberFilter(field_name='term_result__term__academic_year_id', lookup_expr='exact')

    class Meta:
        model = ResultAuditLog
        fields = [
            'action',
            'performed_by',
            'student',
            'classroom',
            'term',
            'academic_year',
            'start_date',
            'end_date',
            'date',
        ]
