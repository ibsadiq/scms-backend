# api/reports/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q, Count, Sum, Avg, F, DecimalField, Case, When, FloatField
from django.db.models.functions import Coalesce
from decimal import Decimal
from datetime import datetime
import csv
from django.http import HttpResponse, FileResponse
import io

from academic.models import Student, ClassLevel, GradeLevel, ClassRoom
from finance.models import Receipt, StudentFeeAssignment, FeeStructure
from attendance.models import StudentAttendance, AttendanceStatus
from administration.models import Term, AcademicYear

from .serializers import (
    StudentReportResponseSerializer,
    FinancialReportSerializer,
    AttendanceReportResponseSerializer,
)

# Try importing ReportLab for PDF generation
try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


# ============================================================================
# STUDENT REPORT ENDPOINTS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def student_report(request):
    """
    Generate comprehensive student report with demographics, attendance,
    performance, and financial data.

    Query Parameters:
    - academic_year: Filter by academic year ID
    - term: Filter by term ID
    - grade_level: Filter by grade level ID
    - class_level: Filter by class level ID
    - status: Filter by student status (Active, Inactive, Graduated, Withdrawn)
    - date_from: Filter attendance/payments from this date
    - date_to: Filter attendance/payments to this date
    """
    # Get filters from query params
    academic_year_id = request.query_params.get('academic_year')
    term_id = request.query_params.get('term')
    grade_level_id = request.query_params.get('grade_level')
    class_level_id = request.query_params.get('class_level')
    student_status = request.query_params.get('status')
    date_from = request.query_params.get('date_from')
    date_to = request.query_params.get('date_to')

    # Base queryset
    students = Student.objects.select_related(
        'classroom__name',
        'classroom__name__grade_level',
        'class_level',
        'class_level__grade_level'
    ).all()

    # Apply filters
    if class_level_id:
        students = students.filter(Q(class_level_id=class_level_id) | Q(classroom__name_id=class_level_id))

    if grade_level_id:
        students = students.filter(
            Q(class_level__grade_level_id=grade_level_id) |
            Q(classroom__name__grade_level_id=grade_level_id)
        )

    if student_status:
        if student_status == 'Active':
            students = students.filter(is_active=True, graduation_date__isnull=True, date_dismissed__isnull=True)
        elif student_status == 'Inactive':
            students = students.filter(is_active=False, graduation_date__isnull=True, date_dismissed__isnull=True)
        elif student_status == 'Graduated':
            students = students.filter(graduation_date__isnull=False)
        elif student_status == 'Withdrawn':
            students = students.filter(date_dismissed__isnull=True)

    # Build student data
    student_data = []
    total_attendance_rate = 0
    attendance_count = 0
    total_balance = Decimal('0.00')
    active_students = 0

    for student in students:
        # Get class name
        class_name = ""
        grade_level = ""
        if student.classroom:
            class_name = str(student.classroom.name)
            if student.classroom.name.grade_level:
                grade_level = student.classroom.name.grade_level.name
        elif student.class_level:
            class_name = student.class_level.name
            if student.class_level.grade_level:
                grade_level = student.class_level.grade_level.name

        # Calculate attendance rate
        attendance_query = StudentAttendance.objects.filter(student=student)

        if date_from:
            attendance_query = attendance_query.filter(date__gte=date_from)
        if date_to:
            attendance_query = attendance_query.filter(date__lte=date_to)

        # Get absent status
        absent_statuses = AttendanceStatus.objects.filter(absent=True)

        total_absent = attendance_query.filter(status__in=absent_statuses).count()

        # Calculate attendance rate (assuming total school days in period)
        # For simplicity, we'll use a rough estimate
        if date_from and date_to:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
            total_days = (date_to_obj - date_from_obj).days
            # Rough estimate: 5 school days per week
            school_days = (total_days // 7) * 5
        else:
            school_days = 100  # Default assumption

        total_present = max(0, school_days - total_absent)
        attendance_rate = (total_present / school_days * 100) if school_days > 0 else None

        # Calculate fee balance
        fee_assignments = StudentFeeAssignment.objects.filter(student=student)
        if term_id:
            fee_assignments = fee_assignments.filter(term_id=term_id)

        total_fees = fee_assignments.aggregate(total=Sum('amount_owed'))['total'] or Decimal('0.00')
        fees_paid = fee_assignments.aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')
        balance = total_fees - fees_paid

        # Get status
        student_status_text = student.status

        student_data.append({
            'student_id': student.id,
            'admission_number': student.admission_number or '',
            'full_name': student.full_name,
            'class_name': class_name,
            'grade_level': grade_level,
            'status': student_status_text,
            'attendance_rate': round(attendance_rate, 2) if attendance_rate is not None else None,
            'total_present': total_present,
            'total_absent': total_absent,
            'average_grade': None,  # TODO: Implement grade calculation
            'total_fees': total_fees,
            'fees_paid': fees_paid,
            'balance': balance,
        })

        # Aggregate for summary
        if attendance_rate is not None:
            total_attendance_rate += attendance_rate
            attendance_count += 1

        total_balance += balance

        if student_status_text == 'Active':
            active_students += 1

    # Calculate summary
    total_students = len(student_data)
    avg_attendance = (total_attendance_rate / attendance_count) if attendance_count > 0 else 0
    avg_balance = (total_balance / total_students) if total_students > 0 else Decimal('0.00')

    response_data = {
        'students': student_data,
        'summary': {
            'total_students': total_students,
            'active_students': active_students,
            'average_attendance': round(avg_attendance, 2),
            'average_balance': avg_balance,
        }
    }

    serializer = StudentReportResponseSerializer(data=response_data)
    serializer.is_valid(raise_exception=True)

    return Response(serializer.validated_data, status=status.HTTP_200_OK)


# ============================================================================
# FINANCIAL REPORT ENDPOINTS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def financial_report(request):
    """
    Generate financial report with collections, revenue breakdown,
    payment methods, and defaulters.

    Query Parameters:
    - academic_year: Filter by academic year ID
    - term: Filter by term ID
    - date_from: Filter payments from this date
    - date_to: Filter payments to this date
    - payment_method: Filter by payment method (Cash, Bank Transfer, etc.)
    - class_level: Filter by class level ID
    """
    # Get filters from query params
    academic_year_id = request.query_params.get('academic_year')
    term_id = request.query_params.get('term')
    date_from = request.query_params.get('date_from')
    date_to = request.query_params.get('date_to')
    payment_method = request.query_params.get('payment_method')
    class_level_id = request.query_params.get('class_level')

    # Base queryset for receipts
    receipts = Receipt.objects.filter(status='Completed')

    # Apply date filters
    if date_from:
        receipts = receipts.filter(date__gte=date_from)
    if date_to:
        receipts = receipts.filter(date__lte=date_to)

    # Apply payment method filter
    if payment_method:
        receipts = receipts.filter(paid_through=payment_method)

    # Apply term filter
    if term_id:
        receipts = receipts.filter(term_id=term_id)

    # Apply class level filter (filter by student's class)
    if class_level_id:
        receipts = receipts.filter(
            Q(student__class_level_id=class_level_id) |
            Q(student__classroom__name_id=class_level_id)
        )

    # Calculate total collected
    total_collected = receipts.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # Calculate revenue by payment method
    payment_by_method = receipts.values('paid_through').annotate(
        amount=Sum('amount'),
        count=Count('id')
    ).order_by('-amount')

    payment_by_method_data = [
        {
            'method': item['paid_through'],
            'amount': item['amount'],
            'count': item['count']
        }
        for item in payment_by_method
    ]

    # Calculate revenue by fee type
    # Get all fee assignments that have payments
    fee_assignments = StudentFeeAssignment.objects.filter(amount_paid__gt=0)

    if term_id:
        fee_assignments = fee_assignments.filter(term_id=term_id)

    if class_level_id:
        fee_assignments = fee_assignments.filter(
            Q(student__class_level_id=class_level_id) |
            Q(student__classroom__name_id=class_level_id)
        )

    revenue_by_type = fee_assignments.values(
        'fee_structure__fee_type'
    ).annotate(
        amount=Sum('amount_paid')
    ).order_by('-amount')

    revenue_by_type_data = [
        {
            'fee_type': item['fee_structure__fee_type'] or 'Unknown',
            'amount': item['amount']
        }
        for item in revenue_by_type
    ]

    # Calculate total outstanding (all balances)
    all_assignments = StudentFeeAssignment.objects.filter(is_waived=False)

    if term_id:
        all_assignments = all_assignments.filter(term_id=term_id)

    if class_level_id:
        all_assignments = all_assignments.filter(
            Q(student__class_level_id=class_level_id) |
            Q(student__classroom__name_id=class_level_id)
        )

    total_outstanding = all_assignments.aggregate(
        outstanding=Sum(F('amount_owed') - F('amount_paid'), output_field=DecimalField())
    )['outstanding'] or Decimal('0.00')

    # Ensure positive value
    total_outstanding = max(Decimal('0.00'), total_outstanding)

    # Calculate collection rate
    total_expected = total_collected + total_outstanding
    collection_rate = (float(total_collected) / float(total_expected) * 100) if total_expected > 0 else 0

    # Get defaulters (students with outstanding balance)
    defaulters_query = Student.objects.annotate(
        total_owed=Sum('fee_assignments__amount_owed', filter=Q(fee_assignments__is_waived=False)),
        total_paid=Sum('fee_assignments__amount_paid', filter=Q(fee_assignments__is_waived=False)),
        balance=F('total_owed') - F('total_paid')
    ).filter(balance__gt=0)

    if term_id:
        defaulters_query = defaulters_query.filter(fee_assignments__term_id=term_id)

    if class_level_id:
        defaulters_query = defaulters_query.filter(
            Q(class_level_id=class_level_id) |
            Q(classroom__name_id=class_level_id)
        )

    defaulters_query = defaulters_query.order_by('-balance')[:50]  # Top 50 defaulters

    defaulters_data = []
    for student in defaulters_query:
        class_name = ""
        if student.classroom:
            class_name = str(student.classroom.name)
        elif student.class_level:
            class_name = student.class_level.name

        defaulters_data.append({
            'student_id': student.id,
            'student_name': student.full_name,
            'admission_number': student.admission_number or '',
            'class_name': class_name,
            'balance': student.balance,
        })

    response_data = {
        'total_collected': total_collected,
        'total_outstanding': total_outstanding,
        'collection_rate': round(collection_rate, 2),
        'payment_by_method': payment_by_method_data,
        'revenue_by_type': revenue_by_type_data,
        'defaulters': defaulters_data,
    }

    serializer = FinancialReportSerializer(data=response_data)
    serializer.is_valid(raise_exception=True)

    return Response(serializer.validated_data, status=status.HTTP_200_OK)


# ============================================================================
# ATTENDANCE REPORT ENDPOINTS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def attendance_report(request):
    """
    Generate attendance report with daily records and summary statistics.

    Query Parameters:
    - date_from: Filter from this date
    - date_to: Filter to this date
    - class_level: Filter by class level ID
    """
    date_from = request.query_params.get('date_from')
    date_to = request.query_params.get('date_to')
    class_level_id = request.query_params.get('class_level')

    # Base queryset
    attendance_records = StudentAttendance.objects.select_related(
        'student', 'ClassRoom', 'status'
    ).all()

    # Apply filters
    if date_from:
        attendance_records = attendance_records.filter(date__gte=date_from)
    if date_to:
        attendance_records = attendance_records.filter(date__lte=date_to)
    if class_level_id:
        attendance_records = attendance_records.filter(
            Q(student__class_level_id=class_level_id) |
            Q(student__classroom__name_id=class_level_id)
        )

    # Group by date and class
    records_data = []
    absent_statuses = AttendanceStatus.objects.filter(absent=True)

    # This is a simplified version - in production, you'd want more sophisticated grouping
    dates = attendance_records.values_list('date', flat=True).distinct()

    for date in dates:
        day_records = attendance_records.filter(date=date)

        # Get unique classrooms for this date
        classrooms = day_records.values_list('ClassRoom', flat=True).distinct()

        for classroom_id in classrooms:
            if not classroom_id:
                continue

            classroom = ClassRoom.objects.get(id=classroom_id)
            class_records = day_records.filter(ClassRoom_id=classroom_id)

            total_students = Student.objects.filter(classroom_id=classroom_id).count()
            absent_count = class_records.filter(status__in=absent_statuses).count()
            present_count = total_students - absent_count

            attendance_rate = (present_count / total_students * 100) if total_students > 0 else 0

            records_data.append({
                'date': date,
                'class_name': str(classroom.name),
                'total_students': total_students,
                'present': present_count,
                'absent': absent_count,
                'attendance_rate': round(attendance_rate, 2),
            })

    # Calculate summary
    total_days = len(dates)
    total_absences = attendance_records.filter(status__in=absent_statuses).count()

    # Calculate average attendance
    if records_data:
        avg_attendance = sum(r['attendance_rate'] for r in records_data) / len(records_data)
    else:
        avg_attendance = 0

    response_data = {
        'records': records_data,
        'summary': {
            'total_days': total_days,
            'average_attendance': round(avg_attendance, 2),
            'total_absences': total_absences,
        }
    }

    serializer = AttendanceReportResponseSerializer(data=response_data)
    serializer.is_valid(raise_exception=True)

    return Response(serializer.validated_data, status=status.HTTP_200_OK)


# ============================================================================
# EXPORT ENDPOINTS (PDF & Excel)
# ============================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def export_student_report_pdf(request):
    """Export student report to PDF"""
    if not REPORTLAB_AVAILABLE:
        return Response(
            {'error': 'PDF generation not available. Please install reportlab.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    # Get report data using same filters
    filters = request.data
    query_params = '&'.join([f"{k}={v}" for k, v in filters.items() if v])

    # Create a temporary request object with query params
    from rest_framework.request import Request
    from django.http import QueryDict
    temp_request = Request(request._request)
    temp_request._request.GET = QueryDict(query_params)

    # Get data from student_report view
    report_response = student_report(temp_request)
    data = report_response.data

    # Create PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []

    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=30,
        alignment=TA_CENTER
    )

    # Title
    elements.append(Paragraph('Student Report', title_style))
    elements.append(Spacer(1, 12))

    # Summary section
    summary_data = [
        ['Total Students', data['summary']['total_students']],
        ['Active Students', data['summary']['active_students']],
        ['Avg Attendance', f"{data['summary']['average_attendance']}%"],
        ['Avg Balance', f"₦{data['summary']['average_balance']}"],
    ]

    summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0f0f0')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
    ]))

    elements.append(summary_table)
    elements.append(Spacer(1, 20))

    # Student details table (limited for PDF)
    if data['students']:
        student_table_data = [['Admission #', 'Name', 'Class', 'Status', 'Balance']]

        for student in data['students'][:50]:  # Limit to 50 for PDF
            student_table_data.append([
                student['admission_number'],
                student['full_name'][:20],  # Truncate long names
                student['class_name'],
                student['status'],
                f"₦{student['balance']}",
            ])

        student_table = Table(student_table_data, colWidths=[1*inch, 2*inch, 1*inch, 1*inch, 1*inch])
        student_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#333333')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))

        elements.append(student_table)

    # Build PDF
    doc.build(elements)
    buffer.seek(0)

    response = FileResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="student_report_{datetime.now().strftime("%Y%m%d")}.pdf"'

    return response


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def export_student_report_excel(request):
    """Export student report to CSV/Excel"""
    # Get report data using same filters
    filters = request.data
    query_params = '&'.join([f"{k}={v}" for k, v in filters.items() if v])

    # Create a temporary request object with query params
    from rest_framework.request import Request
    from django.http import QueryDict
    temp_request = Request(request._request)
    temp_request._request.GET = QueryDict(query_params)

    # Get data from student_report view
    report_response = student_report(temp_request)
    data = report_response.data

    # Create CSV
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="student_report_{datetime.now().strftime("%Y%m%d")}.csv"'

    writer = csv.writer(response)

    # Write summary
    writer.writerow(['STUDENT REPORT SUMMARY'])
    writer.writerow(['Total Students', data['summary']['total_students']])
    writer.writerow(['Active Students', data['summary']['active_students']])
    writer.writerow(['Average Attendance', f"{data['summary']['average_attendance']}%"])
    writer.writerow(['Average Balance', f"₦{data['summary']['average_balance']}"])
    writer.writerow([])

    # Write headers
    writer.writerow([
        'Admission Number', 'Full Name', 'Class', 'Grade Level', 'Status',
        'Attendance Rate', 'Total Present', 'Total Absent',
        'Total Fees', 'Fees Paid', 'Balance'
    ])

    # Write student data
    for student in data['students']:
        writer.writerow([
            student['admission_number'],
            student['full_name'],
            student['class_name'],
            student['grade_level'],
            student['status'],
            f"{student['attendance_rate']}%" if student['attendance_rate'] else 'N/A',
            student['total_present'],
            student['total_absent'],
            student['total_fees'],
            student['fees_paid'],
            student['balance'],
        ])

    return response


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def export_financial_report_pdf(request):
    """Export financial report to PDF"""
    if not REPORTLAB_AVAILABLE:
        return Response(
            {'error': 'PDF generation not available. Please install reportlab.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    # Get report data
    filters = request.data
    query_params = '&'.join([f"{k}={v}" for k, v in filters.items() if v])

    from rest_framework.request import Request
    from django.http import QueryDict
    temp_request = Request(request._request)
    temp_request._request.GET = QueryDict(query_params)

    report_response = financial_report(temp_request)
    data = report_response.data

    # Create PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=30,
        alignment=TA_CENTER
    )

    # Title
    elements.append(Paragraph('Financial Report', title_style))
    elements.append(Spacer(1, 12))

    # Summary
    summary_data = [
        ['Total Collected', f"₦{data['total_collected']}"],
        ['Total Outstanding', f"₦{data['total_outstanding']}"],
        ['Collection Rate', f"{data['collection_rate']}%"],
    ]

    summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0f0f0')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
    ]))

    elements.append(summary_table)
    elements.append(Spacer(1, 20))

    # Payment by method
    if data['payment_by_method']:
        elements.append(Paragraph('Revenue by Payment Method', styles['Heading2']))
        elements.append(Spacer(1, 10))

        method_data = [['Payment Method', 'Amount', 'Count']]
        for item in data['payment_by_method']:
            method_data.append([
                item['method'],
                f"₦{item['amount']}",
                item['count']
            ])

        method_table = Table(method_data, colWidths=[2*inch, 2*inch, 1*inch])
        method_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#333333')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))

        elements.append(method_table)
        elements.append(Spacer(1, 20))

    # Build PDF
    doc.build(elements)
    buffer.seek(0)

    response = FileResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="financial_report_{datetime.now().strftime("%Y%m%d")}.pdf"'

    return response


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def export_financial_report_excel(request):
    """Export financial report to CSV/Excel"""
    # Get report data
    filters = request.data
    query_params = '&'.join([f"{k}={v}" for k, v in filters.items() if v])

    from rest_framework.request import Request
    from django.http import QueryDict
    temp_request = Request(request._request)
    temp_request._request.GET = QueryDict(query_params)

    report_response = financial_report(temp_request)
    data = report_response.data

    # Create CSV
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="financial_report_{datetime.now().strftime("%Y%m%d")}.csv"'

    writer = csv.writer(response)

    # Write summary
    writer.writerow(['FINANCIAL REPORT SUMMARY'])
    writer.writerow(['Total Collected', f"₦{data['total_collected']}"])
    writer.writerow(['Total Outstanding', f"₦{data['total_outstanding']}"])
    writer.writerow(['Collection Rate', f"{data['collection_rate']}%"])
    writer.writerow([])

    # Payment by method
    writer.writerow(['REVENUE BY PAYMENT METHOD'])
    writer.writerow(['Payment Method', 'Amount', 'Transaction Count'])
    for item in data['payment_by_method']:
        writer.writerow([item['method'], item['amount'], item['count']])
    writer.writerow([])

    # Revenue by type
    writer.writerow(['REVENUE BY FEE TYPE'])
    writer.writerow(['Fee Type', 'Amount'])
    for item in data['revenue_by_type']:
        writer.writerow([item['fee_type'], item['amount']])
    writer.writerow([])

    # Defaulters
    writer.writerow(['STUDENTS WITH OUTSTANDING FEES'])
    writer.writerow(['Admission Number', 'Student Name', 'Class', 'Balance'])
    for item in data['defaulters']:
        writer.writerow([
            item['admission_number'],
            item['student_name'],
            item['class_name'],
            item['balance']
        ])

    return response
