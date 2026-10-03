import os
import subprocess
import sys

import pytest
from django.conf import settings


def test_request_and_upload_limits_are_bounded():
    assert settings.DATA_UPLOAD_MAX_MEMORY_SIZE == 2_621_440
    assert settings.DATA_UPLOAD_MAX_NUMBER_FIELDS == 1_000
    assert settings.DATA_UPLOAD_MAX_NUMBER_FILES == 20
    assert settings.FILE_UPLOAD_MAX_MEMORY_SIZE == 2_621_440


@pytest.mark.parametrize(
    ("invalid", "message"),
    [
        ({"DATABASE_URL": None}, "DATABASE_URL"),
        ({"DATABASE_URL": "sqlite:////tmp/template-audit.sqlite3"}, "PostgreSQL"),
        ({"DJANGO_SECRET_KEY": None}, "DJANGO_SECRET_KEY"),
        ({"DJANGO_CORS_ALLOWED_ORIGINS": "http://web.example.com"}, "HTTPS origins"),
        ({"DJANGO_CSRF_TRUSTED_ORIGINS": "http://web.example.com"}, "HTTPS origins"),
    ],
)
def test_production_rejects_insecure_configuration(invalid: dict[str, str | None], message: str):
    env = os.environ.copy()
    env.update(
        DJANGO_SETTINGS_MODULE="config.settings.production",
        DATABASE_URL="postgresql://app:app@localhost:5432/app",
        DJANGO_SECRET_KEY="ci-only-not-a-secret-ci-only-not-a-secret-ci-only-not-a-secret",
        DJANGO_ALLOWED_HOSTS="example.com",
        DJANGO_CORS_ALLOWED_ORIGINS="https://web.example.com",
        DJANGO_CSRF_TRUSTED_ORIGINS="https://web.example.com",
    )
    for key, value in invalid.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", "import django; django.setup()"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert message in result.stderr
