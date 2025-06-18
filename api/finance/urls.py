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
    DebtRecordListView,
    DebtRecordDetailView,
    ReverseStudentDebtView,
    PaymentRecordListView,
    PaymentRecordDetailView,
    StudentDebtOverviewView,
)


urlpatterns = [
    path("receipts/", ReceiptsListView.as_view(), name="receipt-list"),
    path("receipts/<int:pk>/", ReceiptDetailView.as_view(), name="receipt-detail"),
    path(
        "receipts/student/<int:student_id>/",
        StudentReceiptsView.as_view(),
        name="student-receipts",
    ),
    path("debts/", DebtRecordListView.as_view()),
    path("debts/<int:pk>/", DebtRecordDetailView.as_view()),
    path("debts/update/", UpdateStudentDebtView.as_view()),
    path("debts/reverse/", ReverseStudentDebtView.as_view()),
    path("payments/record/", PaymentRecordListView.as_view()),
    path("payments/record/<int:pk>/", PaymentRecordDetailView.as_view()),
    path("students/<int:student_id>/debt-overview/", StudentDebtOverviewView.as_view()),
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
]
