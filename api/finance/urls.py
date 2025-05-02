from django.urls import path
from finance.views import (
    ReceiptsListView,
    ReceiptDetailView,
    StudentReceiptsView,
    PaymentListView,
    PaymentDetailView,
    UpdateStudentDebtView,
    PaymentAllocationListView,
    PaymentAllocationDetailView,
    ReceiptAllocationListView,
    ReceiptAllocationDetailView,
)


urlpatterns = [
    path("receipts/", ReceiptsListView.as_view(), name="receipt-list"),
    path("receipts/<int:pk>/", ReceiptDetailView.as_view(), name="receipt-detail"),
    path(
        "receipts/student/<int:student_id>/",
        StudentReceiptsView.as_view(),
        name="student-receipts",
    ),
    path("payments/", PaymentListView.as_view(), name="payment-list"),
    path("payments/<int:pk>/", PaymentDetailView.as_view(), name="payment-detail"),
    path(
        "payment-allocations/",
        PaymentAllocationListView.as_view(),
        name="payment-allocation-list",
    ),
    path(
        "payment-allocations/<int:pk>/",
        PaymentAllocationDetailView.as_view(),
        name="payment-allocation-detail",
    ),
    path(
        "receipt-allocations/",
        ReceiptAllocationListView.as_view(),
        name="receipt-allocation-list",
    ),
    path(
        "receipt-allocations/<int:pk>/",
        ReceiptAllocationDetailView.as_view(),
        name="receipt-allocation-detail",
    ),
    path(
        "update-student-debt/",
        UpdateStudentDebtView.as_view(),
        name="update-student-debt",
    ),
]
