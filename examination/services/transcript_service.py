from django.db import transaction
from django.utils import timezone
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
            
        import json
        import hashlib
        
        snapshot_str = json.dumps(history_snapshot, sort_keys=True)
        snapshot_hash = hashlib.sha256(snapshot_str.encode('utf-8')).hexdigest()
        history_snapshot["verification_hash"] = snapshot_hash
        
        # Determine next version with concurrency safety
        latest_transcript = AcademicTranscript.objects.select_for_update().filter(student=student).order_by('-version').first()
        next_version = (latest_transcript.version + 1) if latest_transcript else 1
        
        serial_number = f"TR-{student.admission_number}-{next_version:03d}"
        
        metadata = {
            "generated_at": timezone.now().isoformat(),
            "total_records": len(cumulatives),
        }
            
        transcript = AcademicTranscript.objects.create(
            student=student,
            version=next_version,
            serial_number=serial_number,
            status=AcademicTranscript.Status.CURRENT,
            generated_by=user,
            history_snapshot=history_snapshot,
            metadata=metadata
        )
        
        # Mark all previous transcripts as SUPERSEDED
        AcademicTranscript.objects.filter(
            student=student, 
            status=AcademicTranscript.Status.CURRENT
        ).exclude(id=transcript.id).update(status=AcademicTranscript.Status.SUPERSEDED)
        
        return transcript
