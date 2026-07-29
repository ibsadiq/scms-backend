import django_filters
from django.db.models import F
from .models import StudentFeeAssignment

class StudentFeeAssignmentFilter(django_filters.FilterSet):
    payment_status = django_filters.CharFilter(method='filter_payment_status')
    classroom = django_filters.NumberFilter(field_name='student__classroom')

    class Meta:
        model = StudentFeeAssignment
        fields = ['student', 'term', 'fee_structure', 'is_waived', 'fee_structure__fee_type']

    def filter_payment_status(self, queryset, name, value):
        qs = queryset.alias(balance_calc=F('amount_owed') - F('amount_paid'))
        if value == 'Paid':
            return qs.filter(balance_calc__lte=0)
        elif value == 'Partial':
            return qs.filter(amount_paid__gt=0, balance_calc__gt=0)
        elif value == 'Unpaid':
            return qs.filter(amount_paid=0, balance_calc__gt=0)
        return queryset
