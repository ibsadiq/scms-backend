import logging
from collections import Counter

from django.core.exceptions import ValidationError
from django.db import transaction

from academic.models import ClassRoom, Student, StudentClassEnrollment

logger = logging.getLogger(__name__)


class EnrollmentService:
    @classmethod
    @transaction.atomic
    def enroll(cls, *, student, classroom, academic_year, notes=""):
        Student.objects.select_for_update().get(pk=student.pk)
        enrollment = StudentClassEnrollment.objects.select_for_update().filter(
            student=student, academic_year=academic_year
        ).first()
        if enrollment:
            enrollment.classroom = classroom
            enrollment.is_active = True
            enrollment.notes = notes
            enrollment.save()
            created = False
        else:
            enrollment = StudentClassEnrollment.objects.create(
                student=student, classroom=classroom, academic_year=academic_year,
                is_active=True, notes=notes,
            )
            created = True

        if enrollment.is_active:
            enrollment_id = enrollment.pk
            transaction.on_commit(lambda: cls._sync_enrollment_fees(enrollment_id))

        return enrollment, created

    @classmethod
    @transaction.atomic
    def deactivate(cls, enrollment):
        enrollment = StudentClassEnrollment.objects.select_for_update().get(pk=enrollment.pk)
        if enrollment.is_active:
            enrollment.is_active = False
            enrollment.save(update_fields=("is_active",))
        return enrollment

    @classmethod
    @transaction.atomic
    def bulk_enroll(cls, rows):
        rows = list(rows)
        if not rows:
            return []
        keys = [(row["student"].pk, row["academic_year"].pk) for row in rows]
        if len(keys) != len(set(keys)):
            raise ValidationError("Bulk enrollment contains duplicate student/year rows.")

        classroom_counts = Counter(
            row["classroom"].pk for row in rows if row.get("is_active", True)
        )
        student_ids = sorted(row["student"].pk for row in rows)
        students = {
            student.pk: student
            for student in Student.objects.select_for_update().filter(
                pk__in=student_ids
            ).order_by("pk")
        }
        classrooms = {
            classroom.pk: classroom
            for classroom in ClassRoom.objects.select_for_update().filter(
                pk__in=sorted(classroom_counts)
            ).order_by("pk")
        }
        for classroom_id, count in classroom_counts.items():
            classroom = classrooms[classroom_id]
            if classroom.occupied_sits + count > classroom.capacity:
                raise ValidationError(f"Classroom '{classroom}' does not have capacity for this import.")

        existing = StudentClassEnrollment.objects.filter(
            student_id__in=student_ids,
            academic_year_id__in={row["academic_year"].pk for row in rows},
        )
        if existing.exists():
            raise ValidationError("Bulk enrollment cannot overwrite an existing student/year enrollment.")

        enrollments = StudentClassEnrollment.objects.bulk_create([
            StudentClassEnrollment(
                student=row["student"], classroom=row["classroom"],
                academic_year=row["academic_year"], is_active=row.get("is_active", True),
                notes=row.get("notes", ""),
            )
            for row in rows
        ])
        for classroom_id, count in classroom_counts.items():
            classroom = classrooms[classroom_id]
            classroom.occupied_sits += count
        ClassRoom.objects.bulk_update(classrooms.values(), ("occupied_sits",))

        changed_students = []
        for row in rows:
            if row.get("is_active", True) and row["academic_year"].active_year:
                student = students[row["student"].pk]
                student.classroom = row["classroom"]
                changed_students.append(student)
        Student.objects.bulk_update(changed_students, ("classroom",))

        active_ids = [e.pk for e in enrollments if e.is_active]
        if active_ids:
            transaction.on_commit(lambda: cls._sync_bulk_enrollment_fees(active_ids))

        return enrollments

    @classmethod
    def _sync_enrollment_fees(cls, enrollment_id):
        try:
            from finance.services.fee_assignment_service import FeeAssignmentService
            enrollment = StudentClassEnrollment.objects.select_related(
                "student", "classroom__grade_level", "academic_year"
            ).filter(pk=enrollment_id, is_active=True).first()
            if enrollment:
                FeeAssignmentService.sync_fees_for_enrollment(enrollment=enrollment)
        except Exception:
            logger.exception("Failed to synchronize fees for enrollment %s", enrollment_id)

    @classmethod
    def _sync_bulk_enrollment_fees(cls, enrollment_ids):
        try:
            from finance.services.fee_assignment_service import FeeAssignmentService
            enrollments = list(
                StudentClassEnrollment.objects.select_related(
                    "student", "classroom__grade_level", "academic_year"
                ).filter(pk__in=enrollment_ids, is_active=True)
            )
            for enrollment in enrollments:
                FeeAssignmentService.sync_fees_for_enrollment(enrollment=enrollment)
        except Exception:
            logger.exception("Failed to synchronize fees for bulk enrollments")

