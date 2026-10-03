"""WR-16: 30-day password expiry, strong passwords, history, single-use reset."""

import re
from datetime import timedelta

import pytest
from auth_helpers import (
    PASSWORD,
    create_staff,
    csrf_client,
    enroll_totp,
    mfa_session_for,
    mobile_login,
    totp_code,
    web_login,
    web_password_step,
    web_post,
)
from django.contrib.auth.password_validation import validate_password
from django.core import mail
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import PasswordHistory, User, UserSession
from apps.audit.models import AuditEvent

NEW = "a-fresh-and-long-passphrase-2026"
CHANGE = "/api/v1/auth/password/change"
RESET = "/api/v1/auth/password/reset"
CONFIRM = "/api/v1/auth/password/reset/confirm"


def _expire(user: User) -> None:
    User.objects.filter(pk=user.pk).update(password_changed_at=timezone.now() - timedelta(days=31))


# --- Policy ------------------------------------------------------------------------------


@pytest.mark.django_db
def test_password_rules_require_length_and_reject_common_passwords():
    user = create_staff()
    for weak in ("short-pw-1", "password12345", "123456789012", "staff@example.com"):
        with pytest.raises(ValidationError):
            validate_password(weak, user)
    validate_password("x" * 200 + " long passphrases are fine", user)
    with pytest.raises(ValidationError):
        validate_password("y" * 1025, user)


@pytest.mark.django_db
def test_recent_passwords_cannot_be_reused_and_history_is_hashed():
    user = create_staff()
    user.set_password(NEW)
    user.save()
    with pytest.raises(ValidationError):
        validate_password(PASSWORD, user)
    with pytest.raises(ValidationError):
        validate_password(NEW, user)
    stored = list(PasswordHistory.objects.filter(user=user).values_list("password_hash", flat=True))
    assert stored and all(NEW not in value and PASSWORD not in value for value in stored)


@pytest.mark.django_db
def test_password_age_is_configurable_and_stamped_on_change(settings):
    user = create_staff()
    assert user.password_changed_at is not None
    assert not user.password_expired
    settings.PASSWORD_MAX_AGE_DAYS = 30
    _expire(user)
    user.refresh_from_db()
    assert user.password_expired
    settings.PASSWORD_MAX_AGE_DAYS = 60
    assert not user.password_expired


# --- Expiry enforcement ------------------------------------------------------------------


@pytest.mark.django_db
def test_expired_password_still_requires_mfa_and_then_only_allows_password_change():
    user = create_staff()
    totp = enroll_totp(user)
    _expire(user)
    client, csrf = csrf_client()
    web_password_step(client, csrf, user.email)
    assert client.get("/api/v1/users/me").status_code == 401  # MFA still required

    client, csrf = web_login(user, totp)
    me = client.get("/api/v1/users/me")
    assert me.status_code == 200
    assert me.json()["password_change_required"] is True
    blocked = client.get("/api/v1/auth/sessions")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "password_change_required"
    assert AuditEvent.objects.filter(action="password.expired", actor=user).exists()

    changed = web_post(client, csrf, CHANGE, {"current_password": PASSWORD, "new_password": NEW})
    assert changed.status_code == 204
    assert client.get("/api/v1/auth/sessions").status_code == 200


@pytest.mark.django_db
def test_django_admin_refuses_expired_passwords():
    root = create_staff("root@example.com", is_superuser=True)
    client, _ = web_login(root, enroll_totp(root))
    assert client.get("/django-admin/").status_code == 200
    _expire(root)
    assert client.get("/django-admin/").status_code == 302


# --- Change ------------------------------------------------------------------------------


@pytest.mark.django_db
def test_change_requires_current_password_and_recent_mfa():
    user = create_staff()
    totp = enroll_totp(user)
    client, csrf = web_login(user, totp)
    wrong = web_post(
        client, csrf, CHANGE, {"current_password": "nope-nope-nope", "new_password": NEW}
    )
    assert wrong.status_code == 400
    assert AuditEvent.objects.filter(action="password.change", outcome="failure").exists()

    UserSession.objects.filter(user=user).update(
        mfa_verified_at=timezone.now() - timedelta(minutes=30)
    )
    stale = web_post(client, csrf, CHANGE, {"current_password": PASSWORD, "new_password": NEW})
    assert stale.status_code == 403
    assert stale.json()["error"]["code"] == "step_up_required"


@pytest.mark.django_db
def test_change_rejects_weak_or_reused_passwords_without_echoing_them():
    user = create_staff()
    client, csrf = web_login(user, enroll_totp(user))
    for candidate in (PASSWORD, "password12345"):
        response = web_post(
            client, csrf, CHANGE, {"current_password": PASSWORD, "new_password": candidate}
        )
        assert response.status_code == 400
        assert candidate not in response.content.decode()


