# 🚀 Quick VPS Deployment via IP Address

**Deploy SSync to VPS accessible via IP: 72.61.184.120**

This guide is for immediate deployment using IP address instead of domain name.

---

## Pre-Deployment Checklist

- [x] VPS IP: 72.61.184.120
- [ ] Docker and Docker Compose installed on VPS
- [ ] Port 80 and 8000 are open on VPS firewall
- [ ] SSH access to VPS
- [ ] Project cloned on VPS

---

## Step 1: Configure Environment for IP Access (3 mins)

SSH into your VPS:

```bash
ssh user@72.61.184.120
```

Navigate to project:

```bash
cd /home/abu/Projects/django-scms  # Or your actual path
```

Create/update `.env` file:

```bash
nano .env
```

**Use this configuration:**

```bash
# ==============================================================================
# DJANGO CORE SETTINGS
# ==============================================================================
DEBUG=False  # Set to False for production
SECRET_KEY=django-insecure-change-this-in-production-$(openssl rand -base64 32)
ALLOWED_HOSTS=72.61.184.120,localhost,127.0.0.1,backend

# Application Settings
APP_NAME=SSync
SCHOOL_NAME=SureStart Schools
BASE_DOMAIN=72.61.184.120
FRONTEND_URL=http://72.61.184.120:3000
BASE_URL=http://72.61.184.120:8000

# ==============================================================================
# CORS & CSRF SETTINGS
# ==============================================================================
CORS_ALLOWED_ORIGINS=http://72.61.184.120:3000,http://72.61.184.120
CSRF_TRUSTED_ORIGINS=http://72.61.184.120:3000,http://72.61.184.120:8000,http://72.61.184.120

# ==============================================================================
# DATABASE CONFIGURATION (PostgreSQL)
# ==============================================================================
DB_NAME=ssync_production
DB_USER=ssync_user
DB_PASSWORD=changeme_production_password_123
DB_HOST=postgres
DB_PORT=5432

# ==============================================================================
# CELERY & REDIS CONFIGURATION
# ==============================================================================
CELERY_BROKER_URL=redis://redis:6379/0

# ==============================================================================
# EMAIL CONFIGURATION
# ==============================================================================
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=ssync007@gmail.com
EMAIL_HOST_PASSWORD=ybwqihdvgyxtajrh
DEFAULT_FROM_EMAIL=noreply@ssync.app

# ==============================================================================
# DOCKER BUILD SETTINGS
# ==============================================================================
BUILD_TARGET=production
FRONTEND_BUILD_TARGET=production
NODE_ENV=production
```

**Generate a strong SECRET_KEY:**
```bash
openssl rand -base64 64
# Copy output and update SECRET_KEY in .env
```

Update `.env.docker` to match:
```bash
cp .env .env.docker
```

---

## Step 2: Update docker-compose.yml (2 mins)

The existing `docker-compose.yml` should work. Just verify the postgres service environment:

```bash
nano docker-compose.yml
```

Ensure postgres section has:

```yaml
  postgres:
    image: postgres:16-alpine
    container_name: ssync-postgres
    env_file:
      - .env.docker
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: ssync_production
      POSTGRES_USER: ssync_user
      POSTGRES_PASSWORD: changeme_production_password_123  # Match .env
    ports:
      - "5433:5432"
    networks:
      - ssync-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ssync_user"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
```

---

## Step 3: Configure Nginx for IP Access (3 mins)

Create simple nginx config for IP-based access:

```bash
mkdir -p nginx/conf.d
nano nginx/conf.d/ip-production.conf
```

**Add this configuration:**

```nginx
# HTTP Server for IP-based access
server {
    listen 80;
    server_name 72.61.184.120;

    client_max_body_size 100M;

    # API Backend
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }

    # Admin Panel
    location /admin/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Static files
    location /static/ {
        alias /app/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Media files
    location /media/ {
        alias /app/media/;
        expires 7d;
        add_header Cache-Control "public";
    }

    # Frontend (Nuxt)
    location / {
        proxy_pass http://frontend:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
```

Remove any existing nginx configs:
```bash
rm -f nginx/conf.d/production.conf nginx/conf.d/default.conf
```

---

## Step 4: Build and Start Services (5 mins)

```bash
# Clean up any existing containers
docker compose down -v

# Build all images
docker compose build --no-cache

# Start services
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f backend
```

