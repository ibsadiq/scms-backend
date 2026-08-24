"""
Report Card Generator Service (Phase 1.2)
Handles PDF generation for student report cards using WeasyPrint.
"""
import os
from io import BytesIO
from decimal import Decimal
from typing import Optional
from django.conf import settings
from django.template.loader import render_to_string
from django.core.files.base import ContentFile
from django.utils import timezone
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration
import base64
import mimetypes
import requests
from examination.models import ReportCard


def _to_base64_uri(field_or_url):
    if not field_or_url:
        return None
    try:
        if hasattr(field_or_url, 'open'):
            f = field_or_url.open('rb')
            data = f.read()
            mime, _ = mimetypes.guess_type(getattr(field_or_url, 'name', 'file.jpg'))
            mime = mime or 'image/jpeg'
            encoded = base64.b64encode(data).decode('utf-8')
            return f"data:{mime};base64,{encoded}"
    except Exception:
        pass

    if isinstance(field_or_url, str) and (field_or_url.startswith('http://') or field_or_url.startswith('https://')):
        try:
            res = requests.get(field_or_url, timeout=5)
            if res.status_code == 200:
                mime = res.headers.get('Content-Type', 'image/jpeg')
                encoded = base64.b64encode(res.content).decode('utf-8')
                return f"data:{mime};base64,{encoded}"
        except Exception:
            pass
    elif isinstance(field_or_url, str) and os.path.exists(field_or_url):
        try:
            with open(field_or_url, 'rb') as f:
                data = f.read()
                mime, _ = mimetypes.guess_type(field_or_url)
                mime = mime or 'image/jpeg'
                encoded = base64.b64encode(data).decode('utf-8')
                return f"data:{mime};base64,{encoded}"
        except Exception:
            pass
    return field_or_url


