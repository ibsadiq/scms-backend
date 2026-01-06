"""
Management command to manually trigger fee reminders immediately.

Usage:
    python manage.py send_fee_reminders_now
"""
from django.core.management.base import BaseCommand
from finance.tasks import send_fee_reminders


class Command(BaseCommand):
    help = 'Manually send fee payment reminders now (for testing or manual trigger)'

    def handle(self, *args, **options):
        self.stdout.write('Sending fee payment reminders...')
        self.stdout.write('')

        # Call the task directly (synchronously for testing)
        results = send_fee_reminders()

        self.stdout.write(self.style.SUCCESS('='*50))
        self.stdout.write(self.style.SUCCESS('Fee Reminders Sent!'))
        self.stdout.write(self.style.SUCCESS('='*50))
        self.stdout.write('')
        self.stdout.write(f'  7-day reminders sent:     {results["week_ahead"]}')
        self.stdout.write(f'  3-day reminders sent:     {results["three_days"]}')
        self.stdout.write(f'  1-day reminders sent:     {results["tomorrow"]}')
        self.stdout.write(f'  Overdue notices sent:     {results["overdue"]}')
        self.stdout.write('')
        self.stdout.write(f'  Total:                    {sum([results["week_ahead"], results["three_days"], results["tomorrow"], results["overdue"]])}')

        if results['errors']:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(f'  Errors: {len(results["errors"])}'))
            for error in results['errors'][:5]:  # Show first 5 errors
                self.stdout.write(self.style.WARNING(f'    - {error}'))
            if len(results['errors']) > 5:
                self.stdout.write(self.style.WARNING(f'    ... and {len(results["errors"]) - 5} more'))

        self.stdout.write('')
