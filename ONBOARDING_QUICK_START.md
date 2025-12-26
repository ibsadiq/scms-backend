# Tenant Onboarding - Quick Start Guide

## Overview

The tenant onboarding system ensures that each new school completes the setup process before accessing the system. Here's how it works:

## Key Features

✅ **Checkbox System**: `onboarding_completed` field tracks completion status
✅ **Auto-redirect**: Incomplete tenants are redirected to onboarding
✅ **Admin Setup**: Creates admin user during onboarding
✅ **Settings Configuration**: Optional tenant customization
✅ **Seamless Login**: Auto-generates JWT tokens after admin creation

## The Flow

```
┌─────────────────────┐
│  Access Website     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Check Onboarding    │◄─── GET /api/tenants/onboarding/check/
│ Status              │
└──────────┬──────────┘
           │
     ┌─────┴─────┐
     │           │
     ▼           ▼
 Completed    Not Completed
     │           │
     │           ▼
     │    ┌─────────────────────┐
     │    │ Step 1: Create      │◄─── POST /step1/create-tenant/
     │    │ Tenant              │
     │    └──────────┬──────────┘
     │               │
     │               ▼
     │    ┌─────────────────────┐
     │    │ Step 2: Create      │◄─── POST /step2/create-admin/
     │    │ Admin User          │      (Returns JWT tokens)
     │    └──────────┬──────────┘
     │               │
     │         ┌─────┴─────┐
     │         │           │
     │         ▼           ▼
     │    ┌─────────┐  ┌─────────────┐
     │    │ Step 3  │  │ Skip to     │◄─── POST /skip-to-complete/
     │    │ Config  │  │ Complete    │
     │    └────┬────┘  └──────┬──────┘
     │         │              │
     │         ▼              │
     │    ┌─────────────────┐ │
     │    │ Step 4:         │ │
     │    │ Complete        │◄┘◄─── POST /step4/complete/
     │    └────┬────────────┘
     │         │
     └─────────┴─────┐
                     ▼
           ┌─────────────────────┐
           │ Redirect to Login   │
           └─────────────────────┘
```

## Quick Implementation

### Backend Setup (Already Done!)

1. ✅ Model updated with `onboarding_completed` field
2. ✅ Middleware enforces onboarding completion
3. ✅ Multi-step API endpoints created
4. ✅ Admin user creation integrated
5. ✅ JWT tokens auto-generated

### Frontend Integration (What You Need to Build)

#### 1. App Initialization
```javascript
// On app load, check if onboarding is needed
const response = await fetch('/api/tenants/onboarding/check/');
const { needs_onboarding } = await response.json();

if (needs_onboarding) {
  // Show onboarding wizard
  navigate('/onboarding');
} else {
  // Show login page
  navigate('/login');
}
```

#### 2. Onboarding Wizard Pages

**Page 1: School Information**
```javascript
// Collect: school_name, colors, contact info
const response = await fetch('/api/tenants/onboarding/step1/create-tenant/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    school_name: "My School",
    primary_color: "#1E40AF",
    contact_email: "admin@myschool.com"
  })
});
// Move to Step 2
```

**Page 2: Create Admin User**
```javascript
// Collect: email, password, name
const response = await fetch('/api/tenants/onboarding/step2/create-admin/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    email: "admin@myschool.com",
    password: "SecurePass123!",
    confirm_password: "SecurePass123!",
    first_name: "John",
    last_name: "Doe"
  })
});

const data = await response.json();
// IMPORTANT: Store these tokens!
localStorage.setItem('access_token', data.tokens.access);
localStorage.setItem('refresh_token', data.tokens.refresh);

// Move to Step 3 or Skip
```

**Page 3: Configure Settings (Optional)**
```javascript
// Option 1: Configure settings
const formData = new FormData();
formData.append('logo', logoFile);
formData.append('primary_color', '#2E5090');

await fetch('/api/tenants/onboarding/step3/configure-settings/', {
  method: 'PATCH',
  headers: {
    'Authorization': `Bearer ${accessToken}`
  },
  body: formData
});

// Option 2: Skip to complete
await fetch('/api/tenants/onboarding/skip-to-complete/', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json'
  }
});

// Redirect to login
window.location.href = '/login';
```

## API Endpoints Cheat Sheet

| Step | Endpoint | Data Needed |
|------|----------|-------------|
| Check | `GET /api/tenants/onboarding/check/` | None |
| Step 1 | `POST /step1/create-tenant/` | school_name, colors, contact |
| Step 2 | `POST /step2/create-admin/` | email, password, name |
| Step 3 | `PATCH /step3/configure-settings/` | logo, colors (optional) |
| Complete | `POST /step4/complete/` | confirm: true |
| Skip | `POST /skip-to-complete/` | None |

## Database Migration

```bash
# Run this to apply the new fields
source .venv/bin/activate
python manage.py migrate tenants
```

## Existing Tenants

If you have existing tenants that should skip onboarding:

```bash
python manage.py shell
```

```python
from tenants.models import Tenant
Tenant.objects.all().update(onboarding_completed=True)
```

## Testing

```bash
# Check tenant status
curl http://yourschool.localhost:8000/api/tenants/onboarding/check/

# Create tenant
curl -X POST http://yourschool.localhost:8000/api/tenants/onboarding/step1/create-tenant/ \
  -H "Content-Type: application/json" \
  -d '{"school_name": "Test School"}'
```

## What the Middleware Does

The middleware automatically:
- ✅ Detects the tenant from subdomain
- ✅ Checks if `onboarding_completed` is False
- ✅ Blocks access to all endpoints except:
  - `/api/tenants/onboarding/*`
  - `/api/tenants/debug/`
  - `/admin/`
  - `/static/`, `/media/`
- ✅ Returns helpful error with redirect information

## Example Error Response

When onboarding is not completed:
```json
{
  "error": "Onboarding required",
  "message": "This tenant has not completed onboarding. Please complete the setup process.",
  "onboarding_required": true,
  "redirect_to": "/api/tenants/onboarding/check/"
}
```

## Files Modified/Created

### Modified
- `tenants/models.py` - Added `onboarding_completed`, `admin_user`, `updated_at`
- `tenants/views.py` - Added multi-step onboarding views
- `tenants/middleware.py` - Added onboarding enforcement
- `tenants/admin.py` - Added Tenant admin interface
- `school/urls.py` - Added tenants URL include

### Created
- `tenants/serializers.py` - Onboarding serializers
- `tenants/urls.py` - Onboarding URL patterns
- `tenants/migrations/0002_*.py` - Database migration
- `TENANT_ONBOARDING_GUIDE.md` - Full documentation
- `ONBOARDING_QUICK_START.md` - This guide

## Next Steps

1. **Run Migrations**: `python manage.py migrate tenants`
2. **Build Frontend**: Create onboarding wizard UI
3. **Test Flow**: Test complete onboarding process
4. **Deploy**: Push changes to production

## Need Help?

- 📖 **Full Documentation**: See `TENANT_ONBOARDING_GUIDE.md`
- 🔍 **Debug**: Use `/api/tenants/debug/` to check tenant detection
- 🛠️ **Admin Panel**: Use `/admin/` to manually manage tenants

---

**Quick Reference**: The key is the `onboarding_completed` checkbox field - when False, users must complete onboarding; when True, they proceed to login! 🎉
