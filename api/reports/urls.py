# api/reports/urls.py
from django.urls import path
from .views import (
    student_report,
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
    path('financial/', financial_report, name='financial-report'),
    path('attendance/', attendance_report, name='attendance-report'),

    # Export endpoints
    path('student/export/pdf/', export_student_report_pdf, name='export-student-pdf'),
    path('student/export/excel/', export_student_report_excel, name='export-student-excel'),
    path('financial/export/pdf/', export_financial_report_pdf, name='export-financial-pdf'),
    path('financial/export/excel/', export_financial_report_excel, name='export-financial-excel'),
]

"""
This creates the following API endpoints:

REPORTS:
========
GET  /api/reports/students/                    - Student report with demographics, attendance, fees
     Query params:
     - academic_year: Academic year ID
     - term: Term ID
     - grade_level: Grade level ID
     - class_level: Class level ID
     - status: Student status (Active, Inactive, Graduated, Withdrawn)
     - date_from: Start date for attendance/payments
     - date_to: End date for attendance/payments

GET  /api/reports/financial/                   - Financial report with collections and revenue
     Query params:
     - academic_year: Academic year ID
     - term: Term ID
     - date_from: Start date for payments
     - date_to: End date for payments
     - payment_method: Payment method (Cash, Bank Transfer, Mobile Money, Cheque)
     - class_level: Class level ID

GET  /api/reports/attendance/                  - Attendance report with daily records
     Query params:
     - date_from: Start date
     - date_to: End date
     - class_level: Class level ID

EXPORTS:
========
POST /api/reports/student/export/pdf/         - Export student report as PDF
     Body: Same filters as GET /api/reports/students/

POST /api/reports/student/export/excel/       - Export student report as Excel/CSV
     Body: Same filters as GET /api/reports/students/

POST /api/reports/financial/export/pdf/       - Export financial report as PDF
     Body: Same filters as GET /api/reports/financial/

POST /api/reports/financial/export/excel/     - Export financial report as Excel/CSV
     Body: Same filters as GET /api/reports/financial/


Example Usage:
==============

1. Get student report for a specific class:
   GET /api/reports/students/?class_level=3&status=Active

2. Get financial report for current term:
   GET /api/reports/financial/?term=1&date_from=2025-01-01&date_to=2025-03-31

3. Export student report to PDF:
   POST /api/reports/student/export/pdf/
   {
     "class_level": 3,
     "status": "Active",
     "date_from": "2025-01-01",
     "date_to": "2025-03-31"
   }

4. Export financial report to Excel:
   POST /api/reports/financial/export/excel/
   {
     "term": 1,
     "payment_method": "Cash"
   }

5. Get attendance report for date range:
   GET /api/reports/attendance/?date_from=2025-01-01&date_to=2025-01-31&class_level=5
"""
