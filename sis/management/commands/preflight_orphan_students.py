from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef
from academic.models import Student, StudentClassEnrollment
from administration.models import AcademicYear

class Command(BaseCommand):
    help = "Identifies active Students missing a current active StudentClassEnrollment"

    def handle(self, *args, **options):
        active_year = AcademicYear.objects.filter(active_year=True).first()
        if not active_year:
            self.stdout.write(self.style.ERROR("No active academic year found."))
            return

        active_enrollments = StudentClassEnrollment.objects.filter(
            student=OuterRef('pk'),
            academic_year=active_year,
            is_active=True
        )

        orphans = Student.objects.filter(
            is_active=True
        ).annotate(
            has_enrollment=Exists(active_enrollments)
        ).filter(
            has_enrollment=False
        )

        orphan_count = orphans.count()
        
        self.stdout.write(self.style.WARNING(f"Found {orphan_count} active students without an active enrollment for {active_year.name}."))

        if orphan_count > 0:
            for orphan in orphans:
                self.stdout.write(f"- {orphan.admission_number}: {orphan.first_name} {orphan.last_name}")
            
            self.stdout.write(self.style.NOTICE("\nRun an enrollment repair script or manually enroll these students to fix."))
