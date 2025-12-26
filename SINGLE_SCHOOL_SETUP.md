# Single School Setup - Simplified Onboarding

The system has been converted from multi-tenant to **single school mode**.

## Changes Made

### 1. Disabled Tenant Middleware
- **File**: `school/settings.py`
- Commented out `TenantMiddleware` - no more tenant detection required
- System now works for a single school installation

### 2. Renamed Model
- **Old**: `Tenant` model (multi-tenant)
- **New**: `SchoolSettings` model (single school)
- Enforces only ONE school instance in the database
- `Tenant` kept as alias for backward compatibility

### 3. Simplified Onboarding Flow
All onboarding endpoints now work **without requiring tenant context**:

#### Endpoint: `/api/tenants/onboarding/check/`
**GET** - Check onboarding status
- Returns school info if exists
- Returns `needs_onboarding: true` for fresh installations

#### Endpoint: `/api/tenants/onboarding/step1/create-tenant/`
**POST** - Create/update school information
```json
{
  "school_name": "My School",
  "primary_color": "#1E40AF",
  "contact_email": "admin@myschool.com",
  "contact_phone": "+1234567890",
  "address": "123 School Street"
}
```

#### Endpoint: `/api/tenants/onboarding/step2/create-admin/`
**POST** - Create admin user
```json
{
  "email": "admin@myschool.com",
  "password": "SecurePass123!",
  "confirm_password": "SecurePass123!",
  "first_name": "Admin",
  "last_name": "User"
}
```
Returns JWT tokens for immediate login.

#### Endpoint: `/api/tenants/onboarding/step3/configure-settings/`
**PATCH** - Update branding (authenticated)
```json
{
  "logo": "<file>",
  "primary_color": "#1E40AF",
  "secondary_color": "#BA770F"
}
```

#### Endpoint: `/api/tenants/onboarding/skip-to-complete/`
**POST** - Skip optional steps and complete (authenticated)

## Migration Applied
- **Migration**: `tenants/migrations/0005_schoolsettings_delete_tenant.py`
- Converts existing Tenant data to SchoolSettings
- Applied successfully ✅

## Testing Results

✅ Fresh installation detected correctly
✅ School creation works (`step1`)
✅ Onboarding status updates properly
✅ No tenant middleware required

## Usage for Frontend

```javascript
// 1. Check if onboarding needed
const response = await fetch('/api/tenants/onboarding/check/');
const { needs_onboarding, school_name, onboarding_step } = await response.json();

if (needs_onboarding) {
  // Show onboarding wizard
  // Start with step 1: School Information
}

// 2. Create school (Step 1)
await fetch('/api/tenants/onboarding/step1/create-tenant/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    school_name: "My School",
    contact_email: "admin@school.com"
  })
});

// 3. Create admin (Step 2)
const adminResponse = await fetch('/api/tenants/onboarding/step2/create-admin/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    email: "admin@school.com",
    password: "SecurePass123!",
    confirm_password: "SecurePass123!",
    first_name: "Admin",
    last_name: "User"
  })
});

const { tokens } = await adminResponse.json();
// Store tokens.access and tokens.refresh

// 4. Skip to complete (or continue with step 3)
await fetch('/api/tenants/onboarding/skip-to-complete/', {
  method: 'POST',
  headers: { 
    'Authorization': `Bearer ${tokens.access}`,
    'Content-Type': 'application/json'
  }
});
```

## Admin Panel
Access at `/admin/` to manage school settings manually.
- Only ONE SchoolSettings instance allowed
- Cannot be deleted (protected)

## Key Features
- ✅ **Simple**: No complex tenant routing
- ✅ **Single school**: One installation = one school
- ✅ **Guided setup**: 4-step onboarding wizard
- ✅ **Flexible**: Can skip optional branding steps
- ✅ **Secure**: Admin creation with JWT authentication
