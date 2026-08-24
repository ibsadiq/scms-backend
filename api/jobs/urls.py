from django.urls import path

from .views import BackgroundJobDetailView


app_name = "background_jobs"

urlpatterns = [
    path("<uuid:public_id>/", BackgroundJobDetailView.as_view(), name="detail"),
]
