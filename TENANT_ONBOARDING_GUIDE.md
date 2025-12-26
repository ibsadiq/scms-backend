# Tenant Onboarding System - Complete Guide

## Overview

The Tenant Onboarding System provides a multi-step setup wizard for new school tenants. It ensures that each tenant completes the necessary setup steps before accessing the system, including creating an admin user and configuring basic settings.

## Features

- **Multi-step onboarding flow** with clear progression
- **Onboarding status tracking** via `onboarding_completed` flag
- **Admin user creation** during setup
- **Automatic JWT token generation** for seamless login after admin creation
- **Middleware enforcement** to redirect incomplete onboarding
- **Flexible flow** with optional configuration steps

## Database Schema Changes

### Tenant Model Updates

Three new fields have been added to the `Tenant` model:

```python
# Onboarding status flag
onboarding_completed = models.BooleanField(default=False)

# Reference to the admin user created during onboarding
admin_user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True)

# Track when tenant settings were last updated
updated_at = models.DateTimeField(auto_now=True)
```

## Onboarding Flow

### Step 1: Create Tenant
**Endpoint:** `POST /api/tenants/onboarding/step1/create-tenant/`

Creates a new tenant with basic school information.

**Request Body:**
```json
{
  "school_name": "ABC High School",
  "primary_color": "#1E40AF",
  "secondary_color": "#BA770F",
  "address": "123 Main Street",
  "contact_email": "admin@abchighschool.com",
  "contact_phone": "+1234567890"
}
```

**Response:**
```json
{
  "message": "Tenant created successfully",
  "tenant_id": 1,
  "domain": "abchighschool.localhost",
  "school_name": "ABC High School",
  "next_step": "create_admin_user"
}
```

### Step 2: Create Admin User
**Endpoint:** `POST /api/tenants/onboarding/step2/create-admin/`

Creates the primary admin user for the tenant. This step automatically logs in the user by returning JWT tokens.

**Request Body:**
```json
{
  "email": "admin@abchighschool.com",
  "password": "SecurePassword123!",
  "confirm_password": "SecurePassword123!",
  "first_name": "John",
  "last_name": "Doe",
  "phone_number": "+1234567890"
}
```

**Response:**
```json
{
  "message": "Admin user created successfully",
  "user": {
    "id": 1,
    "email": "admin@abchighschool.com",
    "first_name": "John",
    "last_name": "Doe"
  },
  "tokens": {
    "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "access": "eyJ0eXAiOiJKV1QiLCJhbGc..."
  },
  "next_step": "configure_settings"
}
```

**Important:** Store the JWT tokens and use them for subsequent authenticated requests.

### Step 3: Configure Settings (Optional)
**Endpoint:** `PATCH /api/tenants/onboarding/step3/configure-settings/`

Update additional tenant settings like logo, colors, etc. This step requires authentication with the tokens from Step 2.

**Headers:**
```
Authorization: Bearer <access_token>
Content-Type: multipart/form-data
```

**Request Body (multipart/form-data):**
```
school_name: ABC High School Updated
logo: <file>
primary_color: #2E5090
secondary_color: #CA880F
```

**Response:**
```json
{
  "message": "Settings updated successfully",
  "tenant": {
    "id": 1,
    "school_name": "ABC High School Updated",
    "logo": "/media/tenant_logos/logo.png",
    "primary_color": "#2E5090",
    "secondary_color": "#CA880F",
    "onboarding_completed": false,
    "needs_onboarding": true,
    "domain": "abchighschool.localhost"
  },
  "next_step": "complete_onboarding"
}
```

**Get Current Settings:**
```
GET /api/tenants/onboarding/step3/configure-settings/
```

### Step 4: Complete Onboarding
**Endpoint:** `POST /api/tenants/onboarding/step4/complete/`

