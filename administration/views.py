import openpyxl
from django.http import HttpResponse
from django.utils.dateparse import parse_date
from rest_framework import generics, viewsets, status, permissions, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import AcademicYear, Term, Article, CarouselImage, SchoolEvent
from .serializers import (
    AcademicYearSerializer,
    TermSerializer,
    ArticleSerializer,
    CarouselImageSerializer,
    SchoolEventSerializer,
    SchoolEventBulkUploadSerializer,
)
from .permissions import IsAdminOrReadOnly


from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Sum, Avg, Q
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from academic.models import Subject, Student, Teacher
from finance.models import StudentFeeAssignment, Receipt, FeePaymentAllocation
from attendance.models import StudentAttendance
from examination.models import TermResult


# Article Views
class ArticleListCreateView(generics.ListCreateAPIView):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer
    permission_classes = [IsAuthenticated]


class ArticleDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer
    permission_classes = [IsAuthenticated]


# CarouselImage Views
class CarouselImageListCreateView(generics.ListCreateAPIView):
    queryset = CarouselImage.objects.all()
    serializer_class = CarouselImageSerializer
    permission_classes = [IsAuthenticated]


class CarouselImageDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = CarouselImage.objects.all()
    serializer_class = CarouselImageSerializer
    permission_classes = [IsAuthenticated]


# AcademicYear Views
class AcademicYearListCreateView(generics.ListCreateAPIView):
    queryset = AcademicYear.objects.all()
    serializer_class = AcademicYearSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        print(request.data)
        return super().create(request, *args, **kwargs)


class AcademicYearDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = AcademicYear.objects.all()
    serializer_class = AcademicYearSerializer
    permission_classes = [IsAuthenticated]


# Term Views
class TermListCreateView(generics.ListCreateAPIView):
    queryset = Term.objects.all()
    serializer_class = TermSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        print(request.data)
        return super().create(request, *args, **kwargs)


class TermDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Term.objects.all()
    serializer_class = TermSerializer
    permission_classes = [IsAuthenticated]


