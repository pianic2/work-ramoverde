import os
from datetime import timedelta
from pathlib import Path
from typing import Any

import dj_database_url

BASE_DIR = Path(__file__).resolve().parents[2]
DEVELOPMENT_SECRET_KEY = "insecure-development-key-change-before-production-use"  # noqa: S105
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", DEVELOPMENT_SECRET_KEY)
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = [host for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost").split(",") if host]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

INSTALLED_APPS = [
    "apps.accounts.apps.StaffAdminConfig",  # django.contrib.admin, locked down
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "drf_spectacular",
    "rest_framework_simplejwt.token_blacklist",
    "apps.core",
    "apps.audit",
    "apps.accounts",
    "apps.media",
    "apps.cms",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "apps.core.middleware.RequestIdMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

DATABASES = {
    "default": dj_database_url.config(
        default="postgresql://app:app@localhost:5440/app", conn_max_age=60
    )
}
AUTH_USER_MODEL = "accounts.User"
LANGUAGE_CODE = "it"
TIME_ZONE = "Europe/Rome"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES: dict[str, Any] = {
    "default": {
        "BACKEND": os.getenv(
            "DJANGO_DEFAULT_FILE_STORAGE", "django.core.files.storage.FileSystemStorage"
        )
    },
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Django excludes uploaded file bytes from DATA_UPLOAD_MAX_MEMORY_SIZE; larger files
# are streamed to temporary storage once FILE_UPLOAD_MAX_MEMORY_SIZE is exceeded.
DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv("DJANGO_DATA_UPLOAD_MAX_MEMORY_SIZE", "2621440"))
DATA_UPLOAD_MAX_NUMBER_FIELDS = int(os.getenv("DJANGO_DATA_UPLOAD_MAX_NUMBER_FIELDS", "1000"))
DATA_UPLOAD_MAX_NUMBER_FILES = int(os.getenv("DJANGO_DATA_UPLOAD_MAX_NUMBER_FILES", "20"))
FILE_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv("DJANGO_FILE_UPLOAD_MAX_MEMORY_SIZE", "2621440"))

CORS_ALLOWED_ORIGINS = [
    value for value in os.getenv("DJANGO_CORS_ALLOWED_ORIGINS", "").split(",") if value
]
CSRF_TRUSTED_ORIGINS = [
    value for value in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if value
]
CORS_ALLOW_CREDENTIALS = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "1025"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "false").lower() == "true"
EMAIL_BACKEND = (
    "django.core.mail.backends.smtp.EmailBackend"
    if os.getenv("EMAIL_ENABLED", "false").lower() == "true"
    else "django.core.mail.backends.console.EmailBackend"
)

if os.getenv("S3_STORAGE_ENABLED", "false").lower() == "true":
    if not os.getenv("S3_BUCKET_NAME"):
        raise RuntimeError("S3_BUCKET_NAME is required when S3_STORAGE_ENABLED=true")
    INSTALLED_APPS.append("storages")
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": os.environ["S3_BUCKET_NAME"],
            "endpoint_url": os.getenv("S3_ENDPOINT_URL") or None,
            "access_key": os.getenv("S3_ACCESS_KEY_ID") or None,
            "secret_key": os.getenv("S3_SECRET_ACCESS_KEY") or None,
            "default_acl": None,
            "file_overwrite": False,
        },
    }