**Expected output:**
```
✔ Container ssync-postgres   Running
✔ Container ssync-redis      Running
✔ Container ssync-backend    Running
✔ Container ssync-celery-worker  Running
✔ Container ssync-celery-beat    Running
✔ Container ssync-flower     Running
✔ Container ssync-frontend   Running
✔ Container ssync-nginx      Running
```

---

## Step 5: Run Database Setup (5 mins)

```bash
# Wait for backend to be healthy (check logs)
docker compose logs -f backend
# Press Ctrl+C when you see "Booting worker" or "Spawning worker"

# Run migrations
docker compose exec backend python manage.py migrate

# Create superuser
docker compose exec backend python manage.py createsuperuser
# Follow prompts to create admin account

# Collect static files
docker compose exec backend python manage.py collectstatic --noinput

# Setup fee reminders (Celery periodic tasks)
docker compose exec backend python manage.py setup_fee_reminders
```

---

## Step 6: Configure Firewall (2 mins)

```bash
# Allow SSH (CRITICAL - do this first!)
sudo ufw allow 22/tcp

# Allow HTTP
sudo ufw allow 80/tcp

# Allow backend direct access (optional)
sudo ufw allow 8000/tcp

# Allow frontend direct access (optional)
sudo ufw allow 3000/tcp

# Enable firewall
sudo ufw enable

# Check status
sudo ufw status
```

---

## Step 7: Verify Deployment (3 mins)

Test all endpoints from your browser or local machine:

### ✅ Via Nginx (Port 80 - Recommended):
- **Frontend:** http://72.61.184.120/
- **API:** http://72.61.184.120/api/
- **Admin:** http://72.61.184.120/admin/

### ✅ Direct Access (for testing):
- **Backend Direct:** http://72.61.184.120:8000/admin/
- **Frontend Direct:** http://72.61.184.120:3000/
- **Flower (Celery Monitor):** http://72.61.184.120:5555/

### Test from command line:

```bash
# Test backend API
curl http://72.61.184.120/api/

# Test admin page
curl http://72.61.184.120/admin/

# Test frontend
curl http://72.61.184.120/
```

---

## Step 8: Test Email (2 mins)

```bash
docker compose exec backend python manage.py shell
```

In the Django shell:
```python
from django.core.mail import send_mail

send_mail(
    'SSync Production Test',
    'If you receive this, email is working on 72.61.184.120!',
    'noreply@ssync.app',
    ['your-email@example.com'],
)
# Should return 1 if successful
```

Press `Ctrl+D` to exit shell.

---

## Step 9: Verify Celery Workers (1 min)

```bash
# Check Celery worker logs
docker compose logs -f celery_worker

# You should see:
# [tasks]
#   . finance.tasks.send_fee_reminders
#   . users.tasks.send_invitation_email
#   . academic.tasks.process_bulk_upload
#
# celery@... ready.
```

Visit Flower dashboard:
```
http://72.61.184.120:5555
```

---

## Step 10: Create Test Data (Optional, 5 mins)

```bash
docker compose exec backend python manage.py shell
```

```python
from tenants.models import School, SchoolSettings
from academic.models import AcademicYear, Term
from django.utils import timezone

# Create school settings
school = School.objects.first()
if school:
    SchoolSettings.objects.update_or_create(
        school=school,
        defaults={
            'school_name': 'SureStart Schools',
            'app_name': 'SSync',
        }
    )

# Create academic year
year = AcademicYear.objects.create(
    name='2025/2026',
    start_date='2025-01-01',
    end_date='2025-12-31',
    is_current=True
)

# Create first term
Term.objects.create(
    academic_year=year,
    name='First Term',
    start_date='2025-01-01',
    end_date='2025-04-30',
)

print("✅ Test data created!")
```

Press `Ctrl+D` to exit.

---

## Common Management Commands

```bash
# View logs
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f celery_worker
docker compose logs -f nginx

# Restart specific service
docker compose restart backend
docker compose restart frontend
docker compose restart nginx

# Stop all services
docker compose down

# Start all services
docker compose up -d

# Rebuild after code changes
git pull  # If using git
docker compose build backend frontend
docker compose up -d
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py collectstatic --noinput

# Database backup
docker compose exec postgres pg_dump -U ssync_user ssync_production > backup_$(date +%Y%m%d).sql

# Database restore
docker compose exec -T postgres psql -U ssync_user ssync_production < backup_file.sql

# Scale Celery workers (if needed)
docker compose up -d --scale celery_worker=4

# Check resource usage
docker stats

# View running containers
docker compose ps
```

