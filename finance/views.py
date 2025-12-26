# views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Sum, Q, F
from django.shortcuts import get_object_or_404
from decimal import Decimal
from .models import (
    FeeStructure,
    StudentFeeAssignment,
    FeeAdjustment,
    Receipt,
    FeePaymentAllocation,
    Payment,
    PaymentCategory
)
from .serializers import (
    FeeStructureSerializer,
    StudentFeeAssignmentSerializer,
    FeeAdjustmentSerializer,
    ReceiptSerializer,
    FeePaymentAllocationSerializer,
    PaymentSerializer,
    PaymentCategorySerializer,
    StudentFeeBalanceSerializer
)
from academic.models import Student
from administration.models import Term


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
    filterset_fields = ['student', 'term', 'fee_structure', 'is_waived', 'fee_structure__fee_type']
    search_fields = ['student__first_name', 'student__last_name', 'student__admission_number', 'fee_structure__name']
    ordering_fields = ['assigned_date', 'amount_owed', 'balance']
    ordering = ['-assigned_date']

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

    @action(detail=True, methods=['post'])
    def waive(self, request, pk=None):
        """
        Waive a fee (scholarship, discount, etc.).
        POST /api/financial/student-fee-assignments/{id}/waive/
        Body: { "reason": "Scholarship awarded" }
        """
        assignment = self.get_object()
        reason = request.data.get('reason', 'No reason provided')

        assignment.waive_fee(reason=reason, waived_by=request.user)

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
            assignment.adjust_amount(new_amount, reason)

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
        'term',
        'received_by'
    ).prefetch_related('fee_allocations')
    serializer_class = ReceiptSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = {
        'student': ['exact'],
        'term': ['exact'],
        'status': ['exact', 'iexact'],
        'paid_through': ['exact', 'iexact'],
        'received_by': ['exact'],
        'date': ['gte', 'lte', 'exact'],
        'amount': ['gte', 'lte', 'exact']
    }
    search_fields = ['payer', 'reference_number', 'receipt_number', 'student__first_name', 'student__last_name', 'student__admission_number']
    ordering_fields = ['date', 'receipt_number', 'amount']
    ordering = ['-date', '-receipt_number']

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


class StudentFeeBalanceViewSet(viewsets.ViewSet):
    """
    ViewSet for getting student fee balance summaries.

    Endpoints:
    - GET /api/finance/fee-balance/?student={id}&term={id} - Get balance by query param
    - GET /api/finance/student-balance/{student_id}/?term_id={id} - Get balance by path param
    """
    permission_classes = [IsAuthenticated]

    def list(self, request):
        """
        Get fee balance using query parameters.
        GET /api/finance/fee-balance/?student={student_id}&term={term_id}
        """
        student_id = request.query_params.get('student')

        if not student_id:
            return Response(
                {'error': 'student parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Use the retrieve logic with query params
        student = get_object_or_404(Student, id=student_id)
        term_id = request.query_params.get('term')

        return self._get_student_balance(student, term_id)

    def retrieve(self, request, pk=None):
        """
        Get fee balance for a specific student.
        GET /api/financial/student-balance/{student_id}/?term_id=1
        """
        student = get_object_or_404(Student, id=pk)
        term_id = request.query_params.get('term_id')

        return self._get_student_balance(student, term_id)

    def _get_student_balance(self, student, term_id=None):
        """Helper method to get student balance data"""

        # Get all fee assignments for this student
        assignments = StudentFeeAssignment.objects.filter(student=student)

        if term_id:
            assignments = assignments.filter(term_id=term_id)
            term = get_object_or_404(Term, id=term_id)
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
            fee_breakdown.append({
                'id': assignment.id,
                'fee_name': assignment.fee_structure.name,
                'fee_type': assignment.fee_structure.fee_type,
                'amount_owed': assignment.amount_owed,
                'amount_paid': assignment.amount_paid,
                'balance': assignment.balance,
                'status': assignment.payment_status,
                'is_waived': assignment.is_waived,
            })

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
            'student_admission_number': student.admission_number,
            'term': term.id if term else None,
            'term_name': term.name if term else None,
            'academic_year': term.academic_year.name if term else None,
            'total_fee': total_fees,  # Frontend expects total_fee
            'total_fees': total_fees,  # Keep backward compatibility
            'amount_paid': total_paid,  # Frontend expects amount_paid
            'total_paid': total_paid,  # Keep backward compatibility
            'balance': balance,
            'status': payment_status.lower(),  # Frontend expects lowercase
            'last_payment_date': last_payment,
            'fee_breakdown': fee_breakdown,
        }

        serializer = StudentFeeBalanceSerializer(data)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Get fee balance summary for all students.
        GET /api/financial/student-balance/summary/?term_id=1
        """
        term_id = request.query_params.get('term_id')

        students = Student.objects.filter(status='Active')
        summaries = []

        for student in students:
            assignments = StudentFeeAssignment.objects.filter(student=student)

            if term_id:
                assignments = assignments.filter(term_id=term_id)

            total_fees = assignments.aggregate(
                total=Sum('amount_owed')
            )['total'] or Decimal('0.00')

            total_paid = assignments.aggregate(
                total=Sum('amount_paid')
            )['total'] or Decimal('0.00')

            balance = total_fees - total_paid

            if balance == 0:
                payment_status = 'Paid'
            elif total_paid > 0:
                payment_status = 'Partial'
            else:
                payment_status = 'Unpaid'

            summaries.append({
                'student': student.id,
                'student_name': student.full_name,
                'student_admission_number': student.admission_number,
                'total_fees': total_fees,
                'total_paid': total_paid,
                'balance': balance,
                'status': payment_status,
            })

        return Response(summaries)
