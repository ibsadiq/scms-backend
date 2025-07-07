from django.http import Http404
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import (
    DjangoFilterBackend,
    FilterSet,
    DateFilter,
    CharFilter,
)
from rest_framework import generics
from rest_framework.exceptions import NotFound
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from academic.models import Student
from administration.models import Term
from django.utils.timezone import now
from .models import (
    Receipt,
    Payment,
    ReceiptAllocation,
    PaymentAllocation,
    DebtRecord,
    PaymentRecord,
)
from .serializers import (
    ReceiptSerializer,
    PaymentSerializer,
    ReceiptAllocationSerializer,
    PaymentAllocationSerializer,
    DebtRecordSerializer,
    PaymentRecordSerializer,
    StudentDebtOverviewSerializer,
)


class PaymentAllocationListView(APIView):
    """
    Handles GET and POST requests for the list of insurances.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Retrieve a list of all insurances.
        """
        insurances = PaymentAllocation.objects.all()
        serializer = PaymentAllocationSerializer(insurances, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        """
        Create a new insurance record.
        """
        serializer = PaymentAllocationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PaymentAllocationDetailView(APIView):
    """
    Handles GET, PUT, PATCH, and DELETE requests for a single insurance.
    """

    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(PaymentAllocation, pk=pk)

    def get(self, request, pk):
        """
        Retrieve details of a specific insurance.
        """
        print(request.data)
        insurance = self.get_object(pk)
        serializer = PaymentAllocationSerializer(insurance)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        """
        Update an entire insurance record.
        """
        insurance = self.get_object(pk)
        serializer = PaymentAllocationSerializer(insurance, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        """
        Partially update an insurance record.
        """
        insurance = self.get_object(pk)
        serializer = PaymentAllocationSerializer(
            insurance, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        """
        Delete an insurance record.
        """
        insurance = self.get_object(pk)
        insurance.delete()
        return Response(
            {"detail": "PaymentAllocation record deleted successfully"},
            status=status.HTTP_204_NO_CONTENT,
        )


class ReceiptAllocationListView(APIView):
    """
    Handles GET and POST requests for the list of insurances.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Retrieve a list of all insurances.
        """
        insurances = ReceiptAllocation.objects.all()
        serializer = ReceiptAllocationSerializer(insurances, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        """
        Create a new insurance record.
        """
        serializer = ReceiptAllocationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ReceiptAllocationDetailView(APIView):
    """
    Handles GET, PUT, PATCH, and DELETE requests for a single insurance.
    """

    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(ReceiptAllocation, pk=pk)

    def get(self, request, pk):
        """
        Retrieve details of a specific insurance.
        """
        insurance = self.get_object(pk)
        serializer = ReceiptAllocationSerializer(insurance)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        """
        Update an entire insurance record.
        """
        insurance = self.get_object(pk)
        serializer = ReceiptAllocationSerializer(insurance, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        """
        Partially update an insurance record.
        """
        insurance = self.get_object(pk)
        serializer = ReceiptAllocationSerializer(
            insurance, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        """
        Delete an insurance record.
        """
        insurance = self.get_object(pk)
        insurance.delete()
        return Response(
            {"detail": "ReceiptAllocation record deleted successfully"},
            status=status.HTTP_204_NO_CONTENT,
        )


# Receipts filter
class ReceiptFilter(FilterSet):
    from_date = DateFilter(field_name="date", lookup_expr="gte")
    to_date = DateFilter(field_name="date", lookup_expr="lte")
    class_level = CharFilter(method="filter_by_class_level")

    class Meta:
        model = Receipt
        fields = ["status", "student", "date"]

    def filter_by_class_level(self, queryset, name, value):
        return queryset.filter(student__class_level__name__iexact=value)


# Receipts List & Create View using DRF's ListCreateAPIView
class ReceiptsListView(generics.ListCreateAPIView):
    queryset = Receipt.objects.all()
    serializer_class = ReceiptSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ReceiptFilter
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        receipt = serializer.save()
        response_serializer = self.get_serializer(receipt)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class StudentReceiptsView(generics.ListAPIView):
    serializer_class = ReceiptSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        student_id = self.kwargs.get("student_id")
        return Receipt.objects.filter(student_id=student_id)


# Receipt Detail View (Retrieve, Update, Delete)
class ReceiptDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Receipt.objects.all()
    serializer_class = ReceiptSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        try:
            return super().get_object()
        except Http404:
            raise NotFound(detail="Receipt not found.", code=404)


# Payment List & Create View using DRF's ListCreateAPIView
class PaymentListView(generics.ListCreateAPIView):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    filter_backends = [
        SearchFilter,
    ]
    filterset_fields = ["status", "date", "user"]
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        """
        Override the create method to handle custom validation or processing.
        """
        print(request.data)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Save the receipt and process student debt logic
        receipt = serializer.save()

        # Return response with detailed serialized data
        response_serializer = self.get_serializer(receipt)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


# Payment Detail View (Retrieve, Update, Delete)
class PaymentDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        try:
            return super().get_object()
        except Http404:
            raise NotFound(detail="Payment not found.", code=404)


class DebtRecordListView(generics.ListAPIView):
    queryset = DebtRecord.objects.all()
    serializer_class = DebtRecordSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["term", "student", "is_reversed"]


class DebtRecordDetailView(generics.RetrieveAPIView):
    queryset = DebtRecord.objects.all()
    serializer_class = DebtRecordSerializer
    permission_classes = [IsAuthenticated]


class PaymentRecordListView(generics.ListAPIView):
    queryset = PaymentRecord.objects.all()
    serializer_class = PaymentRecordSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["student", "debt_record", "processed_by"]
    search_fields = ["reference", "note"]


class PaymentRecordDetailView(generics.RetrieveAPIView):
    queryset = PaymentRecord.objects.all()
    serializer_class = PaymentRecordSerializer
    permission_classes = [IsAuthenticated]


class StudentDebtOverviewView(generics.RetrieveAPIView):
    queryset = Student.objects.all()
    serializer_class = StudentDebtOverviewSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        student_id = self.kwargs.get("student_id")
        try:
            return Student.objects.get(pk=student_id)
        except Student.DoesNotExist:
            raise NotFound(detail="Student not found.")


class UpdateStudentDebtView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        today = now().date()
        current_term = Term.objects.filter(
            start_date__lte=today, end_date__gte=today
        ).first()

        if not current_term:
            return Response(
                {"detail": "No active term found."}, status=status.HTTP_400_BAD_REQUEST
            )

        students = Student.objects.exclude(debt_records__term=current_term)

        for student in students:
            student.update_debt_for_term(current_term)

        return Response(
            {"detail": "Student debts updated successfully."}, status=status.HTTP_200_OK
        )


class UpdateAllUnrecordedDebtsView(APIView):
    """
    API view to update student debts for all past terms that haven't been updated.
    Ensures that no term is double-counted.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        today = now().date()

        # Get all terms up to today (including current and past)
        terms = Term.objects.filter(end_date__lte=today).order_by("start_date")
        updated_count = 0
        skipped = 0

        for term in terms:
            students = Student.objects.exclude(debt_records__term=term)

            for student in students:
                student.update_debt_for_term(term)
                updated_count += 1

        return Response(
            {
                "detail": "Student debts updated for all missing terms.",
                "updated_count": updated_count,
            },
            status=200,
        )


class UpdatePastDebtsView(APIView):
    """
    API view to update student debts for selected past terms.
    Skips already updated records.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        term_ids = request.data.get("term_ids", [])

        if not term_ids:
            return Response(
                {"detail": "Provide a list of term IDs to update."}, status=400
            )

        terms = Term.objects.filter(id__in=term_ids)
        if not terms.exists():
            return Response({"detail": "No valid terms found."}, status=404)

        updated = 0
        for term in terms:
            students = Student.objects.exclude(debt_records__term=term)
            for student in students:
                student.update_debt_for_term(term)
                updated += 1

        return Response(
            {
                "detail": f"Debts updated for selected terms.",
                "terms_updated": [term.name for term in terms],
                "students_updated": updated,
            },
            status=200,
        )


class ReverseStudentDebtView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        term_id = request.data.get("term_id")

        if not term_id:
            return Response(
                {"detail": "Term ID is required."}, status=status.HTTP_400_BAD_REQUEST
            )

        term = Term.objects.filter(id=term_id).first()
        if not term:
            return Response(
                {"detail": "Invalid term ID."}, status=status.HTTP_404_NOT_FOUND
            )

        students = Student.objects.filter(
            debt_records__term=term, debt_records__is_reversed=False
        )

        for student in students:
            student.reverse_debt_for_term(term)

        return Response(
            {"detail": f"Student debts for {term.name} reversed successfully."},
            status=status.HTTP_200_OK,
        )
