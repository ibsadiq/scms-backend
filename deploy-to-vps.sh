#!/bin/bash

# ==============================================================================
# SSync Quick VPS Deployment Script
# VPS IP: 72.61.184.120
#
# Usage:
#   ./deploy-to-vps.sh           # Deploy backend + frontend
#   ./deploy-to-vps.sh --backend-only   # Deploy backend only (skip frontend)
# ==============================================================================

set -e  # Exit on error

# Check for backend-only flag
SKIP_FRONTEND=false
if [[ "$1" == "--backend-only" ]]; then
    SKIP_FRONTEND=true
    echo "🚀 Starting SSync BACKEND-ONLY deployment on VPS..."
else
    echo "🚀 Starting SSync FULL deployment on VPS..."
fi
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# ==============================================================================
# Step 1: Check if running on VPS
# ==============================================================================
echo -e "${YELLOW}Step 1: Checking environment...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker not found! Please install Docker first.${NC}"
    exit 1
fi

if ! command -v docker compose &> /dev/null; then
    echo -e "${RED}❌ Docker Compose not found! Please install Docker Compose first.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Docker and Docker Compose found${NC}"
echo ""

# ==============================================================================
# Step 2: Setup environment file
# ==============================================================================
echo -e "${YELLOW}Step 2: Setting up environment file...${NC}"

if [ ! -f .env ]; then
    if [ -f .env.production.ip ]; then
        echo "Copying .env.production.ip to .env..."
        cp .env.production.ip .env

        echo -e "${YELLOW}⚠️  IMPORTANT: You need to update SECRET_KEY in .env${NC}"
        echo "Generating SECRET_KEY..."
        SECRET_KEY=$(openssl rand -base64 64 | tr -d '\n')

        # Replace SECRET_KEY in .env file
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            sed -i '' "s|SECRET_KEY=REPLACE-WITH-OUTPUT-FROM-openssl-rand-base64-64|SECRET_KEY=${SECRET_KEY}|g" .env
        else
            # Linux
            sed -i "s|SECRET_KEY=REPLACE-WITH-OUTPUT-FROM-openssl-rand-base64-64|SECRET_KEY=${SECRET_KEY}|g" .env
        fi

        echo -e "${GREEN}✅ Generated and set SECRET_KEY${NC}"
    else
        echo -e "${RED}❌ .env.production.ip template not found!${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✅ .env file already exists${NC}"
fi

# Copy to .env.docker
cp .env .env.docker

echo ""

# ==============================================================================
# Step 3: Clean up old containers
# ==============================================================================
echo -e "${YELLOW}Step 3: Cleaning up old containers...${NC}"

if docker compose ps -q | grep -q .; then
    echo "Stopping existing containers..."
    docker compose down -v
else
    echo "No existing containers to clean up"
fi

echo -e "${GREEN}✅ Cleanup complete${NC}"
echo ""

# ==============================================================================
# Step 3.5: Copy fixed frontend Dockerfile (if building frontend)
# ==============================================================================
if [ "$SKIP_FRONTEND" = false ]; then
    echo -e "${YELLOW}Step 3.5: Setting up frontend Dockerfile...${NC}"

    # Check if frontend directory exists
    if [ -d "../scms" ]; then
        echo "Copying optimized Dockerfile to frontend..."
        cp nuxt-pnpm.Dockerfile ../scms/Dockerfile
        echo -e "${GREEN}✅ Frontend Dockerfile updated (with memory optimization)${NC}"
    else
        echo -e "${YELLOW}⚠️  Frontend directory not found at ../scms${NC}"
        echo "Frontend build may fail if Dockerfile is not configured properly"
    fi

    echo ""
else
    echo -e "${YELLOW}Skipping frontend setup (backend-only mode)${NC}"
    echo ""
fi

# ==============================================================================
# Step 4: Build Docker images
# ==============================================================================
if [ "$SKIP_FRONTEND" = false ]; then
    echo -e "${YELLOW}Step 4: Building ALL services (backend + frontend, 5-10 minutes)...${NC}"
    docker compose build --no-cache
