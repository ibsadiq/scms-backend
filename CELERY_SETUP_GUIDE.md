# Celery Setup Guide - SSync

This guide explains how to set up and use Celery for asynchronous task processing in SSync (School Management System).

## Overview

Celery has been integrated to handle long-running tasks asynchronously, improving user experience by preventing timeout issues on operations like:

- **Bulk Uploads**: Students, teachers, parents, classrooms
- **Result Computation**: Computing results for entire classrooms
- **Report Card Generation**: Generating PDFs for multiple students
- **Email Sending**: Asynchronous email notifications

## Architecture

```
┌──────────────┐
│   Django     │ ← Creates tasks
│ Application  │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│    Redis     │ ← Message broker (task queue)
│   (Broker)   │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│    Celery    │ ← Processes tasks
│   Workers    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  PostgreSQL  │ ← Stores task results
│  (Results)   │
└──────────────┘
```

## Prerequisites

### 1. Install Redis

Redis is used as the message broker for Celery.

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install redis-server
sudo systemctl start redis
sudo systemctl enable redis
```

**macOS:**
```bash
brew install redis
brew services start redis
```

**Docker:**
```bash
docker run -d -p 6379:6379 redis:latest
```

**Verify Redis is running:**
```bash
redis-cli ping
# Should respond: PONG
```

### 2. Install Python Dependencies

Dependencies are already in `requirements.txt`:
```bash
uv pip install -r requirements.txt
```

This installs:
- `celery==5.4.0` - Task queue
- `redis==5.2.0` - Redis client
- `django-celery-results==2.5.1` - Store results in Django DB
- `django-celery-beat==2.7.0` - Periodic task scheduler

### 3. Environment Configuration

Add to your `.env` file:
```bash
CELERY_BROKER_URL=redis://localhost:6379/0
```

For production, use a managed Redis service:
```bash
# Example: Redis Cloud
CELERY_BROKER_URL=redis://username:password@redis-host:port/0
```

## Running Celery

### Development Mode

You need to run **3 processes** in separate terminals:

**Terminal 1: Django Development Server**
```bash
uv run python manage.py runserver
```

**Terminal 2: Celery Worker**
```bash
uv run celery -A school worker --loglevel=info
```

**Terminal 3: Celery Beat (Optional - for scheduled tasks)**
```bash
uv run celery -A school beat --loglevel=info
```

### Production Mode

Use a process manager like Supervisor or systemd.

**Example Supervisor Configuration (`/etc/supervisor/conf.d/celery.conf`):**

```ini
[program:celery_worker]
command=/path/to/venv/bin/celery -A school worker --loglevel=info
directory=/path/to/django-scms
user=www-data
numprocs=1
stdout_logfile=/var/log/celery/worker.log
stderr_logfile=/var/log/celery/worker_err.log
autostart=true
autorestart=true
startsecs=10
stopwaitsecs=600
priority=998

[program:celery_beat]
command=/path/to/venv/bin/celery -A school beat --loglevel=info
directory=/path/to/django-scms
user=www-data
numprocs=1
stdout_logfile=/var/log/celery/beat.log
stderr_logfile=/var/log/celery/beat_err.log
autostart=true
autorestart=true
startsecs=10
priority=999
```

Then:
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start celery_worker
sudo supervisorctl start celery_beat
```

## Available Async Tasks

### Academic Tasks

**1. Bulk Upload Students**
```python
from academic.tasks import bulk_upload_students_task

# In your view
file_content = request.FILES['file'].read()
task = bulk_upload_students_task.delay(
    file_content=file_content,
    academic_year_id=academic_year.id,
    uploaded_by_id=request.user.id
)
task_id = task.id  # Return this to frontend
```

**2. Bulk Upload Classrooms**
```python
from academic.tasks import bulk_upload_classrooms_task

file_content = request.FILES['file'].read()
task = bulk_upload_classrooms_task.delay(file_content)
```

### Users Tasks

**1. Bulk Upload Teachers**
```python
from users.tasks import bulk_upload_teachers_task

file_content = request.FILES['file'].read()
task = bulk_upload_teachers_task.delay(file_content)
```

**2. Bulk Upload Parents**
```python
from users.tasks import bulk_upload_parents_task

file_content = request.FILES['file'].read()
task = bulk_upload_parents_task.delay(file_content)
```

**3. Send Email Async**
```python
from users.tasks import send_email_async

task = send_email_async.delay(
    subject="Welcome to SSync",
    message="Your account has been created.",
    recipient_list=["user@example.com"],
    from_email="noreply@yourdomain.com"
)
```

### Examination Tasks

**1. Compute Classroom Results**
```python
from examination.tasks import compute_classroom_results_task

task = compute_classroom_results_task.delay(
    term_id=term.id,
    classroom_id=classroom.id,
    computed_by_id=request.user.id
)
```

**2. Generate Classroom Report Cards**
```python
from examination.tasks import generate_classroom_report_cards_task

task = generate_classroom_report_cards_task.delay(
    term_id=term.id,
    classroom_id=classroom.id
)
```

