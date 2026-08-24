# serializers.py
from rest_framework import serializers
from decimal import Decimal
from .models import (
    OptionalService,
    ServiceSubscription,
    FeeStructure,
    StudentFeeAssignment,
    FeeAdjustment,
    Receipt,
    FeePaymentAllocation,
    Payment,
    PaymentCategory,
    ReminderSetting
)


class FinanceMethodTotalSerializer(serializers.Serializer):
    method = serializers.CharField()
    total = serializers.FloatField()


class FinanceRecentReceiptSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    receipt_number = serializers.CharField(allow_null=True)
    student_name = serializers.CharField()
    amount = serializers.FloatField()
    method = serializers.CharField(allow_null=True)
    date = serializers.DateField()
    term_name = serializers.CharField()


class FinanceDashboardSummarySerializer(serializers.Serializer):
    total_expected = serializers.FloatField()
    total_collected = serializers.FloatField()
    total_outstanding = serializers.FloatField()
    collection_rate = serializers.FloatField()
    paid_count = serializers.IntegerField()
    partial_count = serializers.IntegerField()
    unpaid_count = serializers.IntegerField()
    method_breakdown = FinanceMethodTotalSerializer(many=True)
    recent_receipts = FinanceRecentReceiptSerializer(many=True)


class ParentFeeBreakdownSerializer(serializers.Serializer):
    fee_name = serializers.CharField()
    fee_type = serializers.CharField()
    amount_owed = serializers.FloatField()
    amount_paid = serializers.FloatField()
    balance = serializers.FloatField()
    status = serializers.CharField()


class ParentReceiptSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    receipt_number = serializers.CharField()
    amount = serializers.FloatField()
    payment_date = serializers.DateField()
    paid_through = serializers.CharField(allow_null=True)
    term_name = serializers.CharField()


class ParentChildFeesSerializer(serializers.Serializer):
    student_id = serializers.IntegerField()
    student_name = serializers.CharField()
    admission_number = serializers.CharField(allow_null=True)
    classroom_display = serializers.CharField()
    total_fees = serializers.FloatField()
    amount_paid = serializers.FloatField()
    balance = serializers.FloatField()
    status = serializers.ChoiceField(choices=("Paid", "Partial", "Unpaid"))
    receipts = ParentReceiptSerializer(many=True)
    fee_breakdown = ParentFeeBreakdownSerializer(many=True)


class ParentFeesResponseSerializer(serializers.Serializer):
    children_fees = ParentChildFeesSerializer(many=True)
# from academic.models import Student
# from administration.models import Term, AcademicYear
# from academic.models import GradeLevel, ClassLevel



class OptionalServiceSerializer(serializers.ModelSerializer):
    subscribers_count = serializers.SerializerMethodField()
    active_subscribers_count = serializers.SerializerMethodField()

    class Meta:
        model = OptionalService
        fields = '__all__'

    def get_subscribers_count(self, obj):
        return obj.subscriptions.count()

    def get_active_subscribers_count(self, obj):
        return obj.subscriptions.filter(is_active=True).count()


class ServiceSubscriptionSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    student_admission_number = serializers.CharField(source='student.admission_number', read_only=True)
    student_classroom_name = serializers.SerializerMethodField()
    service_name = serializers.CharField(source='service.name', read_only=True)
    fee_type = serializers.CharField(source='service.fee_type', read_only=True)

    class Meta:
        model = ServiceSubscription
        fields = '__all__'

    def get_student_classroom_name(self, obj):
        if not obj.student:
            return None
        if hasattr(obj.student, 'classroom') and obj.student.classroom:
            return getattr(obj.student.classroom, 'name_display', None) or (obj.student.classroom.name.name if obj.student.classroom.name else str(obj.student.classroom))
        if hasattr(obj.student, 'class_level') and obj.student.class_level:
            return obj.student.class_level.name
        return None