# Media (WR-21): blobs live in object storage, never in PostgreSQL. Two logical storages keep
# PUBLIC and PRIVATE assets apart; locally they are directories outside STATIC_ROOT that
# Django never serves. In production S3_STORAGE_ENABLED switches both to S3/R2 buckets.
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", str(BASE_DIR / "mediafiles")))
MEDIA_PUBLIC_BASE_URL = os.getenv("MEDIA_PUBLIC_BASE_URL", "/media/public/")
MEDIA_MAX_UPLOAD_SIZE = int(os.getenv("MEDIA_MAX_UPLOAD_SIZE", str(15 * 1024 * 1024)))
MEDIA_MAX_VIDEO_UPLOAD_SIZE = int(os.getenv("MEDIA_MAX_VIDEO_UPLOAD_SIZE", str(200 * 1024 * 1024)))
MEDIA_MAX_IMAGE_PIXELS = int(os.getenv("MEDIA_MAX_IMAGE_PIXELS", str(50_000_000)))
MEDIA_PRIVATE_URL_TTL = int(os.getenv("MEDIA_PRIVATE_URL_TTL", "300"))
# True when the private storage can sign short-lived URLs (S3/R2); otherwise downloads stream.
MEDIA_PRIVATE_PRESIGNED_DOWNLOADS = False
STORAGES["media_public"] = {
    "BACKEND": "django.core.files.storage.FileSystemStorage",
    "OPTIONS": {"location": MEDIA_ROOT / "public", "base_url": MEDIA_PUBLIC_BASE_URL},
}
STORAGES["media_private"] = {
    "BACKEND": "django.core.files.storage.FileSystemStorage",
    "OPTIONS": {"location": MEDIA_ROOT / "private"},
}
if os.getenv("S3_STORAGE_ENABLED", "false").lower() == "true":
    _public_bucket = os.getenv("S3_PUBLIC_BUCKET_NAME") or os.environ["S3_BUCKET_NAME"]
    _private_bucket = os.getenv("S3_PRIVATE_BUCKET_NAME") or os.environ["S3_BUCKET_NAME"]
    if _public_bucket == _private_bucket:
        # A bucket is either publicly readable or not: sharing one would expose private media
        # (or hide public media). See docs/architecture/media.md.
        raise RuntimeError(
            "S3_PUBLIC_BUCKET_NAME and S3_PRIVATE_BUCKET_NAME must differ when "
            "S3_STORAGE_ENABLED=true"
        )
    _s3_common = {
        "endpoint_url": os.getenv("S3_ENDPOINT_URL") or None,
        "access_key": os.getenv("S3_ACCESS_KEY_ID") or None,
        "secret_key": os.getenv("S3_SECRET_ACCESS_KEY") or None,
        "default_acl": None,
        "file_overwrite": False,
    }
    STORAGES["media_public"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            **_s3_common,
            "bucket_name": _public_bucket,
            "location": os.getenv("S3_PUBLIC_LOCATION", "public"),
            "custom_domain": os.getenv("S3_PUBLIC_CUSTOM_DOMAIN") or None,
            "querystring_auth": False,
        },
    }
    STORAGES["media_private"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            **_s3_common,
            "bucket_name": _private_bucket,
            "location": os.getenv("S3_PRIVATE_LOCATION", "private"),
            "querystring_auth": True,
            "querystring_expire": MEDIA_PRIVATE_URL_TTL,
        },
    }
    MEDIA_PRIVATE_PRESIGNED_DOWNLOADS = True

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    # SafeJSONParser turns pathological nesting into a 400 for every endpoint (incl. anonymous).
    "DEFAULT_PARSER_CLASSES": [
        "apps.core.parsers.SafeJSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "auth_session_login": "10/minute",
        "auth_token_obtain": "10/minute",
        "auth_token_refresh": "60/hour",
        "auth_token_logout": "10/minute",
    },
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.errors.api_exception_handler",
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}
SPECTACULAR_SETTINGS = {
    "TITLE": "RamoVerde API",
    "DESCRIPTION": "Versioned REST contract shared by the RamoVerde web and mobile clients.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "apps.core.logging.JsonFormatter"},
        "pretty": {"format": "{levelname} {name} [{request_id}] {message}", "style": "{"},
    },
    "filters": {"request_id": {"()": "apps.core.logging.RequestIdFilter"}},
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["request_id"],
        }
    },
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
}

