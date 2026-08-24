from decimal import Decimal

from django.db.models import Count, F, Q, Sum

from attendance.models import AttendanceStatus, StudentAttendance
from examination.models import TermResult
from finance.models import Receipt, StudentFeeAssignment

from .access import ReportAccessService


def _student_filters(queryset, filters):
    class_level = filters.get("class_level")
    grade_level = filters.get("grade_level")
    student = filters.get("student")
    if class_level:
        queryset = queryset.filter(
            Q(class_level=class_level) | Q(classroom__name=class_level)
        )
    if grade_level:
        queryset = queryset.filter(
            Q(class_level__grade_level=grade_level)
            | Q(classroom__name__grade_level=grade_level)
        )
    if student:
        queryset = queryset.filter(pk=student.pk)
    if filters.get("academic_year"):
        queryset = queryset.filter(
            student_classes__academic_year=filters["academic_year"]
        ).distinct()
    status = filters.get("status")
    if status == "Active":
        queryset = queryset.filter(is_active=True)
    elif status == "Inactive":
        queryset = queryset.filter(is_active=False)
    elif status == "Graduated":
        queryset = queryset.filter(graduation_date__isnull=False)
    elif status == "Withdrawn":
        queryset = queryset.filter(date_dismissed__isnull=False)
    return queryset


def scoped_students(user, filters, *, product):
    source = {
        "administrative": ReportAccessService.administrative_students,
        "finance": ReportAccessService.finance_students,
        "academic": ReportAccessService.academic_students,
    }[product]
    return _student_filters(source(user), filters).select_related(
        "classroom__name__grade_level", "class_level__grade_level"
    ).order_by("admission_number", "pk")


def student_identity(student):
    classroom = student.classroom
    class_level = classroom.name if classroom else student.class_level
    grade = class_level.grade_level if class_level else None
    return {
        "admission_number": student.admission_number or "",
        "full_name": student.full_name,
        "class_name": str(class_level) if class_level else "",
        "grade_level": (grade.alias or grade.default_name) if grade else "",
        "status": student.status,
    }


def administrative_student_rows(students):
    return [student_identity(student) for student in students]


def teacher_academic_rows(students, filters):
    absent_statuses = AttendanceStatus.objects.filter(absent=True)
    rows = []
    for student in students:
        attendance = StudentAttendance.objects.filter(student=student)
        if filters.get("date_from"):
            attendance = attendance.filter(date__gte=filters["date_from"])
        if filters.get("date_to"):
            attendance = attendance.filter(date__lte=filters["date_to"])
        total = attendance.count()
        absent = attendance.filter(status__in=absent_statuses).count()
        results = TermResult.objects.filter(student=student)
        if filters.get("term"):
            results = results.filter(term=filters["term"])
        result = results.order_by("-term__start_date", "-pk").first()
        row = student_identity(student)
        row.update({
            "attendance_rate": round(((total - absent) / total) * 100, 2) if total else None,
            "total_present": total - absent,
            "total_absent": absent,
            "average_grade": result.grade if result else None,
        })
        rows.append(row)
    return rows


