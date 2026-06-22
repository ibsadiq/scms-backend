"""
api/core/views.py

Cross-schema endpoints that must run against the public schema.
These are tenant-agnostic — they look up GlobalIDRegistry and optionally
reach into a tenant schema to pull academic records.

Endpoints
---------
GET  /api/core/lookup/student/?id=STU-XXXXXXXX
     Look up a student across all schools. Returns basic identity info
     from the registry plus academic records from their current school.

POST /api/core/transfers/complete/
     Called by the receiving school after the new Student record is saved.
     Updates GlobalIDRegistry.current_schema and creates a TransferLog entry.

POST /api/sis/students/<pk>/issue-transfer/  (lives in api/sis/views.py — see note)
     Sending school marks a student as transferred out.
     Student.save() handles the registry sync automatically.
"""

from django.db import connection
from django_tenants.utils import schema_context
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status


class StudentLookupView(APIView):
    """
    Cross-schema student lookup for transfer enrollment.

    GET /api/core/lookup/student/?id=STU-XXXXXXXX

    Returns:
      - Identity info from GlobalIDRegistry (name, DOB, current school)
      - Academic records from the student's current school:
          * Current class / class level
          * Full class enrollment history
          * Term results summary
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        student_id = request.query_params.get('id', '').strip().upper()
        if not student_id:
            return Response({'error': 'id query parameter is required'}, status=400)

        # ── 1. Look up registry (public schema) ───────────────────────────────
        with schema_context('public'):
            from core.models import GlobalIDRegistry
            try:
                reg = GlobalIDRegistry.objects.get(unique_id=student_id, entity_type='student')
            except GlobalIDRegistry.DoesNotExist:
                return Response({'error': 'Student ID not found'}, status=404)

        result = {
            'student_id':      reg.unique_id,
            'first_name':      reg.first_name,
            'last_name':       reg.last_name,
            'date_of_birth':   reg.date_of_birth,
            'national_id':     reg.national_id,
            'current_schema':  reg.current_schema,
            'in_transit':      not bool(reg.current_schema),
            'academic_records': None,
            'transfer_history': [],
        }

        # ── 2. Transfer history (public schema) ───────────────────────────────
        with schema_context('public'):
            from core.models import TransferLog
            logs = TransferLog.objects.filter(
                entity_id=student_id
            ).values('from_schema', 'to_schema', 'transferred_at', 'notes')
            result['transfer_history'] = list(logs)

        # ── 3. Academic records from the current school ───────────────────────
        if reg.current_schema:
            try:
                with schema_context(reg.current_schema):
                    result['academic_records'] = _fetch_student_academic_records(student_id)
            except Exception:
                # Non-fatal — return what we have from the registry
                result['academic_records'] = None

        return Response(result)


def _fetch_student_academic_records(student_id: str) -> dict:
    """
    Runs inside a tenant schema_context.
    Returns academic records for the given student_id.
    """
    from academic.models import Student, StudentClassEnrollment

    student = Student.objects.select_related(
        'classroom', 'class_level', 'class_of_year'
    ).get(student_id=student_id)

    # ── Enrollment history ────────────────────────────────────────────────────
    enrollments = (
        StudentClassEnrollment.objects
        .filter(student=student)
        .select_related('classroom', 'classroom__class_level', 'academic_year')
        .order_by('-academic_year__start_date')
    )
    enrollment_history = [
        {
            'academic_year': str(e.academic_year),
            'classroom':     str(e.classroom),
            'class_level':   str(e.classroom.class_level) if e.classroom.class_level else None,
            'is_active':     e.is_active,
            'notes':         e.notes,
        }
        for e in enrollments
    ]

    # ── Term results summary ──────────────────────────────────────────────────
    term_results = []
    try:
        from examination.models import TermResult
        results = (
            TermResult.objects
            .filter(student=student)
            .select_related('term', 'academic_year', 'classroom')
            .order_by('-academic_year__start_date', 'term__order')
        )
        for r in results:
            term_results.append({
                'academic_year':      str(r.academic_year),
                'term':               str(r.term),
                'classroom':          str(r.classroom) if r.classroom else None,
                'total_marks':        str(r.total_marks),
                'average_percentage': str(r.average_percentage),
                'grade':              r.grade,
                'gpa':                str(r.gpa),
                'position':           getattr(r, 'position', None),
            })
    except Exception:
        pass

    return {
        'admission_number': student.admission_number,
        'gender':           student.gender,
        'blood_group':      student.blood_group,
        'current_class':    str(student.classroom)   if student.classroom   else None,
        'current_level':    str(student.class_level) if student.class_level else None,
        'status':           student.status,
        'enrollment_history': enrollment_history,
        'term_results':       term_results,
    }


class TransferCompleteView(APIView):
    """
    Called by the receiving school after the new Student record has been saved
    (i.e., after enrollment is confirmed on their side).

    POST /api/core/transfers/complete/
    Body: { "student_id": "STU-XXXXXXXX", "notes": "..." }

    Updates GlobalIDRegistry.current_schema to the receiving school and
    creates an immutable TransferLog entry.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        student_id = request.data.get('student_id', '').strip().upper()
        notes      = request.data.get('notes', '')

        if not student_id:
            return Response({'error': 'student_id is required'}, status=400)

        # Capture the receiving school schema before entering public context
        to_schema = connection.schema_name

        with schema_context('public'):
            from core.models import GlobalIDRegistry, TransferLog
            try:
                reg = GlobalIDRegistry.objects.get(unique_id=student_id, entity_type='student')
            except GlobalIDRegistry.DoesNotExist:
                return Response({'error': 'Student ID not found'}, status=404)

            from_schema = reg.current_schema

            reg.current_schema = to_schema
            reg.save(update_fields=['current_schema', 'updated_at'])

            TransferLog.objects.create(
                entity_id=student_id,
                entity_type='student',
                from_schema=from_schema,
                to_schema=to_schema,
                person_name=f"{reg.first_name} {reg.last_name}".strip(),
                notes=notes,
            )

        return Response({
            'success':     True,
            'student_id':  student_id,
            'from_school': from_schema or None,
            'to_school':   to_schema,
        })
