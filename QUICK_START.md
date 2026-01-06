# SSync - Quick Start Guide

## What's New

### ✅ Celery Async Tasks
- Bulk uploads (students, teachers, parents, classrooms)
- Result computation and report card generation
- Email sending
- Fee reminders

### ✅ Docker Support
- Complete containerized stack
- PostgreSQL, Redis, Celery workers, Flower monitoring
- Nuxt.js frontend integration support
- Production-ready with Nginx

### ✅ Automated Fee Reminders
- 7 days before due date (email)
- 3 days before due date (email + SMS)
- 1 day before due date (email + SMS)
- Weekly overdue notices
- Manual trigger options via API

---

## Starting the Application

### Option 1: Docker (Recommended)

**First time setup:**
```bash
# Copy environment template
cp .env.docker .env.docker.local

# Build containers
docker compose build

# Start all services (backend + dev tools)
docker compose --profile dev up -d

# Run migrations
docker compose exec backend python manage.py migrate

# Create superuser (optional - auto-created in dev mode)
docker compose exec backend python manage.py createsuperuser

# Setup fee reminders
docker compose exec backend python manage.py setup_fee_reminders
```

**Daily usage:**
```bash
# Start services
docker compose --profile dev up -d

# Stop services
docker compose down

# View logs
docker compose logs -f backend
```

**Access points:**
- Backend API: http://localhost:8000/api/
- API Docs: http://localhost:8000/
- Admin Panel: http://localhost:8000/admin/
- Celery Flower: http://localhost:5555/
- Mailpit (email testing): http://localhost:8025/

### Option 2: Local Development (without Docker)

**Backend:**
```bash
# Install dependencies
pip install -r requirements.txt

# Start Redis (required for Celery)
redis-server

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Start Django
python manage.py runserver

# In separate terminals:
celery -A school worker --loglevel=info
celery -A school beat --loglevel=info
```

**Frontend (Nuxt):**
```bash
cd ../ssync-frontend  # Your Nuxt project

# Configure API URL in .env
echo "NUXT_PUBLIC_API_URL=http://localhost:8000/api" > .env

# Start Nuxt
npm run dev
```

---

## Testing Fee Reminders

### Setup (First Time)
```bash
docker compose exec backend python manage.py setup_fee_reminders
```

### Create Test Fee with Due Date
```bash
curl -X POST http://localhost:8000/api/financial/fee-structures/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Term 1 Tuition",
    "fee_type": "Tuition",
    "amount": 150000,
    "academic_year": 1,
    "term": 1,
    "is_mandatory": true,
    "due_date": "2026-02-15"
  }'
```

### Manual Trigger (Testing)
```bash
# Send all reminders now
docker compose exec backend python manage.py send_fee_reminders_now

# Or via API
curl -X POST http://localhost:8000/api/financial/fee-structures/send_all_reminders/ \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Common Docker Commands

```bash
# View running containers
docker compose ps

# View logs
docker compose logs -f backend
docker compose logs -f celery_worker

# Restart specific service
docker compose restart backend
docker compose restart celery_worker

# Execute Django commands
docker compose exec backend python manage.py shell
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser

# Database shell
docker compose exec postgres psql -U ssync_user -d ssync_db

# Scale Celery workers
docker compose up -d --scale celery_worker=4

# Clean rebuild
docker compose build --no-cache
docker compose down -v  # Warning: removes volumes
```

---

## Monitoring

### Celery Tasks (Flower)
http://localhost:5555
- View active workers
- Monitor task queue
- Check task history
- Inspect failures

### Email Testing (Mailpit - Dev only)
http://localhost:8025
- View all emails sent
- Test email templates
- No actual emails sent

### Check Celery Health
```bash
curl http://localhost:8000/api/celery/health/

