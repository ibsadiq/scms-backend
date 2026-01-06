#!/bin/bash

# ==============================================================================
# SSync Quick VPS Deployment Script
# VPS IP: 72.61.184.120
# ==============================================================================

set -e  # Exit on error

echo "🚀 Starting SSync deployment on VPS..."
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
# Step 4: Build Docker images
# ==============================================================================
echo -e "${YELLOW}Step 4: Building Docker images (this may take 5-10 minutes)...${NC}"

docker compose build --no-cache

echo -e "${GREEN}✅ Docker images built successfully${NC}"
echo ""

# ==============================================================================
# Step 5: Start services
# ==============================================================================
echo -e "${YELLOW}Step 5: Starting services...${NC}"

docker compose --profile production up -d

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
echo -e "${GREEN}🎉 Deployment Complete!${NC}"
echo "=========================================="
echo ""
echo "Your SSync application is now running!"
echo ""
echo "Access URLs:"
echo "  • Frontend:  http://72.61.184.120/"
echo "  • API:       http://72.61.184.120/api/"
echo "  • Admin:     http://72.61.184.120/admin/"
echo "  • Flower:    http://72.61.184.120:5555/"
echo ""
echo "Next Steps:"
echo "  1. Create superuser: docker compose exec backend python manage.py createsuperuser"
echo "  2. Configure firewall: sudo ufw allow 80/tcp && sudo ufw allow 8000/tcp"
echo "  3. Login to admin panel and set up your school"
echo ""
echo "View logs:"
echo "  docker compose logs -f backend"
echo "  docker compose logs -f frontend"
echo ""
echo "=========================================="
