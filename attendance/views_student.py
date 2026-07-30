"""
Student Attendance Views
Provides endpoints for student attendance tracking and summaries.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.db import transaction


from django.db.models import Count, Q
from datetime import datetime,date

from .models import StudentAttendance, AttendanceStatus
from .serializers import StudentAttendanceSerializer, StudentAttendanceListSerializer
from academic.models import ClassRoom, Teacher, AcademicYear, AllocatedSubject, Term
from academic.models import Student



class StudentAttendanceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for student attendance records.
    """
    serializer_class = StudentAttendanceSerializer
    permission_classes = [IsAuthenticated]
    queryset = StudentAttendance.objects.all().select_related('student', 'ClassRoom', 'status', 'term', 'marked_by')
    
    def get_serializer_class(self):
        """Use lightweight serializer for list endpoint"""
        if self.action == 'list':
            return StudentAttendanceListSerializer
        return self.serializer_class
    
    def get_queryset(self):
        """Filter attendance based on query parameters"""
        queryset = super().get_queryset()
        
        # ── Filter by student ──
        student_id = self.request.query_params.get('student')
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        
        # ── Filter by classroom ──
        classroom_id = self.request.query_params.get('classroom')
        if classroom_id:
            queryset = queryset.filter(ClassRoom_id=classroom_id)
        
        # ── CRITICAL FIX: Filter by specific date ──
        date_param = self.request.query_params.get('date')
        if date_param:
            queryset = queryset.filter(date=date_param)
        
        # ── Filter by date range ──
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)
        
        return queryset.order_by('date', 'student__admission_number')
    
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

    
    @action(detail=False, methods=['get'])
    def marked_dates(self, request):
        """
        GET /api/attendance/student-attendance/marked_dates/?classroom=X&start_date=Y&end_date=Z
        """
        classroom_id = request.query_params.get('classroom')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if not classroom_id:
            return Response(
                {'error': 'classroom parameter is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        queryset = StudentAttendance.objects.filter(ClassRoom_id=classroom_id)
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)

        dates = list(queryset.values_list('date', flat=True).distinct().order_by('date'))
        return Response({'dates': [d.isoformat() for d in dates]})


class BulkMarkAttendanceView(APIView):
    """
    POST /api/attendance/student-attendance/bulk-mark/
    Mark or update attendance for multiple students at once.
    Same-day edits allowed. Past dates are read-only (403).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        is_admin = getattr(request.user, "is_admin", False) or getattr(request.user, "is_superuser", False)
        teacher = getattr(request.user, "teacher", None)

        if not teacher and not is_admin:
            return Response(
                {"error": "Teacher profile not found for this user"},
                status=status.HTTP_404_NOT_FOUND
            )

        classroom_id = request.data.get('classroom')
        date_str = request.data.get('date')
        records = request.data.get('records', [])

        if not classroom_id or not date_str or not records:
            return Response(
                {"error": "Missing required fields: classroom, date, or records"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Parse date
        try:
            attendance_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST
            )

        today = date.today()
        if attendance_date > today and not is_admin:
            return Response(
                {"error": "Attendance cannot be marked for future dates."},
                status=status.HTTP_403_FORBIDDEN
            )

        classroom = get_object_or_404(ClassRoom, id=classroom_id)

        if not is_admin:
            is_class_teacher = classroom.class_teacher == teacher
            current_academic_year = AcademicYear.objects.filter(active_year=True).first()

            has_subject_allocation = False
            if teacher and current_academic_year:
                has_subject_allocation = AllocatedSubject.objects.filter(
                    teacher_name=teacher,
                    class_room=classroom,
                    academic_year=current_academic_year
                ).exists()

            if not is_class_teacher and not has_subject_allocation:
                return Response(
                    {"error": "You do not have permission to mark attendance for this classroom"},
                    status=status.HTTP_403_FORBIDDEN
                )

        # Get current term
        term = Term.objects.filter(
            start_date__lte=attendance_date,
            end_date__gte=attendance_date
        ).first()
        
        if not term:
            term = Term.objects.order_by('-start_date').first()

        created_count = 0
        updated_count = 0
        errors = []

        with transaction.atomic():
            for record in records:
                student_id = record.get('student')
                status_name = record.get('status', 'Present')
                remarks = record.get('remarks', '')

                if not student_id:
                    errors.append({"error": "Missing student ID in record"})
                    continue

                try:
                    student = Student.objects.get(id=student_id)
                except Student.DoesNotExist:
                    errors.append({
                        "student_id": student_id,
                        "error": "Student not found in this classroom"
                    })
                    continue

                # Get or create attendance status
                attendance_status, _ = AttendanceStatus.objects.get_or_create(
                    name=status_name,
                    defaults={
                        'code': status_name[:2].upper(),
                        'absent': status_name == 'Absent',
                        'late': status_name == 'Late',
                        'excused': status_name == 'Excused'
                    }
                )

                # ── FIX: Store "Present" like any other status (no more deletion) ──
                attendance, created = StudentAttendance.objects.update_or_create(
                    student=student,
                    date=attendance_date,
                    defaults={
                        'ClassRoom': classroom,
                        'status': attendance_status,
                        'notes': remarks,
                        'term': term,
                        'marked_by': request.user  # Track who last edited
                    }
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

        response_data = {
            'success': True,
            'message': f'Attendance processed for {len(records)} students',
            'created': created_count,
            'updated': updated_count,
            'errors': errors if errors else None
        }

        return Response(response_data, status=status.HTTP_200_OK)


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