@pytest.mark.django_db
def test_change_keeps_this_session_and_revokes_every_other_one():
    user = create_staff()
    totp = enroll_totp(user)
    other_web, _ = web_login(user, totp, offset_steps=-1)
    tokens = mobile_login(user, totp, offset_steps=0)
    client, csrf = web_login(user, totp, offset_steps=1)

    assert (
        web_post(
            client, csrf, CHANGE, {"current_password": PASSWORD, "new_password": NEW}
        ).status_code
        == 204
    )

    assert client.get("/api/v1/users/me").status_code == 200
    assert other_web.get("/api/v1/users/me").status_code in (401, 403)
    mobile = APIClient()
    mobile.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    assert mobile.get("/api/v1/users/me").status_code == 401
    assert (
        APIClient().post("/api/v1/auth/token/refresh", {"refresh": tokens["refresh"]}).status_code
        == 401
    )
    assert AuditEvent.objects.filter(action="password.change", outcome="success").exists()


@pytest.mark.django_db
def test_mobile_change_returns_a_fresh_token_pair_for_the_same_device():
    user = create_staff()
    tokens = mobile_login(user, enroll_totp(user))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    response = client.post(
        CHANGE, {"current_password": PASSWORD, "new_password": NEW}, format="json"
    )
    assert response.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.json()['access']}")
    assert client.get("/api/v1/users/me").status_code == 200
    assert UserSession.objects.filter(user=user, revoked_at__isnull=True).count() == 1


# --- Reset -------------------------------------------------------------------------------


def _reset_link(email: str) -> tuple[str, str]:
    body = mail.outbox[-1].body
    match = re.search(r"uid=([\w-]+)&token=([\w-]+)", body)
    assert match, body
    return match.group(1), match.group(2)


@pytest.mark.django_db
def test_reset_request_does_not_reveal_whether_the_account_exists():
    create_staff()
    client = APIClient()
    known = client.post(RESET, {"email": "staff@example.com"}, format="json")
    unknown = client.post(RESET, {"email": "nobody@example.com"}, format="json")
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["staff@example.com"]


@pytest.mark.django_db
def test_reset_is_single_use_never_signs_in_and_revokes_all_sessions():
    user = create_staff()
    totp = enroll_totp(user)
    web_client, _ = web_login(user, totp, offset_steps=-1)
    tokens = mobile_login(user, totp)
    APIClient().post(RESET, {"email": user.email}, format="json")
    uid, token = _reset_link(user.email)

    client = APIClient()
    done = client.post(CONFIRM, {"uid": uid, "token": token, "new_password": NEW}, format="json")
    assert done.status_code == 204
    assert "sessionid" not in done.cookies and "access" not in (done.content.decode() or "")
    assert client.get("/api/v1/users/me").status_code == 401

    again = client.post(
        CONFIRM, {"uid": uid, "token": token, "new_password": NEW + "-2"}, format="json"
    )
    assert again.status_code == 400
    assert web_client.get("/api/v1/users/me").status_code in (401, 403)
    assert (
        APIClient().post("/api/v1/auth/token/refresh", {"refresh": tokens["refresh"]}).status_code
        == 401
    )
    assert not UserSession.objects.filter(user=user, revoked_at__isnull=True).exists()

    # The next sign-in still requires the second factor.
    fresh, csrf = csrf_client()
    response = web_post(
        fresh, csrf, "/api/v1/auth/session/login", {"email": user.email, "password": NEW}
    )
    assert response.json()["status"] == "mfa_required"
    assert fresh.get("/api/v1/users/me").status_code == 401
    assert fresh.get("/api/v1/users/me").status_code == 401
    web_post(
        fresh,
        csrf,
        "/api/v1/auth/session/mfa/verify",
        {"method": "totp", "code": totp_code(totp, 1)},
    )
    assert fresh.get("/api/v1/users/me").status_code == 200
    assert AuditEvent.objects.filter(action="password.reset.complete", actor=user).exists()


@pytest.mark.django_db
def test_reset_tokens_expire(settings):
    user = create_staff()
    APIClient().post(RESET, {"email": user.email}, format="json")
    uid, token = _reset_link(user.email)
    settings.PASSWORD_RESET_TIMEOUT = -1
    response = APIClient().post(
        CONFIRM, {"uid": uid, "token": token, "new_password": NEW}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_reset_applies_the_password_policy():
    user = create_staff()
    APIClient().post(RESET, {"email": user.email}, format="json")
    uid, token = _reset_link(user.email)
    response = APIClient().post(
        CONFIRM, {"uid": uid, "token": token, "new_password": PASSWORD}, format="json"
    )
    assert response.status_code == 400
    user.refresh_from_db()
    assert user.check_password(PASSWORD)


@pytest.mark.django_db
def test_forced_auth_helper_sessions_also_respect_expiry():
    user = create_staff()
    _expire(user)
    client = APIClient()
    client.force_authenticate(user=User.objects.get(pk=user.pk), token=mfa_session_for(user))
    assert client.get("/api/v1/auth/mfa").status_code == 403