**3. Publish Results**
```python
from examination.tasks import publish_results_task

task = publish_results_task.delay(
    term_id=term.id,
    classroom_id=classroom.id
)
```

## Monitoring Tasks

### API Endpoints

**1. Check Task Status**
```bash
GET /api/tasks/<task_id>/
```

Response:
```json
{
  "task_id": "abc-123-def-456",
  "state": "PROGRESS",
  "ready": false,
  "successful": null,
  "progress": {
    "current": 50,
    "total": 100,
    "status": "Processing row 50"
  }
}
```

**Task States:**
- `PENDING` - Task waiting to execute
- `STARTED` - Task has started
- `PROGRESS` - Task in progress (with progress info)
- `SUCCESS` - Task completed successfully
- `FAILURE` - Task failed

**2. Check Celery Health**
```bash
GET /api/celery/health/
```

Response:
```json
{
  "status": "healthy",
  "message": "1 worker(s) active",
  "workers": ["celery@hostname"],
  "stats": {...},
  "registered_tasks": [...]
}
```

### Frontend Integration Example

```javascript
// 1. Upload file and get task ID
const uploadFile = async (file) => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch('/api/academic/students/bulk-upload/', {
    method: 'POST',
    body: formData,
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });

  const { task_id } = await response.json();
  return task_id;
};

// 2. Poll task status
const checkTaskStatus = async (taskId) => {
  const response = await fetch(`/api/tasks/${taskId}/`, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });

  return await response.json();
};

// 3. Complete workflow
const handleBulkUpload = async (file) => {
  // Start task
  const taskId = await uploadFile(file);

  // Poll every 2 seconds
  const interval = setInterval(async () => {
    const status = await checkTaskStatus(taskId);

    if (status.state === 'PROGRESS') {
      // Update progress bar
      updateProgress(status.progress.current, status.progress.total);
    } else if (status.state === 'SUCCESS') {
      clearInterval(interval);
      showSuccess(status.result);
    } else if (status.state === 'FAILURE') {
      clearInterval(interval);
      showError(status.error);
    }
  }, 2000);
};
```

## Task Configuration

### Routing (Queue Organization)

Tasks are automatically routed to specific queues:

```python
CELERY_TASK_ROUTES = {
    'academic.tasks.*': {'queue': 'academic'},
    'users.tasks.*': {'queue': 'users'},
    'examination.tasks.*': {'queue': 'examination'},
    'finance.tasks.*': {'queue': 'finance'},
}
```

To run workers for specific queues:
```bash
# Academic queue only
celery -A school worker -Q academic --loglevel=info

# Multiple queues
celery -A school worker -Q academic,users --loglevel=info

# All queues (default)
celery -A school worker --loglevel=info
```

### Time Limits

Tasks have time limits to prevent hanging:
- **Hard limit**: 30 minutes
- **Soft limit**: 25 minutes

Configure in `settings.py`:
```python
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # 25 minutes
```

## Troubleshooting

### Redis Connection Error

**Error:** `celery.exceptions.OperationalError: Error 111 connecting to localhost:6379`

**Fix:**
```bash
# Check if Redis is running
redis-cli ping

# If not running, start it
sudo systemctl start redis
```

### Tasks Not Executing

**Check worker is running:**
```bash
# In project directory
celery -A school inspect active
```

**Check worker logs:**
```bash
celery -A school worker --loglevel=debug
```

### Task Results Not Appearing

**Check migrations applied:**
```bash
python manage.py migrate django_celery_results
```

**Check database tables:**
```bash
python manage.py dbshell
\dt django_celery_results_*
```

### Flower (Web-based Monitoring Tool)

Install Flower for a web UI:
```bash
uv pip install flower
```

Run:
```bash
celery -A school flower
```

Access at: http://localhost:5555

## Best Practices

1. **Always use `.delay()` or `.apply_async()`** to run tasks asynchronously
   ```python
   # Good
   task = my_task.delay(arg1, arg2)

   # Bad (runs synchronously)
   result = my_task(arg1, arg2)
   ```

2. **Return task ID to frontend** for status tracking
   ```python
   return Response({'task_id': task.id})
   ```

3. **Handle task failures gracefully** in your views
   ```python
   if task.state == 'FAILURE':
       return Response({'error': str(task.info)}, status=500)
   ```

4. **Use progress updates** for long tasks
   ```python
   self.update_state(
       state='PROGRESS',
       meta={'current': i, 'total': total}
   )
   ```

5. **Set appropriate time limits** based on task complexity

6. **Monitor task queue size** to prevent backlog

## Next Steps

1. ✅ Redis installed and running
2. ✅ Celery workers running
3. ✅ Tasks created for bulk operations
4. 🔜 Update existing bulk upload views to use Celery tasks
5. 🔜 Add progress tracking to frontend
6. 🔜 Set up monitoring with Flower or custom dashboard

## Additional Resources

- [Celery Documentation](https://docs.celeryq.dev/)
- [Django Celery Results](https://django-celery-results.readthedocs.io/)
- [Django Celery Beat](https://django-celery-beat.readthedocs.io/)
- [Redis Documentation](https://redis.io/docs/)