# Or
docker compose exec backend celery -A school inspect active
```

### Check Task Status
```bash
curl http://localhost:8000/api/tasks/{task_id}/
```

---

## Project Structure

```
django-scms/
├── academic/           # Students, classrooms, class levels
│   └── tasks.py       # Async bulk uploads
├── api/               # API configurations
│   ├── finance/       # Fee structure endpoints
│   └── celery_views.py # Task monitoring
├── examination/       # Exams, results, report cards
│   └── tasks.py      # Async result computation
├── finance/          # Fee management
│   ├── tasks.py      # Fee reminders
│   └── management/commands/
├── users/            # Teachers, parents, auth
│   └── tasks.py     # User bulk uploads
├── school/          # Main settings
│   ├── celery.py   # Celery config
│   └── settings.py
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## API Endpoints

### Fee Management
```
GET    /api/financial/fee-structures/
POST   /api/financial/fee-structures/
GET    /api/financial/fee-structures/{id}/
PUT    /api/financial/fee-structures/{id}/
DELETE /api/financial/fee-structures/{id}/

# New reminder endpoints
POST   /api/financial/fee-structures/{id}/send_reminder/
POST   /api/financial/fee-structures/send_all_reminders/
```

### Task Monitoring
```
GET /api/tasks/{task_id}/           # Check task status
GET /api/celery/health/             # Check Celery workers
```

### Students & Classrooms
```
GET    /api/academic/students/
POST   /api/academic/students/bulk-upload/    # Async
GET    /api/academic/classrooms/
POST   /api/academic/classrooms/bulk-create/  # Async
```

### Examination
```
POST /api/examination/results/compute/        # Async result computation
POST /api/examination/report-cards/generate/  # Async report generation
```

---

## Documentation Files

- **[DOCKER_GUIDE.md](DOCKER_GUIDE.md)** - Complete Docker deployment guide
- **[NUXT_INTEGRATION.md](NUXT_INTEGRATION.md)** - Nuxt.js frontend integration
- **[CELERY_SETUP_GUIDE.md](CELERY_SETUP_GUIDE.md)** - Celery configuration
- **[FEE_REMINDERS_GUIDE.md](FEE_REMINDERS_GUIDE.md)** - Fee reminder system
- **[ANNOUNCEMENT_MESSAGING_SYSTEM.md](ANNOUNCEMENT_MESSAGING_SYSTEM.md)** - Notifications

---

## Troubleshooting

### Celery tasks not running
```bash
# Check workers
docker compose logs celery_worker

# Restart Celery
docker compose restart celery_worker celery_beat
```

### Database connection errors
```bash
# Check PostgreSQL
docker compose ps postgres
docker compose logs postgres
```

### CORS errors (Nuxt → Django)
Already configured in `settings.py`:
```python
CORS_ALLOW_ALL_ORIGINS = True  # Development
```

### Fee reminders not sending
```bash
# Check periodic task is enabled
docker compose exec backend python manage.py shell
>>> from django_celery_beat.models import PeriodicTask
>>> PeriodicTask.objects.filter(name='Send Fee Payment Reminders').first().enabled
True

# Manual test
docker compose exec backend python manage.py send_fee_reminders_now
```

---

## Next Steps

1. ✅ Start Docker services
2. ✅ Run migrations
3. ✅ Setup fee reminders
4. 🔜 Configure Nuxt frontend (see NUXT_INTEGRATION.md)
5. 🔜 Create fee structures with due dates
6. 🔜 Test reminder system
7. 🔜 Configure production email/SMS settings
8. 🔜 Deploy to production (see DOCKER_GUIDE.md)

---

## Support

For detailed guides, check the documentation files listed above.

**Common issues:**
- Django 5.2 compatibility: Ensure `django-celery-beat==2.8.0`
- Docker version warnings: Removed obsolete `version` from docker-compose.yml
- Celery tasks: Check Redis is running and workers are started

**Development workflow:**
1. Backend in Docker: `docker compose --profile dev up -d`
2. Frontend locally: `cd ../ssync-frontend && npm run dev`
3. Monitor tasks: http://localhost:5555
4. Test emails: http://localhost:8025

Your SSync school management system is ready! 🚀
