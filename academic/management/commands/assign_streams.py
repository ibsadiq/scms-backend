"""
Management command to assign streams to classrooms for testing
"""

from django.core.management.base import BaseCommand
from academic.models import ClassRoom, Stream


class Command(BaseCommand):
    help = 'Assigns streams to classrooms for testing purposes'

    def handle(self, *args, **options):
        streams = list(Stream.objects.all())

        if not streams:
            self.stdout.write(self.style.ERROR('No streams found. Create streams first.'))
            return

        classrooms = ClassRoom.objects.all()
        total = classrooms.count()

        if total == 0:
            self.stdout.write(self.style.ERROR('No classrooms found.'))
            return

        self.stdout.write(f'Assigning streams to {total} classrooms...')

        updated = 0
        for i, classroom in enumerate(classrooms):
            # Only assign streams to Senior Secondary (SS) classes
            if 'SS' not in classroom.grade_level.system_code and 'SS' not in str(classroom.grade_level):
                if classroom.stream:
                    classroom.stream = None
                    classroom.save()
                continue

            # Cycle through streams (Science, Commerce, Arts)
            stream = streams[i % len(streams)]
            classroom.stream = stream
            classroom.save()
            updated += 1
            self.stdout.write(f'  - {classroom.display_name} → Stream {stream.name}')

        self.stdout.write(
            self.style.SUCCESS(f'\nSuccessfully assigned streams to {updated} classrooms!')
        )