---

## Troubleshooting

### Services won't start
```bash
# Check logs
docker compose logs

# Check all services
docker compose ps

# Check disk space
df -h

# Check memory
free -h

# Restart everything
docker compose down
docker compose up -d
```

### Can't access from browser
```bash
# Check if ports are listening
sudo netstat -tlnp | grep -E '80|8000|3000'

# Check firewall
sudo ufw status

# Check nginx logs
docker compose logs nginx

# Test from VPS itself
curl http://localhost/api/
```

### Database connection errors
```bash
# Check postgres is running
docker compose ps postgres

# Check postgres logs
docker compose logs postgres

# Connect to postgres
docker compose exec postgres psql -U ssync_user -d ssync_production

# Check environment variables in backend
docker compose exec backend env | grep DB_
```

### Frontend shows 502 Bad Gateway
```bash
# Check frontend logs
docker compose logs frontend

# Frontend might still be building, wait 2-3 minutes
# Check if frontend container is running
docker compose ps frontend

# Restart frontend
docker compose restart frontend
```

### Email not sending
```bash
# Test SMTP connection
docker compose exec backend python manage.py shell
```
```python
from django.core.mail import send_mail
send_mail('Test', 'Message', 'ssync007@gmail.com', ['your-email@example.com'])
```

### Celery tasks not running
```bash
# Check Celery worker
docker compose logs celery_worker

# Check Celery beat
docker compose logs celery_beat

# Check Redis
docker compose exec redis redis-cli ping
# Should return: PONG

# Restart Celery services
docker compose restart celery_worker celery_beat
```

---

## Security Notes for IP-Based Deployment

⚠️ **Important:** IP-based deployment without HTTPS is suitable for:
- Development/testing on VPS
- Internal networks
- Temporary deployments

❌ **NOT recommended for production with real user data because:**
- No encryption (HTTP instead of HTTPS)
- Passwords and data sent in plain text
- Vulnerable to man-in-the-middle attacks

### To upgrade to HTTPS with domain later:

1. Point your domain to 72.61.184.120
2. Follow [VPS_QUICK_DEPLOY.md](VPS_QUICK_DEPLOY.md) for SSL setup
3. Get Let's Encrypt certificate
4. Update ALLOWED_HOSTS and CORS settings

---

## Access URLs Summary

Once deployed, access your application at:

| Service | URL | Description |
|---------|-----|-------------|
| **Frontend** | http://72.61.184.120/ | Main application UI |
| **API** | http://72.61.184.120/api/ | REST API endpoints |
| **Admin Panel** | http://72.61.184.120/admin/ | Django admin |
| **Flower** | http://72.61.184.120:5555/ | Celery monitoring |
| **Backend Direct** | http://72.61.184.120:8000/ | Direct backend access |
| **Frontend Direct** | http://72.61.184.120:3000/ | Direct frontend access |

**Default login:** Use the superuser credentials you created in Step 5.

---

## Next Steps After Deployment

1. **Create school data** via admin panel (http://72.61.184.120/admin/)
2. **Setup academic years and terms**
3. **Create classes and subjects**
4. **Invite teachers and staff**
5. **Add students**
6. **Test fee reminder system**
7. **Test email invitations**

---

## Quick Start Commands (All-in-One)

If you're setting up from scratch on the VPS:

```bash
# SSH to VPS
ssh user@72.61.184.120

# Navigate to project
cd /home/abu/Projects/django-scms

# Create .env file (paste the config from Step 1)
nano .env

# Generate secret key
openssl rand -base64 64
# Update .env with the generated key

# Copy to .env.docker
cp .env .env.docker

# Build and start
docker compose down -v
docker compose build --no-cache
docker compose up -d

# Wait 30 seconds for services to start
sleep 30

# Run migrations and setup
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser
docker compose exec backend python manage.py collectstatic --noinput
docker compose exec backend python manage.py setup_fee_reminders

# Configure firewall
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 8000/tcp
sudo ufw allow 3000/tcp
sudo ufw --force enable

# Done! Access at http://72.61.184.120/
```

---

**Total Deployment Time: ~20-25 minutes**

Your SSync application is now running on http://72.61.184.120/ 🚀
