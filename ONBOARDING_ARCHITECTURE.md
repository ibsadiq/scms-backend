# Tenant Onboarding System - Architecture Diagram

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (To Build)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Check Status │  │  Onboarding  │  │ Login Page   │          │
│  │   Component  │  │   Wizard     │  │              │          │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘          │
│         │                  │                                     │
└─────────┼──────────────────┼─────────────────────────────────────┘
          │                  │
          │ GET /check/      │ POST /step1/, /step2/, etc.
          ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                      MIDDLEWARE LAYER                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  TenantMiddleware:                                               │
│  1. Detect tenant from subdomain                                │
│  2. Check onboarding_completed flag                             │
│  3. Block access if False (except allowed paths)                │
│  4. Return 403 error with redirect info                         │
│                                                                  │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                       URL ROUTING                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  /api/tenants/onboarding/check/           → OnboardingCheckView │
│  /api/tenants/onboarding/step1/...        → Step1CreateTenant   │
│  /api/tenants/onboarding/step2/...        → Step2CreateAdmin    │
│  /api/tenants/onboarding/step3/...        → Step3ConfigSettings │
│  /api/tenants/onboarding/step4/complete/  → Step4Complete       │
│  /api/tenants/onboarding/skip-to-complete/→ SkipToComplete      │
│                                                                  │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                         VIEWS LAYER                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────┐  │
│  │ OnboardingCheck │  │  Step1: Create  │  │  Step2: Create │  │
│  │      View       │  │     Tenant      │  │   Admin User   │  │
│  └────────┬────────┘  └────────┬────────┘  └────────┬───────┘  │
│           │                    │                     │          │
│           ▼                    ▼                     ▼          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────┐  │
│  │  Step3: Config  │  │ Step4: Complete │  │ Skip to        │  │
│  │    Settings     │  │   Onboarding    │  │ Complete       │  │
│  └────────┬────────┘  └────────┬────────┘  └────────┬───────┘  │
│           │                    │                     │          │
└───────────┼────────────────────┼─────────────────────┼──────────┘
            │                    │                     │
            ▼                    ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                     SERIALIZERS LAYER                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  • OnboardingCheckSerializer      - Status checking              │
│  • TenantCreateSerializer         - Tenant creation             │
│  • AdminUserCreateSerializer      - Admin user creation         │
│  • TenantSettingsUpdateSerializer - Settings update             │
│  • CompleteOnboardingSerializer   - Completion confirmation     │
│  • TenantSerializer               - Full tenant data            │
│                                                                  │
│  Responsibilities:                                               │
│  - Input validation                                              │
│  - Data transformation                                           │
│  - Business logic enforcement                                    │
│                                                                  │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                       MODELS LAYER                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Tenant Model:                                                   │
│  ┌──────────────────────────────────────────────────────┐       │
│  │ • school_name: CharField                             │       │
│  │ • site: OneToOneField(Site)                          │       │
│  │ • logo: ImageField                                   │       │
│  │ • primary_color, secondary_color: CharField          │       │
│  │ • address, contact_email, contact_phone: CharField   │       │
│  │ • onboarding_completed: BooleanField ⭐ NEW          │       │
│  │ • admin_user: ForeignKey(CustomUser) ⭐ NEW          │       │
│  │ • created_at, updated_at: DateTimeField ⭐ NEW       │       │
│  │                                                      │       │
│  │ Property:                                            │       │
│  │ • needs_onboarding → not onboarding_completed       │       │
│  └──────────────────────────────────────────────────────┘       │
│                                                                  │
│  Related Models:                                                 │
│  • Site (Django contrib.sites)                                  │
│  • CustomUser (users.models)                                    │
│                                                                  │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DATABASE LAYER                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Tables:                                                         │
│  • tenants_tenant                                                │
│  • django_site                                                   │
│  • users_customuser                                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow Diagram

### Flow 1: Checking Onboarding Status

```
User Request
    │
    ▼
┌───────────────────┐
│ TenantMiddleware  │
│ Detects Tenant    │
│ from Subdomain    │
└─────────┬─────────┘
          │
          ▼
┌───────────────────────────────┐
│ Check onboarding_completed?   │
└─────────┬─────────────────────┘
          │
    ┌─────┴─────┐
    │           │
    ▼           ▼
  False       True
    │           │
    │           └──→ Allow Access
    │
    ▼
┌───────────────────┐
│ Check if path is  │
│ in ALLOWED_PATHS  │
└─────────┬─────────┘
          │
    ┌─────┴─────┐
    │           │
    ▼           ▼
   Yes         No
    │           │
    │           └──→ Return 403 Error
    │                "Onboarding Required"
    │
    └──→ Allow Access
```

