# Fee Payment Reminders - Complete Guide

## Overview

SSync now has **automatic fee payment reminder system** that sends notifications to parents:

✅ **7 days before** due date (normal priority, email)
✅ **3 days before** due date (high priority, email + SMS)
✅ **1 day before** due date (urgent, email + SMS)
✅ **Overdue** notices (weekly, urgent, email + SMS)

---

## How It Works

### 1. Set Due Dates on Fees

When creating or editing a fee structure, set the `due_date`:

```bash
POST /api/financial/fee-structures/
```

```json
{
  "name": "Term 1 Tuition",
  "fee_type": "Tuition",
  "amount": 150000,
  "academic_year": 1,
  "term": 1,
  "is_mandatory": true,
  "due_date": "2026-02-15"
}
```

### 2. Automatic Reminders

The system automatically checks daily at **8:00 AM** for:

- Fees due in 7 days → Send first reminder
- Fees due in 3 days → Send urgent reminder
- Fees due in 1 day → Send final reminder
- Overdue fees → Send weekly overdue notice

Reminders are only sent to parents with **unpaid or partially paid** fees.

---

## Setup

### 1. Run Migrations (First Time Only)

```bash
# Apply django-celery-beat migrations
docker compose exec backend python manage.py migrate
```

### 2. Configure Periodic Task

```bash
# Set up automatic daily reminders
docker compose exec backend python manage.py setup_fee_reminders
```

This creates a **Celery Beat periodic task** that runs daily at 8:00 AM.

### 3. Start Celery Services

Already done if you're using Docker:

```bash
docker compose --profile dev up -d
```

This starts:
- `celery_worker` - Processes reminder tasks
- `celery_beat` - Scheduler that triggers daily reminders
- `flower` - Monitoring UI at http://localhost:5555

---

## Manual Reminders

### Option 1: Send All Reminders Now (CLI)

```bash
# Manually trigger all fee reminders immediately
docker compose exec backend python manage.py send_fee_reminders_now
```

Output:
```
==================================================
Fee Reminders Sent!
==================================================

  7-day reminders sent:     15
  3-day reminders sent:     8
  1-day reminders sent:     3
  Overdue notices sent:     12

  Total:                    38
```

### Option 2: API - Send All Reminders

```bash
POST /api/financial/fee-structures/send_all_reminders/
```

```json
{
  "message": "Fee reminders task queued successfully",
  "task_id": "abc123",
  "check_status": "/api/tasks/abc123/"
}
```

Then check progress:
```bash
GET /api/tasks/abc123/
```

### Option 3: API - Send Reminder for Specific Fee

```bash
POST /api/financial/fee-structures/{id}/send_reminder/
```

**Optional custom message:**
```json
{
  "message": "Custom reminder message here"
}
```

Response:
```json
{
  "message": "Reminder task queued successfully",
  "task_id": "xyz789",
  "fee_structure": "Term 1 Tuition"
}
```

---

## Reminder Schedule Logic

### 7 Days Before (First Reminder)
- **Priority**: Normal
- **Channels**: Email + In-app
- **SMS**: No
- **Message**: "Reminder: Term 1 Tuition (₦150,000) is due in 7 days on February 15, 2026"

### 3 Days Before (Urgent Reminder)
- **Priority**: High
- **Channels**: Email + In-app + **SMS**
- **SMS**: Yes (if enabled in user preferences)
- **Message**: "Urgent: Term 1 Tuition (₦150,000) is due in 3 days on February 15, 2026. Please make payment soon."

### 1 Day Before (Final Reminder)
- **Priority**: Urgent
- **Channels**: Email + In-app + **SMS**
- **SMS**: Yes (always sent, ignores preferences)
- **Message**: "Final reminder: Term 1 Tuition (₦150,000) is due tomorrow on February 15, 2026. Please pay immediately."

### Overdue (Weekly Notices)
- **Priority**: Urgent
- **Channels**: Email + In-app + **SMS**
- **SMS**: Yes (always sent)
- **Schedule**: Sent on day 1, then every 7 days (day 7, 14, 21, etc.)
- **Message**: "Payment overdue: Term 1 Tuition (₦150,000) was due on February 15, 2026 (7 days ago). Please pay immediately to avoid penalties."

---

## Parent Notification Preferences

Parents can control which reminders they receive:

```bash
GET /api/notification-preferences/
```

```json
{
  "email_enabled": true,
  "email_fees": true,
  "sms_enabled": true,
  "sms_fees": true,
  "sms_urgent_only": false
}
```

**Note**: `urgent` priority reminders (1-day and overdue) **always bypass preferences** to ensure parents are notified of critical deadlines.

---

## API Endpoints

### Fee Structures

```bash
# List all fee structures
GET /api/financial/fee-structures/

# Create fee with due date
POST /api/financial/fee-structures/
{
  "name": "Transport Fee",
  "fee_type": "Transport",
  "amount": 25000,
  "academic_year": 1,
  "term": 1,
  "due_date": "2026-03-01",
  "is_mandatory": true
}

# Update fee due date
PUT /api/financial/fee-structures/{id}/
{
  "due_date": "2026-03-15"
}

# Send reminder for specific fee
POST /api/financial/fee-structures/{id}/send_reminder/
{
  "message": "Optional custom message"
}

# Send all fee reminders
POST /api/financial/fee-structures/send_all_reminders/
```

