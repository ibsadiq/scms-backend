import django_filters
from django.db.models import F
from .models import StudentFeeAssignment, FinanceAuditLog

class StudentFeeAssignmentFilter(django_filters.FilterSet):
    payment_status = django_filters.CharFilter(method='filter_payment_status')
    classroom = django_filters.NumberFilter(field_name='student__classroom')
    academic_year = django_filters.NumberFilter(field_name='term__academic_year')
    due_date = django_filters.DateFilter(field_name='due_date')
    due_date_from = django_filters.DateFilter(field_name='due_date', lookup_expr='gte')
    due_date_to = django_filters.DateFilter(field_name='due_date', lookup_expr='lte')

    class Meta:
        model = StudentFeeAssignment
        fields = ['student', 'term', 'fee_structure', 'is_waived', 'fee_structure__fee_type', 'classroom', 'academic_year', 'due_date', 'charge_number']

    def filter_payment_status(self, queryset, name, value):
        qs = queryset.alias(balance_calc=F('amount_owed') - F('amount_paid'))
        if value in ('Paid', 'paid'):
            return qs.filter(is_waived=False, balance_calc__lte=0)
        elif value in ('Partial', 'partial'):
            return qs.filter(is_waived=False, amount_paid__gt=0, balance_calc__gt=0)
        elif value in ('Unpaid', 'unpaid'):
            return qs.filter(is_waived=False, amount_paid=0, balance_calc__gt=0)
        elif value in ('Waived', 'waived'):
            return qs.filter(is_waived=True)
        return queryset


class FinanceAuditLogFilter(django_filters.FilterSet):
    start_date = django_filters.DateFilter(field_name='timestamp', lookup_expr='date__gte')
    end_date = django_filters.DateFilter(field_name='timestamp', lookup_expr='date__lte')
    date = django_filters.DateFilter(field_name='timestamp', lookup_expr='date')
    action = django_filters.CharFilter(field_name='action', lookup_expr='exact')
    user = django_filters.NumberFilter(field_name='user_id', lookup_expr='exact')
    target_student = django_filters.NumberFilter(field_name='target_student_id', lookup_expr='exact')

    class Meta:
        model = FinanceAuditLog
        fields = ['action', 'user', 'target_student', 'start_date', 'end_date', 'date']