class SchoolEventViewSet(viewsets.ModelViewSet):
    queryset = SchoolEvent.objects.select_related("term", "term__academic_year").all()
    serializer_class = SchoolEventSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        queryset = self.queryset
        term_id = self.request.query_params.get("term")
        year_name = self.request.query_params.get("academic_year")
        start_date = parse_date(self.request.query_params.get("start_date") or "")
        end_date = parse_date(self.request.query_params.get("end_date") or "")

        if term_id:
            queryset = queryset.filter(term__id=term_id)
        if year_name:
            queryset = queryset.filter(term__academic_year__name=year_name)
        if start_date:
            queryset = queryset.filter(start_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(end_date__lte=end_date)


        return queryset


class SchoolEventBulkUploadView(APIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = SchoolEventBulkUploadSerializer

    def post(self, request):
        excel_file = request.FILES.get("file")
        if not excel_file:
            return Response(
                {"error": "No file uploaded"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            workbook = openpyxl.load_workbook(excel_file)
            sheet = workbook.active
            rows = list(sheet.iter_rows(min_row=2, values_only=True))  # Skip header row

            for row in rows:
                name, event_type, term_id, start_date, end_date, description = row
                if not all([name, event_type, term_id, start_date]):
                    continue  # Skip invalid rows

                SchoolEvent.objects.create(
                    name=name,
                    event_type=event_type,
                    term=Term.objects.get(pk=term_id),
                    start_date=start_date,
                    end_date=end_date,
                    description=description or "",
                )

            return Response(
                {"detail": f"{len(rows)} events uploaded successfully."},
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
class EmptySerializer(serializers.Serializer):
    """Empty serializer for download views that don't require input data"""
    pass

class SchoolEventTemplateDownloadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = EmptySerializer

    def get(self, request):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "School Events Template"

        # Headers
        headers = [
            "name",
            "event_type",
            "term_id",
            "start_date",
            "end_date",
            "description",
        ]
        ws.append(headers)

        # Example row
        ws.append(
            [
                "Midterm Exams",
                "exam",
                1,
                "2025-07-10",
                "2025-07-14",
                "Midterm assessment",
            ]
        )

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = (
            "attachment; filename=school_events_template.xlsx"
        )
        wb.save(response)
        return response


class DashboardStatsView(APIView):
    """
    Comprehensive dashboard with REAL FINANCE DATA
    GET /api/academic/dashboard/stats/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.now().date()
        first_day_of_month = today.replace(day=1)
        
        # ===== BASIC STATS =====
        total_students = Student.objects.filter(is_active=True).count()
        new_students_this_month = Student.objects.filter(
            admission_date__gte=first_day_of_month,
            is_active=True
        ).count()
        total_teachers = Teacher.objects.count()
        active_subjects = Subject.objects.count()
        
        # ===== ATTENDANCE RATE (TODAY) =====
        today_attendance = StudentAttendance.objects.filter(date=today)
        total_expected = Student.objects.filter(is_active=True).count()
        present_count = today_attendance.filter(
            Q(status__name__iexact='PRESENT') | Q(status__name__iexact='present')
        ).count()
        attendance_rate = round(
            (present_count / total_expected * 100) if total_expected > 0 else 0,
            1
        )

        # ===== STUDENTS BY LEVEL =====
        students_by_level = []
        students_with_class = Student.objects.filter(is_active=True).select_related('class_level')

        class_counts = {}
        for student in students_with_class:
            if hasattr(student, 'class_level') and student.class_level:
                class_name = getattr(student.class_level, 'name', str(student.class_level))
            else:
                class_name = 'Unassigned'
            class_counts[class_name] = class_counts.get(class_name, 0) + 1
        
        # Categorize into levels
        primary_keywords = ['Primary', 'primary', 'P1', 'P2', 'P3', 'P4', 'P5', 'P6']
        jss_keywords = ['JSS', 'jss', 'Junior']
        sss_keywords = ['SSS', 'sss', 'Senior']
        university_keywords = ['Year', 'year', 'University', 'university']
        
        primary_count = sum(count for class_name, count in class_counts.items() 
                           if any(keyword in class_name for keyword in primary_keywords))
        jss_count = sum(count for class_name, count in class_counts.items() 
                       if any(keyword in class_name for keyword in jss_keywords))
        sss_count = sum(count for class_name, count in class_counts.items() 
                       if any(keyword in class_name for keyword in sss_keywords))
        university_count = sum(count for class_name, count in class_counts.items() 
                              if any(keyword in class_name for keyword in university_keywords))
        
        students_by_level = [
            {
                'name': 'Primary',
                'count': primary_count,
                'percentage': round((primary_count / total_students * 100) if total_students > 0 else 0, 1),
                'icon': 'lucide:baby'
            },
            {
                'name': 'JSS',
                'count': jss_count,
                'percentage': round((jss_count / total_students * 100) if total_students > 0 else 0, 1),
                'icon': 'lucide:book'
            },
            {
                'name': 'SSS',
                'count': sss_count,
                'percentage': round((sss_count / total_students * 100) if total_students > 0 else 0, 1),
                'icon': 'lucide:graduation-cap'
            },
            {
                'name': 'University',
                'count': university_count,
                'percentage': round((university_count / total_students * 100) if total_students > 0 else 0, 1),
                'icon': 'lucide:school'
            }
        ]
        
        # ===== FINANCIAL STATS (REAL DATA FROM NEW FINANCE SYSTEM) =====
        try:
            # Get all student fee assignments (non-waived)
            fee_assignments = StudentFeeAssignment.objects.filter(is_waived=False)

            # Total expected (amount_owed)
            total_expected = fee_assignments.aggregate(
                total=Sum('amount_owed')
            )['total'] or Decimal('0')

            # Total paid (amount_paid)
            total_paid = fee_assignments.aggregate(
                total=Sum('amount_paid')
            )['total'] or Decimal('0')

            # Outstanding (calculated balance)
            total_outstanding = total_expected - total_paid

            # Calculate collection rate
            collection_rate = round(
                (float(total_paid) / float(total_expected) * 100)
                if total_expected > 0 else 0, 1
            )

            # Students with outstanding fees (balance > 0)
            from django.db.models import F
            students_with_debt = fee_assignments.annotate(
                balance=F('amount_owed') - F('amount_paid')
            ).filter(
                balance__gt=0
            ).values('student').distinct().count()

            financial_stats = {
                'collected': float(total_paid),
                'outstanding': float(total_outstanding),
                'expected': float(total_expected),
                'collectionRate': collection_rate,
                'studentsWithDebt': students_with_debt,
                'totalStudents': total_students
            }
        except Exception as e:
            print(f"Financial calculation error: {e}")
            financial_stats = {
                'collected': 0,
                'outstanding': 0,
                'expected': 0,
                'collectionRate': 0,
                'studentsWithDebt': 0,
                'totalStudents': total_students
            }
        
        # ===== ATTENDANCE FOR THE WEEK =====
        week_start = today - timedelta(days=today.weekday())
        attendance_week = []
        
        for i in range(5):  # Monday to Friday
            day = week_start + timedelta(days=i)
            day_attendance = StudentAttendance.objects.filter(date=day)
            present = day_attendance.filter(
                Q(status__name__iexact='PRESENT') | Q(status__name__iexact='present')
            ).count()
            total = Student.objects.filter(is_active=True).count()
            rate = round((present / total * 100) if total > 0 else 0, 1)
            
            attendance_week.append({
                'dayName': day.strftime('%A'),
                'date': day.isoformat(),
                'rate': rate,
                'present': present,
                'total': total
            })

        # ===== RECENT ADMISSIONS =====
        recent_admissions = Student.objects.filter(
            is_active=True
        ).select_related('class_level').order_by('-admission_date')[:5]

        recent_admissions_list = []
        for student in recent_admissions:
            if hasattr(student, 'class_level') and student.class_level:
                class_name = getattr(student.class_level, 'name', str(student.class_level))
            else:
                class_name = 'Unassigned'

            recent_admissions_list.append({
                'id': student.id,
                'first_name': student.first_name,
                'last_name': student.last_name,
                'grade_level': class_name,
                'admission_date': student.admission_date.isoformat() if student.admission_date else None
            })
        
        # ===== PERFORMANCE STATS =====
        # Calculate real performance data from TermResult model
        try:
            # Get the current or most recent academic year
            current_academic_year = AcademicYear.objects.filter(
                is_current=True
            ).first()

            # Get the current or most recent term
            if current_academic_year:
                current_term = Term.objects.filter(
                    academic_year=current_academic_year
                ).order_by('-start_date').first()
            else:
                # If no current academic year, get the most recent term
                current_term = Term.objects.order_by('-start_date').first()

            if current_term:
                # Get all term results for the current term
                term_results = TermResult.objects.filter(term=current_term)

                # Calculate total number of results
                total_results = term_results.count()

                if total_results > 0:
                    # Count grade distribution
                    grade_counts = term_results.values('overall_grade').annotate(
                        count=Count('id')
                    )

                    # Initialize grade percentages
                    grade_dist = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'F': 0}

                    # Calculate percentages for each grade
                    for grade_count in grade_counts:
                        grade = grade_count['overall_grade']
                        count = grade_count['count']
                        if grade in grade_dist:
                            grade_dist[grade] = round((count / total_results) * 100)

                    # Calculate pass rate (A, B, C, D are passing grades)
                    passing_count = term_results.filter(
                        overall_grade__in=['A', 'B', 'C', 'D']
                    ).count()
                    pass_rate = round((passing_count / total_results) * 100)

                    # Get the most common grade as average
                    most_common_grade = max(grade_counts, key=lambda x: x['count'], default=None)
                    average_grade = most_common_grade['overall_grade'] if most_common_grade else 'N/A'

                    performance_stats = {
                        'averageGrade': average_grade,
                        'passRate': pass_rate,
                        'grades': {
                            'a': grade_dist['A'],
                            'b': grade_dist['B'],
                            'c': grade_dist['C'],
                            'df': grade_dist['D'] + grade_dist['F']
                        }
                    }
                else:
                    # No results available
                    performance_stats = {
                        'averageGrade': 'N/A',
                        'passRate': 0,
                        'grades': {'a': 0, 'b': 0, 'c': 0, 'df': 0}
                    }
            else:
                # No current term
                performance_stats = {
                    'averageGrade': 'N/A',
                    'passRate': 0,
                    'grades': {'a': 0, 'b': 0, 'c': 0, 'df': 0}
                }
        except Exception as e:
            # Fallback if there's an error
            performance_stats = {
                'averageGrade': 'N/A',
                'passRate': 0,
                'grades': {'a': 0, 'b': 0, 'c': 0, 'df': 0}
            }
        
        # ===== RECENT PAYMENTS (BONUS) =====
        try:
            # Get recent receipts with their allocations
            recent_receipts = Receipt.objects.select_related(
                'student', 'term'
            ).order_by('-date')[:5]

            recent_payments_list = []
            for receipt in recent_receipts:
                recent_payments_list.append({
                    'id': receipt.id,
                    'receipt_number': receipt.receipt_number,
                    'student_name': receipt.student.full_name if receipt.student else receipt.payer,
                    'amount': float(receipt.amount),
                    'method': receipt.paid_through,
                    'paid_on': receipt.payment_date.isoformat() if receipt.payment_date else receipt.date.isoformat(),
                    'term_name': receipt.term.name if receipt.term else 'N/A'
                })
        except Exception as e:
            print(f"Recent payments error: {e}")
            recent_payments_list = []
        
        # ===== COMPILE RESPONSE =====
        return Response({
            'stats': {
                'totalStudents': total_students,
                'totalTeachers': total_teachers,
                'activeSubjects': active_subjects,
                'attendanceRate': attendance_rate,
                'newStudentsThisMonth': new_students_this_month
            },
            'studentsByLevel': students_by_level,
            'financial': financial_stats,
            'attendance': attendance_week,
            'recentAdmissions': recent_admissions_list,
            'recentPayments': recent_payments_list,
            'performance': performance_stats
        })
