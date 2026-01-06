# SSync - Nuxt Frontend Integration Guide

Quick guide for integrating your Nuxt.js frontend with the SSync Django backend.

## Project Structure

**Recommended: Keep frontend separate**

```
/your-projects/
├── django-scms/          # Backend (this project)
│   ├── docker-compose.yml
│   ├── manage.py
│   └── ...
└── ssync-frontend/       # Your Nuxt project
    ├── nuxt.config.ts
    ├── package.json
    └── ...
```

## Quick Start

### 1. Start Backend Services

```bash
cd django-scms
docker compose --profile dev up -d
```

This starts:
- Django API: http://localhost:8000
- PostgreSQL database
- Redis cache
- Celery workers
- Mailpit (email testing): http://localhost:8025

### 2. Configure Nuxt Environment

In your Nuxt project root, create `.env`:

```bash
# API URL (backend)
NUXT_PUBLIC_API_URL=http://localhost:8000/api

# App settings
NUXT_PUBLIC_APP_NAME=SSync
```

### 3. Update Nuxt Config

```typescript
// nuxt.config.ts
export default defineNuxtConfig({
  runtimeConfig: {
    public: {
      apiUrl: process.env.NUXT_PUBLIC_API_URL || 'http://localhost:8000/api',
      appName: process.env.NUXT_PUBLIC_APP_NAME || 'SSync'
    }
  },

  // Optional: Proxy API requests in development
  devServer: {
    port: 3000
  }
})
```

### 4. Start Nuxt Development Server

```bash
cd ssync-frontend
npm install
npm run dev
```

Access your frontend at: http://localhost:3000

## API Integration

### Example: Fetch Data from Django API

```vue
<!-- pages/index.vue -->
<script setup lang="ts">
const config = useRuntimeConfig()
const apiUrl = config.public.apiUrl

// Fetch students
const { data: students } = await useFetch(`${apiUrl}/academic/students/`)

// Fetch with authentication
const token = useCookie('auth_token')
const { data: profile } = await useFetch(`${apiUrl}/users/profile/`, {
  headers: {
    Authorization: `Bearer ${token.value}`
  }
})
</script>

<template>
  <div>
    <h1>Students</h1>
    <ul>
      <li v-for="student in students?.results" :key="student.id">
        {{ student.first_name }} {{ student.last_name }}
      </li>
    </ul>
  </div>
</template>
```

### Example: Login/Authentication

```typescript
// composables/useAuth.ts
export const useAuth = () => {
  const config = useRuntimeConfig()
  const apiUrl = config.public.apiUrl
  const token = useCookie('auth_token')
  const refreshToken = useCookie('refresh_token')

  const login = async (email: string, password: string) => {
    try {
      const { data } = await useFetch(`${apiUrl}/users/login/`, {
        method: 'POST',
        body: { email, password }
      })

      if (data.value) {
        token.value = data.value.access
        refreshToken.value = data.value.refresh
        return true
      }
      return false
    } catch (error) {
      console.error('Login failed:', error)
      return false
    }
  }

  const logout = () => {
    token.value = null
    refreshToken.value = null
    navigateTo('/login')
  }

  const isAuthenticated = computed(() => !!token.value)

  return {
    login,
    logout,
    isAuthenticated,
    token
  }
}
```

### Example: API Composable

```typescript
// composables/useApi.ts
export const useApi = () => {
  const config = useRuntimeConfig()
  const apiUrl = config.public.apiUrl
  const token = useCookie('auth_token')

  const fetchWithAuth = async (endpoint: string, options: any = {}) => {
    return await useFetch(`${apiUrl}${endpoint}`, {
      ...options,
      headers: {
        ...options.headers,
        Authorization: token.value ? `Bearer ${token.value}` : ''
      }
    })
  }

  return {
    fetchWithAuth
  }
}

// Usage in component
const { fetchWithAuth } = useApi()
const { data: students } = await fetchWithAuth('/academic/students/')
```

## Running Nuxt in Docker (Optional)

If you want to run Nuxt in Docker alongside the backend:

### 1. Create Dockerfile in Nuxt Project

```dockerfile
# Development Dockerfile
FROM node:20-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./
RUN npm install

# Copy project
COPY . .

# Expose port
EXPOSE 3000

# Set environment
ENV NUXT_HOST=0.0.0.0
ENV NUXT_PORT=3000

# Run dev server
CMD ["npm", "run", "dev"]
```

### 2. Uncomment Frontend Service

In `django-scms/docker-compose.yml`, uncomment the frontend service and update the path:

```yaml
frontend:
  build:
    context: ../ssync-frontend  # Adjust path to your Nuxt project
    dockerfile: Dockerfile
  # ... rest of config
```

### 3. Start Both with Docker

