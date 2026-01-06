"""
Management command to set up periodic fee reminder tasks.

Usage:
    python manage.py setup_fee_reminders
"""
from django.core.management.base import BaseCommand
from django_celery_beat.models import PeriodicTask, CrontabSchedule
import json


class Command(BaseCommand):
    help = 'Set up periodic fee reminder tasks in Celery Beat'

    def handle(self, *args, **options):
        self.stdout.write('Setting up fee reminder periodic tasks...')

        # Create schedule: Daily at 8:00 AM
        schedule, created = CrontabSchedule.objects.get_or_create(
            minute='0',
            hour='8',
            day_of_week='*',
            day_of_month='*',
            month_of_year='*',
        )

        if created:
            self.stdout.write(self.style.SUCCESS('✓ Created daily 8 AM schedule'))
        else:
            self.stdout.write('  Daily 8 AM schedule already exists')

        # Create periodic task for fee reminders
        task, created = PeriodicTask.objects.get_or_create(
            name='Send Fee Payment Reminders',
            defaults={
                'crontab': schedule,
                'task': 'finance.send_fee_reminders',
                'enabled': True,
                'description': 'Sends automatic fee payment reminders to parents (7 days, 3 days, 1 day before due date, and overdue notices)'
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS('✓ Created "Send Fee Payment Reminders" periodic task'))
        else:
            self.stdout.write('  "Send Fee Payment Reminders" task already exists')
            # Update it to ensure it's enabled
            task.enabled = True
            task.save()
            self.stdout.write(self.style.SUCCESS('  ✓ Enabled the task'))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('='*50))
        self.stdout.write(self.style.SUCCESS('Fee Reminder Setup Complete!'))
        self.stdout.write(self.style.SUCCESS('='*50))
        self.stdout.write('')
        self.stdout.write('The system will now automatically send fee reminders:')
        self.stdout.write('  • 7 days before due date (normal priority)')
        self.stdout.write('  • 3 days before due date (high priority + SMS)')
        self.stdout.write('  • 1 day before due date (urgent + SMS)')
        self.stdout.write('  • Overdue notices (weekly)')
        self.stdout.write('')
        self.stdout.write('Schedule: Daily at 8:00 AM')
        self.stdout.write('')
        self.stdout.write('To manually send reminders now, run:')
        self.stdout.write('  python manage.py send_fee_reminders_now')
        self.stdout.write('')
