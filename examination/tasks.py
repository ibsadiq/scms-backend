"""
Celery tasks for examination operations.

Handles asynchronous operations like:
- Bulk result computation
- Report card generation for entire classrooms
- Grade publishing
"""
from celery import shared_task
from django.db import transaction
from django.core.exceptions import ValidationError

from examination.models import TermResult, ExaminationListHandler
from examination.services.result_computation import ResultComputationService
from examination.services.report_card_generator import ReportCardGenerator
from academic.models import ClassRoom, Student
from administration.models import Term


@shared_task(bind=True, name='examination.compute_classroom_results')
def compute_classroom_results_task(self, term_id, classroom_id, computed_by_id=None):
    """
    Async task for computing results for an entire classroom.

    Args:
        self: Celery task instance
        term_id: ID of the term
        classroom_id: ID of the classroom
        computed_by_id: ID of user who initiated computation

    Returns:
        dict: Computation summary
    """
    try:
        # Update state
        self.update_state(
            state='PROGRESS',
            meta={'status': 'Initializing result computation...'}
        )

        term = Term.objects.get(id=term_id)
        classroom = ClassRoom.objects.get(id=classroom_id)

        # Initialize service
        service = ResultComputationService(
            term=term,
            classroom=classroom,
            computed_by_id=computed_by_id
        )

        # Update state
        self.update_state(
            state='PROGRESS',
            meta={'status': 'Computing results...'}
        )

        # Compute results
        results = service.compute_results_for_classroom()

        return {
            'status': 'success',
            'term': term.name,
            'classroom': str(classroom),
            'results': results
        }

    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e)
        }


@shared_task(bind=True, name='examination.generate_classroom_report_cards')
def generate_classroom_report_cards_task(self, term_id, classroom_id):
    """
    Async task for generating report cards for all students in a classroom.

    Args:
        self: Celery task instance
        term_id: ID of the term
        classroom_id: ID of the classroom

    Returns:
        dict: Generation summary
    """
    try:
        term = Term.objects.get(id=term_id)
        classroom = ClassRoom.objects.get(id=classroom_id)

        # Get all students in the classroom
        students = Student.objects.filter(
            current_enrollment__classroom=classroom
        )

        total_students = students.count()
        generated = 0
        failed = 0
        errors = []

        for idx, student in enumerate(students, start=1):
            # Update progress
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': idx,
                    'total': total_students,
                    'status': f'Generating report card for {student.first_name} {student.last_name}'
                }
            )

            try:
                # Check if result exists
                result = TermResult.objects.filter(
                    student=student,
                    term=term,
                    classroom=classroom
                ).first()

                if not result:
                    errors.append(f"No result found for {student.admission_number}")
                    failed += 1
                    continue

                # Generate report card
                generator = ReportCardGenerator(term=term, student=student, classroom=classroom)
                pdf_path = generator.generate()

                generated += 1

            except Exception as e:
                failed += 1
                errors.append(f"{student.admission_number}: {str(e)}")

        return {
            'status': 'success',
            'total': total_students,
            'generated': generated,
            'failed': failed,
            'errors': errors
        }

    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e)
        }


@shared_task(bind=True, name='examination.publish_results')
def publish_results_task(self, term_id, classroom_id):
    """
    Async task for publishing results to students and parents.

    Args:
        self: Celery task instance
        term_id: ID of the term
        classroom_id: ID of the classroom

    Returns:
        dict: Publishing summary
    """
    try:
        term = Term.objects.get(id=term_id)
        classroom = ClassRoom.objects.get(id=classroom_id)

        # Update all results to published
        results = TermResult.objects.filter(
            term=term,
            classroom=classroom
        )

        total = results.count()

        self.update_state(
            state='PROGRESS',
            meta={'status': f'Publishing {total} results...'}
        )

        with transaction.atomic():
            updated = results.update(published=True)

        return {
            'status': 'success',
            'published': updated,
            'term': term.name,
            'classroom': str(classroom)
        }

    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e)
        }
