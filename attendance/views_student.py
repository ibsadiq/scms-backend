"""
Student Attendance Views
Provides endpoints for student attendance tracking and summaries.
"""
from rest_framework import viewsets, status
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied, ValidationError
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils.dateparse import parse_date, parse_time


from django.db.models import Count, Q
from datetime import datetime,date

from .models import StudentAttendance, AttendanceStatus
from .serializers import StudentAttendanceSerializer, StudentAttendanceListSerializer
from .schema_serializers import (
    AttendanceClassSummarySerializer,
    BulkAttendanceRequestSerializer,
    BulkAttendanceResponseSerializer,
)
from drf_spectacular.utils import OpenApiParameter, extend_schema
from .services import StudentAttendanceService
from .permissions import (
    AttendanceRecordPermission,
    CanReadAssignedAttendance,
    can_access_classroom,
    can_access_student,
    is_attendance_admin,
    student_ids_for_user,
    teacher_classroom_ids,
)
from academic.models import ClassRoom, Teacher, AcademicYear, AllocatedSubject, Term
from academic.models import Student



def _resolve_attendance_student(identifier, user=None):
    from academic.models import Student
    from django.db.models import Q
    if identifier:
        st = Student.objects.filter(id=identifier).first()
        if not st:
            st = Student.objects.filter(user_id=identifier).first()
        if not st and str(identifier).isdigit():
            st = Student.objects.filter(Q(id=int(identifier)) | Q(user_id=int(identifier))).first()
        if not st:
            st = Student.objects.filter(admission_number=str(identifier)).first()
        if st:
            return st
    if user and user.is_authenticated:
        return getattr(user, 'student_profile', None) or getattr(user, 'student', None) or Student.objects.filter(user=user).first()
    return None


class StudentAttendanceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for student attendance records.
    """
    serializer_class = StudentAttendanceSerializer
    permission_classes = [AttendanceRecordPermission]
    queryset = StudentAttendance.objects.all().select_related('student', 'ClassRoom', 'status', 'term', 'marked_by')

    def get_serializer_class(self):
        """Use lightweight serializer for list endpoint"""
        if self.action == 'list':
            return StudentAttendanceListSerializer
        return self.serializer_class
    
    def get_queryset(self):
        """Filter attendance based on query parameters"""
        queryset = super().get_queryset()
        user = self.request.user
        if is_attendance_admin(user):
            pass
        elif getattr(user, 'teacher', None):
            queryset = queryset.filter(ClassRoom_id__in=teacher_classroom_ids(user))
        else:
            queryset = queryset.filter(student_id__in=student_ids_for_user(user))
        
        # ── Filter by student ──
        student_id = self.request.query_params.get('student')
        if student_id:
            st = _resolve_attendance_student(student_id, self.request.user)
            if st:
                queryset = queryset.filter(student=st)
            else:
                queryset = queryset.filter(student_id=student_id)
        
        # ── Filter by classroom ──
        classroom_id = self.request.query_params.get('classroom')
        if classroom_id:
            queryset = queryset.filter(ClassRoom_id=classroom_id)
        
        # ── Filter by month and year ──
        month = self.request.query_params.get('month') or self.request.query_params.get('date__month')
        year = self.request.query_params.get('year') or self.request.query_params.get('date__year')
        if month:
            queryset = queryset.filter(date__month=month)
        if year:
            queryset = queryset.filter(date__year=year)

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

    def _service_payload(self, request, instance=None):
        student_id = request.data.get('student') or request.data.get('student_id')
        classroom_id = request.data.get('classroom') or request.data.get('ClassRoom')
        attendance_date = request.data.get('date')
        status_value = request.data.get('status')
        if instance:
            if student_id and str(student_id) != str(instance.student_id):
                raise ValidationError({'student': 'The student cannot be changed during a correction.'})
            if classroom_id and str(classroom_id) != str(instance.ClassRoom_id):
                raise ValidationError({'classroom': 'The classroom cannot be changed during a correction.'})
            if attendance_date and str(attendance_date) != instance.date.isoformat():
                raise ValidationError({'date': 'The attendance date cannot be changed during a correction.'})
            student_id = instance.student_id
            classroom_id = instance.ClassRoom_id
            attendance_date = instance.date
            status_value = status_value or instance.status.name
        if not all((student_id, classroom_id, attendance_date, status_value)):
            raise ValidationError('student, classroom, date, and status are required.')
        if isinstance(attendance_date, str):
            attendance_date = parse_date(attendance_date)
            if not attendance_date:
                raise ValidationError({'date': 'Use YYYY-MM-DD.'})
        student = get_object_or_404(Student, id=student_id, classroom_id=classroom_id)
        classroom = get_object_or_404(ClassRoom, id=classroom_id)
        if not can_access_classroom(request.user, classroom.id):
            raise PermissionDenied('You are not authorized for this classroom.')
        if isinstance(status_value, int) or str(status_value).isdigit():
            status_value = get_object_or_404(AttendanceStatus, id=status_value).name
        time_in = request.data.get('time_in', instance.time_in if instance else None)
        time_out = request.data.get('time_out', instance.time_out if instance else None)
        if isinstance(time_in, str):
            time_in = parse_time(time_in)
        if isinstance(time_out, str):
            time_out = parse_time(time_out)
        return {
            'student': student,
            'attendance_date': attendance_date,
            'classroom': classroom,
            'status_name': status_value,
            'marked_by': request.user,
            'notes': request.data.get('remarks', request.data.get('notes', instance.notes if instance else '')),
            'time_in': time_in,
            'time_out': time_out,
            'term': instance.term if instance else None,
        }

    def create(self, request, *args, **kwargs):
        attendance, created = StudentAttendanceService.mark_manual(**self._service_payload(request))
        return Response(self.get_serializer(attendance).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        attendance, _ = StudentAttendanceService.mark_manual(**self._service_payload(request, instance))
        return Response(self.get_serializer(attendance).data)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed('DELETE', detail='Attendance records are auditable and cannot be deleted through this API.')
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        student_id = request.query_params.get('student') or request.query_params.get('student_id')
        is_student_user = getattr(request.user, 'is_student', False)

        student = None
        if student_id or is_student_user:
            student = _resolve_attendance_student(student_id, request.user)
            if not student and student_id:
                return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)

        if student:
            if not can_access_student(request.user, student):
                raise PermissionDenied('You are not authorized to view this student attendance.')
            queryset = self.get_queryset().filter(student=student)

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
            absent_count = queryset.filter(Q(status__absent=True) | Q(status__name__iexact='Absent')).count()
            present_count = total_days - absent_count
            late_count = queryset.filter(Q(status__late=True) | Q(status__name__iexact='Late')).count()
            excused_count = queryset.filter(Q(status__excused=True) | Q(status__name__iexact='Excused')).count()
            attendance_rate = (present_count / total_days * 100) if total_days > 0 else 0

            all_records = queryset.order_by('date')
            records_data = StudentAttendanceSerializer(all_records, many=True).data

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
                'records': records_data,
                'recent_records': records_data[:10]
            }, status=status.HTTP_200_OK)

        # ── School-wide summary (no student param) ──
        from administration.models import Term

        if not is_attendance_admin(request.user):
            raise PermissionDenied('School-wide attendance summaries require administrator access.')
        queryset = self.get_queryset()

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
        absent_count = queryset.filter(status__absent=True).count()
        present_count = total_records - absent_count
        late_count = queryset.filter(status__late=True).count()
        excused_count = queryset.filter(status__excused=True).count()

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
        student_id = request.query_params.get('student') or request.query_params.get('student_id')
        student = _resolve_attendance_student(student_id, request.user)
        if not student:
            return Response(
                {'error': 'Student not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        if not can_access_student(request.user, student):
            raise PermissionDenied('You are not authorized to view this student attendance.')
        
        year = request.query_params.get('year', datetime.now().year)
        
        # Get attendance for each month
        monthly_data = []
        for month in range(1, 13):
            queryset = self.get_queryset().filter(
                student=student,
                date__year=year,
                date__month=month
            )
            
            total = queryset.count()
            absent = queryset.filter(status__absent=True).count()
            present = total - absent
            
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

        if not can_access_classroom(request.user, int(classroom_id)):
            raise PermissionDenied('You are not authorized for this classroom.')
        queryset = self.get_queryset().filter(ClassRoom_id=classroom_id)
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

    @extend_schema(
        request=BulkAttendanceRequestSerializer,
        responses={200: BulkAttendanceResponseSerializer},
    )
    def post(self, request):
        is_admin = is_attendance_admin(request.user)
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
                    student = Student.objects.get(id=student_id, classroom=classroom)
                except Student.DoesNotExist:
                    errors.append({
                        "student_id": student_id,
                        "error": "Student not found in this classroom"
                    })
                    continue

                attendance, created = StudentAttendanceService.mark_manual(
                    student=student,
                    attendance_date=attendance_date,
                    classroom=classroom,
                    status_name=status_name,
                    notes=remarks,
                    term=term,
                    marked_by=request.user,
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
    permission_classes = [CanReadAssignedAttendance]

    @extend_schema(
        parameters=[
            OpenApiParameter("term", int, required=False),
            OpenApiParameter("date", str, required=False),
            OpenApiParameter("startDate", str, required=False),
            OpenApiParameter("endDate", str, required=False),
        ],
        responses={200: AttendanceClassSummarySerializer},
    )
    def get(self, request, classroom_id):
        from administration.models import Term
        from academic.models import StudentClassEnrollment

        if not can_access_classroom(request.user, classroom_id):
            raise PermissionDenied('You are not authorized for this classroom.')
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
        absent_count = queryset.filter(status__absent=True).count()
        present_count = total_records - absent_count
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
