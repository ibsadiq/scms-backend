"""
Parent Portal Views (Phase 1.4)
Provides parents with read-only access to their children's academic information.

Features:
- Parent dashboard with children overview
- View children's published results
- View children's attendance records
- View children's fee status and payment history
- View children's timetable
- View children's basic information

Security:
- Parents can ONLY view their own children's data
- Results must be published to be visible
- No modification permissions
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Q, Sum, Avg, Prefetch
from django.utils import timezone
from datetime import timedelta

from .models import (
    MarksManagement,
    ExaminationListHandler,
    TermResult, 
    SubjectResult
)
from academic.models import Student, AllocatedSubject, ClassRoom
from attendance.models import StudentAttendance, AttendanceStatus
from finance.models import Receipt, StudentFeeAssignment, FeePaymentAllocation
from schedule.models import Period
from administration.models import Term, AcademicYear

from .serializers import (
    TermResultListSerializer,
    SubjectResultSerializer,
)
from .permissions import IsParentOfStudent, CanViewChildData


class ParentDashboardViewSet(viewsets.ViewSet):
    """
    Parent Dashboard ViewSet (Phase 1.4)

    Provides parents with an overview of their children's academic status.

    Endpoints:
    - GET /api/examination/parent/dashboard/ - Overview of all children
    - GET /api/examination/parent/children/ - List of parent's children
    - GET /api/examination/parent/children/{id}/ - Specific child details
    """

    permission_classes = [IsAuthenticated, IsParentOfStudent]

    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """
        Parent dashboard showing overview of all children.

        Returns:
        - Parent information
        - List of children with summary statistics
        - Recent updates and notifications
        """
        try:
            parent = request.user.parent
        except AttributeError:
            return Response(
                {'error': 'User does not have a parent profile'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get all children
        children = Student.objects.filter(
            parent_guardian=parent,
            is_active=True
        ).select_related(
            'classroom',
            'classroom__name',
            'classroom__stream',
            'class_level'
        ).prefetch_related(
            Prefetch(
                'termresult_set',
                queryset=TermResult.objects.filter(is_published=True).order_by('-term__start_date')
            )
        )

        children_data = []

        for child in children:
            # Get latest published result
            latest_result = child.termresult_set.first() if child.termresult_set.exists() else None

            # Get attendance summary (last 30 days)
            thirty_days_ago = timezone.now().date() - timedelta(days=30)
            attendance_records = StudentAttendance.objects.filter(
                student=child,
                date__gte=thirty_days_ago
            )

            total_days = attendance_records.count()
            absent_days = attendance_records.filter(status__absent=True).count()
            late_days = attendance_records.filter(status__late=True).count()

            # Get fee balance
            fee_assignments = StudentFeeAssignment.objects.filter(
                student=child,
                is_active=True
            )

            total_fees = sum(fa.total_amount for fa in fee_assignments)
            total_paid = sum(fa.amount_paid for fa in fee_assignments)
            balance = total_fees - total_paid

            children_data.append({
                'student_id': child.id,
                'admission_number': child.admission_number,
                'full_name': child.full_name,
                'classroom': str(child.classroom) if child.classroom else 'Not Assigned',
                'class_level': str(child.class_level) if child.class_level else 'N/A',
                'latest_result': {
                    'term': str(latest_result.term) if latest_result else None,
                    'average': float(latest_result.average) if latest_result else None,
                    'position': latest_result.position if latest_result else None,
                    'total_students': latest_result.total_students if latest_result else None,
                    'grade': latest_result.grade if latest_result else None
                } if latest_result else None,
                'attendance_summary': {
                    'total_days': total_days,
                    'absent_days': absent_days,
                    'late_days': late_days,
                    'attendance_rate': round(((total_days - absent_days) / total_days * 100), 1) if total_days > 0 else 100
                },
                'fee_summary': {
                    'total_fees': float(total_fees),
                    'total_paid': float(total_paid),
                    'balance': float(balance),
                    'status': 'Paid' if balance == 0 else 'Partial' if total_paid > 0 else 'Unpaid'
                }
            })

        return Response({
            'parent_name': parent.full_name,
            'parent_email': parent.email,
            'parent_phone': parent.phone_number,
            'total_children': len(children_data),
            'children': children_data,
            'current_term': str(Term.get_active_term()) if Term.get_active_term() else None,
            'current_academic_year': str(AcademicYear.get_active_year()) if AcademicYear.get_active_year() else None
        })

    @action(detail=False, methods=['get'])
    def children(self, request):
        """
        Get list of parent's children with basic information.
        """
        try:
            parent = request.user.parent
        except AttributeError:
            return Response(
                {'error': 'User does not have a parent profile'},
                status=status.HTTP_403_FORBIDDEN
            )

        children = Student.objects.filter(
            parent_guardian=parent,
            is_active=True
        ).select_related('classroom', 'class_level')

        children_data = [{
            'id': child.id,
            'admission_number': child.admission_number,
            'full_name': child.full_name,
            'classroom': str(child.classroom) if child.classroom else 'Not Assigned',
            'class_level': str(child.class_level) if child.class_level else 'N/A',
            'gender': child.gender,
            'date_of_birth': child.date_of_birth
        } for child in children]

        return Response({
            'count': len(children_data),
            'children': children_data
        })

    @action(detail=True, methods=['get'])
    def child_detail(self, request, pk=None):
        """
        Get detailed information about a specific child.

        Args:
            pk: Student ID
        """
        try:
            parent = request.user.parent
        except AttributeError:
            return Response(
                {'error': 'User does not have a parent profile'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            child = Student.objects.select_related(
                'classroom',
                'class_level',
                'parent_guardian'
            ).get(id=pk, parent_guardian=parent, is_active=True)
        except Student.DoesNotExist:
            return Response(
                {'error': 'Child not found or you do not have permission to view this child'},
                status=status.HTTP_404_NOT_FOUND
            )

        return Response({
            'id': child.id,
            'admission_number': child.admission_number,
            'full_name': child.full_name,
            'first_name': child.first_name,
            'middle_name': child.middle_name,
            'last_name': child.last_name,
            'gender': child.gender,
            'date_of_birth': child.date_of_birth,
            'classroom': str(child.classroom) if child.classroom else 'Not Assigned',
            'class_level': str(child.class_level) if child.class_level else 'N/A',
            'admission_date': child.admission_date,
            'blood_group': child.blood_group,
            'religion': child.religion,
            'address': f"{child.street}, {child.city}, {child.region}" if child.street else None
        })


class ParentResultsViewSet(viewsets.ViewSet):
    """
    Parent Results ViewSet (Phase 1.4)

    Allows parents to view their children's PUBLISHED results only.

    Endpoints:
    - GET /api/examination/parent/results/child/{child_id}/ - Child's results
    - GET /api/examination/parent/results/term/{term_result_id}/ - Specific term result
    """

    permission_classes = [IsAuthenticated, CanViewChildData]

    @action(detail=False, methods=['get'], url_path='child/(?P<child_id>[^/.]+)')
    def child_results(self, request, child_id=None):
        """
        Get all published results for a specific child.

        Args:
            child_id: Student ID
        """
        try:
            parent = request.user.parent
        except AttributeError:
            return Response(
                {'error': 'User does not have a parent profile'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Verify child belongs to parent
        try:
            child = Student.objects.get(
                id=child_id,
                parent_guardian=parent,
                is_active=True
            )
        except Student.DoesNotExist:
            return Response(
                {'error': 'Child not found or you do not have permission'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get all published term results for this child
        term_results = TermResult.objects.filter(
            student=child,
            is_published=True
        ).select_related(
            'term',
            'academic_year',
            'student',
            'classroom'
        ).order_by('-term__start_date')

        serializer = TermResultListSerializer(term_results, many=True)

        return Response({
            'child_name': child.full_name,
            'admission_number': child.admission_number,
            'total_results': term_results.count(),
            'results': serializer.data
        })

    @action(detail=True, methods=['get'], url_path='term')
    def term_result_detail(self, request, pk=None):
        """
        Get detailed term result with subject breakdown.

        Args:
            pk: TermResult ID
        """
        try:
            parent = request.user.parent
        except AttributeError:
            return Response(
                {'error': 'User does not have a parent profile'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get term result and verify access
        try:
            term_result = TermResult.objects.select_related(
                'student',
                'term',
                'academic_year',
                'classroom'
            ).get(id=pk, is_published=True)

            # Verify child belongs to parent
            if term_result.student.parent_guardian != parent:
                raise PermissionError

        except TermResult.DoesNotExist:
            return Response(
                {'error': 'Result not found or not yet published'},
                status=status.HTTP_404_NOT_FOUND
            )
        except PermissionError:
            return Response(
                {'error': 'You do not have permission to view this result'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get subject results
        subject_results = SubjectResult.objects.filter(
            term_result=term_result
        ).select_related('subject').order_by('subject__name')

        term_serializer = TermResultListSerializer(term_result)
        subject_serializer = SubjectResultSerializer(subject_results, many=True)

        return Response({
            'term_result': term_serializer.data,
            'subject_results': subject_serializer.data
        })


class ParentAttendanceViewSet(viewsets.ViewSet):
    """
    Parent Attendance ViewSet (Phase 1.4)

    Allows parents to view their children's attendance records.

    Endpoints:
    - GET /api/examination/parent/attendance/child/{child_id}/ - Child's attendance
    - GET /api/examination/parent/attendance/summary/{child_id}/ - Attendance summary
    """

    permission_classes = [IsAuthenticated, IsParentOfStudent]

    @action(detail=False, methods=['get'], url_path='child/(?P<child_id>[^/.]+)')
    def child_attendance(self, request, child_id=None):
        """
        Get attendance records for a specific child.

        Query Parameters:
        - start_date: Filter from date (YYYY-MM-DD)
        - end_date: Filter to date (YYYY-MM-DD)
        - status: Filter by status (absent, late, etc.)
        """
        try:
            parent = request.user.parent
        except AttributeError:
            return Response(
                {'error': 'User does not have a parent profile'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Verify child belongs to parent
        try:
            child = Student.objects.get(
                id=child_id,
                parent_guardian=parent,
                is_active=True
            )
        except Student.DoesNotExist:
            return Response(
                {'error': 'Child not found or you do not have permission'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Build query
        attendance_query = StudentAttendance.objects.filter(
            student=child
        ).select_related('status').order_by('-date')

        # Apply filters
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        status_filter = request.query_params.get('status')

        if start_date:
            attendance_query = attendance_query.filter(date__gte=start_date)
        if end_date:
            attendance_query = attendance_query.filter(date__lte=end_date)
        if status_filter:
            attendance_query = attendance_query.filter(status__name__iexact=status_filter)

        # Format attendance records
        attendance_records = [{
            'id': record.id,
            'date': record.date,
            'status': record.status.name if record.status else 'Present',
            'status_code': record.status.code if record.status else 'P',
            'is_absent': record.status.absent if record.status else False,
            'is_late': record.status.late if record.status else False,
            'is_excused': record.status.excused if record.status else False,
            'notes': record.notes
        } for record in attendance_query]

        return Response({
            'child_name': child.full_name,
            'admission_number': child.admission_number,
            'total_records': len(attendance_records),
            'attendance': attendance_records
        })

    @action(detail=False, methods=['get'], url_path='summary/(?P<child_id>[^/.]+)')
    def attendance_summary(self, request, child_id=None):
        """
        Get attendance summary statistics for a child.

        Query Parameters:
        - term_id: Filter by specific term
        - year: Filter by year (YYYY)
        """
        try:
            parent = request.user.parent
        except AttributeError:
            return Response(
                {'error': 'User does not have a parent profile'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Verify child belongs to parent
        try:
            child = Student.objects.get(
                id=child_id,
                parent_guardian=parent,
                is_active=True
            )
        except Student.DoesNotExist:
            return Response(
                {'error': 'Child not found or you do not have permission'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Build base query
        attendance_query = StudentAttendance.objects.filter(student=child)

        # Apply filters
        term_id = request.query_params.get('term_id')
        year = request.query_params.get('year')

        if term_id:
            try:
                term = Term.objects.get(id=term_id)
                attendance_query = attendance_query.filter(
                    date__gte=term.start_date,
                    date__lte=term.end_date
                )
            except Term.DoesNotExist:
                pass
        elif year:
            attendance_query = attendance_query.filter(date__year=year)

        # Calculate statistics
        total_records = attendance_query.count()
        absent_count = attendance_query.filter(status__absent=True).count()
        late_count = attendance_query.filter(status__late=True).count()
        excused_count = attendance_query.filter(status__excused=True).count()

        # Calculate attendance rate
        attendance_rate = round(((total_records - absent_count) / total_records * 100), 1) if total_records > 0 else 100

        return Response({
            'child_name': child.full_name,
            'admission_number': child.admission_number,
            'summary': {
                'total_days_tracked': total_records,
                'absent_days': absent_count,
                'late_days': late_count,
                'excused_absences': excused_count,
                'attendance_rate': attendance_rate,
                'present_days': total_records - absent_count
            }
        })


class ParentFeeViewSet(viewsets.ViewSet):
    """
    Parent Fee ViewSet (Phase 1.4)

    Allows parents to view fee status and payment history for their children.

    Endpoints:
    - GET /api/examination/parent/fees/child/{child_id}/ - Child's fee status
    - GET /api/examination/parent/fees/payments/{child_id}/ - Payment history
    """

    permission_classes = [IsAuthenticated, IsParentOfStudent]

    @action(detail=False, methods=['get'], url_path='child/(?P<child_id>[^/.]+)')
    def child_fees(self, request, child_id=None):
        """
        Get fee status for a specific child.

        Query Parameters:
        - term_id: Filter by specific term
        """
        try:
            parent = request.user.parent
        except AttributeError:
            return Response(
                {'error': 'User does not have a parent profile'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Verify child belongs to parent
        try:
            child = Student.objects.get(
                id=child_id,
                parent_guardian=parent,
                is_active=True
            )
        except Student.DoesNotExist:
            return Response(
                {'error': 'Child not found or you do not have permission'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get fee assignments
        fee_query = StudentFeeAssignment.objects.filter(
            student=child,
            is_active=True
        ).select_related('fee_structure', 'term', 'academic_year')

        # Apply term filter
        term_id = request.query_params.get('term_id')
        if term_id:
            fee_query = fee_query.filter(term_id=term_id)

        fee_data = []
        total_fees = 0
        total_paid = 0

        for fee in fee_query:
            total_fees += fee.total_amount
            total_paid += fee.amount_paid

            fee_data.append({
                'id': fee.id,
                'fee_name': fee.fee_structure.name,
                'fee_type': fee.fee_structure.fee_type,
                'amount': float(fee.total_amount),
                'paid': float(fee.amount_paid),
                'balance': float(fee.balance),
                'term': str(fee.term) if fee.term else None,
                'academic_year': str(fee.academic_year) if fee.academic_year else None,
                'due_date': fee.due_date,
                'status': 'Paid' if fee.balance == 0 else 'Partial' if fee.amount_paid > 0 else 'Unpaid'
            })

        total_balance = total_fees - total_paid

        return Response({
            'child_name': child.full_name,
            'admission_number': child.admission_number,
            'summary': {
                'total_fees': float(total_fees),
                'total_paid': float(total_paid),
                'total_balance': float(total_balance),
                'payment_status': 'Paid' if total_balance == 0 else 'Partial' if total_paid > 0 else 'Unpaid'
            },
            'fees': fee_data
        })

    @action(detail=False, methods=['get'], url_path='payments/(?P<child_id>[^/.]+)')
    def payment_history(self, request, child_id=None):
        """
        Get payment history for a specific child.

        Query Parameters:
        - start_date: Filter from date
        - end_date: Filter to date
        """
        try:
            parent = request.user.parent
        except AttributeError:
            return Response(
                {'error': 'User does not have a parent profile'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Verify child belongs to parent
        try:
            child = Student.objects.get(
                id=child_id,
                parent_guardian=parent,
                is_active=True
            )
        except Student.DoesNotExist:
            return Response(
                {'error': 'Child not found or you do not have permission'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get receipts
        receipt_query = Receipt.objects.filter(
            student=child,
            status='Completed'
        ).select_related('term', 'received_by').order_by('-date')

        # Apply date filters
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if start_date:
            receipt_query = receipt_query.filter(date__gte=start_date)
        if end_date:
            receipt_query = receipt_query.filter(date__lte=end_date)

        payment_data = []
        total_paid = 0

        for receipt in receipt_query:
            total_paid += receipt.amount

            # Get fee allocations for this receipt
            allocations = FeePaymentAllocation.objects.filter(
                receipt=receipt
            ).select_related('fee_assignment__fee_structure')

            allocated_fees = [{
                'fee_name': alloc.fee_assignment.fee_structure.name,
                'amount_allocated': float(alloc.amount_allocated)
            } for alloc in allocations]

            payment_data.append({
                'id': receipt.id,
                'receipt_number': receipt.receipt_number,
                'date': receipt.date,
                'amount': float(receipt.amount),
                'paid_through': receipt.paid_through,
                'payer': receipt.payer,
                'term': str(receipt.term) if receipt.term else None,
                'allocated_to': allocated_fees,
                'notes': receipt.notes
            })

        return Response({
            'child_name': child.full_name,
            'admission_number': child.admission_number,
            'total_payments': len(payment_data),
            'total_amount_paid': float(total_paid),
            'payments': payment_data
        })


class ParentTimetableViewSet(viewsets.ViewSet):
    """
    Parent Timetable ViewSet (Phase 1.4)

    Allows parents to view their children's class timetable.

    Endpoints:
    - GET /api/examination/parent/timetable/child/{child_id}/ - Child's timetable
    """

    permission_classes = [IsAuthenticated, IsParentOfStudent]

    @action(detail=False, methods=['get'], url_path='child/(?P<child_id>[^/.]+)')
    def child_timetable(self, request, child_id=None):
        """
        Get timetable for a specific child's classroom.

        Query Parameters:
        - day: Filter by specific day (Monday, Tuesday, etc.)
        """
        try:
            parent = request.user.parent
        except AttributeError:
            return Response(
                {'error': 'User does not have a parent profile'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Verify child belongs to parent
        try:
            child = Student.objects.select_related('classroom').get(
                id=child_id,
                parent_guardian=parent,
                is_active=True
            )
        except Student.DoesNotExist:
            return Response(
                {'error': 'Child not found or you do not have permission'},
                status=status.HTTP_404_NOT_FOUND
            )

        if not child.classroom:
            return Response({
                'child_name': child.full_name,
                'message': 'Child is not assigned to a classroom yet',
                'timetable': {}
            })

        # Get timetable for child's classroom
        period_query = Period.objects.filter(
            classroom=child.classroom,
            is_active=True
        ).select_related(
            'teacher',
            'teacher__user',
            'subject',
            'subject__subject'
        ).order_by('day_of_week', 'start_time')

        # Apply day filter
        day_filter = request.query_params.get('day')
        if day_filter:
            period_query = period_query.filter(day_of_week=day_filter)

        # Organize by day
        timetable = {}
        for period in period_query:
            day = period.day_of_week
            if day not in timetable:
                timetable[day] = []

            teacher_name = str(period.teacher) if period.teacher else 'TBA'
            subject_name = period.subject.subject.name if period.subject and period.subject.subject else 'Unknown'

            timetable[day].append({
                'subject': subject_name,
                'teacher': teacher_name,
                'start_time': period.start_time.strftime('%H:%M'),
                'end_time': period.end_time.strftime('%H:%M'),
                'room_number': period.room_number,
                'notes': period.notes
            })

        return Response({
            'child_name': child.full_name,
            'classroom': str(child.classroom),
            'timetable': timetable
        })
