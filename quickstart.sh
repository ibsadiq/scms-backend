#!/bin/bash
# Django School Management System - Quick Start Script

echo "=================================================="
echo "Django School Management System - Quick Start"
echo "=================================================="
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}⚠️  Virtual environment not found. Creating one...${NC}"
    uv venv
fi

# Run system verification
echo -e "${BLUE}🔍 Running system verification...${NC}"
uv run python verify_system.py

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ System verification passed!${NC}"
    echo ""
else
    echo -e "${YELLOW}⚠️  System verification failed. Please check the errors above.${NC}"
    echo ""
    exit 1
fi

# Check migrations
echo -e "${BLUE}🔍 Checking migrations...${NC}"
PENDING=$(uv run python manage.py showmigrations 2>/dev/null | grep "[ ]" | wc -l)

if [ $PENDING -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Found $PENDING pending migrations. Applying...${NC}"
    uv run python manage.py migrate
else
    echo -e "${GREEN}✅ All migrations applied${NC}"
fi

echo ""
echo "=================================================="
echo -e "${GREEN}🎉 System is ready!${NC}"
echo "=================================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Start the development server:"
echo -e "   ${BLUE}uv run python manage.py runserver${NC}"
echo ""
echo "2. Access the system:"
echo "   Admin Panel:    http://localhost:8000/admin/"
echo "   API Docs:       http://localhost:8000/"
echo "   API Endpoints:  http://localhost:8000/api/"
echo ""
echo "3. Create a superuser (if not done):"
echo -e "   ${BLUE}uv run python manage.py createsuperuser${NC}"
echo ""
echo "4. Read the documentation:"
echo "   - SYSTEM_READY_GUIDE.md - Complete usage guide"
echo "   - FINAL_SYSTEM_STATUS.md - System status and features"
echo "   - PHASE_1_7_ASSIGNMENTS_SUMMARY.md - Assignment system docs"
echo ""
echo "=================================================="
echo -e "${GREEN}Happy coding! 🚀${NC}"
echo "=================================================="
