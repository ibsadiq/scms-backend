# 🎨 Frontend Integration Guide - Production Ready

## Complete Step-by-Step Setup for Nuxt Frontend with Docker

This guide will help you integrate your Nuxt frontend with the Django backend using Docker, suitable for both development and production environments.

---

## Prerequisites

✅ Backend Docker services running (see [DOCKER_DEPLOYMENT_SUCCESS.md](DOCKER_DEPLOYMENT_SUCCESS.md))
✅ Nuxt project exists at `../ssync-frontend` (or update path in docker-compose.yml)
✅ Dockerfile created in your Nuxt project root

---

## Step 1: Verify Project Structure

Your project structure should look like this:

```
Projects/
├── django-scms/              # Backend (this project)
│   ├── docker-compose.yml
│   ├── Dockerfile
│   ├── manage.py
│   └── ...
└── ssync-frontend/           # Your Nuxt project
    ├── Dockerfile            # ✓ You created this
    ├── package.json
    ├── nuxt.config.ts
    ├── app.vue
    └── ...
```

**If your Nuxt project is in a different location**, update line 183 in `docker-compose.yml`:

```yaml
frontend:
  build:
    context: ../ssync-frontend  # ← Update this path
```

---

## Step 2: Configure Nuxt for Docker

### 2.1 Update nuxt.config.ts

Add/update these settings in your `nuxt.config.ts`:

```typescript
// nuxt.config.ts
export default defineNuxtConfig({
  // Development server configuration
  devServer: {
    host: '0.0.0.0',  // Listen on all interfaces (required for Docker)
    port: 3000
  },

  // Runtime configuration
  runtimeConfig: {
    public: {
      // API URL - will be set via environment variables
      apiUrl: process.env.NUXT_PUBLIC_API_URL || 'http://localhost:8000/api',
      apiBase: process.env.NUXT_PUBLIC_API_BASE || 'http://localhost:8000/api'
    }
  },

  // SSR Mode (recommended for production)
  ssr: true,

  // Nitro configuration for production
  nitro: {
    preset: 'node-server',
    compressPublicAssets: true
  },

  compatibilityDate: '2024-04-03',
  devtools: { enabled: true }
})
```

### 2.2 Create .dockerignore in Nuxt Project

Create `../ssync-frontend/.dockerignore`:

```
node_modules
.nuxt
.output
.env
.env.*
!.env.example
dist
.cache
*.log
.DS_Store
coverage
.vscode
.idea
```

### 2.3 Update package.json Scripts

Ensure your `package.json` has these scripts:

```json
{
  "scripts": {
    "dev": "nuxt dev",
    "build": "nuxt build",
    "generate": "nuxt generate",
    "preview": "nuxt preview",
    "postinstall": "nuxt prepare"
  }
}
```

---

## Step 3: Environment Configuration

### 3.1 Create .env.docker.local (Backend)

Update or create `/home/abu/Projects/django-scms/.env.docker.local`:

```bash
# Django Backend
DEBUG=True
SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=localhost,127.0.0.1,backend

# Database
DB_NAME=ssync_db
DB_USER=ssync_user
DB_PASSWORD=changeme
DB_HOST=postgres
DB_PORT=5432

# Redis
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0

# Email (Development - using Mailpit)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=mailpit
EMAIL_PORT=1025
EMAIL_USE_TLS=False

# CORS (Allow frontend access)
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://frontend:3000

# Frontend Configuration
FRONTEND_BUILD_TARGET=development  # or 'production'
NUXT_PUBLIC_API_URL=http://backend:8000/api
NUXT_PUBLIC_API_BASE=http://localhost:8000/api
```

### 3.2 Create .env in Nuxt Project (Optional)

Create `../ssync-frontend/.env` for local development outside Docker:

```bash
NUXT_PUBLIC_API_URL=http://localhost:8000/api
NUXT_PUBLIC_API_BASE=http://localhost:8000/api
```

---

## Step 4: Using API in Nuxt

### 4.1 Create API Composable

Create `../ssync-frontend/composables/useApi.ts`:

