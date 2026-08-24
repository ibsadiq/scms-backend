"""
API views for Celery task monitoring and status checking.
"""
import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import BasePermission
from drf_spectacular.utils import extend_schema
from school.celery import app as celery_app


logger = logging.getLogger(__name__)


class IsPlatformOperator(BasePermission):
    """Infrastructure details are restricted to superusers on the public schema."""

    def has_permission(self, request, view):
        tenant = getattr(request, "tenant", None)
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
            and getattr(tenant, "schema_name", None) == "public"
        )


class CeleryHealthView(APIView):
    """
    Check if Celery workers are running.

    GET /api/celery/health/
    """
    permission_classes = [IsPlatformOperator]

    @extend_schema(exclude=True)
    def get(self, request):
        """Check Celery worker health."""
        try:
            # Inspect active workers
            inspect = celery_app.control.inspect()

            # Get active workers
            active_workers = inspect.active()
            registered_tasks = inspect.registered()
            stats = inspect.stats()

            if not active_workers:
                return Response(
                    {
                        'status': 'unhealthy',
                        'message': 'No active Celery workers found',
                        'workers': []
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )

            return Response({
                'status': 'healthy',
                'message': f'{len(active_workers)} worker(s) active',
                'workers': list(active_workers.keys()),
                'stats': stats,
                'registered_tasks': registered_tasks
            })

        except Exception:
            logger.exception("Celery health inspection failed")
            return Response(
                {
                    'status': 'error',
                    'message': 'Celery health inspection failed.'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
