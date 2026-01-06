"""
API views for Celery task monitoring and status checking.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from celery.result import AsyncResult
from school.celery import app as celery_app


class TaskStatusView(APIView):
    """
    Check the status of a Celery task.

    GET /api/tasks/<task_id>/

    Returns:
        - state: Task state (PENDING, STARTED, SUCCESS, FAILURE, etc.)
        - result: Task result if completed
        - progress: Progress information if available
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id):
        """Get task status by task ID."""
        try:
            task = AsyncResult(task_id, app=celery_app)

            response_data = {
                'task_id': task_id,
                'state': task.state,
                'ready': task.ready(),
                'successful': task.successful() if task.ready() else None,
            }

            if task.state == 'PENDING':
                response_data['status'] = 'Task is waiting to be executed'

            elif task.state == 'STARTED':
                response_data['status'] = 'Task has been started'

            elif task.state == 'PROGRESS':
                # Get progress information
                response_data['progress'] = task.info

            elif task.state == 'SUCCESS':
                response_data['result'] = task.result
                response_data['status'] = 'Task completed successfully'

            elif task.state == 'FAILURE':
                response_data['error'] = str(task.info)
                response_data['status'] = 'Task failed'

            else:
                response_data['status'] = task.state

            return Response(response_data)

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CeleryHealthView(APIView):
    """
    Check if Celery workers are running.

    GET /api/celery/health/
    """
    permission_classes = [IsAuthenticated]

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

        except Exception as e:
            return Response(
                {
                    'status': 'error',
                    'message': str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