else
    echo -e "${YELLOW}Step 4: Building BACKEND services only (2-3 minutes)...${NC}"
    docker compose build --no-cache backend celery_worker celery_beat flower
fi

echo -e "${GREEN}✅ Docker images built successfully${NC}"
echo ""

# ==============================================================================
# Step 5: Start services
# ==============================================================================
echo -e "${YELLOW}Step 5: Starting services...${NC}"

if [ "$SKIP_FRONTEND" = false ]; then
    # Start all services including frontend and nginx
    docker compose --profile production up -d
else
    # Start only backend services (postgres, redis, backend, celery, flower)
    docker compose up -d postgres redis backend celery_worker celery_beat flower
fi

echo "Waiting 30 seconds for services to initialize..."
sleep 30

echo -e "${GREEN}✅ Services started${NC}"
echo ""

# ==============================================================================
# Step 6: Check service health
# ==============================================================================
echo -e "${YELLOW}Step 6: Checking service health...${NC}"

docker compose ps

echo ""

# ==============================================================================
# Step 7: Run database migrations
# ==============================================================================
echo -e "${YELLOW}Step 7: Running database migrations...${NC}"

docker compose exec -T backend python manage.py migrate

echo -e "${GREEN}✅ Migrations complete${NC}"
echo ""

# ==============================================================================
# Step 8: Collect static files
# ==============================================================================
echo -e "${YELLOW}Step 8: Collecting static files...${NC}"

docker compose exec -T backend python manage.py collectstatic --noinput

echo -e "${GREEN}✅ Static files collected${NC}"
echo ""

# ==============================================================================
# Step 9: Setup fee reminders
# ==============================================================================
echo -e "${YELLOW}Step 9: Setting up fee reminders...${NC}"

docker compose exec -T backend python manage.py setup_fee_reminders

echo -e "${GREEN}✅ Fee reminders configured${NC}"
echo ""

# ==============================================================================
# Final Summary
# ==============================================================================
echo ""
echo "=========================================="
if [ "$SKIP_FRONTEND" = false ]; then
    echo -e "${GREEN}🎉 Full Deployment Complete!${NC}"
else
    echo -e "${GREEN}🎉 Backend Deployment Complete!${NC}"
fi
echo "=========================================="
echo ""

if [ "$SKIP_FRONTEND" = false ]; then
    echo "Your SSync application is now running!"
    echo ""
    echo "Access URLs:"
    echo "  • Frontend:  http://72.61.184.120/"
    echo "  • API:       http://72.61.184.120/api/"
    echo "  • Admin:     http://72.61.184.120/admin/"
    echo "  • Flower:    http://72.61.184.120:5555/"
else
    echo "Backend services are now running!"
    echo ""
    echo "Access URLs:"
    echo "  • API:       http://72.61.184.120:8000/api/"
    echo "  • Admin:     http://72.61.184.120:8000/admin/"
    echo "  • Flower:    http://72.61.184.120:5555/"
    echo ""
    echo -e "${YELLOW}Note: Frontend is NOT deployed${NC}"
fi

echo ""
echo "Next Steps:"
echo "  1. Create superuser: docker compose exec backend python manage.py createsuperuser"
echo "  2. Configure firewall: sudo ufw allow 80/tcp && sudo ufw allow 8000/tcp"

if [ "$SKIP_FRONTEND" = false ]; then
    echo "  3. Login to admin panel and set up your school"
else
    echo "  3. Test backend: curl http://72.61.184.120:8000/api/"
    echo ""
    echo "To add frontend later:"
    echo "  • Fix Dockerfile: cp nuxt-pnpm.Dockerfile ../scms/Dockerfile"
    echo "  • Build frontend: docker compose build frontend"
    echo "  • Start frontend: docker compose --profile production up -d frontend nginx"
fi

echo ""
echo "View logs:"
echo "  docker compose logs -f backend"
if [ "$SKIP_FRONTEND" = false ]; then
    echo "  docker compose logs -f frontend"
fi
echo ""
echo "=========================================="