### Flow 2: Complete Onboarding Process

```
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: Create Tenant                                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ POST /step1/create-tenant/                                  │
│ {                                                           │
│   "school_name": "ABC School",                              │
│   "primary_color": "#1E40AF"                                │
│ }                                                           │
│                                                             │
│ ┌──────────────────────────────────────────┐               │
│ │ TenantCreateSerializer                   │               │
│ │ • Validate school_name not empty         │               │
│ │ • Generate subdomain from school_name    │               │
│ │ • Check domain doesn't exist             │               │
│ └──────────────────┬───────────────────────┘               │
│                    ▼                                        │
│ ┌──────────────────────────────────────────┐               │
│ │ Create Site                              │               │
│ │ domain = "abcschool.localhost"           │               │
│ └──────────────────┬───────────────────────┘               │
│                    ▼                                        │
│ ┌──────────────────────────────────────────┐               │
│ │ Create Tenant                            │               │
│ │ onboarding_completed = False             │               │
│ │ admin_user = None                        │               │
│ └──────────────────┬───────────────────────┘               │
│                    ▼                                        │
│ Returns: {                                                  │
│   "tenant_id": 1,                                           │
│   "domain": "abcschool.localhost",                          │
│   "next_step": "create_admin_user"                          │
│ }                                                           │
└─────────────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 2: Create Admin User                                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ POST /step2/create-admin/                                   │
│ {                                                           │
│   "email": "admin@abc.com",                                 │
│   "password": "SecurePass123!",                             │
│   "confirm_password": "SecurePass123!",                     │
│   "first_name": "John"                                      │
│ }                                                           │
│                                                             │
│ ┌──────────────────────────────────────────┐               │
│ │ AdminUserCreateSerializer                │               │
│ │ • Validate email unique                  │               │
│ │ • Validate passwords match               │               │
│ │ • Validate password strength             │               │
│ └──────────────────┬───────────────────────┘               │
│                    ▼                                        │
│ ┌──────────────────────────────────────────┐               │
│ │ Create CustomUser                        │               │
│ │ is_staff = True                          │               │
│ │ is_superuser = True                      │               │
│ └──────────────────┬───────────────────────┘               │
│                    ▼                                        │
│ ┌──────────────────────────────────────────┐               │
│ │ Link to Tenant                           │               │
│ │ tenant.admin_user = user                 │               │
│ └──────────────────┬───────────────────────┘               │
│                    ▼                                        │
│ ┌──────────────────────────────────────────┐               │
│ │ Generate JWT Tokens                      │               │
│ │ RefreshToken.for_user(user)              │               │
│ └──────────────────┬───────────────────────┘               │
│                    ▼                                        │
│ Returns: {                                                  │
│   "user": {...},                                            │
│   "tokens": {                                               │
│     "access": "eyJ...",                                     │
│     "refresh": "eyJ..."                                     │
│   },                                                        │
│   "next_step": "configure_settings"                         │
│ }                                                           │
└─────────────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 3: Configure Settings (OPTIONAL)                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ PATCH /step3/configure-settings/                            │
│ Headers: Authorization: Bearer {access_token}               │
│ FormData: {                                                 │
│   "logo": <file>,                                           │
│   "primary_color": "#2E5090"                                │
│ }                                                           │
│                                                             │
│ ┌──────────────────────────────────────────┐               │
│ │ TenantSettingsUpdateSerializer           │               │
│ │ • Update tenant fields                   │               │
│ └──────────────────┬───────────────────────┘               │
│                    ▼                                        │
│ Returns: {                                                  │
│   "tenant": {...},                                          │
│   "next_step": "complete_onboarding"                        │
│ }                                                           │
└─────────────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 4: Complete Onboarding                                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ POST /step4/complete/ OR /skip-to-complete/                 │
│ Headers: Authorization: Bearer {access_token}               │
│ {                                                           │
│   "confirm": true                                           │
│ }                                                           │
│                                                             │
│ ┌──────────────────────────────────────────┐               │
│ │ Set onboarding_completed = True          │               │
│ │ tenant.save()                            │               │
│ └──────────────────┬───────────────────────┘               │
│                    ▼                                        │
│ Returns: {                                                  │
│   "message": "Onboarding completed!",                       │
│   "redirect_to": "login"                                    │
│ }                                                           │
└─────────────────────────────────────────────────────────────┘
                     │
                     ▼
              ┌─────────────┐
              │   SUCCESS   │
              │ Full Access │
              └─────────────┘
```

