from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from django.http import JsonResponse
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from api.celery_views import TaskStatusView, CeleryHealthView



def custom_404_handler(request, exception):
    return JsonResponse(
        {
            "error": "Page Not Found",
            "detail": f"The requested URL {request.path} was not found on this server.",
        },
        status=404,
    )


def custom_500_handler(request):
    return JsonResponse(
        {
            "error": "Server Error",
            "detail": "An unexpected error occurred on the server. Please try again later.",
        },
        status=500,
    )


def custom_403_handler(request, exception):
    return JsonResponse(
        {
            "error": "Permission Denied",
            "detail": "You do not have permission to perform this action.",
        },
        status=403,
    )


def custom_400_handler(request, exception):
    return JsonResponse(
        {
            "error": "Bad Request",
            "detail": "The request could not be understood or was missing required parameters.",
        },
        status=400,
    )


urlpatterns = [
    path("django-admin/", admin.site.urls),
    # path("", TemplateView.as_view(template_name="index.html")),
    path("", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),


    path("api/", include("core.urls")),
    path("api/academic/", include("api.academic.urls")),
    path("api/administration/", include("api.administration.urls")),
    path("api/attendance/", include("api.attendance.urls")),
    path("api/assignments/", include("api.assignments.urls")),
    path("api/blog/", include("api.blog.urls")),
    path("api/examination/", include("api.examination.urls")),
    path("api/finance/", include("api.finance.urls")),
    # path('api/journals/', include('api.journals.urls')),
    path("api/notifications/", include("api.notifications.urls")),
    # path("api/notes/", include("api.notes.urls")),
    path("api/users/", include("api.users.urls")),
    path("api/timetable/", include("api.schedule.urls")),
    path("api/sis/", include("api.sis.urls")),
    path("api/tenants/", include("tenants.urls")),

    # Admission management
    path("api/admissions/", include("api.admissions_admin.urls")),

    # Public admission portal (no authentication required)
    path("api/public/admissions/", include("api.admissions_public.urls")),

    # Reports
    path("api/reports/", include("api.reports.urls")),

    # Celery task monitoring
    path("api/tasks/<str:task_id>/", TaskStatusView.as_view(), name="task-status"),
    path("api/celery/health/", CeleryHealthView.as_view(), name="celery-health"),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

handler404 = custom_404_handler
handler500 = custom_500_handler
handler403 = custom_403_handler
handler400 = custom_400_handler