Marks the onboarding process as complete. After this, the tenant can access all system features.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "confirm": true
}
```

**Response:**
```json
{
  "message": "Onboarding completed successfully! You can now log in.",
  "tenant": {
    "id": 1,
    "school_name": "ABC High School",
    "onboarding_completed": true,
    "needs_onboarding": false,
    "domain": "abchighschool.localhost",
    "admin_email": "admin@abchighschool.com"
  },
  "redirect_to": "login"
}
```

### Skip to Complete (Shortcut)
**Endpoint:** `POST /api/tenants/onboarding/skip-to-complete/`

Skips optional configuration steps and marks onboarding as complete immediately after admin user creation.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response:**
```json
{
  "message": "Onboarding completed successfully!",
  "tenant": {
    "id": 1,
    "school_name": "ABC High School",
    "onboarding_completed": true,
    "needs_onboarding": false
  },
  "redirect_to": "login"
}
```

## Utility Endpoints

### Check Onboarding Status
**Endpoint:** `GET /api/tenants/onboarding/check/`

Check if the current tenant needs to complete onboarding.

**Response (Onboarding Incomplete):**
```json
{
  "onboarding_completed": false,
  "needs_onboarding": true,
  "school_name": "ABC High School",
  "tenant_id": 1
}
```

**Response (Onboarding Complete):**
```json
{
  "onboarding_completed": true,
  "needs_onboarding": false,
  "school_name": "ABC High School",
  "tenant_id": 1
}
```

### Debug Tenant Detection
**Endpoint:** `GET /api/tenants/debug/`

Debug endpoint to verify tenant detection from subdomain.

**Response:**
```json
{
  "school_name": "ABC High School",
  "primary_color": "#1E40AF",
  "onboarding_completed": false
}
```

## Middleware Enforcement

The `TenantMiddleware` automatically enforces onboarding completion. If a tenant exists but hasn't completed onboarding, all API requests (except allowed paths) will return:

```json
{
  "error": "Onboarding required",
  "message": "This tenant has not completed onboarding. Please complete the setup process.",
  "onboarding_required": true,
  "redirect_to": "/api/tenants/onboarding/check/"
}
```

### Allowed Paths (Bypass Onboarding)
The following paths are accessible even without completing onboarding:
- `/api/tenants/onboarding/*` - All onboarding endpoints
- `/api/tenants/debug/` - Debug endpoint
- `/api/schema/` - API schema
- `/admin/` - Django admin
- `/static/` - Static files
- `/media/` - Media files

## Frontend Integration Guide

### 1. On Page Load / App Initialization

```javascript
// Check onboarding status when the app loads
async function checkOnboardingStatus() {
  try {
    const response = await fetch('/api/tenants/onboarding/check/');
    const data = await response.json();

    if (data.needs_onboarding) {
      // Redirect to onboarding wizard
      window.location.href = '/onboarding';
    } else {
      // Proceed to login or dashboard
      window.location.href = '/login';
    }
  } catch (error) {
    console.error('Error checking onboarding status:', error);
  }
}
```

### 2. Onboarding Wizard Component

```javascript
// React/Vue example - multi-step wizard
const OnboardingWizard = () => {
  const [step, setStep] = useState(1);
  const [tenantData, setTenantData] = useState({});
  const [tokens, setTokens] = useState(null);

  // Step 1: Create Tenant
  const createTenant = async (formData) => {
    const response = await fetch('/api/tenants/onboarding/step1/create-tenant/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formData)
    });
    const data = await response.json();
    setTenantData(data);
    setStep(2);
  };

  // Step 2: Create Admin User
  const createAdminUser = async (formData) => {
    const response = await fetch('/api/tenants/onboarding/step2/create-admin/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formData)
    });
    const data = await response.json();

    // Store tokens
    setTokens(data.tokens);
    localStorage.setItem('access_token', data.tokens.access);
    localStorage.setItem('refresh_token', data.tokens.refresh);

    setStep(3);
  };

  // Step 3: Configure Settings (Optional)
  const configureSettings = async (formData) => {
    const response = await fetch('/api/tenants/onboarding/step3/configure-settings/', {
      method: 'PATCH',
      headers: {
        'Authorization': `Bearer ${tokens.access}`
      },
      body: formData // multipart/form-data
    });
    const data = await response.json();
    setStep(4);
  };

  // Step 4: Complete Onboarding
  const completeOnboarding = async () => {
    const response = await fetch('/api/tenants/onboarding/step4/complete/', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${tokens.access}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ confirm: true })
    });
    const data = await response.json();

    // Redirect to login
    window.location.href = '/login';
  };

  // Skip to complete
  const skipToComplete = async () => {
    const response = await fetch('/api/tenants/onboarding/skip-to-complete/', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${tokens.access}`,
        'Content-Type': 'application/json'
      }
    });
    const data = await response.json();
    window.location.href = '/login';
  };

  // Render appropriate step component
  return (
    <div>
      {step === 1 && <CreateTenantForm onSubmit={createTenant} />}
      {step === 2 && <CreateAdminForm onSubmit={createAdminUser} />}
      {step === 3 && <ConfigureSettingsForm onSubmit={configureSettings} onSkip={skipToComplete} />}
      {step === 4 && <CompleteOnboardingForm onSubmit={completeOnboarding} />}
    </div>
  );
};
```

### 3. Error Handling

```javascript
// Global error handler for 403 onboarding errors
axios.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.data?.onboarding_required) {
      // Redirect to onboarding
      window.location.href = '/onboarding';
    }
    return Promise.reject(error);
  }
);
```

## Migration Instructions

### 1. Run Migrations

```bash
# Activate virtual environment
source .venv/bin/activate

# Create migrations
python manage.py makemigrations tenants

# Apply migrations
python manage.py migrate tenants
```

### 2. Update Existing Tenants (Optional)

If you have existing tenants that should bypass onboarding, you can mark them as completed:

```python
# Python shell
python manage.py shell

from tenants.models import Tenant

# Mark all existing tenants as onboarding completed
Tenant.objects.all().update(onboarding_completed=True)

# Or mark specific tenant
tenant = Tenant.objects.get(school_name="My School")
tenant.onboarding_completed = True
tenant.save()
```

## Testing the Onboarding Flow

### Manual Testing with cURL

```bash
# Step 1: Create Tenant
curl -X POST http://abchighschool.localhost:8000/api/tenants/onboarding/step1/create-tenant/ \
  -H "Content-Type: application/json" \
  -d '{
    "school_name": "ABC High School",
    "primary_color": "#1E40AF",
    "contact_email": "admin@abc.com"
  }'

# Step 2: Create Admin User
curl -X POST http://abchighschool.localhost:8000/api/tenants/onboarding/step2/create-admin/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@abc.com",
    "password": "SecurePass123!",
    "confirm_password": "SecurePass123!",
    "first_name": "John",
    "last_name": "Doe"
  }'

# Store the access token from the response, then:

# Step 4: Complete Onboarding (skip step 3)
curl -X POST http://abchighschool.localhost:8000/api/tenants/onboarding/skip-to-complete/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json"
```

## Security Considerations

1. **Password Validation**: Admin passwords must be at least 8 characters
2. **Email Uniqueness**: Each admin email must be unique across the system
3. **JWT Authentication**: Steps 3 and 4 require valid JWT tokens
4. **CSRF Protection**: Ensure CSRF tokens are included in frontend requests
5. **HTTPS**: Always use HTTPS in production to protect credentials

## Admin Panel Access

Administrators can manage tenants through the Django admin panel at `/admin/`:

- View all tenants and their onboarding status
- Manually mark onboarding as complete/incomplete
- Update tenant settings
- View associated admin users

## Troubleshooting

### Issue: "No tenant found" error
**Solution:** Ensure the subdomain matches the tenant's site domain. Check that the Site object exists and is linked to the tenant.

### Issue: "Onboarding already completed" error
**Solution:** The tenant has already completed onboarding. To restart, set `onboarding_completed = False` in the admin panel.

### Issue: Middleware blocking all requests
**Solution:** Verify that the request path is not in the `ALLOWED_PATHS` list or that onboarding is actually completed.

### Issue: Cannot create admin user - email already exists
**Solution:** Use a different email address, or delete the existing user if it was created by mistake.

## Future Enhancements

Potential improvements for the onboarding system:

1. **Email Verification**: Send verification email to admin during Step 2
2. **School Logo Upload**: Add logo upload in Step 1 or Step 3
3. **Academic Year Setup**: Add academic year configuration as part of onboarding
4. **Multi-language Support**: Support for different languages during onboarding
5. **Onboarding Analytics**: Track completion rates and drop-off points
6. **Welcome Email**: Send welcome email upon completion
7. **Video Tutorials**: Embed video guides in each step

## API Endpoints Summary

| Endpoint | Method | Auth Required | Description |
|----------|--------|---------------|-------------|
| `/api/tenants/onboarding/check/` | GET | No | Check onboarding status |
| `/api/tenants/onboarding/step1/create-tenant/` | POST | No | Create new tenant |
| `/api/tenants/onboarding/step2/create-admin/` | POST | No | Create admin user |
| `/api/tenants/onboarding/step3/configure-settings/` | PATCH/GET | Yes | Configure tenant settings |
| `/api/tenants/onboarding/step4/complete/` | POST | Yes | Complete onboarding |
| `/api/tenants/onboarding/skip-to-complete/` | POST | Yes | Skip to completion |
| `/api/tenants/debug/` | GET | No | Debug tenant detection |

---

**Created:** December 2024
**Version:** 1.0
**Maintained by:** SCMS Development Team
