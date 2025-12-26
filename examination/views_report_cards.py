"""
Report Card Views (Phase 1.2)
Handles API endpoints for generating and downloading report card PDFs.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404

from .models import TermResult, ReportCard
from .serializers import ReportCardSerializer
from .services import ReportCardGenerator
from administration.models import Term
from academic.models import ClassRoom, Student


class ReportCardViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for managing report cards.

    Endpoints:
    - GET /api/examination/report-cards/ - List all report cards
    - GET /api/examination/report-cards/?student={id} - Get report cards for student
    - GET /api/examination/report-cards/{id}/ - Get report card details
    - GET /api/examination/report-cards/{id}/download/ - Download PDF
    - POST /api/examination/report-cards/generate/ - Generate single report card
    - POST /api/examination/report-cards/bulk-generate/ - Generate for classroom
    - GET /api/examination/report-cards/{id}/preview/ - HTML preview
    """
    permission_classes = [IsAuthenticated]
    serializer_class = ReportCardSerializer
    queryset = ReportCard.objects.all().select_related(
        'term_result__student',
        'term_result__term',
        'term_result__academic_year',
        'generated_by'
    )

    def get_queryset(self):
        """Filter report cards based on user permissions and query params"""
        queryset = super().get_queryset()

        # If not staff, only show report cards for published results
        if not self.request.user.is_staff:
            queryset = queryset.filter(term_result__is_published=True)

        # Filter by student if provided
        student_id = self.request.query_params.get('student')
        if student_id:
            queryset = queryset.filter(term_result__student_id=student_id)

        # Filter by term if provided
        term_id = self.request.query_params.get('term')
        if term_id:
            queryset = queryset.filter(term_result__term_id=term_id)

        return queryset

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """
        Download report card PDF.

        GET /api/examination/report-cards/{id}/download/
        """
        report_card = self.get_object()

        # Check if PDF exists
        if not report_card.pdf_file:
            return Response(
                {'error': 'Report card PDF has not been generated yet'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Increment download counter
        report_card.increment_download_count()

        # Return PDF file
        try:
            filename = f"report_card_{report_card.term_result.student.full_name.replace(' ', '_')}.pdf"
            response = FileResponse(
                report_card.pdf_file.open('rb'),
                content_type='application/pdf'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        except Exception as e:
            return Response(
                {'error': f'Failed to download report card: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'])
    def preview(self, request, pk=None):
        """
        Preview report card HTML (for debugging).

        GET /api/examination/report-cards/{id}/preview/
        """
        if not request.user.is_staff:
            return Response(
                {'error': 'Only staff can preview report cards'},
                status=status.HTTP_403_FORBIDDEN
            )

        report_card = self.get_object()

        try:
            generator = ReportCardGenerator(report_card.term_result)
            html_content = generator.preview_html()

            from django.http import HttpResponse
            return HttpResponse(html_content, content_type='text/html')
        except Exception as e:
            return Response(
                {'error': f'Failed to generate preview: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def generate(self, request):
        """
        Generate report card for a single student.

        POST /api/examination/report-cards/generate/
        {
            "term_result_id": 1,
            "regenerate": false
        }
        """
        term_result_id = request.data.get('term_result_id')
        regenerate = request.data.get('regenerate', False)

        if not term_result_id:
            return Response(
                {'error': 'term_result_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            term_result = TermResult.objects.select_related(
                'student', 'term', 'academic_year', 'classroom'
            ).get(id=term_result_id)

            # Check if result is published (only generate for published results)
            if not term_result.is_published:
                return Response(
                    {'error': 'Cannot generate report card for unpublished results'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Generate report card
            generator = ReportCardGenerator(
                term_result=term_result,
                generated_by=request.user
            )
            report_card = generator.generate_pdf(regenerate=regenerate)

            return Response({
                'message': 'Report card generated successfully',
                'report_card_id': report_card.id,
                'student': term_result.student.full_name,
                'term': term_result.term.name,
                'download_url': f'/api/examination/report-cards/{report_card.id}/download/'
            }, status=status.HTTP_201_CREATED)

        except TermResult.DoesNotExist:
            return Response(
                {'error': 'Term result not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': f'Failed to generate report card: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def bulk_generate(self, request):
        """
        Generate report cards for all students in a classroom.

        POST /api/examination/report-cards/bulk-generate/
        {
            "term_id": 1,
            "classroom_id": 2,
            "regenerate": false
        }
        """
        term_id = request.data.get('term_id')
        classroom_id = request.data.get('classroom_id')
        regenerate = request.data.get('regenerate', False)

        if not term_id or not classroom_id:
            return Response(
                {'error': 'term_id and classroom_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            term = Term.objects.get(id=term_id)
            classroom = ClassRoom.objects.get(id=classroom_id)

            # Generate bulk report cards
            summary = ReportCardGenerator.generate_bulk_report_cards(
                term=term,
                classroom=classroom,
                generated_by=request.user,
                regenerate=regenerate
            )

            return Response({
                'message': 'Bulk report card generation completed',
                'summary': summary,
                'term': term.name,
                'classroom': str(classroom)
            }, status=status.HTTP_201_CREATED)

        except Term.DoesNotExist:
            return Response(
                {'error': 'Term not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except ClassRoom.DoesNotExist:
            return Response(
                {'error': 'Classroom not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': f'Failed to generate report cards: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def by_student(self, request):
        """
        Get all report cards for a specific student.

        GET /api/examination/report-cards/by_student/?student_id=5
        """
        student_id = request.query_params.get('student_id')
        if not student_id:
            return Response(
                {'error': 'student_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        queryset = self.get_queryset().filter(
            term_result__student_id=student_id
        ).order_by('-term_result__academic_year__start_date', '-term_result__term__start_date')

        report_cards = []
        for rc in queryset:
            report_cards.append({
                'id': rc.id,
                'student': rc.term_result.student.full_name,
                'term': rc.term_result.term.name,
                'academic_year': rc.term_result.academic_year.name,
                'grade': rc.term_result.grade,
                'gpa': rc.term_result.gpa,
                'position': f"{rc.term_result.position_in_class}/{rc.term_result.total_students}",
                'generated_date': rc.generated_date,
                'download_count': rc.download_count,
                'download_url': f'/api/examination/report-cards/{rc.id}/download/'
            })

        return Response(report_cards)

    @action(detail=False, methods=['get'])
    def by_classroom(self, request):
        """
        Get all report cards for a specific classroom and term.

        GET /api/examination/report-cards/by_classroom/?classroom_id=2&term_id=1
        """
        classroom_id = request.query_params.get('classroom_id')
        term_id = request.query_params.get('term_id')

        if not classroom_id or not term_id:
            return Response(
                {'error': 'classroom_id and term_id parameters are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        queryset = self.get_queryset().filter(
            term_result__classroom_id=classroom_id,
            term_result__term_id=term_id
        ).order_by('term_result__position_in_class')

        report_cards = []
        for rc in queryset:
            report_cards.append({
                'id': rc.id,
                'student': rc.term_result.student.full_name,
                'admission_number': rc.term_result.student.admission_number,
                'grade': rc.term_result.grade,
                'gpa': rc.term_result.gpa,
                'position': rc.term_result.position_in_class,
                'generated_date': rc.generated_date,
                'download_count': rc.download_count,
                'has_pdf': bool(rc.pdf_file),
                'download_url': f'/api/examination/report-cards/{rc.id}/download/' if rc.pdf_file else None
            })

        return Response(report_cards)
