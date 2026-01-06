# 🚀 SSync Production Deployment Guide

## Prerequisites on VPS

✅ Docker and Docker Compose installed
✅ Project cloned on VPS
✅ Domain name pointing to VPS IP
✅ SSL certificate (Let's Encrypt recommended)

---

## Step-by-Step Production Deployment

### Step 1: Prepare Production Environment File

On your VPS, create `.env.production`:

```bash
cd /path/to/django-scms
cp .env.docker .env.production
```

Edit `.env.production` with production values:

```bash
# ==============================================================================
# DJANGO CORE SETTINGS
# ==============================================================================
DEBUG=False
SECRET_KEY=<generate-strong-random-key>  # Use: openssl rand -base64 64
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com,api.yourdomain.com
CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
CORS_ALLOWED_ORIGINS=https://yourdomain.com

# Application Settings
APP_NAME=SSync
SCHOOL_NAME=Your School Name
BASE_DOMAIN=yourdomain.com
FRONTEND_URL=https://yourdomain.com
BASE_URL=https://api.yourdomain.com

# ==============================================================================
# DATABASE CONFIGURATION (PostgreSQL)
# ==============================================================================
DB_NAME=ssync_production
DB_USER=ssync_user
DB_PASSWORD=<strong-secure-password>  # Change this!
DB_HOST=postgres
DB_PORT=5432

# ==============================================================================
# CELERY & REDIS CONFIGURATION
# ==============================================================================
CELERY_BROKER_URL=redis://:redis_password@redis:6379/0
REDIS_PASSWORD=<redis-password>  # Generate strong password

# ==============================================================================
# EMAIL CONFIGURATION (Production)
# ==============================================================================
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=<your-app-password>
DEFAULT_FROM_EMAIL=noreply@yourdomain.com
SERVER_EMAIL=server@yourdomain.com

# ==============================================================================
# SMS CONFIGURATION (Optional)
# ==============================================================================
# TWILIO_ACCOUNT_SID=<your-sid>
# TWILIO_AUTH_TOKEN=<your-token>
# TWILIO_PHONE_NUMBER=<your-number>

# ==============================================================================
# SECURITY SETTINGS
# ==============================================================================
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000

# ==============================================================================
# DOCKER BUILD SETTINGS
# ==============================================================================
BUILD_TARGET=production
FRONTEND_BUILD_TARGET=production
NODE_ENV=production
```

### Step 2: Update docker-compose.yml for Production

The existing docker-compose.yml should work, but ensure:

```yaml
# Use .env.production file
env_file:
  - .env.production
```

### Step 3: Configure Nginx for SSL

Create `nginx/conf.d/production.conf`:

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

# Main HTTPS server
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

    # API Backend (Django)
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

    # Static files (Django)
    location /static/ {
        alias /app/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Media files
    location /media/ {
        alias /app/mediafiles/;
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

### Step 4: Get SSL Certificate (Let's Encrypt)

Add certbot service to docker-compose.yml:

```yaml
  certbot:
    image: certbot/certbot
    container_name: certbot
    volumes:
      - ./nginx/certbot/conf:/etc/letsencrypt
      - ./nginx/certbot/www:/var/www/certbot
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done;'"
```

Update nginx service volumes:

```yaml
  nginx:
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - ./nginx/certbot/conf:/etc/letsencrypt:ro
      - ./nginx/certbot/www:/var/www/certbot:ro
```

Get initial certificate:

```bash
# Create certificate directories
mkdir -p nginx/certbot/conf nginx/certbot/www

# Get certificate (before starting nginx with SSL)
docker compose run --rm certbot certonly --webroot \
  --webroot-path=/var/www/certbot \
  --email your-email@example.com \
  --agree-tos \
  --no-eff-email \
  -d yourdomain.com -d www.yourdomain.com
```

### Step 5: Build Production Images

```bash
cd /path/to/django-scms

# Copy .env.production to .env for the build
cp .env.production .env

# Build all services
docker compose build --no-cache

# Build frontend separately (if needed)
docker compose build frontend
```

### Step 6: Start Production Services

```bash
# Start all services in production mode
docker compose --profile production up -d

# Check status
docker compose ps

# View logs
docker compose logs -f
```

### Step 7: Run Database Migrations

```bash
# Run migrations
docker compose exec backend python manage.py migrate

# Create superuser
docker compose exec backend python manage.py createsuperuser

# Collect static files
docker compose exec backend python manage.py collectstatic --noinput
```

### Step 8: Setup Fee Reminders

```bash
# Setup automated fee reminders
docker compose exec backend python manage.py setup_fee_reminders
```

### Step 9: Configure Firewall

```bash
# Allow SSH
sudo ufw allow 22/tcp

# Allow HTTP and HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Enable firewall
sudo ufw enable

# Check status
sudo ufw status
```

### Step 10: Verify Deployment

Check these endpoints:
- ✅ https://yourdomain.com (Frontend)
- ✅ https://yourdomain.com/api/ (API)
- ✅ https://yourdomain.com/admin/ (Admin Panel)

Test email:
```bash
docker compose exec backend python manage.py shell
>>> from django.core.mail import send_mail
>>> send_mail('Test', 'Test message', 'noreply@yourdomain.com', ['test@example.com'])
```

---

## Post-Deployment Tasks

### 1. Setup Automatic Backups

Create backup script `/opt/ssync-backup.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/backups/ssync"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup database
docker compose exec -T postgres pg_dump -U ssync_user ssync_production > $BACKUP_DIR/db_$DATE.sql

# Backup media files
tar -czf $BACKUP_DIR/media_$DATE.tar.gz ./media/

# Keep only last 7 days
find $BACKUP_DIR -name "*.sql" -mtime +7 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete
```

Add to crontab:
```bash
crontab -e
# Add: 0 2 * * * /opt/ssync-backup.sh
```

### 2. Setup Monitoring

Add health check monitoring:

```bash
# Install monitoring tools
sudo apt install prometheus grafana

# Configure Prometheus to monitor:
# - Docker containers
# - Nginx
# - PostgreSQL
# - Redis
# - Celery workers
```

### 3. Configure Log Rotation

Create `/etc/logrotate.d/docker-ssync`:

```
/var/lib/docker/containers/*/*.log {
  rotate 7
  daily
  compress
  missingok
  delaycompress
  copytruncate
}
```

---

## Maintenance Commands

```bash
# View logs
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f celery_worker

# Restart services
docker compose restart backend
docker compose restart frontend

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

# Clean up
docker system prune -a
```

---

## Troubleshooting

### Issue: Services not starting
```bash
# Check logs
docker compose logs

# Check disk space
df -h

# Check memory
free -h
```

### Issue: Database connection errors
```bash
# Check postgres container
docker compose exec postgres psql -U ssync_user -d ssync_production

# Check environment variables
docker compose exec backend env | grep DB_
```

### Issue: SSL certificate errors
```bash
# Renew certificate manually
docker compose run --rm certbot renew

# Check certificate expiry
docker compose run --rm certbot certificates
```

### Issue: Email not sending
```bash
# Test SMTP connection
docker compose exec backend python manage.py shell
>>> from django.core.mail import send_mail
>>> send_mail('Test', 'Message', 'from@example.com', ['to@example.com'])
```

---

## Security Checklist

- [x] DEBUG=False
- [x] Strong SECRET_KEY
- [x] Strong database password
- [x] Redis password configured
- [x] SSL/HTTPS enabled
- [x] Firewall configured
- [x] Security headers in Nginx
- [x] Automated backups setup
- [x] Monitoring configured
- [x] Log rotation setup
- [ ] Regular security updates
- [ ] Regular backups tested
- [ ] Incident response plan

---

## Performance Optimization

### 1. Database Indexing
```sql
-- Add indexes for frequently queried fields
CREATE INDEX idx_student_admission_date ON academic_student(admission_date);
CREATE INDEX idx_receipt_date ON finance_receipt(date);
```

### 2. Redis Caching
Configure Django caching in settings.py for frequently accessed data.

### 3. CDN for Static Files
Use CloudFlare or AWS CloudFront for static assets.

### 4. Database Connection Pooling
Already configured via pgbouncer (if needed).

---

## Scaling Guide

### Horizontal Scaling

```yaml
# Scale specific services
docker compose up -d --scale celery_worker=4
docker compose up -d --scale backend=3  # Requires load balancer
```

### Load Balancer

Add HAProxy or Nginx load balancer for multiple backend instances.

---

## Support

For issues or questions:
- Check logs: `docker compose logs -f`
- Review documentation files
- Check GitHub issues

Your production deployment is ready! 🚀
