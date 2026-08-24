"""
Celery tasks for examination operations.

Handles asynchronous operations like:
- Result computation for classrooms
- Report card PDF generation
- Bulk report card PDF generation
"""
from celery import shared_task
from django.db import transaction
from django_tenants.utils import schema_context
from django.core.exceptions import ValidationError as DjangoValidationError
from examination.models import ReportCard, ReportCardStatus, TermResult
from examination.services.report_card_generator import ReportCardGenerator
from examination.services.result_computation_service import ResultComputationService
from academic.models import ClassRoom
from administration.models import Term, AcademicYear
from users.models import CustomUser
from api.jobs.services import BackgroundJobService
from api.jobs.tasks import TenantBackgroundJobTask

import logging
logger = logging.getLogger(__name__)


@shared_task(bind=True, base=TenantBackgroundJobTask, name='examination.compute_class_results')
def compute_class_results_task(
    self, schema_name, classroom_id, term_id, academic_year_id, user_id, job_public_id=None
):
    """
    Async task for computing term results for a classroom via Celery.
    """
    with schema_context(schema_name):
        if job_public_id:
            BackgroundJobService.mark_started(job_public_id)
        try:
            classroom = ClassRoom.objects.get(id=classroom_id)
            term = Term.objects.get(id=term_id)
            academic_year = AcademicYear.objects.get(id=academic_year_id)
            user = CustomUser.objects.filter(id=user_id).first() if user_id else None
        except (ClassRoom.DoesNotExist, Term.DoesNotExist, AcademicYear.DoesNotExist):
            if job_public_id:
                BackgroundJobService.mark_failure(job_public_id, "RESULT_INPUT_NOT_FOUND")
            return {"status": "failed"}

        def update_progress(current, total, student):
            progress = int((current / total) * 100) if total else 0
            if job_public_id:
                BackgroundJobService.mark_progress(job_public_id, progress)
            self.update_state(
                state='PROGRESS',
                meta={'current': current, 'total': total, 'student': getattr(student, 'full_name', str(student))}
            )

        try:
            summary = ResultComputationService.compute_classroom_term_results(
                classroom=classroom,
                term=term,
                academic_year=academic_year,
                user=user,
                progress_callback=update_progress,
            )
        except Exception:
            logger.exception("Class result background job failed", extra={"job_id": job_public_id})
            if job_public_id:
                BackgroundJobService.mark_failure(job_public_id, "RESULT_COMPUTATION_FAILED")
            raise

        summary["status"] = "success"
        if job_public_id:
            BackgroundJobService.mark_success(
                job_public_id,
                {"computed": summary.get("computed", 0), "failed": summary.get("failed", 0)},
            )
        logger.info(f"Computed term results asynchronously for classroom {classroom_id}: {summary['computed']} success, {summary['failed']} failed.")
        return summary


@shared_task(bind=True, name='examination.generate_report_card')
def generate_report_card_task(self, schema_name, term_result_id, user_id, regenerate=False, allow_unpublished=False):
    """
    Async task for generating a single report card PDF.
    """
    with schema_context(schema_name):
        report_card = None
        try:
            # Fetch resources
            term_result = TermResult.objects.get(id=term_result_id)
            user = CustomUser.objects.filter(id=user_id).first() if user_id else None

            # Get the latest report card or create a new generating placeholder
            with transaction.atomic():
                latest_report_card = ReportCard.objects.select_for_update().filter(term_result=term_result).order_by('-version').first()
                if regenerate or not latest_report_card:
                    next_version = (latest_report_card.version + 1) if latest_report_card else 1
                    report_card = ReportCard.objects.create(
                        term_result=term_result,
                        generated_by=user,
                        version=next_version,
                        status=ReportCardStatus.GENERATING
                    )
                else:
                    report_card = latest_report_card
                    if report_card.status != ReportCardStatus.GENERATING:
                        report_card.status = ReportCardStatus.GENERATING
                        report_card.error_message = ""
                        report_card.save(update_fields=['status', 'error_message'])

            # Generate the PDF
            generator = ReportCardGenerator(term_result, generated_by=user)
            # We don't need the generator to create another one, but generator.generate_pdf currently creates one if regenerate=True!
            # We need to tell the generator to use this report_card, or just let generator do everything!
            # Wait, since the generator does everything, we can just call it.
            # But the UI polls the database. So creating it here is good.
            generator.generate_pdf(regenerate=regenerate, allow_unpublished=allow_unpublished, target_report_card=report_card)

            return {
                'status': 'success',
                'term_result_id': term_result_id,
            }

        except Exception as e:
            logger.exception(f"Failed to generate report card for TermResult {term_result_id}")
            if report_card:
                report_card.status = ReportCardStatus.FAILED
                report_card.error_message = str(e)
                report_card.save(update_fields=['status', 'error_message'])
            
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
            
            for term_result in term_results:
                with transaction.atomic():
                    latest_rc = ReportCard.objects.select_for_update().filter(term_result=term_result).order_by('-version').first()
                    if regenerate or not latest_rc:
                        next_version = (latest_rc.version + 1) if latest_rc else 1
                        report_card = ReportCard.objects.create(
                            term_result=term_result,
                            generated_by=user,
                            version=next_version,
                            status=ReportCardStatus.PENDING
                        )
                    else:
                        report_card = latest_rc
                        if report_card.status != ReportCardStatus.PENDING:
                            report_card.status = ReportCardStatus.PENDING
                            report_card.save(update_fields=['status'])

            for i, term_result in enumerate(term_results):
                self.update_state(
                    state='PROGRESS',
                    meta={'current': i, 'total': results['total'], 'status': f'Generating for {term_result.student.full_name}'}
                )
                
                report_card = ReportCard.objects.filter(
                    term_result=term_result, 
                    status=ReportCardStatus.PENDING
                ).order_by('-version').first()
                
                if not report_card:
                    continue
                    
                try:
                    report_card.status = ReportCardStatus.GENERATING
                    report_card.save(update_fields=['status'])

                    generator = ReportCardGenerator(term_result, generated_by=user)
                    generator.generate_pdf(regenerate=regenerate, allow_unpublished=False, target_report_card=report_card)
                    
                    results['success'] += 1
                except Exception as e:
                    logger.exception(f"Failed to generate report card for TermResult {term_result.id}")
                    results['failed'] += 1
                    results['errors'].append({'student': term_result.student.full_name, 'error': str(e)})
                    
                    report_card.status = ReportCardStatus.FAILED
                    report_card.error_message = str(e)
                    report_card.save(update_fields=['status', 'error_message'])
                        
            return results

        except Exception as e:
            logger.exception(f"Failed bulk generation for term {term_id}, classroom {classroom_id}")
            results['errors'].append({'error': str(e)})
            return results
