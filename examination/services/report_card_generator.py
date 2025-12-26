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

    def generate_pdf(self, regenerate=False) -> 'ReportCard':
        """
        Generate PDF report card and save to database.

        Args:
            regenerate: If True, regenerate even if PDF already exists

        Returns:
            ReportCard instance with generated PDF
        """
        from examination.models import ReportCard

        # Check if report card already exists
        try:
            report_card = ReportCard.objects.get(term_result=self.term_result)
            if not regenerate and report_card.pdf_file:
                return report_card
        except ReportCard.DoesNotExist:
            report_card = ReportCard(
                term_result=self.term_result,
                generated_by=self.generated_by
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
        report_card.generated_date = timezone.now()
        report_card.save()

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
        """
        Prepare template context with all necessary data.

        Returns:
            Dictionary containing all report card data
        """
        term_result = self.term_result
        student = term_result.student

        # Get subject results ordered by subject name
        subject_results = term_result.subject_results.select_related(
            'subject', 'teacher'
        ).order_by('subject__name')

        # Get grade scale rules for legend
        grade_scale = None
        if subject_results.exists():
            from examination.services import GradingEngine
            engine = GradingEngine()
            grade_scale = engine.grade_scale

        # Prepare grade scale legend
        grade_legend = []
        if grade_scale:
            rules = grade_scale.gradescalerule_set.all().order_by('-min_grade')
            for rule in rules:
                grade_legend.append({
                    'letter': rule.letter_grade,
                    'range': f"{rule.min_grade}-{rule.max_grade}",
                    'gpa': rule.numeric_scale
                })

        # Get school info from settings (you can customize this)
        school_info = {
            'name': getattr(settings, 'SCHOOL_NAME', 'School Name'),
            'address': getattr(settings, 'SCHOOL_ADDRESS', 'School Address'),
            'phone': getattr(settings, 'SCHOOL_PHONE', ''),
            'email': getattr(settings, 'SCHOOL_EMAIL', ''),
            'logo': getattr(settings, 'SCHOOL_LOGO_PATH', None),
            'motto': getattr(settings, 'SCHOOL_MOTTO', '')
        }

        # Get attendance if available
        attendance_stats = self._get_attendance_stats()

        context = {
            # School info
            'school': school_info,

            # Student info
            'student': student,
            'admission_number': student.admission_number,
            'student_name': student.full_name,
            'date_of_birth': student.date_of_birth,
            'gender': student.gender,

            # Term info
            'term': term_result.term,
            'term_name': term_result.term.name,
            'academic_year': term_result.academic_year,
            'classroom': term_result.classroom,
            'classroom_name': str(term_result.classroom) if term_result.classroom else 'N/A',

            # Overall results
            'total_marks': term_result.total_marks,
            'total_possible': term_result.total_possible,
            'average_percentage': term_result.average_percentage,
            'grade': term_result.grade,
            'gpa': term_result.gpa,
            'position': term_result.position_in_class,
            'total_students': term_result.total_students,

            # Subject results
            'subject_results': subject_results,
            'subject_count': subject_results.count(),

            # Remarks
            'class_teacher_remarks': term_result.class_teacher_remarks or 'No remarks provided',
            'principal_remarks': term_result.principal_remarks or 'No remarks provided',

            # Grade legend
            'grade_legend': grade_legend,

            # Attendance
            'attendance': attendance_stats,

            # Metadata
            'computed_date': term_result.computed_date,
            'published_date': term_result.published_date,
            'generated_date': timezone.now(),

            # Term dates
            'term_start': term_result.term.start_date if hasattr(term_result.term, 'start_date') else None,
            'term_end': term_result.term.end_date if hasattr(term_result.term, 'end_date') else None,
        }

        return context

    def _get_attendance_stats(self) -> Optional[dict]:
        """
        Get attendance statistics for the student if available.

        Returns:
            Dictionary with attendance stats or None
        """
        try:
            from attendance.models import Attendance

            # Get attendance records for student and term
            attendances = Attendance.objects.filter(
                student=self.term_result.student,
                date__gte=self.term_result.term.start_date,
                date__lte=self.term_result.term.end_date
            )

            total_days = attendances.count()
            present_days = attendances.filter(status='Present').count()
            absent_days = attendances.filter(status='Absent').count()
            late_days = attendances.filter(status='Late').count()

            if total_days > 0:
                attendance_percentage = (present_days / total_days) * 100
            else:
                attendance_percentage = 0

            return {
                'total_days': total_days,
                'present': present_days,
                'absent': absent_days,
                'late': late_days,
                'percentage': round(attendance_percentage, 2)
            }
        except Exception:
            # Attendance module might not be available or configured
            return None

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