## Component Interaction Diagram

```
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│  Request: http://school.localhost/api/users/                   │
│                                                                │
└───────────────────────────┬────────────────────────────────────┘
                            │
                            ▼
              ┌─────────────────────────┐
              │  TenantMiddleware       │
              │  Execution              │
              └────────┬────────────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │ 1. Parse host from request  │
         │    host = "school.localhost"│
         └────────┬────────────────────┘
                  │
                  ▼
         ┌─────────────────────────────┐
         │ 2. Lookup Site              │
         │    Site.objects.get(        │
         │      domain=host            │
         │    )                        │
         └────────┬────────────────────┘
                  │
            ┌─────┴─────┐
            │           │
            ▼           ▼
        Found       Not Found
            │           │
            │           └──→ request.tenant = None
            │                → Continue
            ▼
    ┌──────────────────────┐
    │ 3. Get Tenant        │
    │    request.tenant =  │
    │    site.tenant       │
    └──────┬───────────────┘
           │
           ▼
    ┌──────────────────────────────┐
    │ 4. Check onboarding_completed│
    │    if not tenant.onboarding_ │
    │       completed              │
    └──────┬───────────────────────┘
           │
      ┌────┴────┐
      │         │
      ▼         ▼
   False      True
      │         │
      │         └──→ Continue to view
      ▼
┌────────────────────────┐
│ 5. Check if path       │
│    is in ALLOWED_PATHS │
└──────┬─────────────────┘
       │
  ┌────┴────┐
  │         │
  ▼         ▼
 Yes       No
  │         │
  │         └──→ Return JsonResponse 403
  │              {
  │                "onboarding_required": true,
  │                "redirect_to": "/api/tenants/onboarding/check/"
  │              }
  ▼
Continue to view
```

## State Machine Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                   Tenant Onboarding States                   │
└─────────────────────────────────────────────────────────────┘

    ┌──────────────────┐
    │  INITIAL STATE   │
    │                  │
    │ onboarding_      │
    │ completed = False│
    │ admin_user = None│
    └────────┬─────────┘
             │
             │ Step 1: Create Tenant
             ▼
    ┌──────────────────┐
    │ TENANT CREATED   │
    │                  │
    │ onboarding_      │
    │ completed = False│
    │ admin_user = None│
    └────────┬─────────┘
             │
             │ Step 2: Create Admin
             ▼
    ┌──────────────────┐
    │  ADMIN CREATED   │
    │                  │
    │ onboarding_      │
    │ completed = False│
    │ admin_user = Set │
    └────────┬─────────┘
             │
             │ Step 3: Configure (Optional)
             │ OR Skip to Complete
             ▼
    ┌──────────────────┐
    │   CONFIGURED     │
    │                  │
    │ onboarding_      │
    │ completed = False│
    │ admin_user = Set │
    │ settings updated │
    └────────┬─────────┘
             │
             │ Step 4: Complete
             ▼
    ┌──────────────────┐
    │   COMPLETED      │
    │                  │
    │ onboarding_      │
    │ completed = True │◄─── Final State
    │ admin_user = Set │     (Cannot revert)
    └──────────────────┘
```

## Security Flow

```
┌────────────────────────────────────────────────────────────┐
│                     Security Layers                         │
└────────────────────────────────────────────────────────────┘

Step 1 & 2: No Authentication Required
┌────────────────────┐
│ AllowAny           │  Anyone can create tenant & admin
└────────────────────┘

Step 2: Password Validation
┌────────────────────┐
│ • Min 8 characters │
│ • Must match       │  Django password validators
│ • Unique email     │
└────────────────────┘

Step 2: JWT Token Generation
┌────────────────────┐
│ RefreshToken       │  Tokens issued for immediate
│ + AccessToken      │  authentication
└────────────────────┘

Step 3 & 4: Authentication Required
┌────────────────────┐
│ IsAuthenticated    │  Must have valid JWT token
│ Permission         │  from Step 2
└────────────────────┘

Middleware: Path-based Access Control
┌────────────────────┐
│ ALLOWED_PATHS      │  Whitelist approach for
│ • /onboarding/*    │  onboarding endpoints
│ • /admin/*         │
└────────────────────┘

Database: Atomic Transactions
┌────────────────────┐
│ @transaction.atomic│  Ensures data consistency
└────────────────────┘
```

---

**This architecture provides:**
- ✅ Clear separation of concerns
- ✅ Secure authentication flow
- ✅ Flexible multi-step process
- ✅ Automatic enforcement via middleware
- ✅ Easy frontend integration