```typescript
export const useApi = () => {
  const config = useRuntimeConfig()

  // Use apiBase for client-side, apiUrl for server-side
  const baseURL = process.server
    ? config.public.apiUrl
    : config.public.apiBase

  const api = $fetch.create({
    baseURL,
    headers: {
      'Content-Type': 'application/json'
    },
    onRequest({ options }) {
      // Add auth token if exists
      const token = useCookie('auth_token')
      if (token.value) {
        options.headers = {
          ...options.headers,
          Authorization: `Bearer ${token.value}`
        }
      }
    },
    onResponseError({ response }) {
      // Handle errors globally
      if (response.status === 401) {
        // Redirect to login
        navigateTo('/login')
      }
    }
  })

  return {
    api,
    baseURL
  }
}
```

### 4.2 Example Usage in Components

```vue
<script setup lang="ts">
const { api } = useApi()

// Fetch students
const { data: students, pending, error } = await useAsyncData(
  'students',
  () => api('/academic/students/')
)

// Create a student
async function createStudent(studentData: any) {
  try {
    const result = await api('/academic/students/', {
      method: 'POST',
      body: studentData
    })
    console.log('Student created:', result)
  } catch (err) {
    console.error('Error creating student:', err)
  }
}
</script>

<template>
  <div>
    <div v-if="pending">Loading...</div>
    <div v-else-if="error">Error: {{ error.message }}</div>
    <div v-else>
      <div v-for="student in students" :key="student.id">
        {{ student.first_name }} {{ student.last_name }}
      </div>
    </div>
  </div>
</template>
```

---

## Step 5: Start the Frontend

### Development Mode (with hot reload)

```bash
cd /home/abu/Projects/django-scms

# Start backend + frontend
docker compose --profile dev up -d

# View logs
docker compose logs -f frontend

# Or start just frontend if backend already running
docker compose up -d frontend
```

**Access:**
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000/api/
- Admin: http://localhost:8000/admin/

### Production Mode

```bash
# Set production environment
echo "FRONTEND_BUILD_TARGET=production" >> .env.docker.local
echo "NODE_ENV=production" >> .env.docker.local

# Build production image
docker compose build frontend

# Start with production profile
docker compose --profile production up -d

# Or rebuild and start
docker compose up -d --build frontend
```

---

## Step 6: Update Nginx Configuration (Production)

For production, route frontend through Nginx. Update `nginx/conf.d/ssync.conf`:

```nginx
# Frontend (Nuxt.js)
upstream frontend {
    server frontend:3000;
}

# Backend (Django)
upstream backend {
    server backend:8000;
}

server {
    listen 80;
    server_name yourdomain.com;  # Update with your domain

    client_max_body_size 100M;

    # API requests go to Django
    location /api/ {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Admin panel
    location /admin/ {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Static files from Django
    location /static/ {
        alias /app/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Media files
    location /media/ {
        alias /app/mediafiles/;
        expires 7d;
    }

    # Everything else goes to Nuxt
    location / {
        proxy_pass http://frontend;
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

Then rebuild Nginx:

```bash
docker compose restart nginx
```

---

## Step 7: Common Commands

### Service Management

```bash
# Start everything (backend + frontend)
docker compose --profile dev up -d

# Stop everything
docker compose down

# Restart frontend
docker compose restart frontend

# View frontend logs
docker compose logs -f frontend

# View all logs
docker compose logs -f

# Rebuild frontend after code changes
docker compose up -d --build frontend
```

### Install npm Packages

```bash
# Method 1: Inside container
docker compose exec frontend npm install <package-name>

# Method 2: Locally (recommended for faster development)
cd ../ssync-frontend
npm install <package-name>
docker compose restart frontend
```

### Debugging

```bash
# Enter frontend container shell
docker compose exec frontend sh

# Check Nuxt environment
docker compose exec frontend npm run build -- --debug

# Check API connectivity from frontend
docker compose exec frontend wget -O- http://backend:8000/api/
```

---

## Step 8: Troubleshooting

### Frontend not starting?

```bash
# Check logs
docker compose logs frontend

# Common issues:
# 1. Node modules missing
docker compose exec frontend npm install

# 2. Port conflict
# Check if port 3000 is in use
lsof -i :3000
```

### API requests failing?

```bash
# Test from frontend container
docker compose exec frontend wget -O- http://backend:8000/api/

