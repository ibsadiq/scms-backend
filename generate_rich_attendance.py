import os
import sys
import random
from datetime import date, timedelta
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

from django_tenants.utils import schema_context
from academic.models import Student
from administration.models import Term, AcademicYear
from attendance.models import AttendanceStatus, StudentAttendance

schema_name = 'green_valley_academy'

with schema_context(schema_name):
    students = list(Student.objects.all())
    active_year = AcademicYear.objects.filter(active_year=True).first() or AcademicYear.objects.first()
    active_term = Term.objects.filter(academic_year=active_year).last() or Term.objects.first()
    
    present, _ = AttendanceStatus.objects.get_or_create(name='Present', defaults={'code': 'P', 'absent': False, 'late': False})
    absent, _ = AttendanceStatus.objects.get_or_create(name='Absent', defaults={'code': 'A', 'absent': True, 'late': False})
    late, _ = AttendanceStatus.objects.get_or_create(name='Late', defaults={'code': 'L', 'absent': False, 'late': True})
    
    today = date.today()
    raw_dates = [today - timedelta(days=i) for i in range(50)]
    dates = [d for d in raw_dates if d.weekday() < 5][:30] # 30 weekdays
    
    print(f"Generating 30 days of attendance for {len(students)} students in '{schema_name}'...")
    
    attendance_objects = []
    
    # Check existing (student_id, date)
    existing = set(StudentAttendance.objects.values_list('student_id', 'date'))
    
    for d in dates:
        for student in students:
            if (student.id, d) in existing:
                continue
            r = random.random()
            if r < 0.88:
                status = present
            elif r < 0.94:
                status = late
            else:
                status = absent
                
            attendance_objects.append(StudentAttendance(
                student=student,
                date=d,
                term=active_term,
                ClassRoom=student.classroom,
                status=status
            ))
            
    if attendance_objects:
        StudentAttendance.objects.bulk_create(attendance_objects, batch_size=1000)
        
    total_records = StudentAttendance.objects.count()
    print(f"🎉 RICH ATTENDANCE SEEDED!")
    print(f"Created {len(attendance_objects)} new attendance records.")
    print(f"Total attendance records in database: {total_records} across 30 weekdays (~6 school weeks).")
