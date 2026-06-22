from django.urls import path
from .views import StudentLookupView, TransferCompleteView

urlpatterns = [
    path('lookup/student/',      StudentLookupView.as_view(),    name='student-lookup'),
    path('transfers/complete/',  TransferCompleteView.as_view(), name='transfer-complete'),
]
