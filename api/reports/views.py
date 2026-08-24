import csv
import io

from django.http import FileResponse, HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from .filters import validated_filters
from .permissions import (
    CanViewAdministrativeReports, CanViewAttendanceReports,
    CanViewFinanceReports, CanViewTeacherAcademicReports,
)
from .serializers import (
    AdministrativeStudentReportSerializer, AttendanceReportSerializer,
    FinancialReportSerializer, TeacherAcademicReportSerializer,
)
from .services import (
    administrative_student_rows, attendance_report_data,
    financial_report_data, scoped_students, teacher_academic_rows,
)

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


class ReportPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


def _paginated_rows(request, queryset, builder, serializer_class):
    paginator = ReportPagination()
    page = paginator.paginate_queryset(queryset, request)
    rows = builder(page)
    serialized = serializer_class(rows, many=True).data
    return {
        "count": paginator.page.paginator.count,
        "next": paginator.get_next_link(),
        "previous": paginator.get_previous_link(),
        "results": serialized,
    }


@extend_schema(responses={200: AdministrativeStudentReportSerializer(many=True)})
@api_view(["GET"])
@permission_classes([CanViewAdministrativeReports])
def student_report(request):
    """Administrative identity/enrollment report. Finance and grades are excluded."""
    filters = validated_filters(request)
    students = scoped_students(request.user, filters, product="administrative")
    active_count = students.filter(is_active=True).count()
    response = _paginated_rows(
        request, students, administrative_student_rows,
        AdministrativeStudentReportSerializer,
    )
    response["summary"] = {
        "total_students": response["count"], "active_students": active_count,
    }
    return Response(response)


@extend_schema(responses={200: TeacherAcademicReportSerializer(many=True)})
@api_view(["GET"])
@permission_classes([CanViewTeacherAcademicReports])
def academic_report(request):
    """Academic and attendance summary for admin or assigned-class teachers."""
    filters = validated_filters(request)
    students = scoped_students(request.user, filters, product="academic")
    return Response(_paginated_rows(
        request, students,
        lambda page: teacher_academic_rows(page, filters),
        TeacherAcademicReportSerializer,
    ))


@extend_schema(responses={200: FinancialReportSerializer})
@api_view(["GET"])
@permission_classes([CanViewFinanceReports])
def financial_report(request):
    filters = validated_filters(request)
    data = financial_report_data(request.user, filters)
    serializer = FinancialReportSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return Response(serializer.validated_data)


@extend_schema(responses={200: AttendanceReportSerializer})
@api_view(["GET"])
@permission_classes([CanViewAttendanceReports])
def attendance_report(request):
    filters = validated_filters(request)
    data = attendance_report_data(request.user, filters)
    serializer = AttendanceReportSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return Response(serializer.validated_data)


def _pdf_response(title, summary, headers, rows, filename):
    if not REPORTLAB_AVAILABLE:
        return Response(
            {"error": "PDF generation is unavailable."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    buffer = io.BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = [Paragraph(title, styles["Heading1"]), Spacer(1, 12)]
    if summary:
        elements.extend([Table(summary, colWidths=[3 * inch, 2 * inch]), Spacer(1, 16)])
    table = Table([headers, *rows], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#333333")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    elements.append(table)
    document.build(elements)
    buffer.seek(0)
    response = FileResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _student_export_data(request):
    filters = validated_filters(request, body=True)
    students = scoped_students(request.user, filters, product="administrative")
    return administrative_student_rows(students)


@extend_schema(request=None, responses={(200, "application/pdf"): bytes})
@api_view(["POST"])
@permission_classes([CanViewAdministrativeReports])
def export_student_report_pdf(request):
    rows = _student_export_data(request)
    return _pdf_response(
        "Administrative Student Report", [],
        ["Admission Number", "Name", "Class", "Grade", "Status"],
        [[row["admission_number"], row["full_name"], row["class_name"],
          row["grade_level"], row["status"]] for row in rows],
        f"student_report_{timezone.localdate():%Y%m%d}.pdf",
    )


@extend_schema(request=None, responses={(200, "text/csv"): bytes})
@api_view(["POST"])
@permission_classes([CanViewAdministrativeReports])
def export_student_report_excel(request):
    rows = _student_export_data(request)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="student_report_{timezone.localdate():%Y%m%d}.csv"'
    )
    writer = csv.writer(response)
    writer.writerow(["Admission Number", "Full Name", "Class", "Grade Level", "Status"])
    for row in rows:
        writer.writerow([
            row["admission_number"], row["full_name"], row["class_name"],
            row["grade_level"], row["status"],
        ])
    return response


def _finance_export_data(request):
    filters = validated_filters(request, body=True)
    return financial_report_data(request.user, filters)


@extend_schema(request=None, responses={(200, "application/pdf"): bytes})
@api_view(["POST"])
@permission_classes([CanViewFinanceReports])
def export_financial_report_pdf(request):
    data = _finance_export_data(request)
    rows = [[
        item["admission_number"], item["student_name"],
        item["class_name"], item["balance"],
    ] for item in data["defaulters"]]
    return _pdf_response(
        "Financial Report",
        [["Total Collected", data["total_collected"]],
         ["Total Outstanding", data["total_outstanding"]],
         ["Collection Rate", f'{data["collection_rate"]}%']],
        ["Admission Number", "Student", "Class", "Balance"], rows,
        f"financial_report_{timezone.localdate():%Y%m%d}.pdf",
    )


@extend_schema(request=None, responses={(200, "text/csv"): bytes})
@api_view(["POST"])
@permission_classes([CanViewFinanceReports])
def export_financial_report_excel(request):
    data = _finance_export_data(request)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="financial_report_{timezone.localdate():%Y%m%d}.csv"'
    )
    writer = csv.writer(response)
    writer.writerow(["Total Collected", data["total_collected"]])
    writer.writerow(["Total Outstanding", data["total_outstanding"]])
    writer.writerow(["Collection Rate", data["collection_rate"]])
    writer.writerow([])
    writer.writerow(["Admission Number", "Student Name", "Class", "Balance"])
    for item in data["defaulters"]:
        writer.writerow([
            item["admission_number"], item["student_name"],
            item["class_name"], item["balance"],
        ])
    return response
