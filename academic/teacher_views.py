"""
Teacher-specific API views for the academic app.
These views handle teacher-related operations like fetching assigned classes,
students, and attendance marking.
"""

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.shortcuts import get_object_or_404
from datetime import datetime

from .models import (
    Teacher,
    AllocatedSubject,
    ClassRoom,
    Student,
)
from attendance.models import StudentAttendance, AttendanceStatus
from administration.models import AcademicYear


class TeacherMyClassesView(APIView):
    """
    GET /api/academic/allocated-subjects/my-classes/
    Returns all classes assigned to the logged-in teacher.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Get the teacher associated with the logged-in user
        try:
            teacher = Teacher.objects.get(user=request.user)
        except Teacher.DoesNotExist:
            return Response(
                {"error": "Teacher profile not found for this user"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get current academic year
        try:
            current_academic_year = AcademicYear.objects.get(active_year=True)
        except AcademicYear.DoesNotExist:
            return Response(
                {"error": "No active academic year found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get all subject allocations for this teacher in the current academic year
        allocations = AllocatedSubject.objects.filter(
            teacher_name=teacher,
            academic_year=current_academic_year
        ).select_related('class_room', 'subject', 'class_room__name')

        classes_data = []
        for allocation in allocations:
            classroom = allocation.class_room

            # Count active students in this classroom
            student_count = Student.objects.filter(
                classroom=classroom,
                is_active=True
            ).count()

            # Check if teacher is the classroom teacher (homeroom)
            is_class_teacher = classroom.class_teacher == teacher

            # Get schedule (you can expand this based on your timetable model)
            schedule = []
            # TODO: If you have a timetable model, query it here
            # Example:
            # timetable_entries = TimetableEntry.objects.filter(allocated_subject=allocation)
            # for entry in timetable_entries:
            #     schedule.append({
            #         'day': entry.day_of_week,
            #         'start_time': entry.start_time.strftime('%H:%M:%S'),
            #         'end_time': entry.end_time.strftime('%H:%M:%S')
            #     })

            classes_data.append({
                'id': allocation.id,
                'classroom_id': classroom.id,
                'classroom_name': str(classroom),
                'subject_name': allocation.subject.name,
                'grade_level_name': classroom.name.name if classroom.name else '',
                'student_count': student_count,
                'is_class_teacher': is_class_teacher,
                'schedule': schedule
            })

        return Response(classes_data, status=status.HTTP_200_OK)


class ClassroomStudentsView(APIView):
    """
    GET /api/academic/classrooms/{classroom_id}/students/
    Returns all students enrolled in a specific classroom.
    Only teachers who are assigned to this classroom can access this endpoint.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, classroom_id):
        # Get the teacher associated with the logged-in user
        try:
            teacher = Teacher.objects.get(user=request.user)
        except Teacher.DoesNotExist:
            return Response(
                {"error": "Teacher profile not found for this user"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get the classroom
        classroom = get_object_or_404(ClassRoom, id=classroom_id)

        # Verify teacher has access to this classroom
        # Either they are the class teacher OR they teach a subject in this classroom
        is_class_teacher = classroom.class_teacher == teacher

        # Get current academic year
        try:
            current_academic_year = AcademicYear.objects.get(active_year=True)
        except AcademicYear.DoesNotExist:
            return Response(
                {"error": "No active academic year found"},
                status=status.HTTP_404_NOT_FOUND
            )

        has_subject_allocation = AllocatedSubject.objects.filter(
            teacher_name=teacher,
            class_room=classroom,
            academic_year=current_academic_year
        ).exists()

        if not is_class_teacher and not has_subject_allocation:
            return Response(
                {"error": "You do not have permission to view students in this classroom"},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get all active students in this classroom
        students = Student.objects.filter(
            classroom=classroom,
            is_active=True
        ).values(
            'id',
            'admission_number',
            'first_name',
            'last_name',
            'email',
            'parent_contact',
            'image'
        ).order_by('admission_number')

        # Format the response
        students_data = [
            {
                'id': student['id'],
                'admission_number': student['admission_number'],
                'first_name': student['first_name'].capitalize() if student['first_name'] else '',
                'last_name': student['last_name'].capitalize() if student['last_name'] else '',
                'email': student['email'] or '',
                'phone': student['parent_contact'] or '',
                'photo': student['image'] if student['image'] else None,
                'status': 'active',
                'grade_level_name': classroom.name.name if classroom.name else ''
            }
            for student in students
        ]

        return Response(students_data, status=status.HTTP_200_OK)


class BulkMarkAttendanceView(APIView):
    """
    POST /api/attendance/student-attendance/bulk-mark/
    Mark attendance for multiple students at once.

    Expected request body:
    {
        "classroom": 101,
        "date": "2025-11-24",
        "records": [
            {"student": 1, "status": "Present", "remarks": ""},
            {"student": 2, "status": "Absent", "remarks": "Sick"}
        ]
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Get the teacher associated with the logged-in user
        try:
            teacher = Teacher.objects.get(user=request.user)
        except Teacher.DoesNotExist:
            return Response(
                {"error": "Teacher profile not found for this user"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get data from request
        classroom_id = request.data.get('classroom')
        date_str = request.data.get('date')
        records = request.data.get('records', [])

        # Validate required fields
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

        # Get the classroom
        classroom = get_object_or_404(ClassRoom, id=classroom_id)

        # Verify teacher has access to this classroom
        is_class_teacher = classroom.class_teacher == teacher

        try:
            current_academic_year = AcademicYear.objects.get(active_year=True)
        except AcademicYear.DoesNotExist:
            return Response(
                {"error": "No active academic year found"},
                status=status.HTTP_404_NOT_FOUND
            )

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

        # Process attendance records
        created_count = 0
        updated_count = 0
        errors = []

        with transaction.atomic():
            for record in records:
                student_id = record.get('student')
                status_name = record.get('status', 'Present')
                remarks = record.get('remarks', '')

                # Skip if no student ID
                if not student_id:
                    errors.append({"error": "Missing student ID in record"})
                    continue

                # Get the student
                try:
                    student = Student.objects.get(id=student_id, classroom=classroom)
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

                # Don't save "Present" status (as per model logic)
                if status_name == 'Present':
                    # Check if there's an existing non-present record and delete it
                    StudentAttendance.objects.filter(
                        student=student,
                        date=attendance_date,
                        ClassRoom=classroom
                    ).delete()
                    updated_count += 1
                    continue

                # Create or update attendance record
                attendance, created = StudentAttendance.objects.update_or_create(
                    student=student,
                    date=attendance_date,
                    ClassRoom=classroom,
                    defaults={
                        'status': attendance_status,
                        'notes': remarks
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
