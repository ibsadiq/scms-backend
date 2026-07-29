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
    PaymentCategory,
    ReminderSetting
)
from .filters import StudentFeeAssignmentFilter
from .serializers import (
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
        'student_id': ['exact'],
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

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """
        Generate and download a PDF receipt.
        GET /api/finance/receipts/{id}/download/
        """
        from django.http import HttpResponse
        from weasyprint import HTML
        from django.utils import timezone as tz

        receipt = self.get_object()

        # Get school name from current tenant
        try:
            from django.db import connection
            from tenants.models import Client
            school_name = Client.objects.get(schema_name=connection.schema_name).name
        except Exception:
            school_name = "School"

        allocations = receipt.fee_allocations.select_related(
            'fee_assignment__fee_structure'
        ).all()

        student = receipt.student
        student_name = f"{student.first_name} {student.last_name}" if student else receipt.payer
        admission_no = student.admission_number if student else "—"
        classroom = str(student.classroom) if student and student.classroom else "—"

        # Build fee breakdown rows
        fee_rows = ""
        for alloc in allocations:
            fee_name = alloc.fee_assignment.fee_structure.name if alloc.fee_assignment else "Fee"
            fee_rows += f"""
            <tr>
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">{fee_name}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;text-align:right;">
                    &#8358;{alloc.amount:,.2f}
                </td>
            </tr>"""

        if not fee_rows:
            fee_rows = f"""
            <tr>
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">School Fees</td>
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;text-align:right;">
                    &#8358;{receipt.amount:,.2f}
                </td>
            </tr>"""

        term_name = str(receipt.term) if receipt.term else "—"
        payment_date = receipt.payment_date.strftime("%d %B %Y") if receipt.payment_date else "—"
        generated_at = tz.now().strftime("%d %B %Y, %H:%M")

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="UTF-8"/>
          <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
            * {{ margin:0; padding:0; box-sizing:border-box; }}
            body {{ font-family: Inter, Arial, sans-serif; background:#f9fafb; color:#111827; font-size:14px; }}
            .page {{ max-width:680px; margin:40px auto; background:#fff; border-radius:12px;
                     box-shadow:0 1px 3px rgba(0,0,0,.12); padding:40px; }}
            .header {{ display:flex; justify-content:space-between; align-items:flex-start;
                       border-bottom:2px solid #059669; padding-bottom:24px; margin-bottom:28px; }}
            .school-name {{ font-size:22px; font-weight:700; color:#059669; }}
            .school-sub {{ font-size:12px; color:#6b7280; margin-top:4px; }}
            .receipt-badge {{ background:#059669; color:#fff; padding:6px 18px;
                              border-radius:20px; font-size:12px; font-weight:600; }}
            .receipt-no {{ font-size:24px; font-weight:700; color:#111827; text-align:right; margin-top:6px; }}
            .section-label {{ font-size:11px; font-weight:600; color:#6b7280;
                               text-transform:uppercase; letter-spacing:.05em; margin-bottom:6px; }}
            .info-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:28px; }}
            .info-block p {{ font-size:14px; font-weight:600; color:#111827; }}
            table {{ width:100%; border-collapse:collapse; margin-bottom:20px; }}
            thead th {{ background:#f3f4f6; padding:10px 12px; text-align:left; font-size:12px;
                        font-weight:600; color:#374151; text-transform:uppercase; letter-spacing:.04em; }}
            thead th:last-child {{ text-align:right; }}
            .total-row td {{ padding:12px; font-weight:700; font-size:15px;
                             background:#f0fdf4; color:#065f46; }}
            .total-row td:last-child {{ text-align:right; }}
            .status-badge {{ display:inline-block; background:#d1fae5; color:#065f46;
                              border-radius:12px; padding:3px 12px; font-size:12px; font-weight:600; }}
            .footer {{ margin-top:32px; padding-top:20px; border-top:1px solid #e5e7eb;
                       text-align:center; font-size:11px; color:#9ca3af; }}
          </style>
        </head>
        <body>
          <div class="page">
            <div class="header">
              <div>
                <div class="school-name">{school_name}</div>
                <div class="school-sub">Official Payment Receipt</div>
              </div>
              <div style="text-align:right;">
                <span class="receipt-badge">RECEIPT</span>
                <div class="receipt-no">#{receipt.receipt_number}</div>
              </div>
            </div>

            <div class="info-grid">
              <div class="info-block">
                <div class="section-label">Student</div>
                <p>{student_name}</p>
                <div style="color:#6b7280;font-size:12px;margin-top:2px;">
                  Adm: {admission_no} &nbsp;|&nbsp; {classroom}
                </div>
              </div>
              <div class="info-block">
                <div class="section-label">Payment Details</div>
                <p>{payment_date}</p>
                <div style="color:#6b7280;font-size:12px;margin-top:2px;">
                  Via: {receipt.paid_through} &nbsp;|&nbsp; Term: {term_name}
                </div>
              </div>
              <div class="info-block">
                <div class="section-label">Received From</div>
                <p>{receipt.payer}</p>
              </div>
              <div class="info-block">
                <div class="section-label">Status</div>
                <span class="status-badge">{receipt.status}</span>
              </div>
            </div>

            <table>
              <thead>
                <tr>
                  <th>Description</th>
                  <th style="text-align:right;">Amount</th>
                </tr>
              </thead>
              <tbody>
                {fee_rows}
              </tbody>
              <tfoot>
                <tr class="total-row">
                  <td>Total Paid</td>
                  <td>&#8358;{receipt.amount:,.2f}</td>
                </tr>
              </tfoot>
            </table>

            {"<p style='font-size:12px;color:#6b7280;margin-bottom:16px;'><strong>Remarks:</strong> " + receipt.remarks + "</p>" if receipt.remarks else ""}
            {"<p style='font-size:12px;color:#6b7280;'><strong>Reference:</strong> " + receipt.reference_number + "</p>" if receipt.reference_number else ""}

            <div class="footer">
              <p>This is a computer-generated receipt. No signature required.</p>
              <p style="margin-top:4px;">Generated on {generated_at} &nbsp;|&nbsp; {school_name} Finance System</p>
            </div>
          </div>
        </body>
        </html>
        """

        pdf = HTML(string=html_content).write_pdf()
        filename = f"receipt_{receipt.receipt_number}.pdf"
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        response['Content-Length'] = len(pdf)
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
        Get fee balance summary for all students.
        GET /api/financial/student-balance/summary/?term_id=1&academic_year_id=1
        """
        term_id = request.query_params.get('term_id')
        academic_year_id = request.query_params.get('academic_year_id')
        status_param = request.query_params.get('status')
        classroom_id = request.query_params.get('classroom_id')
        fee_type = request.query_params.get('fee_type')

        students = Student.objects.filter(is_active=True)
        if classroom_id:
            students = students.filter(classroom_id=classroom_id)

        summaries = []

        for student in students:
            assignments = StudentFeeAssignment.objects.filter(student=student)

            if term_id:
                assignments = assignments.filter(term_id=term_id)
            elif academic_year_id:
                assignments = assignments.filter(term__academic_year_id=academic_year_id)

            if fee_type:
                assignments = assignments.filter(fee_structure__fee_type=fee_type)

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

        # Calculate mathematically sound method breakdown based on fee allocations
        from finance.models import FeePaymentAllocation

        allocations = FeePaymentAllocation.objects.filter(fee_assignment__student__in=students)
        if term_id:
            allocations = allocations.filter(fee_assignment__term_id=term_id)
        elif academic_year_id:
            allocations = allocations.filter(fee_assignment__term__academic_year_id=academic_year_id)
            
        if fee_type:
            allocations = allocations.filter(fee_assignment__fee_structure__fee_type=fee_type)

        # Aggregate allocations by receipt payment method
        method_breakdown_map = {}
        # Avoid N+1 queries by selecting related receipt
        for alloc in allocations.select_related('receipt'):
            method = alloc.receipt.paid_through or 'Unknown'
            method_breakdown_map[method] = method_breakdown_map.get(method, Decimal('0.00')) + alloc.amount
            
        method_list = [{'method': m, 'total': t} for m, t in method_breakdown_map.items()]
        method_list.sort(key=lambda x: x['total'], reverse=True)

        return Response({
            'results': summaries,
            'method_breakdown': method_list
        })

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

