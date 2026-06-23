import os
import environ
from pathlib import Path
from datetime import timedelta, date
from django.core.validators import MinValueValidator  # Could use MaxValueValidator too

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env(
    "SECRET_KEY", default="2_5ub5rqi!%3v#xk$0e4z-jg22zg_$ejz&t3s0g$5lt*vvu!b@"
)

BASE_DOMAIN = env("BASE_DOMAIN", default="localhost")
# slug used by frontend/backend to indicate the public schema
PUBLIC_TENANT_SLUG = env("PUBLIC_TENANT_SLUG", default="public")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env.bool("DEBUG", default=True)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")


DATE_VALIDATORS = [MinValueValidator(date(1970, 1, 1))]  # Unix epoch!

# Application branding
APP_NAME = env('APP_NAME', default='SSync School Management System')
FRONTEND_URL = env('FRONTEND_URL', default='http://localhost:3000')
BACKEND_URL  = env('BACKEND_URL',  default='http://localhost:8000')
BASE_DOMAIN = env('BASE_DOMAIN', default='localhost')

SUPPORT_EMAIL = env('SUPPORT_EMAIL', default='support@ssyncportal.com')
PLATFORM_LOGO_URL = env('PLATFORM_LOGO_URL', default=f"{BACKEND_URL}/static/images/platform_logo.png")

# Application definition
# settings.py

# ==============================================================================
# 1. SHARED APPS (Public Schema)
# These apps exist in the "Landing Page" or "SaaS Admin" layer.
# ==============================================================================
SHARED_APPS = [
    "django_tenants",  # MANDATORY: Must be at the top
    "tenants",      

    # Standard Django (Required for Public Admin)
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.sites",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third Party (Global Configs)
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_celery_results", # Centralized task results
    "django_celery_beat",    # Centralized periodic tasks

    # Your Shared Apps
    "core.apps.CoreConfig",   # Base utilities
    "users.apps.UsersConfig", # IMPORTANT: Needed here for the SaaS SuperAdmin
]

# ==============================================================================
# 2. TENANT APPS (School Schemas)
# These apps exist separately for EACH school. 
# Data in "School A" is physically invisible to "School B".
# ==============================================================================
TENANT_APPS = [
    
    "django.contrib.auth",
    "django.contrib.contenttypes",

    # Your Business Logic Apps
    "users.apps.UsersConfig", # IMPORTANT: Needed here for Students/Teachers
    "academic.apps.AcademicConfig",
    "administration.apps.AdministrationConfig",
    "assignments.apps.AssignmentsConfig",
    "attendance.apps.AttendanceConfig",
    "examination.apps.ExaminationConfig",
    "finance.apps.FinanceConfig",
    "notes.apps.NotesConfig",
    "notifications.apps.NotificationsConfig",
    "schedule.apps.ScheduleConfig",
    "sis.apps.SisConfig",
]

# ==============================================================================
# 3. CONSOLIDATION
# Django needs a single list to boot up.
# ==============================================================================
INSTALLED_APPS = list(SHARED_APPS) + [
    app for app in TENANT_APPS if app not in SHARED_APPS
]

# ==============================================================================
# 4. TENANT CONFIGURATION
# ==============================================================================
TENANT_MODEL = "tenants.Client"
TENANT_DOMAIN_MODEL = "tenants.Domain"

DATABASE_ROUTERS = (
    'django_tenants.routers.TenantSyncRouter',
)

MIDDLEWARE = [
    # CORS should be as high as possible so preflight requests are handled early
    "corsheaders.middleware.CorsMiddleware",
    "django_tenants.middleware.main.TenantMainMiddleware", 
    "tenants.tenant_header_middleware.TenantHeaderMiddleware",  # handle header before access check
    "tenants.middleware.TenantAccessMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "api.middleware.CustomExceptionMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "school.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            os.path.join(BASE_DIR, "static/dist"),
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "school.wsgi.application"


# Database
# https://docs.djangoproject.com/en/3.1/ref/settings/#databases
DB_NAME = env("DB_NAME", default=None)


if DB_NAME:
    # PostgreSQL mode
    DATABASES = {
        "default": {
            "ENGINE": "django_tenants.postgresql_backend",
            "NAME": DB_NAME,
            "USER": env("DB_USER"),
            "PASSWORD": env("DB_PASSWORD"),
            "HOST": env("DB_HOST", default="localhost"),
            "PORT": env("DB_PORT", default="5432"),
        }
    }
else:
    # SQLite fallback mode
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
    print("⚠️  Using SQLite (no .env or DB vars found)")


# Password validation
# https://docs.djangoproject.com/en/3.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/3.1/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_L10N = True

USE_TZ = True

SITE_ID = 1


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.1/howto/static-files/


STATIC_URL = "/static/"
MEDIA_URL = "/media/"

STATICFILES_DIRS = [
    BASE_DIR / "static",  # your app-level static (optional)
    BASE_DIR / "static/dist/assets",  # vite/react build output
]

STATIC_ROOT = BASE_DIR / "staticfiles"  # final destination after collectstatic
MEDIA_ROOT = BASE_DIR / "media"  # uploads

# ── Cloud storage (S3-compatible) ────────────────────────────────────────────
# Set USE_S3=True in production. Works with AWS S3, DigitalOcean Spaces, MinIO.
USE_S3 = env.bool('USE_S3', default=False)

if USE_S3:
    AWS_ACCESS_KEY_ID       = env('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY   = env('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = env('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME      = env('AWS_S3_REGION_NAME', default='us-east-1')
    # For non-AWS providers (DO Spaces, MinIO) set the provider endpoint
    AWS_S3_ENDPOINT_URL     = env('AWS_S3_ENDPOINT_URL', default=None)
    # Optional CDN domain — e.g. 'cdn.yourdomain.com' or '<bucket>.nyc3.cdn.digitaloceanspaces.com'
    AWS_S3_CUSTOM_DOMAIN    = env('AWS_S3_CUSTOM_DOMAIN', default=None)
    AWS_DEFAULT_ACL         = env('AWS_DEFAULT_ACL', default='public-read')
    AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}
    AWS_QUERYSTRING_AUTH    = False   # public files don't need signed URLs

    STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    # Use Django's standard `django.contrib.auth` permissions,
    # or allow read-only access for unauthenticated users.
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',

    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "EXCEPTION_HANDLER": "api.exceptions.custom_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",

}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
    "ALGORITHM": "HS256",
    "VERIFYING_KEY": None,
    "AUDIENCE": None,
    "ISSUER": None,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
    "JTI_CLAIM": "jti"
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Your API',
    'DESCRIPTION': 'Your API description',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    # Add these to help with schema generation
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': r'/api/',
}
CORS_ALLOW_ALL_ORIGINS = True

