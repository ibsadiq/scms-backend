# 🚀 Deploy SSync to 72.61.184.120 - Quick Reference

## Option 1: Automated Deployment (Recommended)

SSH to your VPS and run:

```bash
cd /home/abu/Projects/django-scms
./deploy-to-vps.sh
```

Then create your admin user:

```bash
docker compose exec backend python manage.py createsuperuser
```

**Done!** Access at: http://72.61.184.120/

---

## Option 2: Manual Step-by-Step

```bash
# 1. Setup environment
cp .env.production.ip .env
openssl rand -base64 64  # Copy output
nano .env  # Update SECRET_KEY with output above
cp .env .env.docker

# 2. Build and start
docker compose down -v
docker compose build --no-cache
docker compose up -d

# 3. Wait for services to start (30 seconds)
sleep 30

# 4. Setup database
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser
docker compose exec backend python manage.py collectstatic --noinput
docker compose exec backend python manage.py setup_fee_reminders

# 5. Configure firewall
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw --force enable
```

---

## Access Your Application

| Service | URL |
|---------|-----|
| **Frontend** | http://72.61.184.120/ |
| **Admin Panel** | http://72.61.184.120/admin/ |
| **API** | http://72.61.184.120/api/ |
| **Celery Monitor** | http://72.61.184.120:5555/ |

---

## Quick Commands Reference

```bash
# View logs
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f celery_worker

# Restart services
docker compose restart backend
docker compose restart nginx

# Check status
docker compose ps

# Stop all
docker compose down

# Start all
docker compose up -d
```

---

## Files Created for Your Deployment

✅ **[VPS_IP_DEPLOY.md](VPS_IP_DEPLOY.md)** - Complete deployment guide
✅ **[.env.production.ip](.env.production.ip)** - Environment template
✅ **[nginx/conf.d/ip-production.conf](nginx/conf.d/ip-production.conf)** - Nginx config
✅ **[deploy-to-vps.sh](deploy-to-vps.sh)** - Automated deployment script

---

## Troubleshooting

**Can't access website?**
```bash
# Check services
docker compose ps

# Check nginx
docker compose logs nginx

# Check firewall
sudo ufw status
```

**Database errors?**
```bash
# Check postgres
docker compose logs postgres

# Verify credentials
docker compose exec backend env | grep DB_
```

**Email not working?**
```bash
# Test email
docker compose exec backend python manage.py shell
```
```python
from django.core.mail import send_mail
send_mail('Test', 'It works!', 'ssync007@gmail.com', ['your@email.com'])
```

---

## Support & Documentation

- **Full Guide:** [VPS_IP_DEPLOY.md](VPS_IP_DEPLOY.md)
- **Domain Deployment:** [VPS_QUICK_DEPLOY.md](VPS_QUICK_DEPLOY.md)
- **Comprehensive Guide:** [PRODUCTION_DEPLOYMENT_GUIDE.md](PRODUCTION_DEPLOYMENT_GUIDE.md)

---

**Your VPS is ready to deploy! 🎉**
