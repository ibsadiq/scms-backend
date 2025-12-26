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

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env.bool("DEBUG", default=True)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")


DATE_VALIDATORS = [MinValueValidator(date(1970, 1, 1))]  # Unix epoch!

# Application branding
APP_NAME = env('APP_NAME', default='SCMS')
SCHOOL_NAME = env('SCHOOL_NAME', default='School Management System')
FRONTEND_URL = env('FRONTEND_URL', default='http://localhost:3000')
BASE_URL = env('BASE_URL', default='http://localhost:8000')

# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.sites",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "rest_framework_simplejwt",
    "core.apps.CoreConfig",
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
    "users.apps.UsersConfig",
]

INSTALLED_APPS += ["tenants"]

MIDDLEWARE = [
    # "tenants.middleware.TenantMiddleware",  # Disabled - Single school mode
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
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
            "ENGINE": "django.db.backends.postgresql",
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
