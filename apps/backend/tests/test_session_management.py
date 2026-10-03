"""WR-16: list devices, revoke one, log out other sessions, global logout."""

import pytest
from auth_helpers import create_staff, enroll_totp, mobile_login, web_login, web_post
from rest_framework.test import APIClient

from apps.accounts.models import UserSession
from apps.audit.models import AuditEvent

SESSIONS = "/api/v1/auth/sessions"


def _bearer(access: str) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


@pytest.fixture
def three_devices():
    user = create_staff()
    totp = enroll_totp(user)
    laptop, _ = web_login(user, totp, offset_steps=-1)
    tokens = mobile_login(user, totp, offset_steps=0)
    current, csrf = web_login(user, totp, offset_steps=1)
    return user, laptop, tokens, current, csrf


@pytest.mark.django_db
def test_lists_own_active_sessions_with_device_metadata(three_devices):
    user, _, _, current, _ = three_devices
    create_staff("other@example.com")
    response = current.get(SESSIONS)
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 3
    assert {row["kind"] for row in rows} == {"web", "mobile"}
    assert sum(row["current"] for row in rows) == 1
    for row in rows:
        assert {"id", "created_at", "last_seen_at", "user_agent", "ip_address"} <= row.keys()
        assert "session_key" not in row
    mobile_row = next(row for row in rows if row["kind"] == "mobile")
    assert mobile_row["user_agent"] == "RamoVerdeStaff/1.0 (Android 15)"


@pytest.mark.django_db
def test_revoke_one_session(three_devices):
    user, laptop, _, current, csrf = three_devices
    laptop_row = UserSession.objects.filter(user=user, kind="web").order_by("id").first()
    response = current.delete(f"{SESSIONS}/{laptop_row.pk}", HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == 204
    assert laptop.get("/api/v1/users/me").status_code in (401, 403)
    assert current.get("/api/v1/users/me").status_code == 200
    assert AuditEvent.objects.filter(action="session.revoke", actor=user).exists()


@pytest.mark.django_db
def test_cannot_revoke_someone_elses_session(three_devices):
    _, _, _, current, csrf = three_devices
    other = create_staff("other@example.com")
    foreign = UserSession.objects.create(user=other, kind="web", session_key="x")
    assert current.delete(f"{SESSIONS}/{foreign.pk}", HTTP_X_CSRFTOKEN=csrf).status_code == 404
    foreign.refresh_from_db()
    assert foreign.revoked_at is None


@pytest.mark.django_db
def test_logout_other_sessions_keeps_the_current_one(three_devices):
    _, laptop, tokens, current, csrf = three_devices
    assert web_post(current, csrf, f"{SESSIONS}/revoke-others").status_code == 204
    assert current.get("/api/v1/users/me").status_code == 200
    assert laptop.get("/api/v1/users/me").status_code in (401, 403)
    assert _bearer(tokens["access"]).get("/api/v1/users/me").status_code == 401
    assert (
        APIClient().post("/api/v1/auth/token/refresh", {"refresh": tokens["refresh"]}).status_code
        == 401
    )


@pytest.mark.django_db
def test_global_logout_from_mobile_covers_web_sessions_and_refresh_tokens(three_devices):
    user, laptop, tokens, current, _ = three_devices
    response = _bearer(tokens["access"]).post(f"{SESSIONS}/revoke-all")
    assert response.status_code == 204
    assert current.get("/api/v1/users/me").status_code in (401, 403)
    assert laptop.get("/api/v1/users/me").status_code in (401, 403)
    assert _bearer(tokens["access"]).get("/api/v1/users/me").status_code == 401
    assert (
        APIClient().post("/api/v1/auth/token/refresh", {"refresh": tokens["refresh"]}).status_code
        == 401
    )
    assert not UserSession.objects.filter(user=user, revoked_at__isnull=True).exists()
    assert AuditEvent.objects.filter(action="session.revoke_all", actor=user).exists()


@pytest.mark.django_db
def test_session_endpoints_require_csrf_for_browser_sessions(three_devices):
    _, _, _, current, _ = three_devices
    assert current.post(f"{SESSIONS}/revoke-all").status_code == 403
