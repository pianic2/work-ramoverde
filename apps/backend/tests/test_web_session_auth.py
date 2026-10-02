"""WR-13: staff web authentication with Django sessions, CSRF and a locked-down Django admin."""

import os
import subprocess
import sys

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import UserSession
from apps.audit.models import AuditEvent

User = get_user_model()
PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


def csrf_client() -> tuple[APIClient, str]:
    client = APIClient(enforce_csrf_checks=True, HTTP_USER_AGENT="Firefox/140 test")
    token = client.get("/api/v1/auth/csrf").json()["csrfToken"]
    return client, token


def login(client: APIClient, csrf: str, email: str, password: str = PASSWORD):
    return client.post(
        "/api/v1/auth/session/login",
        {"email": email, "password": password},
        format="json",
        HTTP_X_CSRFTOKEN=csrf,
    )


@pytest.mark.django_db
def test_session_cookie_is_httponly_lax_and_csrf_cookie_is_not_readable_by_js():
    assert settings.SESSION_COOKIE_HTTPONLY is True
    assert settings.SESSION_COOKIE_SAMESITE == "Lax"
    assert settings.CSRF_COOKIE_HTTPONLY is True
    assert settings.SESSION_COOKIE_AGE <= 12 * 60 * 60


@pytest.mark.django_db
def test_failed_login_messages_do_not_reveal_whether_the_account_exists():
    User.objects.create_user(email="staff@example.com", password=PASSWORD, is_staff=True)
    User.objects.create_user(email="member@example.com", password=PASSWORD)
    User.objects.create_user(
        email="gone@example.com", password=PASSWORD, is_staff=True, is_active=False
    )
    client, csrf = csrf_client()

    wrong_password = login(client, csrf, "staff@example.com", "wrong-password-123")
    unknown = login(client, csrf, "nobody@example.com")
    not_staff = login(client, csrf, "member@example.com")
    inactive = login(client, csrf, "gone@example.com")

    for response in (wrong_password, unknown, not_staff, inactive):
        assert response.status_code == 401
        body = response.json()["error"]
        assert body["code"] == "authentication_failed"
        assert body["message"] == wrong_password.json()["error"]["message"]
        assert PASSWORD not in response.content.decode()
    assert "sessionid" not in client.cookies or not client.cookies["sessionid"].value


@pytest.mark.django_db
def test_login_rotates_session_key_and_tracks_the_web_session():
    user = User.objects.create_user(email="staff@example.com", password=PASSWORD, is_staff=True)
    client, csrf = csrf_client()
    client.cookies["sessionid"] = "attacker-fixed-session"

    response = login(client, csrf, user.email)

    assert response.status_code == 200
    cookie = response.cookies["sessionid"]
    assert cookie["httponly"]
    assert cookie["samesite"] == "Lax"
    assert cookie.value != "attacker-fixed-session"
    tracked = UserSession.objects.get(user=user)
    assert tracked.kind == UserSession.Kind.WEB
    assert tracked.session_key == cookie.value
    assert tracked.user_agent == "Firefox/140 test"
    assert tracked.revoked_at is None


@pytest.mark.django_db
def test_logout_requires_csrf_revokes_the_tracked_session_and_is_audited():
    user = User.objects.create_user(email="staff@example.com", password=PASSWORD, is_staff=True)
    client, csrf = csrf_client()
    login(client, csrf, user.email)
    csrf = client.get("/api/v1/auth/csrf").json()["csrfToken"]

    assert client.post("/api/v1/auth/session/logout").status_code == 403
    assert client.post("/api/v1/auth/session/logout", HTTP_X_CSRFTOKEN=csrf).status_code == 204

    assert client.get("/api/v1/users/me").status_code in (401, 403)
    assert UserSession.objects.get(user=user).revoked_at is not None
    assert not Session.objects.exists()
    assert AuditEvent.objects.filter(action="auth.logout", actor=user).exists()


