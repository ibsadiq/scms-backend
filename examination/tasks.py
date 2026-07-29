"""
Celery tasks for examination operations.

Handles asynchronous operations like:
- Result computation for classrooms
- Report card PDF generation
- Bulk report card PDF generation
"""
from celery import shared_task
from django_tenants.utils import schema_context
from django.core.exceptions import ValidationError as DjangoValidationError
from examination.models import ReportCard, ReportCardStatus, TermResult
from examination.services.report_card_generator import ReportCardGenerator
from examination.services.result_computation_service import ResultComputationService
from academic.models import ClassRoom
from administration.models import Term, AcademicYear
from users.models import CustomUser

import logging
logger = logging.getLogger(__name__)


@shared_task(bind=True, name='examination.compute_class_results')
def compute_class_results_task(self, schema_name, classroom_id, term_id, academic_year_id, user_id):
    """
    Async task for computing term results for a classroom via Celery.
    """
    with schema_context(schema_name):
        summary = {"computed": 0, "failed": 0, "errors": []}
        try:
            classroom = ClassRoom.objects.get(id=classroom_id)
            term = Term.objects.get(id=term_id)
            academic_year = AcademicYear.objects.get(id=academic_year_id)
            user = CustomUser.objects.filter(id=user_id).first() if user_id else None
        except (ClassRoom.DoesNotExist, Term.DoesNotExist, AcademicYear.DoesNotExist) as e:
            return {"status": "failed", "error": "Invalid classroom, term, or academic year."}

        students = classroom.students.filter(is_active=True)
        total = students.count()
        for i, student in enumerate(students):
            self.update_state(
                state='PROGRESS',
                meta={'current': i, 'total': total, 'student': student.full_name}
            )
            try:
                ResultComputationService.compute_student_term_result(
                    student=student, term=term, academic_year=academic_year, user=user
                )
                summary["computed"] += 1
            except (DjangoValidationError, Exception) as e:
                summary["failed"] += 1
                summary["errors"].append({"student": student.full_name, "error": str(e)})

        summary["status"] = "success"
        logger.info(f"Computed term results asynchronously for classroom {classroom_id}: {summary['computed']} success, {summary['failed']} failed.")
        return summary


@shared_task(bind=True, name='examination.generate_report_card')
def generate_report_card_task(self, schema_name, term_result_id, user_id, regenerate=False, allow_unpublished=False):
    """
    Async task for generating a single report card PDF.
    """
    with schema_context(schema_name):
        try:
            # Fetch resources
            term_result = TermResult.objects.get(id=term_result_id)
            user = CustomUser.objects.filter(id=user_id).first() if user_id else None

            # Get or create the ReportCard record
            report_card, _ = ReportCard.objects.get_or_create(
                term_result=term_result,
                defaults={'generated_by': user, 'status': ReportCardStatus.GENERATING}
            )
            
            # If not creating a new one, update the status to GENERATING
            if report_card.status != ReportCardStatus.GENERATING:
                report_card.status = ReportCardStatus.GENERATING
                report_card.error_message = ""
                report_card.save(update_fields=['status', 'error_message'])

            # Generate the PDF
            generator = ReportCardGenerator(term_result, generated_by=user)
            generator.generate_pdf(regenerate=regenerate, allow_unpublished=allow_unpublished)

            # Update status to COMPLETED
            report_card.status = ReportCardStatus.COMPLETED
            report_card.save(update_fields=['status'])

            return {
                'status': 'success',
                'term_result_id': term_result_id,
            }

        except Exception as e:
            logger.exception(f"Failed to generate report card for TermResult {term_result_id}")
            try:
                report_card = ReportCard.objects.get(term_result_id=term_result_id)
                report_card.status = ReportCardStatus.FAILED
                report_card.error_message = str(e)
                report_card.save(update_fields=['status', 'error_message'])
            except ReportCard.DoesNotExist:
                pass
            
            return {
                'status': 'failed',
                'term_result_id': term_result_id,
                'error': str(e)
            }


@shared_task(bind=True, name='examination.generate_bulk_report_cards')
def generate_bulk_report_cards_task(self, schema_name, term_id, classroom_id, user_id, regenerate=False):
    """
    Async task for generating report card PDFs for an entire classroom.
    """
    with schema_context(schema_name):
        results = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'errors': []
        }
        
        try:
            term = Term.objects.get(id=term_id)
            classroom = ClassRoom.objects.get(id=classroom_id)
            user = CustomUser.objects.filter(id=user_id).first() if user_id else None
            
            # Find all published term results for students in this classroom
            term_results = TermResult.objects.filter(
                term=term,
                classroom=classroom,
                is_published=True
            ).select_related('student')
            
            results['total'] = term_results.count()
            
            # Initialize ReportCard records as PENDING to show in UI
            for term_result in term_results:
                report_card, created = ReportCard.objects.get_or_create(
                    term_result=term_result,
                    defaults={'generated_by': user, 'status': ReportCardStatus.PENDING}
                )
                if regenerate and not created:
                    report_card.status = ReportCardStatus.PENDING
                    report_card.save(update_fields=['status'])

            for i, term_result in enumerate(term_results):
                self.update_state(
                    state='PROGRESS',
                    meta={'current': i, 'total': results['total'], 'status': f'Generating for {term_result.student.full_name}'}
                )
                
                try:
                    report_card = ReportCard.objects.get(term_result=term_result)
                    report_card.status = ReportCardStatus.GENERATING
                    report_card.save(update_fields=['status'])

                    generator = ReportCardGenerator(term_result, generated_by=user)
                    generator.generate_pdf(regenerate=regenerate, allow_unpublished=False)
                    
                    report_card.status = ReportCardStatus.COMPLETED
                    report_card.save(update_fields=['status'])
                    
                    results['success'] += 1
                except Exception as e:
                    logger.exception(f"Failed to generate report card for TermResult {term_result.id}")
                    results['failed'] += 1
                    results['errors'].append({'student': term_result.student.full_name, 'error': str(e)})
                    
                    try:
                        report_card = ReportCard.objects.get(term_result=term_result)
                        report_card.status = ReportCardStatus.FAILED
                        report_card.error_message = str(e)
                        report_card.save(update_fields=['status', 'error_message'])
                    except ReportCard.DoesNotExist:
                        pass
                        
            return results

        except Exception as e:
            logger.exception(f"Failed bulk generation for term {term_id}, classroom {classroom_id}")
            results['errors'].append({'error': str(e)})
            return results
