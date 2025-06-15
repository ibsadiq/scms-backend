import openpyxl
from django.http import HttpResponse
from django.utils.dateparse import parse_date
from rest_framework import generics, viewsets, status, permissions
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import AcademicYear, Term, Article, CarouselImage, SchoolEvent
from .serializers import (
    AcademicYearSerializer,
    TermSerializer,
    ArticleSerializer,
    CarouselImageSerializer,
    SchoolEventSerializer
)
from .permissions import IsAdminOrReadOnly


# Article Views
class ArticleListCreateView(generics.ListCreateAPIView):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer
    permission_classes = [IsAuthenticated]


class ArticleDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer
    permission_classes = [IsAuthenticated]


# CarouselImage Views
class CarouselImageListCreateView(generics.ListCreateAPIView):
    queryset = CarouselImage.objects.all()
    serializer_class = CarouselImageSerializer
    permission_classes = [IsAuthenticated]


class CarouselImageDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = CarouselImage.objects.all()
    serializer_class = CarouselImageSerializer
    permission_classes = [IsAuthenticated]


# AcademicYear Views
class AcademicYearListCreateView(generics.ListCreateAPIView):
    queryset = AcademicYear.objects.all()
    serializer_class = AcademicYearSerializer
    permission_classes = [IsAuthenticated]


class AcademicYearDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = AcademicYear.objects.all()
    serializer_class = AcademicYearSerializer
    permission_classes = [IsAuthenticated]


# Term Views
class TermListCreateView(generics.ListCreateAPIView):
    queryset = Term.objects.all()
    serializer_class = TermSerializer
    permission_classes = [IsAuthenticated]


class TermDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Term.objects.all()
    serializer_class = TermSerializer
    permission_classes = [IsAuthenticated]


class SchoolEventViewSet(viewsets.ModelViewSet):
    queryset = SchoolEvent.objects.select_related('term', 'term__academic_year').all()
    serializer_class = SchoolEventSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        queryset = self.queryset
        term_id = self.request.query_params.get('term')
        year_name = self.request.query_params.get('academic_year')
        start_date = parse_date(self.request.query_params.get('start_date') or '')
        end_date = parse_date(self.request.query_params.get('end_date') or '')

        if term_id:
            queryset = queryset.filter(term__id=term_id)
        if year_name:
            queryset = queryset.filter(term__academic_year__name=year_name)
        if start_date:
            queryset = queryset.filter(start_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(end_date__lte=end_date)

        return queryset


class SchoolEventBulkUploadView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        excel_file = request.FILES.get('file')
        if not excel_file:
            return Response({"error": "No file uploaded"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            workbook = openpyxl.load_workbook(excel_file)
            sheet = workbook.active
            rows = list(sheet.iter_rows(min_row=2, values_only=True))  # Skip header row

            for row in rows:
                name, event_type, term_id, start_date, end_date, description = row
                if not all([name, event_type, term_id, start_date]):
                    continue  # Skip invalid rows

                SchoolEvent.objects.create(
                    name=name,
                    event_type=event_type,
                    term=Term.objects.get(pk=term_id),
                    start_date=start_date,
                    end_date=end_date,
                    description=description or ""
                )

            return Response({"detail": f"{len(rows)} events uploaded successfully."}, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class SchoolEventTemplateDownloadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "School Events Template"

        # Headers
        headers = ['name', 'event_type', 'term_id', 'start_date', 'end_date', 'description']
        ws.append(headers)

        # Example row
        ws.append([
            'Midterm Exams', 'exam', 1, '2025-07-10', '2025-07-14', 'Midterm assessment'
        ])

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename=school_events_template.xlsx'
        wb.save(response)
        return response
