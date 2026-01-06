# 🎨 PNPM Setup for Nuxt Frontend

Since you're using pnpm, here's the quick setup:

## Step 1: Copy Dockerfile to Your Nuxt Project

```bash
# Copy the pnpm Dockerfile to your Nuxt project
cp nuxt-pnpm.Dockerfile ../ssync-frontend/Dockerfile
```

**Or manually copy the content from `nuxt-pnpm.Dockerfile` to `../ssync-frontend/Dockerfile`**

## Step 2: Verify pnpm-lock.yaml Exists

```bash
cd ../ssync-frontend
ls -la pnpm-lock.yaml
```

If `pnpm-lock.yaml` doesn't exist:
```bash
pnpm install
```

## Step 3: Update docker-compose.yml Path (if needed)

In `/home/abu/Projects/django-scms/docker-compose.yml`, verify line 183:
```yaml
frontend:
  build:
    context: ../ssync-frontend  # ← Should point to your Nuxt project
```

## Step 4: Build and Start

```bash
# Go back to Django project
cd /home/abu/Projects/django-scms

# Build frontend with pnpm
docker compose build frontend

# Start everything
docker compose --profile dev up -d

# View logs
docker compose logs -f frontend
```

## Access Your App

- **Frontend:** http://localhost:3000
- **Backend API:** http://localhost:8000/api/
- **Admin:** http://localhost:8000/admin/

## Key Differences from NPM

The pnpm Dockerfile:
- Uses `corepack` to enable pnpm
- Uses `pnpm install --frozen-lockfile` instead of `npm ci`
- Uses `pnpm run dev` and `pnpm run build`
- Includes pnpm cache mounting for faster builds

## Development Commands

```bash
# Install package in container
docker compose exec frontend pnpm add <package>

# Install dev dependency
docker compose exec frontend pnpm add -D <package>

# Rebuild after changes
docker compose up -d --build frontend

# Run pnpm commands
docker compose exec frontend pnpm run <script>
```

## Production Build

```bash
# Set production mode
echo "FRONTEND_BUILD_TARGET=production" >> .env.docker.local

# Build
docker compose build frontend

# Deploy
docker compose --profile production up -d
```

---

## Quick Copy-Paste Commands

```bash
# All-in-one setup
cd /home/abu/Projects/django-scms
cp nuxt-pnpm.Dockerfile ../ssync-frontend/Dockerfile
docker compose build frontend
docker compose --profile dev up -d frontend

# View logs
docker compose logs -f frontend
```

That's it! Your Nuxt app with pnpm is ready to run in Docker! 🚀
