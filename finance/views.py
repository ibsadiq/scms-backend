# views.py
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Sum, Q, F
from django.shortcuts import get_object_or_404
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
    ReminderSetting,
    FinanceAuditLog,
    AuditAction
)
from .filters import StudentFeeAssignmentFilter
from .serializers import (
    OptionalServiceSerializer,
    ServiceSubscriptionSerializer,
    FeeStructureSerializer,
    StudentFeeAssignmentSerializer,
    FeeAdjustmentSerializer,
    ReceiptSerializer,
    FeePaymentAllocationSerializer,
    PaymentSerializer,
    PaymentCategorySerializer,
    StudentFeeBalanceSerializer,
    ReminderSettingSerializer
)
from academic.models import Student
from administration.models import Term


class OptionalServiceViewSet(viewsets.ModelViewSet):
    """ViewSet for managing optional services."""
    queryset = OptionalService.objects.all()
    serializer_class = OptionalServiceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active', 'fee_type']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']


class ServiceSubscriptionViewSet(viewsets.ModelViewSet):
    """ViewSet for managing student subscriptions to optional services."""
    queryset = ServiceSubscription.objects.select_related('student', 'service')
    serializer_class = ServiceSubscriptionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['service', 'student', 'is_active']
    search_fields = ['student__first_name', 'student__last_name', 'student__admission_number', 'service__name']
    ordering_fields = ['subscribed_on', 'is_active']
    ordering = ['-subscribed_on']

    @action(detail=False, methods=['post'])
    def bulk_subscribe(self, request):
        """
        Bulk subscribe multiple students to a service.
        Body: { "service": 1, "student_ids": [10, 15, 20] }
        """
        service_id = request.data.get('service')
        student_ids = request.data.get('student_ids', [])
        
        if not service_id or not student_ids:
            return Response(
                {"error": "service and student_ids are required"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        service = get_object_or_404(OptionalService, id=service_id)
        
        created_count = 0
        for student_id in student_ids:
            student = get_object_or_404(Student, id=student_id)
            _, created = ServiceSubscription.objects.get_or_create(
                student=student,
                service=service,
                defaults={'is_active': True}
            )
            if created:
                created_count += 1
                
        if created_count > 0:
            FinanceAuditLog.objects.create(
                user=request.user,
                action=AuditAction.SERVICE_SUBSCRIBED,
                description=f"Bulk subscribed {created_count} students to service '{service.name}'.",
                metadata={"service_id": service.id, "student_ids": student_ids}
            )

        return Response({
            "message": f"Successfully subscribed {created_count} students to {service.name}",
            "subscribed_count": created_count
        })


class FeeStructureViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing fee structures.

    list: Get all fee structures
    retrieve: Get a specific fee structure
    create: Create a new fee structure
    update: Update a fee structure
    destroy: Delete a fee structure
    auto_assign: Manually trigger auto-assignment of a mandatory fee
    """
    queryset = FeeStructure.objects.select_related(
        'academic_year',
        'term',
        'created_by'
    ).prefetch_related(
        'grade_levels',
        'class_levels'
    )
    serializer_class = FeeStructureSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['academic_year', 'term', 'fee_type', 'is_mandatory']
    search_fields = ['name', 'fee_type']
    ordering_fields = ['name', 'amount', 'due_date', 'created_at']
    ordering = ['-created_at']

    def perform_create(self, serializer):
        """Save fee structure with current user."""
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def auto_assign(self, request, pk=None):
        """
        Manually trigger auto-assignment of this fee to applicable students.
        POST /api/financial/fee-structures/{id}/auto_assign/
        Body: { "term_id": 1 } (optional)
        """
        fee_structure = self.get_object()

        term_id = request.data.get('term_id')
        term = None
        if term_id:
            term = get_object_or_404(Term, id=term_id)

        assigned_count = fee_structure.auto_assign_to_students(term=term)

        return Response({
            'message': f'Successfully assigned fee to {assigned_count} students',
            'assigned_count': assigned_count
        })

    @action(detail=False, methods=['get'])
    def by_student(self, request):
        """
        Get all fee structures applicable to a specific student.
        GET /api/financial/fee-structures/by_student/?student_id=1&term_id=1
        """
        student_id = request.query_params.get('student_id')
        term_id = request.query_params.get('term_id')

        if not student_id:
            return Response(
                {'error': 'student_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        student = get_object_or_404(Student, id=student_id)
        term = None
        if term_id:
            term = get_object_or_404(Term, id=term_id)

        # Get all fee structures that apply to this student
        fee_structures = FeeStructure.objects.filter(
            academic_year=term.academic_year if term else F('academic_year')
        )

        applicable_fees = []
        for fee in fee_structures:
            if fee.applies_to_student(student, term):
                applicable_fees.append(fee)

        serializer = self.get_serializer(applicable_fees, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def send_reminder(self, request, pk=None):
        """
        Send payment reminder for this specific fee structure.
        POST /api/financial/fee-structures/{id}/send_reminder/
        Body: { "message": "Custom message (optional)" }
        """
        from finance.tasks import send_custom_fee_reminder

        fee_structure = self.get_object()
        custom_message = request.data.get('message', None)

        # Trigger async task
        task = send_custom_fee_reminder.delay(fee_structure.id, custom_message)

        return Response({
            'message': 'Reminder task queued successfully',
            'task_id': task.id,
            'fee_structure': fee_structure.name
        })

    @action(detail=False, methods=['post'])
    def send_all_reminders(self, request):
        """
        Trigger fee reminders for all due fees.
        POST /api/financial/fee-structures/send_all_reminders/
        """
        from finance.tasks import send_fee_reminders

        # Trigger async task
        task = send_fee_reminders.delay()

        return Response({
            'message': 'Fee reminders task queued successfully',
            'task_id': task.id,
            'check_status': f'/api/tasks/{task.id}/'
        })


class StudentFeeAssignmentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing student fee assignments.

    list: Get all fee assignments
    retrieve: Get a specific fee assignment
    create: Create a new fee assignment (assign fee to student)
    update: Update a fee assignment
    destroy: Delete a fee assignment
    waive: Waive a fee
    adjust_amount: Adjust fee amount
    """
    queryset = StudentFeeAssignment.objects.select_related(
        'student',
        'fee_structure',
        'term',
        'term__academic_year',
        'waived_by'
    )
    serializer_class = StudentFeeAssignmentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = StudentFeeAssignmentFilter
    search_fields = ['student__first_name', 'student__last_name', 'student__admission_number', 'fee_structure__name']
    ordering_fields = ['assigned_date', 'amount_owed', 'balance']
    ordering = ['-assigned_date']

    def perform_create(self, serializer):
        assignment = serializer.save()
        FinanceAuditLog.objects.create(
            user=self.request.user,
            action=AuditAction.FEE_ASSIGNED,
            target_student=assignment.student,
            description=f"Assigned fee '{assignment.fee_structure.name}' (₦{assignment.amount_owed}) to {assignment.student.full_name}.",
            metadata={"amount_owed": float(assignment.amount_owed), "fee_id": assignment.fee_structure.id}
        )

    @action(detail=False, methods=['get'])
    def by_student(self, request):
        """
        Get all fee assignments for a specific student.
        GET /api/financial/student-fee-assignments/by_student/?student_id=1&term_id=1
        """
        student_id = request.query_params.get('student_id')
        term_id = request.query_params.get('term_id')

        if not student_id:
            return Response(
                {'error': 'student_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        queryset = self.get_queryset().filter(student_id=student_id)

        if term_id:
            queryset = queryset.filter(term_id=term_id)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def bulk_assign(self, request):
        """
        Bulk assign a fee structure to multiple students.
        Body: { "fee_structure": 1, "term": 1, "student_ids": [10, 15, 20] }
        """
        fee_structure_id = request.data.get('fee_structure')
        term_id = request.data.get('term')
        student_ids = request.data.get('student_ids', [])

        if not fee_structure_id or not student_ids:
            return Response(
                {"error": "fee_structure and student_ids are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        fee_structure = get_object_or_404(FeeStructure, id=fee_structure_id)
        term = get_object_or_404(Term, id=term_id) if term_id else None

        created_count = 0
        for student_id in student_ids:
            student = get_object_or_404(Student, id=student_id)
            if fee_structure.applies_to_student(student, term):
                _, created = StudentFeeAssignment.objects.get_or_create(
                    student=student,
                    fee_structure=fee_structure,
                    term=term,
                    defaults={
                        'amount_owed': fee_structure.amount,
                        'amount_paid': Decimal('0.00'),
                    }
                )
                if created:
                    created_count += 1

        if created_count > 0:
            FinanceAuditLog.objects.create(
                user=request.user,
                action=AuditAction.BULK_FEE_ASSIGNED,
                description=f"Bulk assigned fee '{fee_structure.name}' to {created_count} students.",
                metadata={"fee_id": fee_structure.id, "student_ids": student_ids}
            )

        return Response({
            "message": f"Successfully assigned fee to {created_count} students",
            "assigned_count": created_count
        })

    @action(detail=True, methods=['post'])
    def waive(self, request, pk=None):
        """
        Waive a fee (scholarship, discount, etc.).
        POST /api/financial/student-fee-assignments/{id}/waive/
        Body: { "reason": "Scholarship awarded" }
        """
        assignment = self.get_object()
        reason = request.data.get('reason', 'No reason provided')
        original_amount = assignment.amount_owed

        assignment.waive_fee(reason=reason, waived_by=request.user)

        FinanceAuditLog.objects.create(
            user=request.user,
            action=AuditAction.FEE_WAIVED,
            target_student=assignment.student,
            description=f"Waived fee '{assignment.fee_structure.name}' for {assignment.student.full_name}. Reason: {reason}",
            metadata={"original_amount": float(original_amount), "new_amount": float(assignment.amount_owed)}
        )

        return Response({
            'message': 'Fee waived successfully',
            'fee_assignment': self.get_serializer(assignment).data
        })

    @action(detail=True, methods=['post'])
    def adjust_amount(self, request, pk=None):
        """
        Adjust the amount owed for a fee.
        POST /api/financial/student-fee-assignments/{id}/adjust_amount/
        Body: { "new_amount": 45000.00, "reason": "10% discount applied" }
        """
        assignment = self.get_object()
        new_amount = request.data.get('new_amount')
        reason = request.data.get('reason', 'Manual adjustment')

        if not new_amount:
            return Response(
                {'error': 'new_amount is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            new_amount = Decimal(str(new_amount))
            original_amount = assignment.amount_owed
            assignment.adjust_amount(new_amount, reason)

            FinanceAuditLog.objects.create(
                user=request.user,
                action=AuditAction.AMOUNT_ADJUSTED,
                target_student=assignment.student,
                description=f"Adjusted fee '{assignment.fee_structure.name}' for {assignment.student.full_name} from ₦{original_amount} to ₦{new_amount}. Reason: {reason}",
                metadata={"original_amount": float(original_amount), "new_amount": float(new_amount)}
            )

            return Response({
                'message': 'Fee amount adjusted successfully',
                'fee_assignment': self.get_serializer(assignment).data
            })
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'])
    def unpaid(self, request):
        """
        Get all unpaid or partially paid fee assignments.
        GET /api/financial/student-fee-assignments/unpaid/?term_id=1
        """
        queryset = self.get_queryset().annotate(
            balance_calc=F('amount_owed') - F('amount_paid')
        ).filter(
            balance_calc__gt=0,
            is_waived=False
        )

        term_id = request.query_params.get('term_id')
        if term_id:
            queryset = queryset.filter(term_id=term_id)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class ReceiptViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing receipts (incoming payments).

    list: Get all receipts
    retrieve: Get a specific receipt
    create: Create a new receipt
    update: Update a receipt
    destroy: Delete a receipt
    allocate_to_fees: Allocate receipt amount to specific fees
    """
    queryset = Receipt.objects.select_related(
        'student',
        'student__classroom',
        'term',
        'received_by'
    ).prefetch_related('fee_allocations')
    serializer_class = ReceiptSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = {
        'student': ['exact'],
        'student_id': ['exact'],
        'student__classroom': ['exact'],
        'student__classroom_id': ['exact'],
        'term': ['exact'],
        'term_id': ['exact'],
        'term__academic_year': ['exact'],
        'term__academic_year_id': ['exact'],
        'status': ['exact', 'iexact'],
        'paid_through': ['exact', 'iexact'],
        'received_by': ['exact'],
        'date': ['gte', 'lte', 'exact'],
        'amount': ['gte', 'lte', 'exact']
    }
    search_fields = ['payer', 'reference_number', 'receipt_number', 'student__first_name', 'student__last_name', 'student__admission_number']
    ordering_fields = ['date', 'receipt_number', 'amount']
    ordering = ['-date', '-receipt_number']

    def get_queryset(self):
        queryset = Receipt.objects.select_related(
            'student',
            'student__classroom',
            'term',
            'received_by'
        ).prefetch_related('fee_allocations')

        user = self.request.user
        if hasattr(user, 'is_student') and user.is_student:
            student = getattr(user, 'student_profile', None) or getattr(user, 'student', None)
            if not student:
                from academic.models import Student
                student = Student.objects.filter(user=user).first()
            if student:
                return queryset.filter(student=student)
            return Receipt.objects.none()

        return queryset

    def perform_create(self, serializer):
        receipt = serializer.save(received_by=self.request.user)
        FinanceAuditLog.objects.create(
            user=self.request.user,
            action=AuditAction.PAYMENT_RECORDED,
            target_student=receipt.student,
            description=f"Recorded incoming payment of ₦{receipt.amount} from {receipt.student.full_name} ({receipt.student.admission_number}).",
            metadata={"amount": float(receipt.amount), "receipt_id": receipt.id}
        )

    def perform_destroy(self, instance):
        FinanceAuditLog.objects.create(
            user=self.request.user,
            action=AuditAction.PAYMENT_REVERSED,
            target_student=instance.student,
            description=f"Reversed/deleted incoming payment of ₦{instance.amount} from {instance.student.full_name}.",
            metadata={"amount": float(instance.amount), "receipt_id": instance.id}
        )
        instance.delete()

    def filter_queryset(self, queryset):
        student_param = self.request.query_params.get('student') or self.request.query_params.get('student_id')
        if student_param:
            from academic.models import Student
            st = Student.objects.filter(id=student_param).first()
            if not st and str(student_param).isdigit():
                st = Student.objects.filter(user_id=student_param).first()
            if st:
                queryset = queryset.filter(student=st)
                mutable_get = self.request.query_params.copy()
                mutable_get.pop('student', None)
                mutable_get.pop('student_id', None)
                self.request._request.GET = mutable_get

        return super().filter_queryset(queryset)

    @action(detail=True, methods=['post'])
    def allocate_to_fees(self, request, pk=None):
        """
        Allocate receipt amount to specific fee assignments.
        POST /api/financial/receipts/{id}/allocate_to_fees/
        Body: {
            "allocations": [
                {"fee_assignment_id": 1, "amount": 25000.00},
                {"fee_assignment_id": 2, "amount": 5000.00}
            ]
        }
        """
        receipt = self.get_object()
        allocations_data = request.data.get('allocations', [])

        if not allocations_data:
            return Response(
                {'error': 'allocations list is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate total doesn't exceed receipt amount
        total_to_allocate = sum(
            Decimal(str(alloc['amount'])) for alloc in allocations_data
        )

        available = receipt.unallocated_amount
        if total_to_allocate > available:
            return Response(
                {'error': f'Total allocation (₦{total_to_allocate}) exceeds available amount (₦{available})'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create allocations
        created_allocations = []
        for alloc_data in allocations_data:
            fee_assignment = get_object_or_404(
                StudentFeeAssignment,
                id=alloc_data['fee_assignment_id']
            )

            allocation = FeePaymentAllocation.objects.create(
                receipt=receipt,
                fee_assignment=fee_assignment,
                amount=Decimal(str(alloc_data['amount'])),
                allocated_by=request.user
            )
            created_allocations.append(allocation)

        return Response({
            'message': f'Successfully allocated ₦{total_to_allocate} to {len(created_allocations)} fees',
            'allocations': FeePaymentAllocationSerializer(created_allocations, many=True).data,
            'receipt': self.get_serializer(receipt).data
        })

    @action(detail=False, methods=['get'])
    def summary_stats(self, request):
        """
        Get aggregated summary statistics for receipts matching active filters.
        GET /api/finance/receipts/summary_stats/
        """
        queryset = self.filter_queryset(self.get_queryset())
        from django.db.models import Sum, Count, Q
        from django.utils import timezone as tz

        today = tz.now().date()
        aggregates = queryset.aggregate(
            total_collected=Sum('amount'),
            total_count=Count('id'),
            today_count=Count('id', filter=Q(date=today) | Q(payment_date=today))
        )

        total_collected = aggregates['total_collected'] or Decimal('0.00')
        total_count = aggregates['total_count'] or 0
        today_count = aggregates['today_count'] or 0
        avg_payment = (total_collected / Decimal(str(total_count))) if total_count > 0 else Decimal('0.00')

        return Response({
            'total_collected': float(total_collected),
            'total_count': total_count,
            'today_count': today_count,
            'avg_payment': float(avg_payment),
        })

    @action(detail=False, methods=['get'])
    def by_student(self, request):
        """
        Get all receipts for a specific student.
        GET /api/financial/receipts/by_student/?student_id=1
        """
        student_id = request.query_params.get('student_id')

        if not student_id:
            return Response(
                {'error': 'student_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        queryset = self.get_queryset().filter(student_id=student_id)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """
        Generate and download a PDF receipt.
        GET /api/finance/receipts/{id}/download/
        """
        if not request.user or not request.user.is_authenticated:
            token = request.query_params.get("token") or request.query_params.get("access_token")
            if token:
                try:
                    from rest_framework_simplejwt.tokens import AccessToken
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    validated = AccessToken(token)
                    user_id = validated.get("user_id")
                    request.user = User.objects.get(id=user_id)
                except Exception:
                    pass

        if not request.user or not request.user.is_authenticated:
            return Response(
                {"error": 401, "detail": {"detail": "Authentication credentials were not provided."}},
                status=status.HTTP_401_UNAUTHORIZED
            )

        from django.http import HttpResponse
        from finance.tasks import render_receipt_pdf

        receipt = self.get_object()
        pdf_bytes = render_receipt_pdf(receipt)

        filename = f"receipt_{receipt.receipt_number}.pdf"
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        response['Content-Length'] = len(pdf_bytes)
        return response


class PaymentCategoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing payment categories.
    """
    queryset = PaymentCategory.objects.all()
    serializer_class = PaymentCategorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name', 'abbr']
    ordering = ['name']


class PaymentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing outgoing payments (expenses, salaries).
    """
    queryset = Payment.objects.select_related('category', 'paid_by', 'user')
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = {
        'category': ['exact'],
        'status': ['exact', 'iexact'],
        'paid_through': ['exact', 'iexact'],
        'paid_by': ['exact'],
        'date': ['gte', 'lte', 'exact'],
        'amount': ['gte', 'lte', 'exact']
    }
    search_fields = ['paid_to', 'payment_number', 'reference_number', 'description']
    ordering_fields = ['date', 'payment_number', 'amount']
    ordering = ['-date', '-payment_number']

    def perform_create(self, serializer):
        payment = serializer.save(paid_by=self.request.user)
        FinanceAuditLog.objects.create(
            user=self.request.user,
            action=AuditAction.PAYMENT_RECORDED,
            description=f"Recorded outgoing payment of ₦{payment.amount} to '{payment.paid_to}' for {payment.category.name if payment.category else 'Uncategorized'}.",
            metadata={"amount": float(payment.amount), "payment_id": payment.id}
        )

    def perform_destroy(self, instance):
        FinanceAuditLog.objects.create(
            user=self.request.user,
            action=AuditAction.PAYMENT_REVERSED,
            description=f"Reversed/deleted outgoing payment of ₦{instance.amount} to '{instance.paid_to}'.",
            metadata={"amount": float(instance.amount), "payment_id": instance.id}
        )
        instance.delete()


class StudentFeeBalanceViewSet(viewsets.ViewSet):
    """
    ViewSet for getting student fee balance summaries.

    Endpoints:
    - GET /api/finance/fee-balance/?student={id}&term={id} - Get balance by query param
    - GET /api/finance/student-balance/{student_id}/?term_id={id} - Get balance by path param
    """
    permission_classes = [IsAuthenticated]

    def _resolve_student(self, pk_or_id, user=None):
        from academic.models import Student
        from django.db.models import Q
        if pk_or_id:
            st = Student.objects.filter(id=pk_or_id).first()
            if not st:
                st = Student.objects.filter(user_id=pk_or_id).first()
            if not st and str(pk_or_id).isdigit():
                st = Student.objects.filter(Q(id=int(pk_or_id)) | Q(user_id=int(pk_or_id))).first()
            if not st:
                st = Student.objects.filter(admission_number=str(pk_or_id)).first()
            if st:
                return st
        if user and user.is_authenticated:
            return getattr(user, 'student_profile', None) or getattr(user, 'student', None) or Student.objects.filter(user=user).first()
        return None

    def list(self, request):
        """
        Get fee balance using query parameters.
        GET /api/finance/fee-balance/?student={student_id}&term={term_id}
        """
        student_id = request.query_params.get('student') or request.query_params.get('student_id')
        student = self._resolve_student(student_id, request.user)
        if not student:
            return Response(
                {'error': 'No student found matching query'},
                status=status.HTTP_404_NOT_FOUND
            )
        term_id = request.query_params.get('term')
        return self._get_student_balance(student, term_id)

    def retrieve(self, request, pk=None):
        """
        Get fee balance for a specific student.
        GET /api/financial/student-balance/{student_id}/?term_id=1
        """
        student = self._resolve_student(pk, request.user)
        if not student:
            return Response(
                {'error': 'No student found matching query'},
                status=status.HTTP_404_NOT_FOUND
            )
        term_id = request.query_params.get('term_id')
        academic_year_id = request.query_params.get('academic_year_id')
        return self._get_student_balance(student, term_id, academic_year_id)

    def _get_student_balance(self, student, term_id=None, academic_year_id=None):
        """Helper method to get student balance data"""

        # Get all fee assignments for this student
        assignments = StudentFeeAssignment.objects.filter(student=student)

        if term_id:
            assignments = assignments.filter(term_id=term_id)
            term = get_object_or_404(Term, id=term_id)
        elif academic_year_id:
            assignments = assignments.filter(term__academic_year_id=academic_year_id)
            term = None
        else:
            # Get current term
            term = Term.objects.filter(
                academic_year__active_year=True
            ).order_by('-start_date').first()

            if term:
                assignments = assignments.filter(term=term)

        # Calculate totals
        total_fees = assignments.aggregate(
            total=Sum('amount_owed')
        )['total'] or Decimal('0.00')

        total_paid = assignments.aggregate(
            total=Sum('amount_paid')
        )['total'] or Decimal('0.00')

        balance = total_fees - total_paid

        # Determine status
        if balance == 0:
            payment_status = 'Paid'
        elif total_paid > 0:
            payment_status = 'Partial'
        else:
            payment_status = 'Unpaid'

        # Fee breakdown
        fee_breakdown = []
        for assignment in assignments:
            term_name = assignment.term.name if assignment.term else 'Yearly'
            term_start = assignment.term.start_date.isoformat() if (assignment.term and hasattr(assignment.term, 'start_date') and assignment.term.start_date) else '1900-01-01'
            
            last_allocation = assignment.payment_allocations.order_by('-receipt__payment_date').first()
            payment_date = last_allocation.receipt.payment_date.isoformat() if (last_allocation and last_allocation.receipt.payment_date) else None
            
            fee_breakdown.append({
                'id': assignment.id,
                'payment_date': payment_date,
                'fee_name': assignment.fee_structure.name,
                'fee_type': assignment.fee_structure.fee_type,
                'term_name': term_name,
                'term_start': term_start,
                'amount_owed': assignment.amount_owed,
                'amount_paid': assignment.amount_paid,
                'balance': assignment.balance,
                'status': assignment.payment_status,
                'is_waived': assignment.is_waived,
            })
            
        fee_breakdown.sort(key=lambda x: x['term_start'])
        
        student_image_url = None
        if student.image:
            student_image_url = self.request.build_absolute_uri(student.image.url) if hasattr(self, 'request') and self.request else student.image.url


        # Get last payment date
        last_payment = None
        if assignments.exists():
            from finance.models import Receipt
            receipts = Receipt.objects.filter(student=student).order_by('-payment_date')
            if receipts.exists():
                last_payment = receipts.first().payment_date

        data = {
            'id': student.id,  # Add id field
            'student': student.id,
            'student_name': student.full_name,
            'student_image': student_image_url,
            'student_admission_number': student.admission_number,
            'class_level_name': str(student.classroom) if student.classroom else (str(student.class_level) if student.class_level else 'N/A'),
            'parent_name': f"{student.parent_guardian.first_name or ''} {student.parent_guardian.last_name or ''}".strip() if student.parent_guardian else "N/A",
            'parent_contact': student.parent_guardian.phone_number if student.parent_guardian else "N/A",
            'term': term.id if term else None,
            'term_name': term.name if term else None,
            'academic_year': term.academic_year.name if term else None,
            'total_fee': total_fees,  # Frontend expects total_fee
            'total_fees': total_fees,  # Keep backward compatibility
            'amount_paid': total_paid,  # Frontend expects amount_paid
            'total_paid': total_paid,  # Keep backward compatibility
            'balance': balance,
            'status': payment_status,  # Frontend expects capitalized (Paid, Partial, Unpaid)
            'last_payment_date': last_payment,
            'fee_breakdown': fee_breakdown,
        }

        return Response(data)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Get fee balance summary for all students (optimized SQL aggregate).
        GET /api/financial/student-balance/summary/?term_id=1&academic_year_id=1
        """
        term_id = request.query_params.get('term_id')
        academic_year_id = request.query_params.get('academic_year_id')
        status_param = request.query_params.get('status')
        classroom_id = request.query_params.get('classroom_id')
        fee_type = request.query_params.get('fee_type')

        students_qs = Student.objects.filter(is_active=True).select_related('classroom', 'class_level')
        if classroom_id:
            students_qs = students_qs.filter(classroom_id=classroom_id)

        assignments = StudentFeeAssignment.objects.filter(is_waived=False)
        if term_id:
            assignments = assignments.filter(term_id=term_id)
        elif academic_year_id:
            assignments = assignments.filter(term__academic_year_id=academic_year_id)
        if fee_type:
            assignments = assignments.filter(fee_structure__fee_type=fee_type)

        # 1 Single SQL aggregation query for all students
        student_totals = assignments.values('student_id').annotate(
            total_fees=Sum('amount_owed'),
            total_paid=Sum('amount_paid')
        )
        totals_map = {row['student_id']: row for row in student_totals}

        summaries = []
        for student in students_qs:
            st = totals_map.get(student.id, {})
            total_fees = st.get('total_fees') or Decimal('0.00')
            total_paid = st.get('total_paid') or Decimal('0.00')
            balance = total_fees - total_paid

            if balance == 0 and total_fees > 0:
                payment_status = 'Paid'
            elif total_paid > 0:
                payment_status = 'Partial'
            else:
                payment_status = 'Unpaid'

            if status_param and payment_status != status_param:
                continue

            summaries.append({
                'id': student.id,
                'student': student.id,
                'student_name': student.full_name,
                'student_admission_number': student.admission_number,
                'class_level_name': str(student.classroom) if student.classroom else (str(student.class_level) if student.class_level else 'N/A'),
                'total_fees': total_fees,
                'total_paid': total_paid,
                'balance': balance,
                'status': payment_status,
            })

        # Method breakdown
        from finance.models import FeePaymentAllocation
        allocations = FeePaymentAllocation.objects.filter(fee_assignment__student__in=students_qs)
        if term_id:
            allocations = allocations.filter(fee_assignment__term_id=term_id)
        elif academic_year_id:
            allocations = allocations.filter(fee_assignment__term__academic_year_id=academic_year_id)
        if fee_type:
            allocations = allocations.filter(fee_assignment__fee_structure__fee_type=fee_type)

        method_breakdown_map = {}
        for alloc in allocations.select_related('receipt'):
            method = alloc.receipt.paid_through or 'Unknown'
            method_breakdown_map[method] = method_breakdown_map.get(method, Decimal('0.00')) + alloc.amount

        method_list = [{'method': m, 'total': t} for m, t in method_breakdown_map.items()]
        method_list.sort(key=lambda x: x['total'], reverse=True)

        return Response({
            'results': summaries,
            'method_breakdown': method_list
        })


class FinanceDashboardSummaryView(APIView):
    """
    Fast, aggregated Finance Dashboard summary with 30-second Redis caching.
    GET /api/finance/dashboard/summary/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.core.cache import cache
        from django.db import connection
        from finance.models import FeePaymentAllocation, Receipt, StudentFeeAssignment

        term_id = request.query_params.get('term_id')
        academic_year_id = request.query_params.get('academic_year_id')
        classroom_id = request.query_params.get('classroom_id')
        fee_type = request.query_params.get('fee_type')

        cache_key = f"finance_dashboard_summary_{connection.schema_name}_{term_id}_{academic_year_id}_{classroom_id}_{fee_type}"
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        assignments = StudentFeeAssignment.objects.filter(is_waived=False)
        if term_id:
            assignments = assignments.filter(term_id=term_id)
        elif academic_year_id:
            assignments = assignments.filter(term__academic_year_id=academic_year_id)
        if fee_type:
            assignments = assignments.filter(fee_structure__fee_type=fee_type)
        if classroom_id:
            assignments = assignments.filter(student__classroom_id=classroom_id)

        agg = assignments.aggregate(
            expected=Sum('amount_owed'),
            collected=Sum('amount_paid')
        )
        total_expected = float(agg['expected'] or 0)
        total_collected = float(agg['collected'] or 0)
        total_outstanding = max(0.0, total_expected - total_collected)
        collection_rate = round((total_collected / total_expected * 100) if total_expected > 0 else 0, 1)

        student_totals = assignments.values('student_id').annotate(
            owed=Sum('amount_owed'),
            paid=Sum('amount_paid')
        )
        paid_count = 0
        partial_count = 0
        unpaid_count = 0

        for st in student_totals:
            owed = st['owed'] or 0
            paid = st['paid'] or 0
            bal = owed - paid
            if bal <= 0 and owed > 0:
                paid_count += 1
            elif paid > 0:
                partial_count += 1
            else:
                unpaid_count += 1

        allocations = FeePaymentAllocation.objects.all()
        if term_id:
            allocations = allocations.filter(fee_assignment__term_id=term_id)
        elif academic_year_id:
            allocations = allocations.filter(fee_assignment__term__academic_year_id=academic_year_id)
        if fee_type:
            allocations = allocations.filter(fee_assignment__fee_structure__fee_type=fee_type)

        method_breakdown_map = {}
        for alloc in allocations.select_related('receipt'):
            method = alloc.receipt.paid_through or 'Other'
            method_breakdown_map[method] = method_breakdown_map.get(method, 0.0) + float(alloc.amount)

        method_list = [{'method': m, 'total': t} for m, t in method_breakdown_map.items()]
        method_list.sort(key=lambda x: x['total'], reverse=True)

        recent_receipts_qs = Receipt.objects.select_related('student', 'term').order_by('-date', '-id')[:10]
        recent_receipts = [
            {
                'id': r.id,
                'receipt_number': r.receipt_number,
                'student_name': r.student.full_name if r.student else r.payer,
                'amount': float(r.amount),
                'method': r.paid_through,
                'date': r.payment_date.isoformat() if r.payment_date else r.date.isoformat(),
                'term_name': r.term.name if r.term else 'N/A'
            }
            for r in recent_receipts_qs
        ]

        payload = {
            'total_expected': total_expected,
            'total_collected': total_collected,
            'total_outstanding': total_outstanding,
            'collection_rate': collection_rate,
            'paid_count': paid_count,
            'partial_count': partial_count,
            'unpaid_count': unpaid_count,
            'method_breakdown': method_list,
            'recent_receipts': recent_receipts,
        }

        cache.set(cache_key, payload, 30)
        return Response(payload)

from rest_framework.views import APIView
from academic.models import Parent

class ParentFeesView(APIView):
    """
    Dedicated Parent Fees API
    GET /api/finance/parent/fees/
    Returns: Detailed fee breakdown and receipt history for all children
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            parent = Parent.objects.get(user=request.user)
        except Parent.DoesNotExist:
            return Response(
                {"error": "Parent profile not found for this user"},
                status=status.HTTP_404_NOT_FOUND
            )

        children_fees = []

        for student in parent.children.all():
            # Fee breakdown
            fee_assignments = StudentFeeAssignment.objects.filter(student=student)
            
            fee_breakdown = []
            total_fees = Decimal('0.00')
            total_paid = Decimal('0.00')
            total_balance = Decimal('0.00')

            for assignment in fee_assignments:
                owed = assignment.amount_owed
                paid = assignment.amount_paid
                balance = assignment.balance
                total_fees += owed
                total_paid += paid
                total_balance += balance
                
                fee_breakdown.append({
                    "fee_name": assignment.fee_structure.name,
                    "fee_type": assignment.fee_structure.fee_type,
                    "amount_owed": float(owed),
                    "amount_paid": float(paid),
                    "balance": float(balance),
                    "status": assignment.payment_status
                })
            
            fee_status = 'Paid' if total_balance == 0 else 'Partial' if total_paid > 0 else 'Unpaid'

            # Receipts
            receipts = Receipt.objects.filter(student=student).order_by('-payment_date', '-receipt_number')
            receipts_list = []
            for r in receipts:
                receipts_list.append({
                    "id": r.id,
                    "receipt_number": f"RCP-{r.receipt_number:06d}" if r.receipt_number else str(r.id),
                    "amount": float(r.amount),
                    "payment_date": r.payment_date.strftime('%Y-%m-%d'),
                    "paid_through": r.paid_through,
                    "term_name": r.term.name if r.term else 'N/A'
                })

            children_fees.append({
                "student_id": student.id,
                "student_name": student.full_name,
                "admission_number": student.admission_number,
                "classroom_display": student.class_level.name if student.class_level else 'N/A',
                "total_fees": float(total_fees),
                "amount_paid": float(total_paid),
                "balance": float(total_balance),
                "status": fee_status,
                "receipts": receipts_list,
                "fee_breakdown": fee_breakdown
            })

        return Response({"children_fees": children_fees})

class ReminderSettingViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing reminder settings.
    """
    queryset = ReminderSetting.objects.all()
    serializer_class = ReminderSettingSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['fee_structure', 'is_active', 'days_before_due']
    search_fields = ['name']
    ordering_fields = ['days_before_due', 'created_at']
    ordering = ['days_before_due']


class FinanceAuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing finance audit logs.
    """
    from finance.models import FinanceAuditLog
    from finance.serializers import FinanceAuditLogSerializer
    queryset = FinanceAuditLog.objects.select_related('user', 'target_student').all()
    serializer_class = FinanceAuditLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['action', 'user', 'target_student']
    search_fields = ['description', 'target_student__first_name', 'target_student__last_name', 'user__first_name', 'user__last_name']
    ordering_fields = ['timestamp']
    ordering = ['-timestamp']

