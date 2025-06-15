from django.utils.dateparse import parse_date
from rest_framework import generics, viewsets
from rest_framework.permissions import IsAuthenticated
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
