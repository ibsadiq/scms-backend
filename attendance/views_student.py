"""
Student Attendance Views
Provides endpoints for student attendance tracking and summaries.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from django.db.models import Count, Q
from datetime import datetime

from .models import StudentAttendance
from .serializers import StudentAttendanceSerializer
from academic.models import Student



class StudentAttendanceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for student attendance records.
    
    Endpoints:
    - GET /api/attendance/student-attendance/ - List all attendance records
    - GET /api/attendance/student-attendance/?student={id} - Filter by student
    - GET /api/attendance/student-attendance/summary/ - Get attendance summary
    - POST /api/attendance/student-attendance/ - Create attendance record
    """
    serializer_class = StudentAttendanceSerializer
    permission_classes = [IsAuthenticated]
    queryset = StudentAttendance.objects.all().select_related('student', 'ClassRoom', 'status')
    
    def get_queryset(self):
        """Filter attendance based on query parameters"""
        queryset = super().get_queryset()
        
        # Filter by student
        student_id = self.request.query_params.get('student')
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        
        # Filter by classroom
        classroom_id = self.request.query_params.get('classroom')
        if classroom_id:
            queryset = queryset.filter(ClassRoom_id=classroom_id)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)
        
        return queryset.order_by('-date')
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        student_id = request.query_params.get('student')

        if student_id:
            # ── existing per-student logic — unchanged, keep exactly as-is ──
            try:
                student = Student.objects.get(id=student_id)
            except Student.DoesNotExist:
                return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)

            queryset = StudentAttendance.objects.filter(student_id=student_id)

            month = request.query_params.get('month')
            year = request.query_params.get('year')
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')

            if month and year:
                queryset = queryset.filter(date__month=month, date__year=year)
                period_label = f"{datetime(int(year), int(month), 1).strftime('%B %Y')}"
            elif start_date and end_date:
                queryset = queryset.filter(date__gte=start_date, date__lte=end_date)
                period_label = f"{start_date} to {end_date}"
            elif year:
                queryset = queryset.filter(date__year=year)
                period_label = f"Year {year}"
            else:
                now = datetime.now()
                queryset = queryset.filter(date__month=now.month, date__year=now.year)
                period_label = f"{now.strftime('%B %Y')}"

            total_days = queryset.count()
            present_count = queryset.filter(status__name__iexact='present').count()
            absent_count = queryset.filter(status__name__iexact='absent').count()
            late_count = queryset.filter(status__name__iexact='late').count()
            excused_count = queryset.filter(status__name__iexact='excused').count()
            attendance_rate = (present_count / total_days * 100) if total_days > 0 else 0

            recent_records = queryset.order_by('-date')[:10]
            records_data = StudentAttendanceSerializer(recent_records, many=True).data

            return Response({
                'student': {
                    'id': student.id,
                    'name': student.full_name,
                    'admission_number': student.admission_number
                },
                'period': period_label,
                'summary': {
                    'total_days': total_days,
                    'present': present_count,
                    'absent': absent_count,
                    'late': late_count,
                    'excused': excused_count,
                    'attendance_rate': round(attendance_rate, 1)
                },
                'recent_records': records_data
            }, status=status.HTTP_200_OK)

        # ── School-wide summary (no student param) ──
        from administration.models import Term

        queryset = StudentAttendance.objects.all()

        term_id = request.query_params.get('term')
        date_param = request.query_params.get('date')
        start_date = request.query_params.get('startDate') or request.query_params.get('start_date')
        end_date = request.query_params.get('endDate') or request.query_params.get('end_date')
        month = request.query_params.get('month')
        year = request.query_params.get('year')

        term = None
        if term_id:
            term = Term.objects.filter(id=term_id).first()
        if not term and not any([date_param, start_date, month, year]):
            # Default: current active term
            term = Term.objects.filter(
                academic_year__active_year=True,
                start_date__lte=datetime.now().date(),
                end_date__gte=datetime.now().date(),
            ).first()
            if not term:
                # fallback: most recent term in the active academic year
                term = Term.objects.filter(academic_year__active_year=True).order_by('-start_date').first()

        if term:
            queryset = queryset.filter(date__gte=term.start_date, date__lte=term.end_date)
            period_label = term.name
        elif date_param:
            queryset = queryset.filter(date=date_param)
            period_label = date_param
        elif start_date and end_date:
            queryset = queryset.filter(date__gte=start_date, date__lte=end_date)
            period_label = f"{start_date} to {end_date}"
        elif month and year:
            queryset = queryset.filter(date__month=month, date__year=year)
            period_label = f"{datetime(int(year), int(month), 1).strftime('%B %Y')}"
        elif year:
            queryset = queryset.filter(date__year=year)
            period_label = f"Year {year}"
        else:
            period_label = "All time"

        total_records = queryset.count()
        total_days = queryset.values('date').distinct().count()
        present_count = queryset.filter(status__name__iexact='present').count()
        absent_count = queryset.filter(status__name__iexact='absent').count()
        late_count = queryset.filter(status__name__iexact='late').count()
        excused_count = queryset.filter(status__name__iexact='excused').count()

        attendance_rate = (present_count / total_records * 100) if total_records > 0 else 0

        return Response({
            'period': period_label,
            'summary': {
                'total_days': total_days,
                'present': present_count,
                'absent': absent_count,
                'late': late_count,
                'excused': excused_count,
                'attendance_rate': round(attendance_rate, 1),
            }
        }, status=status.HTTP_200_OK)
    @action(detail=False, methods=['get'])
    def monthly_breakdown(self, request):
        """
        Get monthly attendance breakdown for a student.
        
        Query Parameters:
        - student (required): Student ID
        - year (optional): Year (defaults to current year)
        
        GET /api/attendance/student-attendance/monthly-breakdown/?student=505&year=2025
        """
        student_id = request.query_params.get('student')
        
        if not student_id:
            return Response(
                {'error': 'student parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        year = request.query_params.get('year', datetime.now().year)
        
        # Get attendance for each month
        monthly_data = []
        for month in range(1, 13):
            queryset = StudentAttendance.objects.filter(
                student_id=student_id,
                date__year=year,
                date__month=month
            )
            
            total = queryset.count()
            present = queryset.filter(status__name__iexact='present').count()
            absent = queryset.filter(status__name__iexact='absent').count()
            
            monthly_data.append({
                'month': month,
                'month_name': datetime(int(year), month, 1).strftime('%B'),
                'total_days': total,
                'present': present,
                'absent': absent,
                'attendance_rate': round((present / total * 100) if total > 0 else 0, 1)
            })
        
        return Response({
            'year': year,
            'months': monthly_data
        }, status=status.HTTP_200_OK)



class ClassAttendanceSummaryView(APIView):
    """
    GET /api/attendance/class/{classroom_id}/summary/?term=X (or date=X, or startDate/endDate)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, classroom_id):
        from administration.models import Term
        from academic.models import StudentClassEnrollment

        queryset = StudentAttendance.objects.filter(ClassRoom_id=classroom_id)

        term_id = request.query_params.get('term')
        date_param = request.query_params.get('date')
        start_date = request.query_params.get('startDate')
        end_date = request.query_params.get('endDate')

        if term_id:
            term = Term.objects.filter(id=term_id).first()
            if term:
                queryset = queryset.filter(date__gte=term.start_date, date__lte=term.end_date)
        elif date_param:
            queryset = queryset.filter(date=date_param)
        elif start_date and end_date:
            queryset = queryset.filter(date__gte=start_date, date__lte=end_date)

        total_records = queryset.count()
        total_days = queryset.values('date').distinct().count()
        present_count = queryset.filter(status__name__iexact='present').count()
        absent_count = queryset.filter(status__name__iexact='absent').count()
        total_students = StudentClassEnrollment.objects.filter(classroom_id=classroom_id).count()

        attendance_rate = (present_count / total_records * 100) if total_records > 0 else 0

        return Response({
            'summary': {
                'attendance_rate': round(attendance_rate, 1),
                'present': present_count,
                'absent': absent_count,
                'total_students': total_students,
                'total_days': total_days,
            }
        }, status=status.HTTP_200_OK)