class FeeStructureSerializer(serializers.ModelSerializer):
    """Serializer for FeeStructure model."""
    academic_year_name = serializers.CharField(
        source='academic_year.name',
        read_only=True
    )
    term_name = serializers.CharField(
        source='term.name',
        read_only=True,
        allow_null=True
    )
    grade_level_names = serializers.SerializerMethodField()
    class_level_names = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = FeeStructure
        fields = [
            'id',
            'name',
            'fee_type',
            'amount',
            'academic_year',
            'academic_year_name',
            'term',
            'term_name',
            'grade_levels',
            'grade_level_names',
            'class_levels',
            'class_level_names',
            'optional_service',
            'is_mandatory',
            'due_date',
            'created_at',
            'updated_at',
            'created_by',
            'created_by_name',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_grade_level_names(self, obj):
        """Return list of grade level names."""
        return [grade.default_name for grade in obj.grade_levels.all()]

    def get_class_level_names(self, obj):
        """Return list of class level names."""
        return [cls.name for cls in obj.class_levels.all()]

    def get_created_by_name(self, obj):
        if obj.created_by:
            name = f"{obj.created_by.first_name} {obj.created_by.last_name}".strip()
            return name or obj.created_by.email
        return None

    def validate(self, data):
        """Validate fee structure data."""
        if data.get('amount', 0) <= 0:
            raise serializers.ValidationError({
                'amount': 'Amount must be a positive value.'
            })

        if data.get('term') and data.get('due_date'):
            term = data['term']
            due_date = data['due_date']
            if due_date < term.start_date or due_date > term.end_date:
                raise serializers.ValidationError({
                    'due_date': f'Due date must be between {term.start_date} and {term.end_date}'
                })

        return data


class StudentFeeAssignmentSerializer(serializers.ModelSerializer):
    """Serializer for StudentFeeAssignment model."""
    student_name = serializers.CharField(
        source='student.full_name',
        read_only=True
    )
    student_admission_number = serializers.CharField(
        source='student.admission_number',
        read_only=True
    )
    classroom_name = serializers.SerializerMethodField()
    fee_structure_name = serializers.CharField(
        source='fee_structure.name',
        read_only=True
    )
    fee_type = serializers.CharField(
        source='fee_structure.fee_type',
        read_only=True
    )
    term_name = serializers.CharField(
        source='term.name',
        read_only=True
    )
    academic_year_name = serializers.CharField(
        source='term.academic_year.name',
        read_only=True
    )
    balance = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    payment_status = serializers.CharField(read_only=True)
    is_fully_paid = serializers.BooleanField(read_only=True)

    def get_classroom_name(self, obj):
        if obj.student and obj.student.classroom:
            return str(obj.student.classroom)
        return None

    class Meta:
        model = StudentFeeAssignment
        fields = [
            'id',
            'student',
            'student_name',
            'student_admission_number',
            'classroom_name',
            'fee_structure',
            'fee_structure_name',
            'fee_type',
            'term',
            'term_name',
            'academic_year_name',
            'amount_owed',
            'amount_paid',
            'balance',
            'is_waived',
            'waived_reason',
            'waived_by',
            'waived_date',
            'payment_status',
            'is_fully_paid',
            'assigned_date',
            'last_payment_date',
        ]
        read_only_fields = [
            'amount_paid',
            'assigned_date',
            'last_payment_date',
            'waived_date'
        ]


class FeeAdjustmentSerializer(serializers.ModelSerializer):
    """Serializer for fee adjustments."""
    adjusted_by_name = serializers.SerializerMethodField()

    class Meta:
        model = FeeAdjustment
        fields = [
            'id',
            'fee_assignment',
            'old_amount',
            'new_amount',
            'reason',
            'adjusted_by',
            'adjusted_by_name',
            'adjusted_date',
        ]
        read_only_fields = ['adjusted_date']

    def get_adjusted_by_name(self, obj):
        if obj.adjusted_by:
            return f"{obj.adjusted_by.first_name} {obj.adjusted_by.last_name}".strip()
        return None


class FeePaymentAllocationSerializer(serializers.ModelSerializer):
    """Serializer for fee payment allocations."""
    fee_structure_name = serializers.CharField(
        source='fee_assignment.fee_structure.name',
        read_only=True
    )
    fee_type = serializers.CharField(
        source='fee_assignment.fee_structure.fee_type',
        read_only=True
    )

    class Meta:
        model = FeePaymentAllocation
        fields = [
            'id',
            'receipt',
            'fee_assignment',
            'fee_structure_name',
            'fee_type',
            'amount',
            'allocated_date',
            'allocated_by',
        ]
        read_only_fields = ['allocated_date']


class ReceiptSerializer(serializers.ModelSerializer):
    """Serializer for Receipt model."""
    student_name = serializers.CharField(
        source='student.full_name',
        read_only=True,
        allow_null=True
    )
    student_admission_number = serializers.CharField(
        source='student.admission_number',
        read_only=True,
        allow_null=True
    )
    classroom_name = serializers.SerializerMethodField()
    term_name = serializers.CharField(
        source='term.name',
        read_only=True,
        allow_null=True
    )
    received_by_name = serializers.SerializerMethodField()
    allocated_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    unallocated_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    fee_allocations = FeePaymentAllocationSerializer(many=True, read_only=True)

    def get_classroom_name(self, obj):
        if obj.student and obj.student.classroom:
            return str(obj.student.classroom)
        return None

    class Meta:
        model = Receipt
        fields = [
            'id',
            'receipt_number',
            'date',
            'payer',
            'student',
            'student_name',
            'student_admission_number',
            'classroom_name',
            'amount',
            'paid_through',
            'term',
            'term_name',
            'payment_date',
            'reference_number',
            'status',
            'received_by',
            'received_by_name',
            'remarks',
            'allocated_amount',
            'unallocated_amount',
            'fee_allocations',
        ]
        read_only_fields = ['receipt_number', 'date']

    def get_received_by_name(self, obj):
        if obj.received_by:
            return f"{obj.received_by.first_name} {obj.received_by.last_name}".strip() or obj.received_by.email
        return None


class PaymentCategorySerializer(serializers.ModelSerializer):
    """Serializer for PaymentCategory model."""

    class Meta:
        model = PaymentCategory
        fields = ['id', 'name', 'abbr', 'description']


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer for outgoing Payment model."""
    category_name = serializers.CharField(
        source='category.name',
        read_only=True,
        allow_null=True
    )
    paid_by_name = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            'id',
            'payment_number',
            'date',
            'paid_to',
            'user',
            'user_name',
            'category',
            'category_name',
            'paid_through',
            'amount',
            'reference_number',
            'description',
            'status',
            'paid_by',
            'paid_by_name',
        ]
        read_only_fields = ['payment_number', 'date']

    def get_paid_by_name(self, obj):
        if obj.paid_by:
            return f"{obj.paid_by.first_name} {obj.paid_by.last_name}".strip() or obj.paid_by.email
        return None

    def get_user_name(self, obj):
        if obj.user:
            return f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.email
        return None


class StudentFeeBalanceSerializer(serializers.Serializer):
    """Serializer for student fee balance summary."""
    student = serializers.IntegerField()
    student_name = serializers.CharField()
    student_admission_number = serializers.CharField()
    class_level_name = serializers.CharField(required=False)
    term = serializers.IntegerField(allow_null=True)
    term_name = serializers.CharField(allow_null=True)
    total_fees = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_paid = serializers.DecimalField(max_digits=10, decimal_places=2)
    balance = serializers.DecimalField(max_digits=10, decimal_places=2)
    status = serializers.CharField()
    fee_breakdown = serializers.ListField()


class ReminderSettingSerializer(serializers.ModelSerializer):
    """Serializer for ReminderSetting model."""
    fee_structure = serializers.PrimaryKeyRelatedField(
        queryset=FeeStructure.objects.all(),
        allow_null=True,
        required=False
    )
    
    class Meta:
        model = ReminderSetting
        fields = '__all__'

class FinanceAuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    target_student_name = serializers.CharField(source='target_student.full_name', read_only=True)
    target_student_admission_number = serializers.CharField(source='target_student.admission_number', read_only=True)

    class Meta:
        from finance.models import FinanceAuditLog
        model = FinanceAuditLog
        fields = [
            'id', 'timestamp', 'user', 'user_name', 'user_email',
            'action', 'target_student', 'target_student_name', 
            'target_student_admission_number', 'description', 'metadata'
        ]
        read_only_fields = fields