# --- Staff authentication and security (owned by accounts/audit, WR-13…WR-18) ---------------
# Web staff use Django sessions (HttpOnly cookie + CSRF); mobile uses JWT. Every staff request
# must be backed by an active, MFA-verified, tracked `accounts.UserSession`.
REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] = [
    "apps.accounts.authentication.StaffJWTAuthentication",
    "apps.accounts.authentication.StaffSessionAuthentication",
]
# Every endpoint requires an MFA-verified staff session unless it opts out explicitly.
REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] = ["apps.accounts.permissions.IsStaffUser"]
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
    **REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],  # type: ignore[dict-item]
    "auth_mfa": "20/minute",
    "auth_password": "10/hour",
}
SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"] = {
    **SPECTACULAR_SETTINGS.get("ENUM_NAME_OVERRIDES", {}),  # type: ignore[dict-item]
    "MfaMethodEnum": "apps.accounts.serializers.MFA_METHODS",
    "MobileMfaMethodEnum": "apps.accounts.serializers.MOBILE_MFA_METHODS",
    "AuthFlowStatusEnum": "apps.accounts.serializers.AUTH_FLOW_STATUSES",
}
# Shared cache (throttles, lockout, single-use MFA challenges) must be visible to every
# worker: PostgreSQL-backed, table created by migration apps.core 0001.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}

# Web sessions (WR-13). React backoffice sign-in page, used by Django admin and emails.
STAFF_LOGIN_URL = os.getenv("STAFF_LOGIN_URL", "http://localhost:5180/admin/login")
SESSION_COOKIE_AGE = int(os.getenv("DJANGO_SESSION_COOKIE_AGE", str(8 * 60 * 60)))
SESSION_COOKIE_NAME = "sessionid"

# Mobile JWT (WR-14): 5-minute access tokens, rotating refresh tokens (old ones blacklisted,
# reuse revokes the session), tokens invalidated by password changes, absolute session age.
SIMPLE_JWT.update(
    {
        "CHECK_REVOKE_TOKEN": True,
        "UPDATE_LAST_LOGIN": False,
        "USER_AUTHENTICATION_RULE": "apps.accounts.auth_sessions.is_staff_account_active",
    }
)
MOBILE_SESSION_MAX_AGE = timedelta(days=int(os.getenv("MOBILE_SESSION_MAX_AGE_DAYS", "30")))

# MFA (WR-15): mandatory for every staff account. WebAuthn preferred, TOTP fallback.
MFA_SECRET_KEY = os.getenv("MFA_SECRET_KEY", SECRET_KEY)
MFA_ISSUER = "RamoVerde"
MFA_PENDING_TTL_SECONDS = 5 * 60
STEP_UP_MAX_AGE = timedelta(minutes=int(os.getenv("STEP_UP_MAX_AGE_MINUTES", "5")))
WEBAUTHN_RP_ID = os.getenv("WEBAUTHN_RP_ID", "localhost")
WEBAUTHN_RP_NAME = "RamoVerde"
WEBAUTHN_ORIGINS = [
    origin for origin in os.getenv("WEBAUTHN_ORIGINS", "http://localhost:5180").split(",") if origin
]

# Password policy (WR-16).
PASSWORD_MAX_AGE_DAYS = int(os.getenv("PASSWORD_MAX_AGE_DAYS", "30"))
PASSWORD_HISTORY_COUNT = 5
PASSWORD_RESET_TIMEOUT = 30 * 60  # seconds; reset links are single use (hash-bound)
STAFF_PASSWORD_RESET_URL = os.getenv(
    "STAFF_PASSWORD_RESET_URL", STAFF_LOGIN_URL.replace("/admin/login", "/admin/reset-password")
)
AUTH_PASSWORD_VALIDATORS: list[dict[str, Any]] = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "apps.accounts.password_validation.MaximumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {
        "NAME": "apps.accounts.password_validation.PasswordHistoryValidator",
        "OPTIONS": {"history": PASSWORD_HISTORY_COUNT},
    },
]
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "RamoVerde <no-reply@localhost>")

# Brute force (WR-15/WR-18): progressive per-account lockout.
AUTH_LOCKOUT_THRESHOLD = 5
AUTH_LOCKOUT_BASE_SECONDS = 60
AUTH_LOCKOUT_MAX_SECONDS = 60 * 60