# Check CORS settings in Django
docker compose exec backend python manage.py shell
>>> from django.conf import settings
>>> print(settings.CORS_ALLOWED_ORIGINS)
```

### Hot reload not working?

The volumes in docker-compose.yml enable hot reload:
```yaml
volumes:
  - ../ssync-frontend:/app      # ← Your code
  - /app/node_modules           # ← Don't override node_modules
  - /app/.nuxt                  # ← Don't override .nuxt
```

If hot reload still doesn't work:
```bash
# Restart with fresh build
docker compose down
docker compose up -d --build frontend
```

### Build errors in production?

```bash
# Check build logs
docker compose build frontend --no-cache --progress=plain

# Test build locally first
cd ../ssync-frontend
npm run build
```

---

## Step 9: Production Deployment Checklist

Before deploying to production:

- [ ] Set `FRONTEND_BUILD_TARGET=production`
- [ ] Set `NODE_ENV=production`
- [ ] Set `DEBUG=False` in Django
- [ ] Update `ALLOWED_HOSTS` in Django settings
- [ ] Update `CORS_ALLOWED_ORIGINS` with production domain
- [ ] Configure SSL/HTTPS in Nginx
- [ ] Update API URLs to use production domain
- [ ] Set strong `SECRET_KEY` for Django
- [ ] Configure real email backend (not Mailpit)
- [ ] Set up proper logging
- [ ] Configure environment-specific settings

---

## Architecture Overview

### Development Flow
```
Browser (localhost:3000)
    ↓
Nuxt Dev Server (Hot Reload)
    ↓
Django API (localhost:8000)
    ↓
PostgreSQL / Redis / Celery
```

### Production Flow
```
Browser
    ↓
Nginx (:80/:443)
    ├─→ /api/* → Django Backend
    ├─→ /admin/* → Django Admin
    ├─→ /static/* → Static Files
    └─→ /* → Nuxt SSR
         ↓
    Django API (internal)
         ↓
    PostgreSQL / Redis / Celery
```

---

## API Endpoints Reference

Your Nuxt app can access these endpoints:

### Authentication
```typescript
POST /api/token/              // Login
POST /api/token/refresh/      // Refresh token
POST /api/register/           // Register
```

### Academic
```typescript
GET  /api/academic/students/
POST /api/academic/students/
GET  /api/academic/students/{id}/
PUT  /api/academic/students/{id}/
```

### Financial
```typescript
GET  /api/financial/fee-structures/
POST /api/financial/fee-structures/
GET  /api/financial/payments/
POST /api/financial/fee-structures/{id}/send_reminder/
```

### Full API documentation: http://localhost:8000/

---

## Performance Tips

### 1. Use SSR for Better SEO
```typescript
// nuxt.config.ts
export default defineNuxtConfig({
  ssr: true  // Server-side rendering
})
```

### 2. Optimize Images
```vue
<NuxtImg
  src="/images/school-logo.png"
  width="200"
  height="200"
  loading="lazy"
/>
```

### 3. Code Splitting
```typescript
// Auto code splitting with dynamic imports
const Dashboard = defineAsyncComponent(() => import('~/components/Dashboard.vue'))
```

### 4. API Caching
```typescript
const { data } = await useFetch('/api/students/', {
  key: 'students',
  getCachedData: (key) => useNuxtData(key).data,
  transform: (data) => data.results
})
```

---

## Next Steps

1. **Start Development:**
   ```bash
   docker compose --profile dev up -d
   ```

2. **Access Frontend:** http://localhost:3000

3. **Test API Integration:**
   - Create a test page that fetches data from `/api/academic/students/`
   - Test authentication flow
   - Verify CORS is working

4. **Build Features:**
   - Student management
   - Fee payment interface
   - Results viewing
   - Parent portal

5. **Deploy to Production:**
   - Follow production deployment checklist
   - Set up CI/CD pipeline
   - Configure monitoring

---

## Support

- **Backend Issues:** Check [DOCKER_DEPLOYMENT_SUCCESS.md](DOCKER_DEPLOYMENT_SUCCESS.md)
- **API Reference:** http://localhost:8000/
- **Nuxt Documentation:** https://nuxt.com/docs

Your frontend is now integrated with the backend! 🎉
