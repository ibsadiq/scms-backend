# SSync - Docker Deployment Guide

Complete guide for running SSync using Docker and Docker Compose.

## Overview

The Docker setup includes:
- **Backend**: Django REST API with Gunicorn
- **Database**: PostgreSQL 16
- **Cache/Broker**: Redis 7
- **Task Queue**: Celery workers + Beat scheduler
- **Monitoring**: Flower (Celery monitoring UI)
- **Email Testing**: Mailpit (development only)
- **Reverse Proxy**: Nginx (production)
- **Frontend**: Nuxt.js (can run separately or in Docker)

## Prerequisites

### Install Docker

**Ubuntu/Debian:**
```bash
# Update package index
sudo apt update

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose
sudo apt install docker-compose-plugin
```

**macOS:**
```bash
# Install Docker Desktop
brew install --cask docker
```

**Windows:**
Download and install [Docker Desktop](https://www.docker.com/products/docker-desktop/)

### Verify Installation

```bash
docker --version
docker compose version
```

## Project Structure

You have two options for organizing your project:

### Option 1: Separate Repositories (Recommended)
```
/your-projects/
├── ssync-backend/           # This Django project
│   ├── docker-compose.yml
│   ├── Dockerfile
│   └── ...
└── ssync-frontend/          # Your Nuxt project (separate repo)
    ├── nuxt.config.ts
    └── ...
```

**Advantages:**
- Independent versioning
- Separate deployment pipelines
- Frontend team can work independently
- Easier to scale separately

### Option 2: Monorepo (All in one)
```
/ssync-monorepo/
├── backend/                 # Django
│   ├── docker-compose.yml
│   └── ...
├── frontend/                # Nuxt
│   ├── nuxt.config.ts
│   └── ...
└── docker-compose.yml       # Root compose file
```

## Quick Start (Development)

### Backend Only (Nuxt Running Separately)

**1. Configure Environment**

```bash
cp .env.docker .env.docker.local
```

**2. Start Backend Services**

```bash
# Build and start (without frontend)
docker compose --profile dev up -d

# View logs
docker compose logs -f
```

**3. Start Your Nuxt Frontend Separately**

```bash
# In your Nuxt project directory
cd ../ssync-frontend
npm run dev
```

**4. Configure Nuxt API URL**

In your Nuxt project's `.env`:
```bash
NUXT_PUBLIC_API_URL=http://localhost:8000/api
```

### Full Stack with Docker (Backend + Frontend)

If you want to run Nuxt in Docker too, follow the setup below.

## Frontend Integration Options

### Option A: Frontend Running Separately (Development)

**Recommended for development**. Backend in Docker, Frontend runs locally with `npm run dev`.

**Backend access from Nuxt:**
```typescript
// nuxt.config.ts
export default defineNuxtConfig({
  runtimeConfig: {
    public: {
      apiBase: process.env.NUXT_PUBLIC_API_URL || 'http://localhost:8000/api'
    }
  }
})
```

**CORS already configured** in Django settings (allows all origins in development).

### Option B: Frontend in Docker (Same Compose File)

Update `docker-compose.yml` to include your frontend:

```yaml
# Add this service to docker-compose.yml
frontend:
  build:
    context: ../ssync-frontend  # Path to your Nuxt project
    dockerfile: Dockerfile
  container_name: ssync-frontend
  volumes:
    - ../ssync-frontend:/app
    - /app/node_modules
    - /app/.nuxt
  ports:
    - "3000:3000"
  environment:
    - NUXT_PUBLIC_API_URL=http://backend:8000/api
    - NUXT_HOST=0.0.0.0
    - NUXT_PORT=3000
  networks:
    - ssync-network
  depends_on:
    - backend
  restart: unless-stopped
  profiles:
    - dev
```

**Create `Dockerfile` in your Nuxt project:**

```dockerfile
# Nuxt 3 Dockerfile
FROM node:20-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy project files
COPY . .

# Expose port
EXPOSE 3000

# Development command
CMD ["npm", "run", "dev"]

# Production would be:
# RUN npm run build
# CMD ["node", ".output/server/index.mjs"]
```

### Option C: Frontend in Separate Docker Compose

Create `docker-compose.frontend.yml` in your Nuxt project:

```yaml
version: '3.9'

services:
  frontend:
    build: .
    ports:
      - "3000:3000"
    environment:
      - NUXT_PUBLIC_API_URL=http://localhost:8000/api
    volumes:
      - .:/app
      - /app/node_modules
    networks:
      - ssync-network

networks:
  ssync-network:
    external: true  # Use backend's network
```

**Start both:**
```bash
# Terminal 1: Backend
cd ssync-backend
docker compose --profile dev up -d

# Terminal 2: Frontend
cd ssync-frontend
docker compose -f docker-compose.frontend.yml up
```

## Access the Application

- **Backend API**: http://localhost:8000/api/
- **API Documentation**: http://localhost:8000/ (Swagger UI)
- **Django Admin**: http://localhost:8000/admin/
  - Username: `admin`
  - Password: `admin123` (auto-created in dev mode)
- **Frontend (Nuxt)**: http://localhost:3000/
- **Celery Flower**: http://localhost:5555/
- **Mailpit (Email UI)**: http://localhost:8025/

## Production Deployment

### 1. Configure Production Environment

Create `.env.docker.local` with production settings:
```bash
DEBUG=False
SECRET_KEY=<generate-strong-secret-key>
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com,api.yourdomain.com

# Database
DB_NAME=ssync_production
DB_USER=ssync_prod
DB_PASSWORD=<strong-secure-password>

# Email
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=<your-app-password>
DEFAULT_FROM_EMAIL=noreply@yourdomain.com

BUILD_TARGET=production
```

### 2. Production Nuxt Build

In your Nuxt project:

```dockerfile
# Production Dockerfile for Nuxt
FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM node:20-alpine AS runner

WORKDIR /app
COPY --from=builder /app/.output ./.output
COPY --from=builder /app/package*.json ./

ENV NODE_ENV=production
ENV NUXT_HOST=0.0.0.0
ENV NUXT_PORT=3000

EXPOSE 3000

CMD ["node", ".output/server/index.mjs"]
```

### 3. Deployment Architecture

**Option 1: Single Server**
```
[Nginx]
   ├─> /api/*  -> Backend (Django:8000)
   └─> /*      -> Frontend (Nuxt:3000)
```

**Option 2: Separate Domains**
```
api.yourdomain.com  -> Backend
yourdomain.com      -> Frontend
```

**Option 3: Cloud Deployment**
- Backend: AWS ECS/EC2, DigitalOcean, Railway
- Frontend: Vercel, Netlify, Cloudflare Pages
- Database: AWS RDS, DigitalOcean Managed PostgreSQL

### 4. Nginx Production Config

Update `nginx/conf.d/ssync.conf` for your setup:

```nginx
# Backend API
upstream backend_api {
    server backend:8000;
}

# Frontend SSR
upstream frontend_app {
    server frontend:3000;
}

server {
    listen 80;
    server_name yourdomain.com;

    # API
    location /api/ {
        proxy_pass http://backend_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Static/Media files
    location /static/ {
        alias /app/staticfiles/;
        expires 30d;
    }

    location /media/ {
        alias /app/media/;
        expires 7d;
    }

    # Frontend (Nuxt SSR)
    location / {
        proxy_pass http://frontend_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Service Management

### Start/Stop Services

```bash
# Start backend only
docker compose up -d

# Start backend with dev tools
docker compose --profile dev up -d

# Stop all services
docker compose down

# Restart specific service
docker compose restart backend
docker compose restart celery_worker
```

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend
docker compose logs -f celery_worker
```

### Execute Commands

```bash
# Django shell
docker compose exec backend python manage.py shell

# Create superuser
docker compose exec backend python manage.py createsuperuser

# Run migrations
docker compose exec backend python manage.py migrate

# Database shell
docker compose exec postgres psql -U ssync_user -d ssync_db
```

## Scaling Services

```bash
# Run multiple Celery workers
docker compose up -d --scale celery_worker=4

# Check running containers
docker compose ps
```

## Troubleshooting

### CORS issues between Nuxt and Django

Django CORS settings in `settings.py`:
```python
# Development
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# Or allow all (development only)
CORS_ALLOW_ALL_ORIGINS = True
```

### Frontend can't connect to backend

**Check network connectivity:**
```bash
# From Nuxt container
docker compose exec frontend ping backend

# Check API from Nuxt container
docker compose exec frontend wget -O- http://backend:8000/api/
```

**Update Nuxt config:**
```typescript
// Use internal Docker network in container
const apiBase = process.env.NUXT_PUBLIC_API_URL ||
                (process.server
                  ? 'http://backend:8000/api'  // Server-side (inside Docker)
                  : 'http://localhost:8000/api') // Client-side (browser)
```

### Database connection errors

```bash
# Check PostgreSQL
docker compose ps postgres
docker compose logs postgres

# Test connection
docker compose exec backend python manage.py dbshell
```

### Celery tasks not executing

```bash
# Check workers
docker compose logs celery_worker

# Inspect active workers
docker compose exec backend celery -A school inspect active

# Restart Celery
docker compose restart celery_worker celery_beat
```

## Backup and Restore

### Database Backup

```bash
# Create backup
docker compose exec postgres pg_dump -U ssync_user ssync_db > backup_$(date +%Y%m%d).sql

# Restore backup
docker compose exec -T postgres psql -U ssync_user ssync_db < backup.sql
```

### Media Files Backup

```bash
# Backup media files
docker cp ssync-backend:/app/media ./media_backup

# Restore media files
docker cp ./media_backup ssync-backend:/app/media
```

## Environment-Specific Setup

### Development
```bash
# Backend with all dev tools
docker compose --profile dev up -d

# Nuxt with hot reload (outside Docker)
cd ../ssync-frontend
npm run dev
```

### Staging
```bash
# Backend in production mode
docker compose --profile production up -d

# Nuxt production build
cd ../ssync-frontend
npm run build
npm run preview
```

### Production
```bash
# Full production stack with Nginx
docker compose --profile production up -d nginx

# Or deploy separately:
# - Backend: Railway, DigitalOcean App Platform
# - Frontend: Vercel, Cloudflare Pages
# - Database: Managed PostgreSQL
```

## Docker Commands Cheat Sheet

```bash
# Build
docker compose build                    # Build all
docker compose build backend            # Build specific service
docker compose build --no-cache         # Clean build

# Start/Stop
docker compose up -d                    # Start background
docker compose down                     # Stop and remove
docker compose restart                  # Restart services

# Logs
docker compose logs -f backend          # Follow logs
docker compose logs --tail=100 backend  # Last 100 lines

# Execute
docker compose exec backend bash        # Backend shell
docker compose exec postgres psql -U ssync_user

# Scale
docker compose up -d --scale celery_worker=4

# Cleanup
docker compose down -v                  # Remove volumes
docker system prune -a                  # Clean all
```

## Recommended Development Workflow

**Best practice for development:**

1. **Backend**: Run in Docker (includes DB, Redis, Celery)
   ```bash
   docker compose --profile dev up -d
   ```

2. **Frontend**: Run natively (faster hot reload)
   ```bash
   cd ../ssync-frontend
   npm run dev
   ```

3. **Frontend Environment** (`.env` in Nuxt project):
   ```bash
   NUXT_PUBLIC_API_URL=http://localhost:8000/api
   ```

This gives you:
- Fast backend services in Docker
- Native Nuxt hot reload (faster than Docker)
- Easy debugging on both sides

## Next Steps

1. ✅ Docker setup complete for backend
2. 🔜 Create Dockerfile in your Nuxt project (if you want Docker)
3. 🔜 Configure NUXT_PUBLIC_API_URL in Nuxt
4. 🔜 Test API calls from Nuxt to Django
5. 🔜 Deploy to production (consider Vercel for Nuxt, Railway/DO for Django)

## Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [Nuxt Docker Deployment](https://nuxt.com/docs/getting-started/deployment#docker)
- [Django Docker Best Practices](https://testdriven.io/blog/dockerizing-django-with-postgres-gunicorn-and-nginx/)
