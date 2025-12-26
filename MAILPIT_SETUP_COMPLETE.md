# ✅ Mailpit Integration Complete

## What Changed

### 1. **Email Backend Now Uses Mailpit**

Updated `.env` to use Mailpit SMTP server:
```bash
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=localhost
EMAIL_PORT=1025
```

### 2. **School Name Now Dynamic from Database**

The email system now gets the school name from the `SchoolSettings` model in the database instead of using a hardcoded value.

**Updated:** `core/email_utils.py`

**New Function:**
```python
def get_school_settings():
    """Get school settings from database"""
    # Gets school_name, contact_email, contact_phone, etc. from SchoolSettings model
    # Falls back to settings.py if database not available
```

**What This Means:**
- School name in emails: `ABC High School` (from your database)
- Previously: `SureStart Schools` (hardcoded)
- Updates automatically when you change school settings

### 3. **All Email Functions Use Dynamic School Name**

Updated functions:
- `send_teacher_invitation()` - Subject: "Invitation to Join **ABC High School** as a Teacher"
- `send_parent_invitation()` - Subject: "Parent Portal Invitation - **ABC High School**"
- `send_accountant_invitation()` - Subject: "Invitation to Join **ABC High School** - Finance Team"
- `send_welcome_parent_email()` - Subject: "Welcome to **ABC High School** Parent Portal"

## How to View Emails in Mailpit

### Step 1: Ensure Mailpit is Running
```bash
docker ps | grep mailpit
# Should show a running container on ports 1025 and 8025
```

If not running:
```bash
docker run -d -p 1025:1025 -p 8025:8025 mailpit/mailpit
```

### Step 2: Create a Teacher with Invitation

Via your frontend or API:
```json
POST /api/users/teachers/
{
  "email": "teacher@example.com",
  "first_name": "John",
  "last_name": "Doe",
  "empId": "EMP001",
  "subject_specialization": ["mathematics"],
  ...
  "send_invitation": true  // ← This triggers the email
}
```

### Step 3: View Email in Mailpit

Open your browser and go to:
```
http://localhost:8025
```

You'll see:
- ✅ Beautiful HTML email with your school name
- ✅ Subject: "Invitation to Join ABC High School as a Teacher"
- ✅ Professional template with gradient header
- ✅ Secure invitation link
- ✅ All school branding from database

## What Data Comes from Database

The email system now pulls these values from `SchoolSettings` model:

| Field | Used In | Example |
|-------|---------|---------|
| `school_name` | Subject line, email body | "ABC High School" |
| `contact_email` | Available in templates | "info@abchigh.com" |
| `contact_phone` | Available in templates | "+1234567890" |
| `website` | Available in templates | "https://abchigh.com" |
| `address` | Available in templates | "123 Main St" |
| `primary_color` | Available in templates | "#1E40AF" |

## Fallback Behavior

If database is not available (migrations not run, etc.), the system falls back to:
- School name from `settings.SCHOOL_NAME` (from `.env`)
- Other fields: `None`

## Testing

### Quick Test Script

```python
python manage.py shell

from core.email_utils import send_teacher_invitation
from users.models import UserInvitation, CustomUser

# Create invitation
admin = CustomUser.objects.filter(is_superuser=True).first()
invitation = UserInvitation.objects.create(
    email='test@example.com',
    first_name='Test',
    last_name='User',
    role='teacher',
    invited_by=admin
)

# Send email
send_teacher_invitation(invitation)

# Check http://localhost:8025 to see the email!

# Clean up
invitation.delete()
```

### Verify School Name

```python
python manage.py shell

from tenants.models import SchoolSettings

school = SchoolSettings.get_settings()
print(f"School name: {school.school_name}")
# Output: School name: ABC High School
```

## Update School Name

To change the school name in emails, update the database:

```python
python manage.py shell

from tenants.models import SchoolSettings

school = SchoolSettings.get_settings()
school.school_name = "Your New School Name"
school.save()

# All new emails will now use "Your New School Name"
```

Or via Django admin:
1. Go to `/admin/`
2. Navigate to "School Settings"
3. Update "School name"
4. Save
5. All new emails will use the updated name

## Files Modified

- ✅ `.env` - Added Mailpit SMTP configuration
- ✅ `core/email_utils.py` - Made school name dynamic from database
  - Added `get_school_settings()` function
  - Updated all email functions to use dynamic school name

## Success Checklist

✅ Mailpit running on localhost:1025 (SMTP) and localhost:8025 (Web UI)
✅ `.env` configured to use Mailpit
✅ School name pulled from `SchoolSettings` database model
✅ Email templates use dynamic school name
✅ All invitation emails (teacher, parent, accountant) updated
✅ Fallback to settings.py if database unavailable
✅ Tested and working - emails visible in Mailpit

## Next Steps (Optional)

1. **Customize email templates** to use additional school settings:
   - Add school logo to email header
   - Use `primary_color` for branding
   - Add contact info to footer

2. **Add more school settings** to emails:
   ```html
   <!-- In email templates -->
   <p>Questions? Contact us at {{ school_contact_email }}</p>
   <p>Phone: {{ school_contact_phone }}</p>
   ```

3. **Set up production SMTP** when ready:
   - Update `.env` with real SMTP credentials
   - Gmail, SendGrid, AWS SES, etc.

---

**Status:** ✅ Complete and Working
**School Name:** ABC High School (from database)
**Mailpit Web UI:** http://localhost:8025
**Date:** December 17, 2025
