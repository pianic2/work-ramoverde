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