class ReportCardGenerator:
    """
    Service class for generating PDF report cards from TermResult data.
    Uses HTML/CSS templates and WeasyPrint for PDF conversion.
    """

    def __init__(self, term_result, generated_by=None):
        """
        Initialize the report card generator.

        Args:
            term_result: TermResult instance to generate report card for
            generated_by: User generating the report card
        """
        self.term_result = term_result
        self.generated_by = generated_by
        self.font_config = FontConfiguration()

    def generate_pdf(self, regenerate=False, allow_unpublished=False, target_report_card=None) -> 'ReportCard':
        """
        Generate PDF report card and save to database.

        Args:
            regenerate: If True, regenerate even if PDF already exists
            allow_unpublished: If True, generate even if result is not published yet
            target_report_card: If provided, saves PDF to this instance instead of looking it up.

        Returns:
            ReportCard instance with generated PDF
        """
        if not allow_unpublished and not getattr(self.term_result, 'is_published', False):
            from django.core.exceptions import ValidationError
            raise ValidationError("Cannot generate report card for unpublished result.")

        from examination.models import ReportCard, ReportCardStatus

        if target_report_card:
            report_card = target_report_card
        else:
            # Determine if we should reuse the current active report card with concurrency safety
            latest_report_card = ReportCard.objects.select_for_update().filter(term_result=self.term_result).order_by('-version').first()
            
            if latest_report_card and not regenerate and latest_report_card.pdf_file:
                return latest_report_card
                
            next_version = (latest_report_card.version + 1) if latest_report_card else 1

            report_card = ReportCard(
                term_result=self.term_result,
                generated_by=self.generated_by,
                version=next_version,
                status=ReportCardStatus.GENERATING
            )

        # Generate PDF content
        pdf_content = self._render_pdf()

        # Create filename
        filename = self._generate_filename()

        # Save PDF to report card
        report_card.pdf_file.save(
            filename,
            ContentFile(pdf_content),
            save=False
        )
        report_card.generated_by = self.generated_by
        report_card.status = ReportCardStatus.CURRENT
        report_card.save()
        
        # Mark all previous report cards as SUPERSEDED
        ReportCard.objects.filter(
            term_result=self.term_result,
            status=ReportCardStatus.CURRENT
        ).exclude(id=report_card.id).update(status=ReportCardStatus.SUPERSEDED)

        return report_card

    def _render_pdf(self) -> bytes:
        """
        Render HTML template to PDF bytes.

        Returns:
            PDF file content as bytes
        """
        # Prepare context data
        context = self._prepare_context()

        # Render HTML from template
        html_string = render_to_string('examination/report_card.html', context)

        # Convert HTML to PDF
        html = HTML(string=html_string, base_url=settings.BASE_DIR)

        # Get CSS for styling
        css_file = os.path.join(settings.BASE_DIR, 'examination', 'templates', 'examination', 'report_card.css')
        if os.path.exists(css_file):
            css = CSS(filename=css_file, font_config=self.font_config)
            pdf = html.write_pdf(stylesheets=[css], font_config=self.font_config)
        else:
            pdf = html.write_pdf(font_config=self.font_config)

        return pdf

    def _prepare_context(self) -> dict:
        from django.db import connection
        from tenants.models import Client
        
        schema_name = connection.schema_name
        try:
            client_tenant = Client.objects.get(schema_name=schema_name)
        except Exception:
            client_tenant = None

        term_result = self.term_result
        student = term_result.student

        subject_results = term_result.subject_results.select_related(
            'subject', 'teacher'
        ).order_by('subject__name')

        scheme = term_result.grading_scheme
        components = list(scheme.components.order_by('order')) if scheme else []

        def get_remark_for_grade(grade_letter):
            g = str(grade_letter or '').strip().upper()
            if g in ['A', 'A1']:
                return 'Distinction'
            elif g in ['B', 'B2', 'B3']:
                return 'Very Good'
            elif g in ['C', 'C4', 'C5', 'C6']:
                return 'Credit'
            elif g in ['D', 'D7', 'E', 'E8']:
                return 'Pass'
            elif g in ['F', 'F9']:
                return 'Fail'
            return 'Good'

        subject_rows = []
        for sr in subject_results:
            scores_by_component = {
                s.component_id: s.score for s in sr.assessment_scores.select_related('component')
            }
            subject_rows.append({
                'result': sr,
                'component_scores': [scores_by_component.get(c.id, '-') for c in components],
                'remark': get_remark_for_grade(sr.grade),
            })

        logo_uri = None
        if client_tenant and getattr(client_tenant, 'logo', None) and client_tenant.logo:
            logo_uri = _to_base64_uri(client_tenant.logo)
        elif client_tenant and hasattr(client_tenant, 'get_logo_url'):
            logo_uri = _to_base64_uri(client_tenant.get_logo_url())

        student_photo_uri = None
        if hasattr(student, 'image') and student.image:
            student_photo_uri = _to_base64_uri(student.image)

        school_info = {
            'name': getattr(client_tenant, 'name', 'SCHOOL NAME') if client_tenant else 'SCHOOL NAME',
            'address': getattr(client_tenant, 'address', '') or '' if client_tenant else '',
            'phone': getattr(client_tenant, 'contact_phone', '') or '' if client_tenant else '',
            'email': getattr(client_tenant, 'contact_email', '') or '' if client_tenant else '',
            'logo': logo_uri,
            'motto': getattr(client_tenant, 'motto', '') or '' if client_tenant else '',
        }

        grade_legend = []
        if scheme:
            for rule in scheme.grade_rules.all().order_by('-min_score'):
                grade_legend.append({
                    'letter': rule.grade,
                    'range': f"{int(rule.min_score)}-{int(rule.max_score)}",
                    'remark': rule.remark or '',
                })

        attendance_stats = self._get_attendance_stats()

        context = {
            'school': school_info,
            'student': student,
            'student_photo': student_photo_uri,
            'admission_number': student.admission_number,
            'student_name': student.full_name,
            'date_of_birth': student.date_of_birth,
            'gender': student.gender,
            'term': term_result.term,
            'term_name': term_result.term.name,
            'academic_year': term_result.academic_year,
            'classroom': term_result.classroom,
            'classroom_name': str(term_result.classroom) if term_result.classroom else 'N/A',
            'total_marks': term_result.total_marks,
            'total_possible': subject_results.count() * 100,
            'average_percentage': term_result.average_percentage,
            'grade': term_result.grade,
            'gpa': term_result.gpa,
            'position': term_result.position_in_class,
            'total_students': term_result.total_students,
            'components': components,
            'subject_rows': subject_rows,
            'subject_count': subject_results.count(),
            'class_teacher_remark': term_result.class_teacher_remarks or 'No remarks provided',
            'admin_remark': term_result.principal_remarks or 'No remarks provided',
            'grade_legend': grade_legend,
            'attendance': attendance_stats,
            'computed_date': term_result.computed_date,
            'published_date': term_result.published_date,
            'generated_date': timezone.now(),
            'term_start': term_result.term.start_date if hasattr(term_result.term, 'start_date') else None,
            'term_end': term_result.term.end_date if hasattr(term_result.term, 'end_date') else None,
        }

        return context

    def _get_attendance_stats(self) -> Optional[dict]:
        from attendance.services import AttendanceSummaryService

        summary = AttendanceSummaryService.get_for_report_card(
            student=self.term_result.student,
            term=self.term_result.term,
        )
        if summary is None:
            return None
        return {
            'total_days': summary.school_days,
            'present': summary.days_present,
            'absent': summary.days_absent,
            'late': summary.times_late,
            'percentage': summary.attendance_percentage,
            'source': summary.source,
        }

    def _generate_filename(self) -> str:
        """
        Generate unique filename for report card PDF.

        Returns:
            Filename string
        """
        student = self.term_result.student
        term = self.term_result.term
        academic_year = self.term_result.academic_year

        # Clean student name for filename
        student_name = student.full_name.replace(' ', '_').replace('/', '-')
        term_name = term.name.replace(' ', '_')
        year_name = academic_year.name.replace('/', '-')

        filename = f"report_card_{student_name}_{term_name}_{year_name}.pdf"

        return filename

    @classmethod
    def generate_bulk_report_cards(cls, term, classroom, generated_by=None, regenerate=False) -> dict:
        """
        Generate report cards for all students in a classroom.

        Args:
            term: Term instance
            classroom: ClassRoom instance
            generated_by: User generating the reports
            regenerate: Whether to regenerate existing report cards

        Returns:
            Dictionary with generation summary
        """
        from examination.models import TermResult

        # Get all term results for classroom and term
        term_results = TermResult.objects.filter(
            term=term,
            classroom=classroom,
            is_published=True  # Only generate for published results
        ).select_related('student')

        summary = {
            'total': term_results.count(),
            'generated': 0,
            'failed': 0,
            'errors': []
        }

        for term_result in term_results:
            try:
                generator = cls(term_result, generated_by=generated_by)
                generator.generate_pdf(regenerate=regenerate)
                summary['generated'] += 1
            except Exception as e:
                summary['failed'] += 1
                summary['errors'].append({
                    'student': term_result.student.full_name,
                    'error': str(e)
                })

        return summary

    def preview_html(self) -> str:
        """
        Generate HTML preview without converting to PDF.
        Useful for debugging templates.

        Returns:
            HTML string
        """
        context = self._prepare_context()
        return render_to_string('examination/report_card.html', context)
