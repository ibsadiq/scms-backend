from django.http import Http404
from django.shortcuts import get_object_or_404
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
from .models import Receipt, Payment, ReceiptAllocation, PaymentAllocation
from .serializers import (
    ReceiptSerializer,
    PaymentSerializer,
    ReceiptAllocationSerializer,
    PaymentAllocationSerializer,
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


# Receipts List & Create View using DRF's ListCreateAPIView
class ReceiptsListView(generics.ListCreateAPIView):
    queryset = Receipt.objects.all()
    serializer_class = ReceiptSerializer
    filter_backends = [
        SearchFilter,
    ]
    filterset_fields = ["status", "date", "student"]
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

    def perform_create(self, serializer):
        # Example: Assign the logged-in user as the payer
        serializer.save(paid_by=self.request.user)


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


class UpdateStudentDebtView(APIView):
    """
    API view to manually trigger student debt updates for the current term.
    """

    def post(self, request, *args, **kwargs):
        today = now().date()
        current_term = Term.objects.filter(
            start_date__lte=today, end_date__gte=today
        ).first()

        if not current_term:
            return Response(
                {"detail": "No active term found."}, status=status.HTTP_400_BAD_REQUEST
            )

        students = Student.objects.exclude(
            debt_records__term=current_term
        )  # Exclude students whose debts are already updated for this term

        for student in students:
            student.update_debt_for_term(current_term)

        return Response(
            {"detail": "Student debts updated successfully."}, status=status.HTTP_200_OK
        )


class ReverseStudentDebtView(APIView):
    """
    API view to manually reverse student debts for a specific term.
    """

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

        students = Student.objects.filter(debt_records__term=term)

        for student in students:
            student.reverse_debt_for_term(term)

        return Response(
            {"detail": f"Student debts for {term.name} reversed successfully."},
            status=status.HTTP_200_OK,
        )
