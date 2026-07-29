import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')
django.setup()

from django_tenants.utils import schema_context
from academic.models import Teacher, AllocatedSubject, ClassRoom

schema_name = 'green_valley_academy'

with schema_context(schema_name):
    all_teachers = list(Teacher.objects.all().order_by('id'))
    total_count = len(all_teachers)
    print(f"Total teachers before cleanup in '{schema_name}': {total_count}")

    if total_count > 20:
        keep_teachers = all_teachers[:20]
        delete_teachers = all_teachers[20:]
        fallback_teacher = keep_teachers[0]
        
        print(f"Keeping first 20 teachers, removing remaining {len(delete_teachers)} duplicates...")

        for t in delete_teachers:
            # Reassign foreign keys before deletion
            ClassRoom.objects.filter(class_teacher=t).update(class_teacher=fallback_teacher)
            AllocatedSubject.objects.filter(teacher_name=t).update(teacher_name=fallback_teacher)
            
            user = t.user
            t.delete()
            if user and not user.is_superuser and not user.is_admin:
                user.delete()

        remaining = Teacher.objects.count()
        print(f"🎉 CLEANUP COMPLETE! Active teachers count is now: {remaining}")
    else:
        print("Teacher count is already 20 or fewer!")
