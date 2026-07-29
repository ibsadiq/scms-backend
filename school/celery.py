"""
Celery configuration for Django SCMS.

This module sets up Celery for asynchronous task processing.
It handles background jobs like:
- Bulk uploads (students, teachers, parents, classrooms)
- Report card generation
- Email sending
- Result computation for large datasets
"""
import os
from celery import Celery
from django.conf import settings
from celery.schedules import crontab


# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')

app = Celery('school')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for testing Celery setup."""
    print(f'Request: {self.request!r}')

CELERY_BEAT_SCHEDULE = {
    'sync-all-tenant-stats': {
        'task': 'tenants.tasks.sync_all_tenant_stats',
        'schedule': crontab(minute='*/30'),  # every 30 minutes
    },
    'send-fee-reminders': {
        'task': 'finance.send_fee_reminders',
        'schedule': crontab(hour=8, minute=0),  # run daily at 8:00 AM
    },
}