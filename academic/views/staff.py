from django.db.models import Q
from django_filters.rest_framework import BooleanFilter, CharFilter, DjangoFilterBackend, FilterSet, NumberFilter
from rest_framework import generics, viewsets
from rest_framework.permissions import IsAuthenticated

from academic.models import Staff, Subject
from academic.permissions import IsAcademicAdminOrReadOnly, IsSchoolAdmin
from academic.serializers import StaffSerializer, SubjectSerializer


class StaffFilter(FilterSet):
    search = CharFilter(method="filter_search")
    role = CharFilter(field_name="role")
    department = NumberFilter(field_name="department_id")
    is_active = BooleanFilter(field_name="is_active")
    staff_id = CharFilter(field_name="staff_id", lookup_expr="icontains")

    class Meta:
        model = Staff
        fields = ["search", "role", "department", "is_active", "staff_id"]

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        val = value.strip()
        return queryset.filter(
            Q(staff_id__icontains=val)
            | Q(designation__icontains=val)
            | Q(user__first_name__icontains=val)
            | Q(user__last_name__icontains=val)
            | Q(user__email__icontains=val)
            | Q(department__name__icontains=val)
        ).distinct()


class StaffViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Canonical ReadOnly endpoint for Staff identity search and detail.
    Restricted to authenticated School Administrators.
    """
    queryset = Staff.objects.select_related("user", "department").all()
    serializer_class = StaffSerializer
    permission_classes = [IsAuthenticated, IsSchoolAdmin]
    filter_backends = [DjangoFilterBackend]
    filterset_class = StaffFilter


class SubjectListView(generics.ListCreateAPIView):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    permission_classes = [IsAcademicAdminOrReadOnly]


class SubjectDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    lookup_field = "id"
    permission_classes = [IsAcademicAdminOrReadOnly]