@pytest.mark.django_db
def test_revoked_tracked_session_no_longer_authenticates():
    user = User.objects.create_user(email="staff@example.com", password=PASSWORD, is_staff=True)
    client, csrf = csrf_client()
    login(client, csrf, user.email)
    tracked = UserSession.objects.get(user=user)
    UserSession.objects.filter(pk=tracked.pk).update(revoked_at=tracked.created_at)

    assert client.get("/api/v1/users/me").status_code in (401, 403)


@pytest.mark.django_db
def test_login_success_and_failure_are_audited_without_secrets():
    user = User.objects.create_user(email="staff@example.com", password=PASSWORD, is_staff=True)
    client, csrf = csrf_client()
    login(client, csrf, user.email, "wrong-password-123")
    login(client, csrf, user.email)

    failure = AuditEvent.objects.get(action="auth.login.failure")
    success = AuditEvent.objects.get(action="auth.login.success")
    assert failure.outcome == "failure"
    assert failure.actor is None
    assert success.actor == user
    assert success.metadata["channel"] == "web"
    for event in (failure, success):
        assert "wrong-password-123" not in str(event.metadata)
        assert PASSWORD not in str(event.metadata)


@pytest.mark.django_db
def test_django_admin_lives_under_django_admin_and_rejects_anonymous_users():
    client = APIClient()
    assert client.get("/admin/").status_code == 404
    response = client.get("/django-admin/")
    assert response.status_code == 302
    assert "/django-admin/login/" in response["Location"]


@pytest.mark.django_db
def test_django_admin_password_form_cannot_log_anyone_in():
    User.objects.create_superuser(email="root@example.com", password=PASSWORD)
    client = APIClient()
    response = client.post(
        "/django-admin/login/", {"username": "root@example.com", "password": PASSWORD}
    )
    assert response.status_code in (302, 403)
    assert not Session.objects.exists()
    assert client.get("/django-admin/").status_code == 302


@pytest.mark.django_db
def test_django_admin_is_limited_to_superusers_with_a_tracked_staff_session():
    staff = User.objects.create_user(email="staff@example.com", password=PASSWORD, is_staff=True)
    root = User.objects.create_superuser(email="root@example.com", password=PASSWORD)

    client, csrf = csrf_client()
    login(client, csrf, staff.email)
    assert client.get("/django-admin/").status_code == 302

    client, csrf = csrf_client()
    login(client, csrf, root.email)
    assert client.get("/django-admin/").status_code == 200

    client = APIClient()
    client.force_login(root)  # session without the staff-auth flow
    assert client.get("/django-admin/").status_code == 302


@pytest.mark.django_db
def test_api_responses_carry_baseline_security_headers():
    response = APIClient().get("/api/v1/auth/csrf")
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["X-Frame-Options"] == "DENY"
    assert response["Referrer-Policy"] == "same-origin"
    assert response["Cross-Origin-Opener-Policy"] == "same-origin"


def test_production_settings_pass_django_deploy_checks_with_secure_cookies():
    env = os.environ.copy()
    env.update(
        DJANGO_SETTINGS_MODULE="config.settings.production",
        DATABASE_URL="postgresql://app:app@localhost:5432/app",
        DJANGO_SECRET_KEY="ci-only-not-a-secret-ci-only-not-a-secret-ci-only-not-a-secret",
        DJANGO_ALLOWED_HOSTS="example.com",
        DJANGO_CORS_ALLOWED_ORIGINS="https://web.example.com",
        DJANGO_CSRF_TRUSTED_ORIGINS="https://web.example.com",
    )
    script = (
        "import django; django.setup(); from django.conf import settings as s; "
        "print(s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, s.SESSION_COOKIE_HTTPONLY, "
        "s.SECURE_SSL_REDIRECT, s.SECURE_HSTS_SECONDS > 0)"
    )
    flags = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script], env=env, capture_output=True, text=True, check=True
    )
    assert flags.stdout.split() == ["True"] * 5
    deploy = subprocess.run(  # noqa: S603
        [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert deploy.returncode == 0, deploy.stdout + deploy.stderr
