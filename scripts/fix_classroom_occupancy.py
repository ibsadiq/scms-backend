from django.db import transaction
from django.db.models import Count, Q
from academic.models import ClassRoom

def run():
    print("Recalculating classroom occupancies...")
    with transaction.atomic():
        # Annotate each classroom with the actual count of active enrollments
        classrooms = ClassRoom.objects.annotate(
            actual_occupancy=Count(
                'class_students', 
                filter=Q(class_students__is_active=True)
            )
        )
        
        updated_count = 0
        for classroom in classrooms:
            if classroom.occupied_sits != classroom.actual_occupancy:
                print(f"Fixing {classroom.name} (ID: {classroom.id}): {classroom.occupied_sits} -> {classroom.actual_occupancy}")
                classroom.occupied_sits = classroom.actual_occupancy
                classroom.save(update_fields=['occupied_sits'])
                updated_count += 1
                
        print(f"Finished! Fixed occupancy for {updated_count} classrooms.")

if __name__ == "__main__":
    run()
