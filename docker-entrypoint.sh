#!/bin/bash
# SSync - Docker Entrypoint Script
# Handles database migrations, static files, and superuser creation

set -e

echo "=================================================="
echo "SSync - Starting Django Application"
echo "=================================================="
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Wait for PostgreSQL
echo -e "${BLUE}🔍 Waiting for PostgreSQL...${NC}"
while ! pg_isready -h $DB_HOST -p $DB_PORT -U $DB_USER > /dev/null 2>&1; do
    echo "PostgreSQL is unavailable - sleeping"
    sleep 1
done
echo -e "${GREEN}✅ PostgreSQL is ready${NC}"
echo ""

# Wait for Redis
# Wait for Redis
echo -e "${BLUE}🔍 Waiting for Redis...${NC}"
until python -c "import socket; s=socket.socket(); s.settimeout(1); s.connect(('$REDIS_HOST', $REDIS_PORT)); s.close()" 2>/dev/null; do
    echo "Redis is unavailable - sleeping"
    sleep 1
done
echo -e "${GREEN}✅ Redis is ready${NC}"
echo ""

# Ensure PostgreSQL public schema exists
echo -e "${BLUE}🛠️  Ensuring public schema exists...${NC}"
python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute('CREATE SCHEMA IF NOT EXISTS public;')
" || true

# Run database migrations
echo -e "${BLUE}🔄 Running database migrations...${NC}"
python manage.py migrate --noinput
echo -e "${GREEN}✅ Migrations complete${NC}"
echo ""

# Setup public tenant & primary domain
echo -e "${BLUE}🏢 Setting up public tenant and domain...${NC}"
python manage.py setup_public_tenant || true
echo ""

# Collect static files
echo -e "${BLUE}📦 Collecting static files...${NC}"
python manage.py collectstatic --noinput --clear
echo -e "${GREEN}✅ Static files collected${NC}"
echo ""

# Create cache table (if using database cache)
echo -e "${BLUE}🗄️  Creating cache table...${NC}"
python manage.py createcachetable 2>/dev/null || echo "Cache table already exists or not using database cache"
echo ""

# Create superuser if it doesn't exist (only in development)
if [ "$DEBUG" = "True" ]; then
    echo -e "${BLUE}👤 Creating superuser (development only)...${NC}"
    python manage.py shell << END
from users.models import CustomUser
if not CustomUser.objects.filter(email='admin@ssync.local').exists():
    CustomUser.objects.create_superuser(email='admin@ssync.local', password='admin123', first_name='Admin', last_name='User')
    print('Superuser created: admin@ssync.local / admin123')
else:
    print('Superuser already exists')
END
    echo ""
fi

echo "=================================================="
echo -e "${GREEN}🚀 SSync is ready!${NC}"
echo "=================================================="
echo ""

# Execute the main command
exec "$@"
