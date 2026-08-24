# api/reports/urls.py
from django.urls import path
from .views import (
    student_report,
    academic_report,
    financial_report,
    attendance_report,
    export_student_report_pdf,
    export_student_report_excel,
    export_financial_report_pdf,
    export_financial_report_excel,
)

urlpatterns = [
    # Report endpoints
    path('students/', student_report, name='student-report'),
    path('academic/', academic_report, name='academic-report'),
    path('financial/', financial_report, name='financial-report'),
    path('attendance/', attendance_report, name='attendance-report'),

    # Export endpoints
    path('student/export/pdf/', export_student_report_pdf, name='export-student-pdf'),
    path('student/export/excel/', export_student_report_excel, name='export-student-excel'),
    path('financial/export/pdf/', export_financial_report_pdf, name='export-financial-pdf'),
    path('financial/export/excel/', export_financial_report_excel, name='export-financial-excel'),
]
