from decimal import Decimal
from django.db import transaction
from rest_framework import serializers

from .models import (
    OptionalService,
    ServiceSubscription,
    FeeStructure,
    FeeTermSchedule,
    StudentFeeAssignment,
    FeeAdjustment,
    Receipt,
    FeePaymentAllocation,
    Payment,
    PaymentCategory,
    ReminderSetting,
    FeeRecurrence,
    FeeApplicability,
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
            return str(obj.student.classroom)
        return None


class FeeTermScheduleSerializer(serializers.ModelSerializer):
    term_name = serializers.CharField(source='term.name', read_only=True)

    class Meta:
        model = FeeTermSchedule
        fields = [
            'id',
            'term',
            'term_name',
            'amount',
            'due_date',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_amount(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Amount must be a positive value.")
        return value


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
    classroom_names = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    recurrence = serializers.ChoiceField(
        choices=FeeRecurrence.choices,
        default=FeeRecurrence.PER_TERM,
        required=False,
    )
    applicability = serializers.ChoiceField(
        choices=FeeApplicability.choices,
        default=FeeApplicability.ALL_ELIGIBLE,
        required=False,
    )
    logical_fee_key = serializers.SlugField(
        max_length=120,
        required=False,
        allow_blank=True,
        default="",
    )
    term_schedules = FeeTermScheduleSerializer(many=True, required=False)

    class Meta:
        model = FeeStructure
        fields = [
            'id',
            'name',
            'fee_type',
            'recurrence',
            'applicability',
            'logical_fee_key',
            'amount',
            'academic_year',
            'academic_year_name',
            'term',
            'term_name',
            'grade_levels',
            'grade_level_names',
            'classrooms',
            'classroom_names',
            'optional_service',
            'is_mandatory',
            'due_date',
            'term_schedules',
            'created_at',
            'updated_at',
            'created_by',
            'created_by_name',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        schedules = instance.term_schedules.select_related("term").order_by("term__start_date", "pk")
        ret["term_schedules"] = FeeTermScheduleSerializer(schedules, many=True).data
        return ret

    def get_grade_level_names(self, obj):
        """Return list of grade level names."""
        return [grade.alias or grade.default_name for grade in obj.grade_levels.all()]

    def get_classroom_names(self, obj):
        """Return list of classroom names."""
        return [cls.name for cls in obj.classrooms.all()]

    def get_created_by_name(self, obj):
        if obj.created_by:
            name = f"{obj.created_by.first_name} {obj.created_by.last_name}".strip()
            return name or obj.created_by.email
        return None

    def validate(self, data):
        """Validate fee structure data."""
        amount = data.get('amount')
        if amount is not None and amount <= 0:
            raise serializers.ValidationError({
                'amount': 'Amount must be a positive value.'
            })

        term = data.get('term') if 'term' in data else getattr(self.instance, 'term', None)
        due_date = data.get('due_date') if 'due_date' in data else getattr(self.instance, 'due_date', None)

        if term and due_date:
            if due_date < term.start_date or due_date > term.end_date:
                raise serializers.ValidationError({
                    'due_date': f'Due date must be between {term.start_date} and {term.end_date}'
                })

        has_term_schedules = (
            'term_schedules' in self.initial_data
            if hasattr(self, 'initial_data') and isinstance(self.initial_data, dict)
            else 'term_schedules' in data
        )
        term_schedules_data = data.get('term_schedules')
        recurrence = data.get('recurrence') if 'recurrence' in data else getattr(self.instance, 'recurrence', FeeRecurrence.PER_TERM)
        academic_year = data.get('academic_year') if 'academic_year' in data else getattr(self.instance, 'academic_year', None)

        # Transition checks: if existing FeeStructure already has term schedules
        if self.instance and self.instance.term_schedules.exists():
            if recurrence != FeeRecurrence.PER_TERM or term is not None:
                # If changing recurrence away from PER_TERM or specifying a term:
                # Only allowed if term_schedules was explicitly passed as empty [] (intentional removal)
                if not (has_term_schedules and term_schedules_data == []):
                    raise serializers.ValidationError(
                        "Cannot change recurrence or term while fee term schedules exist. Remove schedules first."
                    )

        if term_schedules_data is not None:
            if term_schedules_data:
                if recurrence != FeeRecurrence.PER_TERM:
                    raise serializers.ValidationError({
                        'term_schedules': 'Fee term schedules are only allowed for PER_TERM recurrence.'
                    })
                if term is not None:
                    raise serializers.ValidationError({
                        'term_schedules': 'Fee term schedules cannot be configured for specific-term fee structures.'
                    })

                seen_terms = set()
                for schedule_item in term_schedules_data:
                    sched_term = schedule_item.get('term')
                    sched_due_date = schedule_item.get('due_date')
                    sched_amount = schedule_item.get('amount')

                    sched_term_id = sched_term.pk if hasattr(sched_term, 'pk') else sched_term
                    if sched_term_id in seen_terms:
                        raise serializers.ValidationError({
                            'term_schedules': 'Duplicate schedule for the same term is not allowed.'
                        })
                    seen_terms.add(sched_term_id)

                    if academic_year and hasattr(sched_term, 'academic_year_id'):
                        ay_id = academic_year.pk if hasattr(academic_year, 'pk') else academic_year
                        if sched_term.academic_year_id != ay_id:
                            raise serializers.ValidationError({
                                'term_schedules': "Schedule term must belong to the fee structure's academic year."
                            })

                    if sched_due_date and hasattr(sched_term, 'start_date'):
                        if sched_term.start_date and sched_due_date < sched_term.start_date:
                            raise serializers.ValidationError({
                                'term_schedules': f"Due date cannot be before term start date ({sched_term.start_date})."
                            })
                        if sched_term.end_date and sched_due_date > sched_term.end_date:
                            raise serializers.ValidationError({
                                'term_schedules': f"Due date cannot be after term end date ({sched_term.end_date})."
                            })

                    if sched_amount is not None and sched_amount <= 0:
                        raise serializers.ValidationError({
                            'term_schedules': 'Schedule amount must be a positive value.'
                        })

        return data

    @transaction.atomic
    def create(self, validated_data):
        term_schedules_data = validated_data.pop('term_schedules', None)
        grade_levels = validated_data.pop('grade_levels', None)
        classrooms = validated_data.pop('classrooms', None)

        fee_structure = FeeStructure(**validated_data)
        # Suppress auto_assign during initial save so schedules can be created first
        fee_structure._suppress_auto_assign = True
        fee_structure.save()

        if grade_levels is not None:
            fee_structure.grade_levels.set(grade_levels)
        if classrooms is not None:
            fee_structure.classrooms.set(classrooms)

        if term_schedules_data:
            for item in term_schedules_data:
                schedule = FeeTermSchedule(
                    fee_structure=fee_structure,
                    term=item['term'],
                    amount=item.get('amount'),
                    due_date=item['due_date'],
                )
                schedule.full_clean()
                schedule.save()

        if fee_structure.is_mandatory:
            from finance.signals import _assign_fee
            fee_id = fee_structure.pk
            transaction.on_commit(lambda: _assign_fee(fee_id))

        return fee_structure

    @transaction.atomic
    def update(self, instance, validated_data):
        # Explicit check: was 'term_schedules' key provided in the request payload?
        has_term_schedules = (
            'term_schedules' in self.initial_data
            if hasattr(self, 'initial_data') and isinstance(self.initial_data, dict)
            else 'term_schedules' in validated_data
        )
        term_schedules_data = validated_data.pop('term_schedules', None)
        grade_levels = validated_data.pop('grade_levels', None)
        classrooms = validated_data.pop('classrooms', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if grade_levels is not None:
            instance.grade_levels.set(grade_levels)
        if classrooms is not None:
            instance.classrooms.set(classrooms)

        # Semantics:
        # - If 'term_schedules' key is absent: leave existing schedules unchanged.
        # - If 'term_schedules' key is present:
        #     - If empty list []: remove all existing schedules.
        #     - If list [...]: term-keyed upsert/replacement.
        if has_term_schedules:
            if term_schedules_data is None:
                term_schedules_data = []

            existing_schedules = {s.term_id: s for s in instance.term_schedules.all()}
            incoming_term_ids = set()

            for item in term_schedules_data:
                term_obj = item['term']
                term_id = term_obj.pk if hasattr(term_obj, 'pk') else term_obj
                incoming_term_ids.add(term_id)

                if term_id in existing_schedules:
                    sched = existing_schedules[term_id]
                    sched.amount = item.get('amount')
                    sched.due_date = item['due_date']
                    sched.full_clean()
                    sched.save()
                else:
                    sched = FeeTermSchedule(
                        fee_structure=instance,
                        term=term_obj,
                        amount=item.get('amount'),
                        due_date=item['due_date'],
                    )
                    sched.full_clean()
                    sched.save()

            instance.term_schedules.exclude(term_id__in=incoming_term_ids).delete()

        return instance


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
    due_date = serializers.DateField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

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
            'logical_fee_key',
            'recurrence',
            'academic_year',
            'term',
            'term_name',
            'academic_year_name',
            'amount_owed',
            'amount_paid',
            'balance',
            'due_date',
            'is_overdue',
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
            'waived_date',
            'due_date',
            'is_overdue',
        ]

    def create(self, validated_data):
        fee_structure = validated_data.get('fee_structure')
        if fee_structure:
            from finance.services.fee_assignment_service import FeeAssignmentService
            target_term = validated_data.get('term')
            resolved_amount, resolved_due_date = FeeAssignmentService.resolve_assignment_financials(
                fee_structure=fee_structure,
                target_term=target_term,
            )
            if 'due_date' not in validated_data or validated_data['due_date'] is None:
                validated_data['due_date'] = resolved_due_date
            if not validated_data.get('amount_owed'):
                validated_data['amount_owed'] = resolved_amount
            if not validated_data.get('logical_fee_key'):
                validated_data['logical_fee_key'] = fee_structure.logical_fee_key
            if not validated_data.get('recurrence'):
                validated_data['recurrence'] = fee_structure.recurrence
            if not validated_data.get('academic_year'):
                validated_data['academic_year'] = fee_structure.academic_year
        return super().create(validated_data)


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
    academic_year_name = serializers.SerializerMethodField()
    term_name = serializers.SerializerMethodField()
    scope_label = serializers.SerializerMethodField()
    remaining_balance = serializers.DecimalField(
        source='fee_assignment.balance',
        max_digits=10,
        decimal_places=2,
        read_only=True
    )

    def get_academic_year_name(self, obj):
        assignment = getattr(obj, "fee_assignment", None)
        if assignment:
            if getattr(assignment, "academic_year", None):
                return assignment.academic_year.name
            if getattr(assignment, "term", None) and getattr(assignment.term, "academic_year", None):
                return assignment.term.academic_year.name
            if getattr(assignment, "fee_structure", None) and getattr(assignment.fee_structure, "academic_year", None):
                return assignment.fee_structure.academic_year.name
        return None

    def get_term_name(self, obj):
        assignment = getattr(obj, "fee_assignment", None)
        if assignment and getattr(assignment, "term", None):
            return assignment.term.name
        return None

    def get_scope_label(self, obj):
        from finance.tasks import get_fee_scope_label
        return get_fee_scope_label(getattr(obj, "fee_assignment", None))

    class Meta:
        model = FeePaymentAllocation
        fields = [
            'id',
            'receipt',
            'fee_assignment',
            'fee_structure_name',
            'fee_type',
            'academic_year_name',
            'term_name',
            'scope_label',
            'remaining_balance',
            'amount',
            'allocated_date',
            'allocated_by',
        ]
        read_only_fields = ['allocated_date']


class FeePaymentAllocationInputSerializer(serializers.Serializer):
    """Input serializer for nested fee allocations in atomic payment creation."""
    fee_assignment = serializers.IntegerField(required=False)
    fee_assignment_id = serializers.IntegerField(required=False)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))

    def validate(self, attrs):
        assignment_id = attrs.get('fee_assignment') or attrs.get('fee_assignment_id')
        if not assignment_id:
            raise serializers.ValidationError({"fee_assignment": "fee_assignment or fee_assignment_id is required."})
        attrs['fee_assignment_id'] = assignment_id
        return attrs


class SafeDateField(serializers.DateField):
    def to_representation(self, value):
        if hasattr(value, "date") and callable(value.date):
            value = value.date()
        return super().to_representation(value)


class ReceiptSerializer(serializers.ModelSerializer):
    """Serializer for Receipt model."""
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    payment_date = SafeDateField(required=False)
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
    header_term_display = serializers.SerializerMethodField()
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
    allocations = FeePaymentAllocationInputSerializer(many=True, required=False, write_only=True)
    fee_allocations = FeePaymentAllocationSerializer(many=True, read_only=True)

    def get_classroom_name(self, obj):
        if obj.student and obj.student.classroom:
            return str(obj.student.classroom)
        return None

    def get_header_term_display(self, obj):
        from finance.models import FeeRecurrence
        allocations = list(obj.fee_allocations.all())
        has_annual_or_onetime = any(
            getattr(alloc.fee_assignment, 'recurrence', None) in (FeeRecurrence.ANNUAL, FeeRecurrence.ONE_TIME)
            or getattr(getattr(alloc.fee_assignment, 'fee_structure', None), 'recurrence', None) in (FeeRecurrence.ANNUAL, FeeRecurrence.ONE_TIME)
            for alloc in allocations
        )
        if obj.term and getattr(obj.term, 'name', None):
            terms = {
                alloc.fee_assignment.term_id
                for alloc in allocations
                if alloc.fee_assignment and alloc.fee_assignment.term_id
            }
            if has_annual_or_onetime or len(terms) > 1 or (terms and list(terms)[0] != obj.term_id):
                return "Multiple / Mixed"
            return obj.term.name
        if allocations:
            alloc_terms = {
                alloc.fee_assignment.term
                for alloc in allocations
                if alloc.fee_assignment and alloc.fee_assignment.term
            }
            if not has_annual_or_onetime and len(alloc_terms) == 1 and all(
                alloc.fee_assignment and alloc.fee_assignment.term is not None for alloc in allocations
            ):
                return list(alloc_terms)[0].name
            return "Multiple / Mixed"
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
            'header_term_display',
            'payment_date',
            'reference_number',
            'status',
            'received_by',
            'received_by_name',
            'remarks',
            'allocated_amount',
            'unallocated_amount',
            'allocations',
            'fee_allocations',
        ]
        read_only_fields = ['receipt_number', 'date']

    def validate(self, attrs):
        allocations = attrs.get('allocations')
        amount = attrs.get('amount')
        if allocations is None:
            if amount is None:
                raise serializers.ValidationError({"amount": "Amount is required when allocations are not provided."})
            if amount <= 0:
                raise serializers.ValidationError({"amount": "Amount must be a positive value."})
        return attrs

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
