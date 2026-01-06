#!/bin/bash
# SSync - Start Celery Worker and Beat Scheduler

echo "=================================================="
echo "SSync - Starting Celery Services"
echo "=================================================="
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if Redis is running
echo -e "${BLUE}🔍 Checking Redis connection...${NC}"
if ! redis-cli ping > /dev/null 2>&1; then
    echo -e "${RED}❌ Redis is not running!${NC}"
    echo ""
    echo "Please start Redis first:"
    echo "  - Ubuntu/Debian: sudo systemctl start redis"
    echo "  - macOS: brew services start redis"
    echo "  - Docker: docker run -d -p 6379:6379 redis:latest"
    echo ""
    exit 1
fi
echo -e "${GREEN}✅ Redis is running${NC}"
echo ""

# Check which service to start
if [ "$1" = "worker" ]; then
    echo -e "${BLUE}🚀 Starting Celery Worker...${NC}"
    echo ""
    uv run celery -A school worker --loglevel=info
elif [ "$1" = "beat" ]; then
    echo -e "${BLUE}⏰ Starting Celery Beat Scheduler...${NC}"
    echo ""
    uv run celery -A school beat --loglevel=info
elif [ "$1" = "flower" ]; then
    echo -e "${BLUE}🌸 Starting Flower Monitoring...${NC}"
    echo ""
    echo "Install Flower if not already installed:"
    echo "  uv pip install flower"
    echo ""
    uv run celery -A school flower
else
    echo "Usage: ./start_celery.sh [worker|beat|flower]"
    echo ""
    echo "Options:"
    echo "  worker  - Start Celery worker to process tasks"
    echo "  beat    - Start Celery beat scheduler for periodic tasks"
    echo "  flower  - Start Flower web monitoring tool"
    echo ""
    echo "Example:"
    echo "  ./start_celery.sh worker"
    echo ""
    exit 1
fi
