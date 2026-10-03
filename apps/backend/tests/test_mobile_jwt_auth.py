"""WR-14: mobile JWT lifecycle bound to a revocable tracked session."""

from datetime import timedelta

import pytest
from auth_helpers import PASSWORD, enroll_totp, mobile_login, mobile_password_step
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.accounts.models import UserSession
from apps.audit.models import AuditEvent

User = get_user_model()


@pytest.fixture
def staff():
    return User.objects.create_user(email="op@example.com", password=PASSWORD, is_staff=True)


@pytest.fixture
def totp(staff):
    return enroll_totp(staff)


class _Login:
    """Successive full sign-ins use successive TOTP steps (codes are single use)."""

    def __init__(self, staff, totp):
        self.staff, self.totp, self.step = staff, totp, -1

    def __call__(self):
        tokens = mobile_login(self.staff, self.totp, offset_steps=self.step)
        self.step += 1
        return tokens


@pytest.fixture
def login(staff, totp):
    return _Login(staff, totp)


@pytest.mark.django_db
def test_token_pair_is_bound_to_a_tracked_mobile_session(staff, login):
    tokens = login()
    access = AccessToken(tokens["access"])
    refresh = RefreshToken(tokens["refresh"])
    tracked = UserSession.objects.get(user=staff)
    assert tracked.kind == UserSession.Kind.MOBILE
    assert tracked.user_agent == "RamoVerdeStaff/1.0 (Android 15)"
    assert access["sid"] == tracked.pk == refresh["sid"]
    assert AuditEvent.objects.filter(action="auth.login.success", actor=staff).exists()


@pytest.mark.django_db
def test_token_failures_are_generic_and_never_issue_tokens(staff):
    User.objects.create_user(email="member@example.com", password=PASSWORD)
    client = APIClient()
    responses = [
        mobile_password_step(client, staff.email, "wrong-password-123"),
        mobile_password_step(client, "nobody@example.com"),
        mobile_password_step(client, "member@example.com"),
    ]
    for response in responses:
        assert response.status_code == 401
        assert response.json()["error"]["message"] == responses[0].json()["error"]["message"]
        assert "access" not in response.json()
    assert not UserSession.objects.exists()


@pytest.mark.django_db
def test_access_token_stops_working_when_its_session_is_revoked(staff, login):
    tokens = login()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    assert client.get("/api/v1/users/me").status_code == 200

    UserSession.objects.filter(user=staff).update(revoked_at=timezone.now())
    assert client.get("/api/v1/users/me").status_code == 401


@pytest.mark.django_db
def test_tokens_without_a_session_claim_are_rejected(staff, login):
    access = RefreshToken.for_user(staff).access_token
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    assert client.get("/api/v1/users/me").status_code == 401


@pytest.mark.django_db
def test_refresh_rotates_and_blacklists_the_previous_refresh_token(staff, login):
    client = APIClient()
    first = login()
    rotated = client.post("/api/v1/auth/token/refresh", {"refresh": first["refresh"]})
    assert rotated.status_code == 200
    assert rotated.json()["refresh"] != first["refresh"]
    assert (
        RefreshToken(rotated.json()["refresh"])["sid"]
        == RefreshToken(first["refresh"], verify=False)["sid"]
    )


@pytest.mark.django_db
def test_reusing_a_rotated_refresh_token_revokes_the_whole_session(staff, login):
    client = APIClient()
    first = login()
    second = client.post("/api/v1/auth/token/refresh", {"refresh": first["refresh"]}).json()

    replay = client.post("/api/v1/auth/token/refresh", {"refresh": first["refresh"]})
    assert replay.status_code == 401
    assert UserSession.objects.get(user=staff).revoked_at is not None
    assert (
        client.post("/api/v1/auth/token/refresh", {"refresh": second["refresh"]}).status_code == 401
    )
    assert AuditEvent.objects.filter(action="auth.token.reuse_detected").exists()


@pytest.mark.django_db
def test_refresh_is_refused_for_revoked_sessions_and_deactivated_accounts(staff, login):
    client = APIClient()
    tokens = login()
    UserSession.objects.filter(user=staff).update(revoked_at=timezone.now())
    assert (
        client.post("/api/v1/auth/token/refresh", {"refresh": tokens["refresh"]}).status_code == 401
    )

    tokens = login()
    User.objects.filter(pk=staff.pk).update(is_active=False)
    assert (
        client.post("/api/v1/auth/token/refresh", {"refresh": tokens["refresh"]}).status_code == 401
    )


@pytest.mark.django_db
def test_refresh_is_refused_after_the_absolute_mobile_session_lifetime(staff, settings, login):
    client = APIClient()
    tokens = login()
    UserSession.objects.filter(user=staff).update(
        created_at=timezone.now() - settings.MOBILE_SESSION_MAX_AGE - timedelta(minutes=1)
    )
    assert (
        client.post("/api/v1/auth/token/refresh", {"refresh": tokens["refresh"]}).status_code == 401
    )


@pytest.mark.django_db
def test_logout_blacklists_refresh_and_revokes_the_session(staff, login):
    client = APIClient()
    tokens = login()
    assert (
        client.post("/api/v1/auth/token/logout", {"refresh": tokens["refresh"]}).status_code == 204
    )

    assert UserSession.objects.get(user=staff).revoked_at is not None
    assert (
        client.post("/api/v1/auth/token/refresh", {"refresh": tokens["refresh"]}).status_code == 401
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    assert client.get("/api/v1/users/me").status_code == 401
    assert AuditEvent.objects.filter(action="auth.logout", actor=staff).exists()


@pytest.mark.django_db
def test_password_change_invalidates_existing_tokens(staff, login):
    tokens = login()
    staff.set_password("another-long-passphrase-42")
    staff.save()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    assert client.get("/api/v1/users/me").status_code == 401
    assert (
        APIClient().post("/api/v1/auth/token/refresh", {"refresh": tokens["refresh"]}).status_code
        == 401
    )
