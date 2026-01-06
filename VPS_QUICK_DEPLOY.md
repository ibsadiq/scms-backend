# 🚀 Quick VPS Production Deployment

**Quick reference guide for deploying SSync to your VPS**

---

## Pre-Deployment Checklist

Before running any commands:

- [ ] VPS has Docker and Docker Compose installed
- [ ] Domain DNS A record points to VPS IP
- [ ] Port 80 and 443 are open on VPS firewall
- [ ] You have SSH access to VPS
- [ ] Project cloned at: `/path/to/django-scms` (update this path)
- [ ] Frontend cloned at: `/path/to/scms` (update this path)

---

## Step 1: Configure Production Environment (5 mins)

SSH into your VPS and navigate to project:

```bash
cd /path/to/django-scms
```

Create production environment file:

```bash
cp .env.docker .env.production
nano .env.production
```

**Critical settings to update:**

```bash
# SECURITY - MUST CHANGE THESE!
DEBUG=False
SECRET_KEY=$(openssl rand -base64 64)  # Generate this first
DB_PASSWORD=$(openssl rand -base64 32)  # Generate this first
REDIS_PASSWORD=$(openssl rand -base64 32)  # Generate this first

# DOMAIN SETTINGS
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com,api.yourdomain.com
CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
CORS_ALLOWED_ORIGINS=https://yourdomain.com
BASE_DOMAIN=yourdomain.com
FRONTEND_URL=https://yourdomain.com
BASE_URL=https://api.yourdomain.com

# DATABASE
DB_NAME=ssync_production
DB_USER=ssync_user
DB_PASSWORD=<use-generated-password-from-above>
DB_HOST=postgres
DB_PORT=5432

# REDIS & CELERY
CELERY_BROKER_URL=redis://:redis_password@redis:6379/0
REDIS_PASSWORD=<use-generated-password-from-above>

# EMAIL (Gmail example)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=<your-gmail-app-password>
DEFAULT_FROM_EMAIL=noreply@yourdomain.com

# SECURITY HEADERS
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000

# BUILD TARGETS
BUILD_TARGET=production
FRONTEND_BUILD_TARGET=production
NODE_ENV=production
```

**Generate secrets:**
```bash
# Generate SECRET_KEY
openssl rand -base64 64

# Generate DB_PASSWORD
openssl rand -base64 32

# Generate REDIS_PASSWORD
openssl rand -base64 32
```

Copy the production env file to `.env` (Django reads this):
```bash
cp .env.production .env
```

---

## Step 2: Update docker-compose.yml for Production (2 mins)

Add certbot service for SSL certificates. Edit `docker-compose.yml` and add:

```yaml
  # Add this service to docker-compose.yml
  certbot:
    image: certbot/certbot
    container_name: ssync-certbot
    volumes:
      - ./nginx/certbot/conf:/etc/letsencrypt
      - ./nginx/certbot/www:/var/www/certbot
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done;'"
    networks:
      - ssync-network
    profiles:
      - production
```

Update nginx service volumes:

```yaml
  nginx:
    image: nginx:alpine
    container_name: ssync-nginx
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - ./nginx/certbot/conf:/etc/letsencrypt:ro  # Add this
      - ./nginx/certbot/www:/var/www/certbot:ro   # Add this
      - static_volume:/app/staticfiles:ro
      - media_volume:/app/media:ro
    # ... rest of config
```

Update postgres service to use production password:

```yaml
  postgres:
    # ... existing config
    environment:
      POSTGRES_DB: ssync_production
      POSTGRES_USER: ssync_user
      POSTGRES_PASSWORD: ${DB_PASSWORD}  # Will read from .env
```

Update redis to use password:

```yaml
  redis:
    # ... existing config
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
```

---

## Step 3: Configure Nginx for Production (5 mins)

Create production nginx config:

```bash
mkdir -p nginx/conf.d
nano nginx/conf.d/production.conf
```

**Initial HTTP-only config (for getting SSL certificate):**

```nginx
# Initial configuration - HTTP only for certificate verification
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    # Let's Encrypt verification
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # Temporary - allow all traffic for testing
    location / {
        proxy_pass http://frontend:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /admin/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

**Replace `yourdomain.com` with your actual domain!**

---

## Step 4: Start Services (Without SSL First) (5 mins)

```bash
# Create certificate directories
mkdir -p nginx/certbot/conf nginx/certbot/www

# Build images
docker compose build --no-cache

# Start services (production profile)
docker compose --profile production up -d

# Check status
docker compose ps

# View logs
docker compose logs -f backend
```

**Verify HTTP access works:**
- Visit: `http://yourdomain.com` (should show frontend)
- Visit: `http://yourdomain.com/admin/` (should show Django admin)

---

## Step 5: Get SSL Certificate (5 mins)

```bash
# Stop nginx temporarily
docker compose stop nginx

# Get certificate
docker compose run --rm certbot certonly \
  --standalone \
  --preferred-challenges http \
  --email your-email@example.com \
  --agree-tos \
  --no-eff-email \
  -d yourdomain.com \
  -d www.yourdomain.com

# Start nginx again
docker compose start nginx
```

**Verify certificate files:**
```bash
ls -la nginx/certbot/conf/live/yourdomain.com/
# Should see: fullchain.pem, privkey.pem
```

