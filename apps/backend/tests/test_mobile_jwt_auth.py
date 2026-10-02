"""WR-14: mobile JWT lifecycle bound to a revocable tracked session."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.accounts.models import UserSession
from apps.audit.models import AuditEvent

User = get_user_model()
PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


@pytest.fixture
def staff():
    return User.objects.create_user(email="op@example.com", password=PASSWORD, is_staff=True)


def obtain(client: APIClient, email: str, password: str = PASSWORD):
    return client.post(
        "/api/v1/auth/token",
        {"email": email, "password": password},
        format="json",
        HTTP_USER_AGENT="RamoVerdeStaff/1.0 (Android 15)",
    )


@pytest.mark.django_db
def test_token_pair_is_bound_to_a_tracked_mobile_session(staff):
    response = obtain(APIClient(), staff.email)
    assert response.status_code == 200
    access = AccessToken(response.json()["access"])
    refresh = RefreshToken(response.json()["refresh"])
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
        obtain(client, staff.email, "wrong-password-123"),
        obtain(client, "nobody@example.com"),
        obtain(client, "member@example.com"),
    ]
    for response in responses:
        assert response.status_code == 401
        assert response.json()["error"]["message"] == responses[0].json()["error"]["message"]
        assert "access" not in response.json()
    assert not UserSession.objects.exists()


@pytest.mark.django_db
def test_access_token_stops_working_when_its_session_is_revoked(staff):
    tokens = obtain(APIClient(), staff.email).json()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    assert client.get("/api/v1/users/me").status_code == 200

    UserSession.objects.filter(user=staff).update(revoked_at=timezone.now())
    assert client.get("/api/v1/users/me").status_code == 401


@pytest.mark.django_db
def test_tokens_without_a_session_claim_are_rejected(staff):
    access = RefreshToken.for_user(staff).access_token
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    assert client.get("/api/v1/users/me").status_code == 401


@pytest.mark.django_db
def test_refresh_rotates_and_blacklists_the_previous_refresh_token(staff):
    client = APIClient()
    first = obtain(client, staff.email).json()
    rotated = client.post("/api/v1/auth/token/refresh", {"refresh": first["refresh"]})
    assert rotated.status_code == 200
    assert rotated.json()["refresh"] != first["refresh"]
    assert (
        RefreshToken(rotated.json()["refresh"])["sid"]
        == RefreshToken(first["refresh"], verify=False)["sid"]
    )


@pytest.mark.django_db
def test_reusing_a_rotated_refresh_token_revokes_the_whole_session(staff):
    client = APIClient()
    first = obtain(client, staff.email).json()
    second = client.post("/api/v1/auth/token/refresh", {"refresh": first["refresh"]}).json()

    replay = client.post("/api/v1/auth/token/refresh", {"refresh": first["refresh"]})
    assert replay.status_code == 401
    assert UserSession.objects.get(user=staff).revoked_at is not None
    assert (
        client.post("/api/v1/auth/token/refresh", {"refresh": second["refresh"]}).status_code == 401
    )
    assert AuditEvent.objects.filter(action="auth.token.reuse_detected").exists()


@pytest.mark.django_db
def test_refresh_is_refused_for_revoked_sessions_and_deactivated_accounts(staff):
    client = APIClient()
    tokens = obtain(client, staff.email).json()
    UserSession.objects.filter(user=staff).update(revoked_at=timezone.now())
    assert (
        client.post("/api/v1/auth/token/refresh", {"refresh": tokens["refresh"]}).status_code == 401
    )

    tokens = obtain(client, staff.email).json()
    User.objects.filter(pk=staff.pk).update(is_active=False)
    assert (
        client.post("/api/v1/auth/token/refresh", {"refresh": tokens["refresh"]}).status_code == 401
    )


@pytest.mark.django_db
def test_refresh_is_refused_after_the_absolute_mobile_session_lifetime(staff, settings):
    client = APIClient()
    tokens = obtain(client, staff.email).json()
    UserSession.objects.filter(user=staff).update(
        created_at=timezone.now() - settings.MOBILE_SESSION_MAX_AGE - timedelta(minutes=1)
    )
    assert (
        client.post("/api/v1/auth/token/refresh", {"refresh": tokens["refresh"]}).status_code == 401
    )


@pytest.mark.django_db
def test_logout_blacklists_refresh_and_revokes_the_session(staff):
    client = APIClient()
    tokens = obtain(client, staff.email).json()
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
def test_password_change_invalidates_existing_tokens(staff):
    tokens = obtain(APIClient(), staff.email).json()
    staff.set_password("another-long-passphrase-42")
    staff.save()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    assert client.get("/api/v1/users/me").status_code == 401
    assert (
        APIClient().post("/api/v1/auth/token/refresh", {"refresh": tokens["refresh"]}).status_code
        == 401
    )
