#!/bin/bash
# ============================================
# SSync Frontend - Quick Start Script
# ============================================
# This script helps you quickly start the frontend with the backend

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}   SSync Frontend - Quick Start${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# Check if Nuxt project exists
NUXT_PATH="../ssync-frontend"
if [ ! -d "$NUXT_PATH" ]; then
    echo -e "${YELLOW}⚠️  Nuxt project not found at $NUXT_PATH${NC}"
    echo ""
    read -p "Enter the path to your Nuxt project: " NUXT_PATH

    if [ ! -d "$NUXT_PATH" ]; then
        echo -e "${RED}❌ Directory not found: $NUXT_PATH${NC}"
        exit 1
    fi
fi

# Check if Dockerfile exists in Nuxt project
if [ ! -f "$NUXT_PATH/Dockerfile" ]; then
    echo -e "${YELLOW}⚠️  Dockerfile not found in Nuxt project${NC}"
    echo ""
    echo "Creating Dockerfile from template..."

    # Copy the example Dockerfile
    if [ -f "frontend.Dockerfile" ]; then
        cp frontend.Dockerfile "$NUXT_PATH/Dockerfile"
        echo -e "${GREEN}✓ Dockerfile created${NC}"
    else
        echo -e "${RED}❌ Template Dockerfile not found${NC}"
        echo "Please create a Dockerfile in your Nuxt project manually."
        echo "See: FRONTEND_SETUP_GUIDE.md"
        exit 1
    fi
fi

# Check if .dockerignore exists
if [ ! -f "$NUXT_PATH/.dockerignore" ]; then
    echo -e "${YELLOW}Creating .dockerignore...${NC}"
    cat > "$NUXT_PATH/.dockerignore" << 'EOF'
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
EOF
    echo -e "${GREEN}✓ .dockerignore created${NC}"
fi

# Update docker-compose.yml path if needed
COMPOSE_PATH_LINE=$(grep "context: " docker-compose.yml | grep "frontend" | head -1)
if [[ $COMPOSE_PATH_LINE != *"$NUXT_PATH"* ]]; then
    echo -e "${YELLOW}⚠️  Updating docker-compose.yml with correct Nuxt path...${NC}"
    # Note: This is a simple approach, you may want to update manually
    echo -e "${YELLOW}Please ensure line 183 in docker-compose.yml points to: $NUXT_PATH${NC}"
fi

echo ""
echo -e "${BLUE}Starting services...${NC}"
echo ""

# Start backend first (if not running)
if ! docker compose ps backend | grep -q "Up"; then
    echo -e "${BLUE}Starting backend services...${NC}"
    docker compose --profile dev up -d postgres redis backend celery_worker celery_beat

    echo -e "${BLUE}Waiting for backend to be ready...${NC}"
    sleep 10
fi

# Start frontend
echo -e "${BLUE}Starting frontend...${NC}"
docker compose up -d frontend

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}   Services Started Successfully!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "${GREEN}Frontend:${NC}  http://localhost:3000"
echo -e "${GREEN}Backend:${NC}   http://localhost:8000/api/"
echo -e "${GREEN}Admin:${NC}     http://localhost:8000/admin/"
echo -e "${GREEN}Flower:${NC}    http://localhost:5555"
echo ""
echo -e "${BLUE}View logs:${NC}"
echo "  docker compose logs -f frontend"
echo ""
echo -e "${BLUE}Stop services:${NC}"
echo "  docker compose down"
echo ""