---

## Step 6: Enable HTTPS in Nginx (5 mins)

Update `nginx/conf.d/production.conf`:

```nginx
# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS Server
server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    client_max_body_size 100M;

    # Security Headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

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

    # Frontend
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

Reload nginx:
```bash
docker compose restart nginx
```

---

## Step 7: Run Database Setup (5 mins)

```bash
# Run migrations
docker compose exec backend python manage.py migrate

# Create superuser
docker compose exec backend python manage.py createsuperuser

# Collect static files
docker compose exec backend python manage.py collectstatic --noinput

# Setup fee reminders
docker compose exec backend python manage.py setup_fee_reminders
```

---

## Step 8: Configure Firewall (2 mins)

```bash
# Allow SSH (IMPORTANT - do this first!)
sudo ufw allow 22/tcp

# Allow HTTP and HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Enable firewall
sudo ufw enable

# Check status
sudo ufw status
```

---

## Step 9: Verify Deployment (5 mins)

Test all endpoints:

✅ **Frontend:** https://yourdomain.com
✅ **API:** https://yourdomain.com/api/
✅ **Admin:** https://yourdomain.com/admin/
✅ **SSL:** Check certificate in browser (should show valid)

Test email:
```bash
docker compose exec backend python manage.py shell
```
```python
from django.core.mail import send_mail
send_mail(
    'Test Email',
    'If you receive this, email is working!',
    'noreply@yourdomain.com',
    ['your-email@example.com'],
)
# Should return 1 if successful
```

Check Celery is running:
```bash
docker compose logs -f celery_worker
# Should see "celery@... ready"
```

Visit Flower (Celery monitoring):
```
http://your-vps-ip:5555
```

---

## Step 10: Setup Automated Backups (5 mins)

Create backup script:

```bash
sudo nano /opt/ssync-backup.sh
```

```bash
#!/bin/bash
BACKUP_DIR="/backups/ssync"
DATE=$(date +%Y%m%d_%H%M%S)
PROJECT_DIR="/path/to/django-scms"  # Update this!

mkdir -p $BACKUP_DIR

cd $PROJECT_DIR

# Backup database
docker compose exec -T postgres pg_dump -U ssync_user ssync_production > $BACKUP_DIR/db_$DATE.sql

# Backup media files
tar -czf $BACKUP_DIR/media_$DATE.tar.gz ./media/

# Keep only last 7 days
find $BACKUP_DIR -name "*.sql" -mtime +7 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete

echo "Backup completed: $DATE"
```

Make executable and schedule:
```bash
sudo chmod +x /opt/ssync-backup.sh

# Test it
sudo /opt/ssync-backup.sh

# Schedule daily at 2 AM
crontab -e
# Add: 0 2 * * * /opt/ssync-backup.sh
```

---

## Common Production Commands

```bash
# View logs
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f celery_worker

# Restart specific service
docker compose restart backend
docker compose restart nginx

# Update application
git pull origin main
docker compose build
docker compose up -d
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py collectstatic --noinput

# Database backup
docker compose exec postgres pg_dump -U ssync_user ssync_production > backup_$(date +%Y%m%d).sql

# Database restore
docker compose exec -T postgres psql -U ssync_user ssync_production < backup_file.sql

# Scale Celery workers
docker compose up -d --scale celery_worker=4

# Check resource usage
docker stats

# Clean up unused resources
docker system prune -a
```

---

## Troubleshooting

### Services won't start
```bash
docker compose logs
docker compose ps
df -h  # Check disk space
free -h  # Check memory
```

### Database connection errors
```bash
docker compose exec postgres psql -U ssync_user -d ssync_production
docker compose exec backend env | grep DB_
```

### SSL certificate errors
```bash
# Renew manually
docker compose run --rm certbot renew

# Check expiry
docker compose run --rm certbot certificates
```

### Email not sending
```bash
docker compose exec backend python manage.py shell
```
```python
from django.core.mail import send_mail
send_mail('Test', 'Message', 'from@example.com', ['to@example.com'])
```

### Frontend not loading
```bash
docker compose logs -f frontend
# Check for build errors or API connection issues
```

---

## Security Post-Deployment

- [ ] Change all default passwords
- [ ] Verify DEBUG=False
- [ ] Test SSL certificate (A+ rating on ssllabs.com)
- [ ] Setup monitoring (Prometheus/Grafana)
- [ ] Configure log rotation
- [ ] Test backups and restore procedure
- [ ] Setup uptime monitoring (UptimeRobot, etc.)
- [ ] Review Django security checklist: `python manage.py check --deploy`

---

## Performance Optimization

```bash
# Add database indexes (after deployment)
docker compose exec backend python manage.py shell
```
```python
from django.db import connection
cursor = connection.cursor()

# Add frequently queried indexes
cursor.execute("CREATE INDEX IF NOT EXISTS idx_student_admission ON academic_student(admission_date);")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_receipt_date ON finance_receipt(date);")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance_attendance(date);")
```

---

## Total Deployment Time: ~45 minutes

You're now running SSync in production! 🚀

For more details, see [PRODUCTION_DEPLOYMENT_GUIDE.md](PRODUCTION_DEPLOYMENT_GUIDE.md)
