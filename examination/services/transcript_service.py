from django.db import transaction
from ..models import (
    AcademicTranscript, CumulativeResult, LifecycleState
)

class TranscriptService:

    @staticmethod
    @transaction.atomic
    def generate_transcript(student, user):
        """
        Generates or updates the official academic transcript for a student.
        Builds the JSON history snapshot from LOCKED/PUBLISHED records.
        """
        cumulatives = CumulativeResult.objects.filter(
            student=student,
            lifecycle_state__in=[LifecycleState.LOCKED, LifecycleState.PUBLISHED]
        ).select_related('academic_year').order_by('academic_year__start_date')
        
        history_snapshot = {
            "student_id": student.id,
            "student_name": student.full_name,
            "admission_number": student.admission_number,
            "records": []
        }
        
        for cum in cumulatives:
            record = {
                "academic_year": cum.academic_year.name,
                "total_marks": str(cum.total_marks),
                "cumulative_average": str(cum.cumulative_average),
                "cumulative_gpa": str(cum.cumulative_gpa),
                "grade": cum.grade,
                "subjects": []
            }
            
            for sub in cum.subjects.select_related('subject').all():
                record["subjects"].append({
                    "subject": sub.subject.name,
                    "code": sub.subject.subject_code,
                    "average": str(sub.cumulative_average),
                    "grade": sub.grade,
                    "grade_point": str(sub.grade_point)
                })
                
            history_snapshot["records"].append(record)
            
        transcript, created = AcademicTranscript.objects.update_or_create(
            student=student,
            defaults={
                "generated_by": user,
                "history_snapshot": history_snapshot
            }
        )
        
        return transcript
