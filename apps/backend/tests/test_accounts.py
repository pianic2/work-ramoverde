import pytest
from auth_helpers import (
    PASSWORD,
    create_staff,
    csrf_client,
    enroll_totp,
    mfa_session_for,
    mobile_login,
    web_login,
    web_password_step,
)
from django.test import override_settings
from rest_framework.test import APIClient

AUTH_THROTTLE_RATES = {
    "auth_session_login": "1/minute",
    "auth_token_obtain": "1/minute",
    "auth_token_refresh": "1/minute",
    "auth_token_logout": "1/minute",
    "auth_mfa": "1/minute",
}


@pytest.fixture
def one_request_auth_throttle_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    from rest_framework.throttling import ScopedRateThrottle

    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", AUTH_THROTTLE_RATES)


@pytest.mark.django_db
def test_current_user_requires_auth_and_returns_email_identity():
    user = create_staff("ada@example.com")
    client = APIClient()
    assert client.get("/api/v1/users/me").status_code == 401
    client.force_authenticate(user=user, token=mfa_session_for(user))
    response = client.get("/api/v1/users/me")
    assert response.status_code == 200
    assert response.json()["email"] == "ada@example.com"


@pytest.mark.django_db
def test_mobile_jwt_can_access_current_user():
    user = create_staff("mobile@example.com")
    tokens = mobile_login(user, enroll_totp(user))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    assert client.get("/api/v1/users/me").json()["email"] == user.email


@pytest.mark.django_db
def test_valid_mobile_token_attempts_are_throttled_without_throttling_other_api_scopes(
    one_request_auth_throttle_rate: None,
):
    user = create_staff("rate@example.com")
    client = APIClient()
    credentials = {"email": user.email, "password": PASSWORD}

    assert client.post("/api/v1/auth/token", credentials).status_code == 200
    assert client.post("/api/v1/auth/token", credentials).status_code == 429

    client.force_authenticate(user=user, token=mfa_session_for(user))
    response = client.get("/api/v1/users/me")
    assert response.status_code == 200
    assert response.json()["email"] == user.email


@pytest.mark.django_db
def test_invalid_mobile_credentials_count_toward_auth_limit(
    one_request_auth_throttle_rate: None,
):
    client = APIClient()
    invalid = {"email": "unknown@example.com", "password": "incorrect"}

    assert client.post("/api/v1/auth/token", invalid).status_code == 401
    assert client.post("/api/v1/auth/token", invalid).status_code == 429


@pytest.mark.django_db
def test_mfa_attempts_are_rate_limited(one_request_auth_throttle_rate: None):
    client = APIClient()
    body = {"challenge": "x", "method": "totp", "code": "123456"}
    assert client.post("/api/v1/auth/token/mfa/verify", body).status_code == 401
    assert client.post("/api/v1/auth/token/mfa/verify", body).status_code == 429


@pytest.mark.django_db
def test_malformed_mobile_auth_body_counts_toward_auth_limit(
    one_request_auth_throttle_rate: None,
):
    client = APIClient()

    malformed = client.generic(
        "POST", "/api/v1/auth/token", data=b"{", content_type="application/json"
    )
    assert malformed.status_code == 400
    assert (
        client.post(
            "/api/v1/auth/token", {"email": "unknown@example.com", "password": "incorrect"}
        ).status_code
        == 429
    )


@pytest.mark.django_db
def test_malformed_browser_login_body_counts_toward_auth_limit(
    one_request_auth_throttle_rate: None,
):
    user = create_staff("session-rate@example.com")
    client, csrf = csrf_client()

    malformed = client.generic(
        "POST",
        "/api/v1/auth/session/login",
        data=b"{",
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert malformed.status_code == 400
    assert web_password_step(client, csrf, user.email).status_code == 429


@pytest.mark.django_db
def test_oversized_mobile_auth_body_counts_toward_auth_limit(
    one_request_auth_throttle_rate: None,
):
    client = APIClient()

    with override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=8):
        oversized = client.generic(
            "POST", "/api/v1/auth/token", data=b"{" + b" " * 64, content_type="application/json"
        )
        assert oversized.status_code == 400
        blocked = client.post(
            "/api/v1/auth/token", {"email": "unknown@example.com", "password": "incorrect"}
        )
    assert blocked.status_code == 429


@pytest.mark.django_db
def test_mobile_refresh_and_logout_are_public_but_require_refresh_tokens():
    client = APIClient()

    assert client.post("/api/v1/auth/token/refresh", {}).status_code == 400
    assert client.post("/api/v1/auth/token/logout", {}).status_code == 400


@pytest.mark.django_db
def test_browser_session_login_requires_csrf_and_uses_session_cookie():
    user = create_staff("web@example.com")
    totp = enroll_totp(user)
    client = APIClient(enforce_csrf_checks=True)
    without_csrf = client.post(
        "/api/v1/auth/session/login",
        {"email": user.email, "password": PASSWORD},
        format="json",
    )
    assert without_csrf.status_code == 403

    client, csrf = web_login(user, totp)
    assert "sessionid" in client.cookies
    assert client.get("/api/v1/users/me").status_code == 200
    assert client.post("/api/v1/auth/session/logout").status_code == 403
    assert client.get("/api/v1/users/me").status_code == 200


@pytest.mark.django_db
def test_schema_requires_an_mfa_verified_staff_session():
    user = create_staff("schema@example.com")
    client = APIClient()

    assert client.get("/api/schema/").status_code == 401
    client.force_authenticate(user=user)
    assert client.get("/api/schema/").status_code == 403

    client.force_authenticate(user=user, token=mfa_session_for(user))
    assert client.get("/api/schema/").status_code == 200