# Explicitly trust the base domain and all subdomains for CSRF validation (Django Admin login, etc.)
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
    f"https://{BASE_DOMAIN}",
    f"http://{BASE_DOMAIN}",
    f"https://*.{BASE_DOMAIN}",
    f"http://*.{BASE_DOMAIN}",
]
# Allow custom headers used by frontend to select tenant
from corsheaders.defaults import default_headers
CORS_ALLOW_HEADERS = list(default_headers) + [
    'x-tenant-slug',
]

AUTH_USER_MODEL = "users.CustomUser"

INTERNAL_IPS = [
    "127.0.0.1",
]

# ==============================================================================
# EMAIL CONFIGURATION
# ==============================================================================
# Development: Use Mailpit (local SMTP server for testing)
# Production: Use real SMTP server from environment variables

if DEBUG:
    # Development email configuration
    # Options:
    # 1. Console backend (prints to terminal) - default
    # 2. Mailpit (requires: docker run -d -p 1025:1025 -p 8025:8025 mailpit/mailpit)
    # 3. File backend (saves to file)

    # Use console backend by default, can override with EMAIL_BACKEND in .env
    EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')

    # If using SMTP (Mailpit), these settings apply:
    EMAIL_HOST = env('EMAIL_HOST', default='localhost')
    EMAIL_PORT = env.int('EMAIL_PORT', default=1025)
    EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=False)
    EMAIL_USE_SSL = env.bool('EMAIL_USE_SSL', default=False)
    EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
    EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')

    DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='School Management System <noreply@scms.test>')
    SERVER_EMAIL = env('SERVER_EMAIL', default='server@scms.test')
else:
    # Production email configuration from .env
    EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
    EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
    EMAIL_PORT = env.int('EMAIL_PORT', default=587)
    EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
    EMAIL_USE_SSL = env.bool('EMAIL_USE_SSL', default=False)
    EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
    EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
    DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='noreply@example.com')
    SERVER_EMAIL = env('SERVER_EMAIL', default='server@example.com')

# Email timeout (applies to both dev and prod)
EMAIL_TIMEOUT = 10

# ==============================================================================
# SMS CONFIGURATION
# ==============================================================================
# Provider: 'africastalking' (default, for Nigeria/Africa) or 'twilio'
SMS_ENABLED  = env.bool('SMS_ENABLED', default=False)
SMS_PROVIDER = env('SMS_PROVIDER', default='africastalking')

# Africa's Talking
AT_USERNAME  = env('AT_USERNAME', default='')
AT_API_KEY   = env('AT_API_KEY', default='')
AT_SENDER_ID = env('AT_SENDER_ID', default='')   # Optional shortcode/alphanumeric

# Twilio (fallback)
TWILIO_ACCOUNT_SID  = env('TWILIO_ACCOUNT_SID', default='')
TWILIO_AUTH_TOKEN   = env('TWILIO_AUTH_TOKEN', default='')
TWILIO_PHONE_NUMBER = env('TWILIO_PHONE_NUMBER', default='')

# ==============================================================================
# CELERY CONFIGURATION
# ==============================================================================
# Celery settings for asynchronous task processing
# Requires Redis server running (see documentation)

# Celery broker URL (Redis)
CELERY_BROKER_URL = env('CELERY_BROKER_URL', default='redis://localhost:6379/0')

# Celery result backend (store results in Django database)
CELERY_RESULT_BACKEND = 'django-db'

# Use JSON for serialization (more secure than pickle)
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'

# Time zone settings
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = USE_TZ

# Task result expiration (7 days)
CELERY_RESULT_EXPIRES = 60 * 60 * 24 * 7

# Task time limits (prevent hanging tasks)
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes hard limit
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # 25 minutes soft limit

# Celery Beat schedule for periodic tasks (if needed in future)
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# Task routing (optional - for organizing tasks)
CELERY_TASK_ROUTES = {
    'academic.tasks.*': {'queue': 'academic'},
    'users.tasks.*': {'queue': 'users'},
    'examination.tasks.*': {'queue': 'examination'},
    'finance.tasks.*': {'queue': 'finance'},
}

# Worker configuration
CELERY_WORKER_PREFETCH_MULTIPLIER = 4
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000  # Restart worker after 1000 tasks to prevent memory leaks