```bash
cd django-scms
docker compose --profile dev up -d
```

## Available API Endpoints

### Authentication
- `POST /api/users/login/` - Login
- `POST /api/users/token/refresh/` - Refresh token
- `POST /api/users/logout/` - Logout

### Students
- `GET /api/academic/students/` - List students
- `POST /api/academic/students/` - Create student
- `GET /api/academic/students/{id}/` - Get student
- `PUT /api/academic/students/{id}/` - Update student
- `DELETE /api/academic/students/{id}/` - Delete student

### Teachers
- `GET /api/users/teachers/` - List teachers
- `PATCH /api/users/teachers/{id}/` - Partial update teacher

### Classrooms
- `GET /api/academic/classrooms/` - List classrooms
- `POST /api/academic/classrooms/` - Create classroom

### Examinations
- `GET /api/examination/results/` - List results
- `POST /api/examination/results/compute/` - Compute results (async)

### Assignments
- `GET /api/assignments/` - List assignments
- `POST /api/assignments/` - Create assignment

### Celery Tasks
- `GET /api/tasks/{task_id}/` - Check task status
- `GET /api/celery/health/` - Check Celery workers

Full API documentation available at: http://localhost:8000/ (Swagger UI)

## CORS Configuration

CORS is already configured in Django `settings.py`:

**Development:**
```python
CORS_ALLOW_ALL_ORIGINS = True  # Allows requests from localhost:3000
```

**Production** (update in settings):
```python
CORS_ALLOWED_ORIGINS = [
    "https://yourdomain.com",
    "https://www.yourdomain.com",
]
```

## File Uploads

### Upload Assignment Submission

```vue
<script setup lang="ts">
const { fetchWithAuth } = useApi()
const fileInput = ref<HTMLInputElement>()

const uploadAssignment = async () => {
  const file = fileInput.value?.files?.[0]
  if (!file) return

  const formData = new FormData()
  formData.append('file', file)
  formData.append('assignment_id', '123')
  formData.append('student_id', '456')

  const { data } = await fetchWithAuth('/assignments/submissions/', {
    method: 'POST',
    body: formData
  })
}
</script>

<template>
  <div>
    <input ref="fileInput" type="file" />
    <button @click="uploadAssignment">Upload</button>
  </div>
</template>
```

## WebSocket Support (Future)

For real-time features (notifications, live updates), Django Channels can be added:

```typescript
// composables/useWebSocket.ts
export const useWebSocket = () => {
  const ws = ref<WebSocket | null>(null)
  const token = useCookie('auth_token')

  const connect = () => {
    ws.value = new WebSocket(
      `ws://localhost:8000/ws/notifications/?token=${token.value}`
    )

    ws.value.onmessage = (event) => {
      const data = JSON.parse(event.data)
      // Handle notification
    }
  }

  return { connect, ws }
}
```

## Production Deployment Options

### Option 1: Separate Deployments
- **Backend**: Railway, DigitalOcean App Platform, AWS
- **Frontend**: Vercel, Netlify, Cloudflare Pages

### Option 2: Same Server
- Both in Docker with Nginx reverse proxy
- Single domain with path-based routing

### Option 3: Subdomain
- `api.yourdomain.com` → Backend
- `yourdomain.com` → Frontend

## Environment Variables

### Development (.env)
```bash
NUXT_PUBLIC_API_URL=http://localhost:8000/api
NUXT_PUBLIC_APP_NAME=SSync
```

### Production (.env.production)
```bash
NUXT_PUBLIC_API_URL=https://api.yourdomain.com/api
NUXT_PUBLIC_APP_NAME=SSync
```

## Troubleshooting

### CORS errors

**Error:** `Access to fetch at 'http://localhost:8000/api/...' has been blocked by CORS policy`

**Fix:** Check Django CORS settings in `school/settings.py`:
```python
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
]
```

### API not reachable

**From Nuxt container:**
Use `http://backend:8000/api` (internal Docker network)

**From browser:**
Use `http://localhost:8000/api` (host machine)

### File upload fails

Check Django settings:
```python
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
```

And ensure proper permissions on media directory.

## Next Steps

1. ✅ Start backend with Docker
2. ✅ Configure Nuxt environment variables
3. ✅ Update nuxt.config.ts
4. 🔜 Create authentication composables
5. 🔜 Build your UI components
6. 🔜 Integrate API endpoints
7. 🔜 Test file uploads
8. 🔜 Deploy to production

## Quick Commands

```bash
# Start backend
cd django-scms
docker compose --profile dev up -d

# Start frontend
cd ../ssync-frontend
npm run dev

# View backend logs
cd django-scms
docker compose logs -f backend

# Stop all services
docker compose down
```

Your Nuxt frontend is ready to connect to the SSync backend! 🚀