### Student Fee Assignments

```bash
# Get unpaid fees for a student
GET /api/financial/student-fee-assignments/?student={id}&is_waived=false

# Get balance for a student
GET /api/finance/fee-balance/?student={id}
```

### Check Task Status

```bash
GET /api/tasks/{task_id}/
```

---

## Monitoring

### Celery Flower Dashboard

Access at: http://localhost:5555

- View active workers
- Monitor task queue
- See task history
- Check for failures

### Check Periodic Task Schedule

```bash
# View scheduled tasks
docker compose exec backend python manage.py shell
```

```python
from django_celery_beat.models import PeriodicTask

tasks = PeriodicTask.objects.filter(enabled=True)
for task in tasks:
    print(f"{task.name}: {task.crontab} - Enabled: {task.enabled}")
```

### Test Reminders

```bash
# Create a test fee with due date tomorrow
POST /api/financial/fee-structures/
{
  "name": "Test Fee",
  "fee_type": "Other",
  "amount": 1000,
  "academic_year": 1,
  "term": 1,
  "due_date": "2026-01-05",  # Tomorrow
  "is_mandatory": false
}

# Assign to a test student
POST /api/financial/student-fee-assignments/
{
  "student": 1,
  "fee_structure": {fee_id},
  "term": 1,
  "amount_owed": 1000
}

# Trigger reminders manually
python manage.py send_fee_reminders_now
```

---

## Customization

### Change Reminder Schedule

Edit the periodic task:

```python
from django_celery_beat.models import PeriodicTask, CrontabSchedule

# Create new schedule (e.g., daily at 6:00 AM)
schedule = CrontabSchedule.objects.create(
    minute='0',
    hour='6',
    day_of_week='*',
    day_of_month='*',
    month_of_year='*'
)

# Update task
task = PeriodicTask.objects.get(name='Send Fee Payment Reminders')
task.crontab = schedule
task.save()
```

### Modify Reminder Days

Edit `finance/tasks.py` and change the timedelta values:

```python
# Change from 7 days to 14 days
week_ahead_date = today + timedelta(days=14)  # Was: days=7

# Change from 3 days to 5 days
three_days_ahead = today + timedelta(days=5)  # Was: days=3
```

### Custom Messages

Modify messages in `finance/tasks.py`:

```python
message=f'Reminder: {fee_structure.name} (₦{balance:,.2f}) is due in 7 days...'
```

---

## Production Deployment

### Environment Variables

```bash
# Email (required for reminders)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password

# SMS (optional - for Twilio or Africa's Talking)
SMS_ENABLED=True
SMS_PROVIDER=twilio
SMS_API_KEY=your-api-key
SMS_SENDER_ID=SCHOOL
```

### Celery Production Setup

See [CELERY_SETUP_GUIDE.md](CELERY_SETUP_GUIDE.md) for:
- Supervisor configuration
- Worker scaling
- Error handling
- Monitoring

---

## Troubleshooting

### Reminders Not Sending

1. **Check Celery workers are running:**
   ```bash
   docker compose ps celery_worker celery_beat
   ```

2. **Check periodic task is enabled:**
   ```bash
   docker compose exec backend python manage.py shell
   ```
   ```python
   from django_celery_beat.models import PeriodicTask
   task = PeriodicTask.objects.get(name='Send Fee Payment Reminders')
   print(f"Enabled: {task.enabled}")
   ```

3. **Check for task errors in Flower:**
   http://localhost:5555

4. **Manually test:**
   ```bash
   docker compose exec backend python manage.py send_fee_reminders_now
   ```

### No Parents Receiving Reminders

1. **Check parents are linked to students:**
   ```python
   from academic.models import Student
   student = Student.objects.get(id=1)
   print(student.parent)  # Should not be None
   ```

2. **Check parent has user account:**
   ```python
   from users.models import CustomUser
   parent_user = CustomUser.objects.filter(email=student.parent.email, is_parent=True).first()
   print(parent_user)  # Should exist
   ```

3. **Check notification preferences:**
   ```bash
   GET /api/notification-preferences/  # As parent user
   ```

### Email Not Sending

Check email configuration and test:

```bash
docker compose exec backend python manage.py shell
```

```python
from django.core.mail import send_mail

send_mail(
    'Test Email',
    'This is a test.',
    'noreply@school.com',
    ['parent@example.com'],
    fail_silently=False,
)
```

If using Mailpit (development), check: http://localhost:8025

---

## Summary

✅ **Fee due dates** - Set on FeeStructure model
✅ **Automatic reminders** - Daily at 8 AM (7, 3, 1 days before + overdue)
✅ **Manual triggers** - CLI command or API endpoints
✅ **Multi-channel** - Email, in-app, SMS
✅ **Smart scheduling** - Respects preferences, escalates urgency
✅ **Full monitoring** - Flower dashboard + task status API
✅ **Production ready** - Celery + Redis + Beat scheduler

**Parents will never miss a payment deadline!** 💰📅
