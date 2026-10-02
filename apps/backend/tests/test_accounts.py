import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

User = get_user_model()
AUTH_THROTTLE_RATES = {
    "auth_session_login": "1/minute",
    "auth_token_obtain": "1/minute",
    "auth_token_refresh": "1/minute",
    "auth_token_logout": "1/minute",
}


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    cache.clear()


@pytest.fixture
def one_request_auth_throttle_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    from rest_framework.throttling import ScopedRateThrottle

    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", AUTH_THROTTLE_RATES)


@pytest.mark.django_db
def test_current_user_requires_auth_and_returns_email_identity():
    user = User.objects.create_user(email="ada@example.com", password="correct-horse-battery")
    client = APIClient()
    assert client.get("/api/v1/users/me").status_code == 401
    client.force_authenticate(user=user)
    response = client.get("/api/v1/users/me")
    assert response.status_code == 200
    assert response.json()["email"] == "ada@example.com"


@pytest.mark.django_db
def test_mobile_jwt_can_access_current_user():
    user = User.objects.create_user(email="mobile@example.com", password="correct-horse-battery")
    client = APIClient()
    token = client.post(
        "/api/v1/auth/token", {"email": user.email, "password": "correct-horse-battery"}
    )
    assert token.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.json()['access']}")
    assert client.get("/api/v1/users/me").json()["email"] == user.email


@pytest.mark.django_db
def test_valid_mobile_token_attempts_are_throttled_without_throttling_other_api_scopes(
    one_request_auth_throttle_rate: None,
):
    user = User.objects.create_user(email="rate@example.com", password="correct-horse-battery")
    client = APIClient()
    credentials = {"email": user.email, "password": "correct-horse-battery"}

    assert client.post("/api/v1/auth/token", credentials).status_code == 200
    assert client.post("/api/v1/auth/token", credentials).status_code == 429

    client.force_authenticate(user=user)
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
    user = User.objects.create_user(email="session-rate@example.com", password="correct-horse")
    client = APIClient(enforce_csrf_checks=True)
    csrf = client.get("/api/v1/auth/csrf").json()["csrfToken"]

    malformed = client.generic(
        "POST",
        "/api/v1/auth/session/login",
        data=b"{",
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert malformed.status_code == 400

    blocked = client.post(
        "/api/v1/auth/session/login",
        {"email": user.email, "password": "correct-horse"},
        format="json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert blocked.status_code == 429


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
    User.objects.create_user(email="web@example.com", password="correct-horse-battery")
    client = APIClient(enforce_csrf_checks=True)
    without_csrf = client.post(
        "/api/v1/auth/session/login",
        {"email": "web@example.com", "password": "correct-horse-battery"},
        format="json",
    )
    assert without_csrf.status_code == 403
    csrf_response = client.get("/api/v1/auth/csrf")
    csrf = csrf_response.json()["csrfToken"]
    response = client.post(
        "/api/v1/auth/session/login",
        {"email": "web@example.com", "password": "correct-horse-battery"},
        format="json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 200
    assert "sessionid" in response.cookies
    assert client.get("/api/v1/users/me").status_code == 200
    assert client.post("/api/v1/auth/session/logout").status_code == 403
    assert client.get("/api/v1/users/me").status_code == 200


@pytest.mark.django_db
def test_schema_requires_authentication():
    user = User.objects.create_user(email="schema@example.com", password="correct-horse-battery")
    client = APIClient()

    assert client.get("/api/schema/").status_code == 401

    client.force_authenticate(user=user)
    assert client.get("/api/schema/").status_code == 200
