# Email Invitation System - Complete Implementation

## Summary

Successfully implemented a comprehensive email invitation system for the School Management System. The system now automatically sends professional invitation emails when creating teachers, parents, or accountants with the `send_invitation=true` flag.

## What Was Implemented

### 1. **Email Utility Module** (`core/email_utils.py`)

Created a reusable email utility module with functions for:
- Generic email sending with HTML templates
- Teacher invitation emails
- Parent invitation emails
- Accountant invitation emails
- Welcome emails for parents

**Key Features:**
- Uses Django's template system
- Supports both HTML and plain text emails
- Configurable via environment variables
- Graceful error handling

### 2. **Email Templates**

Created professional, responsive email templates:

**Templates Created:**
- `core/templates/email/invitation_teacher.html` & `.txt`
- `core/templates/email/invitation_parent.html`
- `core/templates/email/invitation_accountant.html`

**Template Features:**
- Responsive design (works on mobile & desktop)
- Beautiful gradient header with school branding
- Clear call-to-action buttons
- Expiry warnings
- Professional footer

**Reuses existing base template:**
- `core/templates/email/base.html` - Professional email layout
- `core/templates/email/welcome_parent.html` - Already exists

### 3. **Updated Serializers**

Modified all user creation serializers to send emails:

**Files Updated:**
- `users/serializers.py`:
  - `TeacherSerializer.create()` - Sends teacher invitations
  - `AccountantSerializer.create()` - Sends accountant invitations
  - `ParentSerializer.create()` - Sends parent invitations

**How It Works:**
1. When `send_invitation=true` is passed during creation
2. UserInvitation record is created with a secure token
3. Invitation email is automatically sent
4. User receives email with link to set their password

### 4. **Settings Configuration**

**Updated:** `school/settings.py`

Added new settings:
```python
FRONTEND_URL = env('FRONTEND_URL', default='http://localhost:3000')
BASE_URL = env('BASE_URL', default='http://localhost:8000')
```

**Email Backend Configuration:**

**Development Mode (DEBUG=True):**
- Default: Console backend (prints emails to terminal)
- Alternative: Mailpit SMTP server
- Alternative: File backend

**Production Mode (DEBUG=False):**
- Uses SMTP server configured in `.env`
- Supports Gmail, SendGrid, AWS SES, etc.

## How to Use

### Creating a Teacher with Email Invitation

**API Request:**
```json
POST /api/users/teachers/

{
  "email": "john.doe@example.com",
  "first_name": "John",
  "middle_name": "M",
  "last_name": "Doe",
  "phone_number": "+1234567890",
  "empId": "EMP001",
  "short_name": "JMD",
  "subject_specialization": ["mathematics", "physics"],
  "address": "123 Main St",
  "salary": 50000,
  "send_invitation": true
}
```

**What Happens:**
1. ✅ Teacher account is created
2. ✅ User account is created with random password
3. ✅ UserInvitation record is created
4. ✅ Professional email sent to teacher
5. ✅ Teacher receives link: `http://localhost:3000/accept-invitation/{token}`
6. ✅ Teacher clicks link and sets their own password

### Without Email Invitation (Default)

```json
{
  ...
  "send_invitation": false  // or omit this field
}
```

**What Happens:**
1. ✅ Teacher account is created
2. ✅ User account created with password: `Complex.{last4_of_empId}`
3. ❌ No email sent
4. ✅ Admin manually communicates credentials to teacher

## Email Configuration

### Option 1: Console Backend (Current - Development)

Emails are printed to the terminal where the Django server is running.

**Configuration:** Already set as default in DEBUG mode

**Pros:**
- No setup required
- Instant feedback
- Perfect for development

**Cons:**
- Not sent to actual email addresses
- Only visible in terminal

### Option 2: Mailpit (Recommended for Development)

Mailpit is a local SMTP server with a web UI for viewing emails.

**Setup:**
```bash
# Run Mailpit in Docker
docker run -d -p 1025:1025 -p 8025:8025 mailpit/mailpit

# Update .env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=localhost
EMAIL_PORT=1025
```

**Access emails:** http://localhost:8025

**Pros:**
- See actual rendered emails
- Test email delivery without sending real emails
- Beautiful web interface
- Supports attachments, HTML, etc.

**Cons:**
- Requires Docker

### Option 3: Real SMTP (Production)

**Gmail Example:**

1. **Enable 2FA** on your Gmail account
2. **Create App Password:** Google Account → Security → 2-Step Verification → App passwords
3. **Update `.env`:**

```bash
DEBUG=False
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=School System <your-email@gmail.com>
```

**SendGrid Example:**

```bash
EMAIL_HOST=smtp.sendgrid.net
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=your-sendgrid-api-key
DEFAULT_FROM_EMAIL=School System <noreply@yourdomain.com>
```

## Environment Variables

**Required for email invitations:**
```bash
# .env file

# Frontend URL (where users will set their password)
FRONTEND_URL=http://localhost:3000

# School branding
APP_NAME=SCMS
SCHOOL_NAME=SureStart Schools

# Email settings (production only)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=School System <noreply@example.com>
```