def financial_report_data(user, filters):
    students = scoped_students(user, filters, product="finance")
    assignments = StudentFeeAssignment.objects.filter(student__in=students, is_waived=False)
    receipts = Receipt.objects.filter(student__in=students, status="Completed")
    term = filters.get("term")
    if term:
        assignments = assignments.filter(term=term)
        receipts = receipts.filter(term=term)
    if filters.get("academic_year"):
        assignments = assignments.filter(term__academic_year=filters["academic_year"])
        receipts = receipts.filter(term__academic_year=filters["academic_year"])
    if filters.get("date_from"):
        receipts = receipts.filter(date__gte=filters["date_from"])
    if filters.get("date_to"):
        receipts = receipts.filter(date__lte=filters["date_to"])
    if filters.get("payment_method"):
        receipts = receipts.filter(paid_through=filters["payment_method"])

    total_collected = receipts.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    totals = assignments.aggregate(owed=Sum("amount_owed"), paid=Sum("amount_paid"))
    total_outstanding = max(
        Decimal("0"), (totals["owed"] or Decimal("0")) - (totals["paid"] or Decimal("0"))
    )
    expected = total_collected + total_outstanding
    payment_rows = receipts.values("paid_through").annotate(
        amount=Sum("amount"), count=Count("pk")
    ).order_by("-amount")
    payment_by_method = [{
        "method": item["paid_through"], "amount": item["amount"],
        "count": item["count"],
    } for item in payment_rows]
    revenue_by_type = list(assignments.filter(amount_paid__gt=0).values(
        "fee_structure__fee_type"
    ).annotate(amount=Sum("amount_paid")).order_by("-amount"))
    revenue_by_type = [{
        "fee_type": item["fee_structure__fee_type"] or "Unknown",
        "amount": item["amount"],
    } for item in revenue_by_type]

    balance_filter = Q(fee_assignments__is_waived=False)
    if term:
        balance_filter &= Q(fee_assignments__term=term)
    if filters.get("academic_year"):
        balance_filter &= Q(
            fee_assignments__term__academic_year=filters["academic_year"]
        )
    defaulters = students.annotate(
        report_total_owed=Sum(
            "fee_assignments__amount_owed", filter=balance_filter
        ),
        report_total_paid=Sum(
            "fee_assignments__amount_paid", filter=balance_filter
        ),
        report_balance=F("report_total_owed") - F("report_total_paid"),
    ).filter(report_balance__gt=0).order_by("-report_balance")[:50]
    defaulter_rows = []
    for student in defaulters:
        row = student_identity(student)
        defaulter_rows.append({
            "admission_number": row["admission_number"],
            "student_name": row["full_name"],
            "class_name": row["class_name"],
            "balance": student.report_balance,
        })
    return {
        "total_collected": total_collected,
        "total_outstanding": total_outstanding,
        "collection_rate": round(float(total_collected / expected * 100), 2) if expected else 0,
        "payment_by_method": payment_by_method,
        "revenue_by_type": revenue_by_type,
        "defaulters": defaulter_rows,
    }


def attendance_report_data(user, filters):
    records = StudentAttendance.objects.select_related("student", "ClassRoom__name", "status")
    classroom_ids = ReportAccessService.attendance_classroom_ids(user)
    if classroom_ids is not None:
        records = records.filter(ClassRoom_id__in=classroom_ids)
    if filters.get("class_level"):
        records = records.filter(ClassRoom__name=filters["class_level"])
    if filters.get("student"):
        records = records.filter(student=filters["student"])
    if filters.get("term"):
        records = records.filter(term=filters["term"])
    if filters.get("academic_year"):
        records = records.filter(term__academic_year=filters["academic_year"])
    if filters.get("date_from"):
        records = records.filter(date__gte=filters["date_from"])
    if filters.get("date_to"):
        records = records.filter(date__lte=filters["date_to"])
    absent_statuses = AttendanceStatus.objects.filter(absent=True)
    grouped = records.values("date", "ClassRoom_id", "ClassRoom__name__name").annotate(
        total_students=Count("student_id", distinct=True),
        absent=Count("pk", filter=Q(status__in=absent_statuses)),
    ).order_by("date", "ClassRoom_id")
    rows = []
    for item in grouped:
        total = item["total_students"]
        present = max(0, total - item["absent"])
        rows.append({
            "date": item["date"], "class_name": item["ClassRoom__name__name"],
            "total_students": total, "present": present, "absent": item["absent"],
            "attendance_rate": round(present / total * 100, 2) if total else 0,
        })
    return {
        "records": rows,
        "summary": {
            "total_days": records.values("date").distinct().count(),
            "average_attendance": round(
                sum(row["attendance_rate"] for row in rows) / len(rows), 2
            ) if rows else 0,
            "total_absences": records.filter(status__in=absent_statuses).count(),
        },
    }
