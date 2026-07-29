import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

from django_tenants.utils import schema_context
from academic.models import Teacher, AllocatedSubject

schema_name = 'green_valley_academy'

with schema_context(schema_name):
    teachers = list(Teacher.objects.all().order_by('id'))
    allocations = list(AllocatedSubject.objects.all().order_by('id'))
    
    print(f"Rebalancing {len(allocations)} subject allocations across {len(teachers)} teachers in schema '{schema_name}'...")
    
    if not teachers:
        print("No teachers found!")
        sys.exit(1)
        
    for idx, alloc in enumerate(allocations):
        assigned_teacher = teachers[idx % len(teachers)]
        alloc.teacher_name = assigned_teacher
        alloc.save(update_fields=['teacher_name'])
        
    print(f"🎉 REBALANCE COMPLETE!")
    print(f"Subject allocations evenly distributed across {len(teachers)} teachers.")