## Testing the Email System

### Test Email Sending

```python
python manage.py shell

from core.email_utils import send_teacher_invitation
from users.models import UserInvitation, CustomUser

# Create test invitation
admin = CustomUser.objects.filter(is_superuser=True).first()
invitation = UserInvitation.objects.create(
    email='test@example.com',
    first_name='Test',
    last_name='Teacher',
    role='teacher',
    invited_by=admin
)

# Send email
send_teacher_invitation(invitation)

# Check your terminal (console backend) or Mailpit (localhost:8025)
```

### Test Complete Flow

1. **Start Django server:**
   ```bash
   python manage.py runserver
   ```

2. **Create teacher via API with `send_invitation: true`**

3. **Check email:**
   - Console backend: Check terminal output
   - Mailpit: Visit http://localhost:8025
   - Real SMTP: Check actual inbox

4. **User receives email with invitation link**

5. **User clicks link → redirects to frontend → sets password → account active**

## Email Templates Customization

All templates are in `core/templates/email/`:

**To customize branding:**
- Edit `base.html` - Change colors, logo, footer
- Edit individual invitation templates - Change content, icons, structure

**Template Variables:**
- `{{ app_name }}` - Application name (SCMS)
- `{{ school_name }}` - School name (SureStart Schools)
- `{{ recipient_name }}` - User's full name
- `{{ invitation_url }}` - Link to accept invitation
- `{{ days_until_expiry }}` - Days until invitation expires
- `{{ portal_url }}` - Link to login portal

## Troubleshooting

### Email not sending (Console Backend)
**Solution:** Check terminal where Django server is running

### Email not sending (Mailpit)
```bash
# Check Mailpit is running
docker ps | grep mailpit

# Restart Mailpit
docker run -d -p 1025:1025 -p 8025:8025 mailpit/mailpit
```

### Email not sending (Gmail)
- Enable 2FA
- Use App Password, not regular password
- Check "Less secure app access" if using old Gmail accounts
- Verify EMAIL_HOST_USER and EMAIL_HOST_PASSWORD in .env

### Invitation link not working
- Check FRONTEND_URL in settings
- Ensure frontend is running on that URL
- Verify frontend has route `/accept-invitation/:token`

## API Endpoints

### Create Teacher (with invitation)
```
POST /api/users/teachers/
Body: { ..., "send_invitation": true }
```

### Create Parent (with invitation)
```
POST /api/users/parents/
Body: { ..., "send_invitation": true }
```

### Create Accountant (with invitation)
```
POST /api/users/accountants/
Body: { ..., "send_invitation": true }
```

### List Invitations
```
GET /api/users/invitations/
GET /api/users/invitations/?role=teacher
```

### Validate Invitation
```
GET /api/users/invitations/validate/{token}/
```

### Accept Invitation
```
POST /api/users/invitations/accept/
Body: {
  "token": "invitation-token",
  "password": "newpassword123",
  "password_confirm": "newpassword123"
}
```

## Security Features

✅ **Secure Tokens:** 64-character random tokens
✅ **Expiration:** Invitations expire after 7 days
✅ **One-time Use:** Tokens are invalidated after acceptance
✅ **Password Validation:** Minimum 8 characters
✅ **HTTPS Support:** Works with SSL/TLS
✅ **No Password in Email:** Users set their own password

## Next Steps

### Recommended for Production

1. **Set up real SMTP server** (Gmail, SendGrid, AWS SES)
2. **Configure custom domain** for email sender
3. **Add email logging** for audit trail
4. **Implement resend invitation** functionality
5. **Add email templates for:**
   - Password reset
   - Account activation
   - Welcome messages
   - Fee reminders (already exists)
   - Absence notifications (already exists)

### Optional Enhancements

- Email preview before sending
- Bulk invitation sending
- Custom email templates per school
- Email analytics (open rate, click rate)
- Attachment support

## Files Modified/Created

### Created:
- ✅ `core/email_utils.py` - Email utility functions
- ✅ `core/templates/email/invitation_teacher.html`
- ✅ `core/templates/email/invitation_teacher.txt`
- ✅ `core/templates/email/invitation_parent.html`
- ✅ `core/templates/email/invitation_accountant.html`

### Modified:
- ✅ `users/serializers.py` - Added email sending to create methods
- ✅ `school/settings.py` - Added FRONTEND_URL, improved email config

### Already Existed (Reused):
- ✅ `core/templates/email/base.html` - Email base template
- ✅ `core/templates/email/welcome_parent.html` - Parent welcome email
- ✅ `users/models.py` - UserInvitation model

## Success Criteria

✅ Teacher creation with `send_invitation=true` sends email
✅ Parent creation with `send_invitation=true` sends email
✅ Accountant creation with `send_invitation=true` sends email
✅ Emails use professional HTML templates
✅ Emails include secure invitation links
✅ System works in development (console backend)
✅ System ready for production (SMTP backend)
✅ Graceful error handling (doesn't break user creation if email fails)

---

**Status:** ✅ Fully Implemented and Tested
**Date:** December 17, 2025
**Developer:** Claude
