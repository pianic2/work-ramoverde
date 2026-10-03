import os
from urllib.parse import urlsplit

from .base import *  # noqa: F403

DEBUG = False
if SECRET_KEY == DEVELOPMENT_SECRET_KEY or len(SECRET_KEY) < 50:
    raise RuntimeError("DJANGO_SECRET_KEY must be a unique secret of at least 50 characters")
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise RuntimeError("DJANGO_ALLOWED_HOSTS must contain explicit production hostnames")
if not CORS_ALLOWED_ORIGINS or "*" in CORS_ALLOWED_ORIGINS:
    raise RuntimeError("DJANGO_CORS_ALLOWED_ORIGINS must contain explicit production origins")
if not CSRF_TRUSTED_ORIGINS:
    raise RuntimeError("DJANGO_CSRF_TRUSTED_ORIGINS must contain explicit production origins")
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL must be set in production")
if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise RuntimeError("DATABASE_URL must use PostgreSQL in production")
if any(
    urlsplit(origin).scheme != "https" or not urlsplit(origin).netloc
    for origin in CORS_ALLOWED_ORIGINS
):
    raise RuntimeError("DJANGO_CORS_ALLOWED_ORIGINS must contain only HTTPS origins")
if any(
    urlsplit(origin).scheme != "https" or not urlsplit(origin).netloc
    for origin in CSRF_TRUSTED_ORIGINS
):
    raise RuntimeError("DJANGO_CSRF_TRUSTED_ORIGINS must contain only HTTPS origins")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Staff sign-in page (React backoffice). Defaults to the first allowed web origin.
STAFF_LOGIN_URL = os.getenv("STAFF_LOGIN_URL", f"{CORS_ALLOWED_ORIGINS[0]}/admin/login")
if urlsplit(STAFF_LOGIN_URL).scheme != "https":
    raise RuntimeError("STAFF_LOGIN_URL must use HTTPS in production")

# WebAuthn is bound to the web origins (HTTPS) and their registrable domain.
WEBAUTHN_ORIGINS = [
    value
    for value in os.getenv("WEBAUTHN_ORIGINS", ",".join(CORS_ALLOWED_ORIGINS)).split(",")
    if value
]
if any(urlsplit(origin).scheme != "https" for origin in WEBAUTHN_ORIGINS):
    raise RuntimeError("WEBAUTHN_ORIGINS must contain only HTTPS origins")
WEBAUTHN_RP_ID = os.getenv("WEBAUTHN_RP_ID", urlsplit(WEBAUTHN_ORIGINS[0]).hostname or "")
