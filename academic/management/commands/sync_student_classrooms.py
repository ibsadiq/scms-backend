from django.core.management.base import BaseCommand
from django.db import transaction
from academic.models import Student, StudentClassEnrollment
from administration.models import AcademicYear


class Command(BaseCommand):
    help = 'Sync Student.classroom field with StudentClassEnrollment for current academic year'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Get the current/active academic year
        try:
            current_year = AcademicYear.objects.get(active_year=True)
        except AcademicYear.DoesNotExist:
            self.stdout.write(self.style.ERROR('No active academic year found'))
            return
        except AcademicYear.MultipleObjectsReturned:
            self.stdout.write(self.style.ERROR('Multiple active academic years found'))
            return

        self.stdout.write(f'Processing enrollments for academic year: {current_year}')

        # Get all student class enrollments for the current academic year
        enrollments = StudentClassEnrollment.objects.filter(
            academic_year=current_year
        ).select_related('student', 'classroom')

        updates_needed = 0
        updated_students = []

        for enrollment in enrollments:
            if enrollment.student:
                # Check if student's classroom field needs updating
                if enrollment.student.classroom != enrollment.classroom:
                    updates_needed += 1
                    updated_students.append({
                        'student_id': enrollment.student.id,
                        'student_name': enrollment.student.full_name,
                        'old_classroom': str(enrollment.student.classroom) if enrollment.student.classroom else 'None',
                        'new_classroom': str(enrollment.classroom),
                    })

                    if not dry_run:
                        # Update the student's classroom
                        Student.objects.filter(pk=enrollment.student.pk).update(
                            classroom=enrollment.classroom
                        )

        # Display results
        if dry_run:
            self.stdout.write(self.style.WARNING(f'\nDRY RUN - No changes made'))
        
        self.stdout.write(self.style.SUCCESS(f'\nTotal enrollments checked: {enrollments.count()}'))
        self.stdout.write(self.style.SUCCESS(f'Students needing update: {updates_needed}'))

        if updates_needed > 0:
            self.stdout.write('\nStudents to be updated:')
            for student in updated_students:
                self.stdout.write(
                    f"  - {student['student_name']} (ID: {student['student_id']}): "
                    f"{student['old_classroom']} → {student['new_classroom']}"
                )

        if not dry_run and updates_needed > 0:
            self.stdout.write(self.style.SUCCESS(f'\n✓ Successfully updated {updates_needed} students'))
        elif updates_needed == 0:
            self.stdout.write(self.style.SUCCESS('\n✓ All students already in sync!'))
