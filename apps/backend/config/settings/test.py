from .base import *  # noqa: F403

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Media blobs stay in memory during tests: nothing touches the filesystem or a bucket.
STORAGES = {
    **STORAGES,
    # Admin pages render in tests without running collectstatic.
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    "media_public": {
        "BACKEND": "django.core.files.storage.InMemoryStorage",
        "OPTIONS": {"base_url": "/media/public/"},
    },
    "media_private": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
}
