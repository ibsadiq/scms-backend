import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()
from django.conf import settings
print(settings.DATABASE_ROUTERS)
