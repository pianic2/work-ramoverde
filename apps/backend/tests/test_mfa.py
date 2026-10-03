"""WR-15: mandatory MFA for every staff account, with negative/bypass tests."""

from datetime import timedelta

import pytest
from auth_helpers import (
    PASSWORD,
    SoftAuthenticator,
    create_staff,
    csrf_client,
    enroll_totp,
    mobile_login,
    mobile_password_step,
    totp_code,
    web_login,
    web_password_step,
    web_post,
)
from django.contrib.sessions.models import Session
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import login_flow, mfa
from apps.accounts.models import RecoveryCode, TOTPDevice, UserSession, WebAuthnCredential
from apps.audit.models import AuditEvent

ME = "/api/v1/users/me"
VERIFY = "/api/v1/auth/session/mfa/verify"


# --- Password alone never authenticates ---------------------------------------------------


@pytest.mark.django_db
def test_password_step_returns_pending_state_without_any_authenticated_session():
    user = create_staff()
    enroll_totp(user)
    client, csrf = csrf_client()

    response = web_password_step(client, csrf, user.email)

    assert response.status_code == 200
    assert response.json() == {"status": "mfa_required", "methods": ["totp"]}
    assert client.get(ME).status_code == 401
    assert not UserSession.objects.exists()
    assert AuditEvent.objects.filter(action="auth.login.password_verified").exists()
    assert not AuditEvent.objects.filter(action="auth.login.success").exists()


@pytest.mark.django_db
def test_password_only_session_cannot_reach_django_admin():
    root = create_staff("root@example.com", is_superuser=True)
    enroll_totp(root)
    client, csrf = csrf_client()
    web_password_step(client, csrf, root.email)
    assert client.get("/django-admin/").status_code == 302


@pytest.mark.django_db
def test_mobile_password_step_never_issues_tokens():
    user = create_staff()
    enroll_totp(user)
    response = mobile_password_step(APIClient(), user.email)
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "mfa_required"
    assert body["methods"] == ["totp"]
    assert "access" not in body and "refresh" not in body
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {body['challenge']}")
    assert client.get(ME).status_code == 401
    assert not UserSession.objects.exists()


# --- Web verification ------------------------------------------------------------------


@pytest.mark.django_db
def test_web_totp_verification_completes_sign_in_and_tracks_the_method():
    user = create_staff()
    totp = enroll_totp(user)
    client, csrf = web_login(user, totp)

    assert client.get(ME).status_code == 200
    tracked = UserSession.objects.get(user=user)
    assert tracked.mfa_method == "totp"
    assert tracked.mfa_verified_at is not None
    success = AuditEvent.objects.get(action="auth.login.success")
    assert success.metadata == {"channel": "web", "mfa_method": "totp"}


@pytest.mark.django_db
def test_mfa_verification_requires_csrf():
    user = create_staff()
    totp = enroll_totp(user)
    client, csrf = csrf_client()
    web_password_step(client, csrf, user.email)
    response = client.post(VERIFY, {"method": "totp", "code": totp.now()}, format="json")
    assert response.status_code == 403
    assert client.get(ME).status_code == 401


@pytest.mark.django_db
def test_wrong_totp_is_rejected_and_audited():
    user = create_staff()
    totp = enroll_totp(user)
    client, csrf = csrf_client()
    web_password_step(client, csrf, user.email)
    wrong = "000000" if totp.now() != "000000" else "111111"

    response = web_post(client, csrf, VERIFY, {"method": "totp", "code": wrong})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "mfa_failed"
    assert client.get(ME).status_code == 401
    assert AuditEvent.objects.filter(action="mfa.verify.failure", actor=user).exists()


@pytest.mark.django_db
def test_totp_code_cannot_be_replayed_within_its_time_step():
    user = create_staff()
    totp = enroll_totp(user)
    code = totp_code(totp)
    web_login(user, totp)

    client, csrf = csrf_client()
    web_password_step(client, csrf, user.email)
    replay = web_post(client, csrf, VERIFY, {"method": "totp", "code": code})
    assert replay.status_code == 401


@pytest.mark.django_db
def test_verify_without_password_step_or_after_expiry_is_rejected(monkeypatch):
    user = create_staff()
    totp = enroll_totp(user)
    client, csrf = csrf_client()
    assert web_post(client, csrf, VERIFY, {"method": "totp", "code": totp.now()}).status_code == 401

    web_password_step(client, csrf, user.email)
    later = timezone.now() + timedelta(seconds=login_flow.settings.MFA_PENDING_TTL_SECONDS + 1)
    monkeypatch.setattr(login_flow.timezone, "now", lambda: later)
    assert web_post(client, csrf, VERIFY, {"method": "totp", "code": totp.now()}).status_code == 401


@pytest.mark.django_db
def test_pending_state_is_void_after_a_password_change():
    user = create_staff()
    totp = enroll_totp(user)
    client, csrf = csrf_client()
    web_password_step(client, csrf, user.email)
    user.set_password("an-entirely-new-passphrase-77")
    user.save()
    assert web_post(client, csrf, VERIFY, {"method": "totp", "code": totp.now()}).status_code == 401


@pytest.mark.django_db
def test_repeated_mfa_failures_lock_the_account_even_for_a_correct_code():
    user = create_staff()
    totp = enroll_totp(user)
    client, csrf = csrf_client()
    web_password_step(client, csrf, user.email)
    wrong = "000000" if totp.now() != "000000" else "111111"
    for _ in range(5):
        web_post(client, csrf, VERIFY, {"method": "totp", "code": wrong})

    assert web_post(client, csrf, VERIFY, {"method": "totp", "code": totp.now()}).status_code == 401
    assert AuditEvent.objects.filter(action="auth.lockout", actor=user).exists()


# --- Recovery codes ----------------------------------------------------------------------


@pytest.mark.django_db
def test_recovery_codes_are_hashed_single_use_and_audited():
    user = create_staff()
    enroll_totp(user)
    codes = mfa.generate_recovery_codes(user)
    assert len(codes) == 10 and len(set(codes)) == 10
    stored = list(RecoveryCode.objects.values_list("code_hash", flat=True))
    assert not any(code in stored or code.replace("-", "") in stored for code in codes)

    client, csrf = csrf_client()
    web_password_step(client, csrf, user.email)
    used = web_post(client, csrf, VERIFY, {"method": "recovery", "code": codes[0].lower()})
    assert used.status_code == 200
    event = AuditEvent.objects.get(action="mfa.recovery_used")
    assert event.metadata == {"method": "recovery", "remaining": 9}

    client, csrf = csrf_client()
    web_password_step(client, csrf, user.email)
    assert (
        web_post(client, csrf, VERIFY, {"method": "recovery", "code": codes[0]}).status_code == 401
    )


@pytest.mark.django_db
def test_recovery_codes_alone_are_not_a_second_factor():
    user = create_staff()
    codes = mfa.generate_recovery_codes(user)
    client, csrf = csrf_client()
    assert web_password_step(client, csrf, user.email).json()["status"] == (
        "mfa_enrollment_required"
    )
    assert (
        web_post(client, csrf, VERIFY, {"method": "recovery", "code": codes[0]}).status_code == 401
    )


# --- First-time enrollment ---------------------------------------------------------------


@pytest.mark.django_db
def test_unenrolled_staff_must_enroll_totp_before_being_signed_in():
    user = create_staff()
    client, csrf = csrf_client()
    assert web_password_step(client, csrf, user.email).json() == {
        "status": "mfa_enrollment_required",
        "methods": [],
    }
    setup = web_post(client, csrf, "/api/v1/auth/session/mfa/totp/setup")
    assert setup.status_code == 200
    assert setup.json()["otpauth_uri"].startswith("otpauth://totp/RamoVerde:")
    assert client.get(ME).status_code == 401
    device = TOTPDevice.objects.get(user=user)
    assert setup.json()["secret"] not in device.encrypted_secret

    import pyotp

    confirm = web_post(
        client,
        csrf,
        "/api/v1/auth/session/mfa/totp/confirm",
        {"code": pyotp.TOTP(setup.json()["secret"]).now()},
    )
    assert confirm.status_code == 200
    body = confirm.json()
    assert body["status"] == "authenticated"
    assert len(body["recovery_codes"]) == 10
    assert client.get(ME).status_code == 200
    assert AuditEvent.objects.filter(action="mfa.enroll", actor=user).exists()


@pytest.mark.django_db
def test_enrollment_endpoints_cannot_add_a_factor_to_an_enrolled_account():
    user = create_staff()
    enroll_totp(user)
    client, csrf = csrf_client()
    web_password_step(client, csrf, user.email)
    assert web_post(client, csrf, "/api/v1/auth/session/mfa/totp/setup").status_code == 401
    assert (
        web_post(client, csrf, "/api/v1/auth/session/mfa/webauthn/register/options").status_code
        == 401
    )
    assert TOTPDevice.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_enrollment_endpoints_require_a_password_step():
    create_staff()
    client, csrf = csrf_client()
    assert web_post(client, csrf, "/api/v1/auth/session/mfa/totp/setup").status_code == 401
    assert not TOTPDevice.objects.exists()


# --- WebAuthn (preferred) ----------------------------------------------------------------


def _enroll_passkey(client, csrf, authenticator: SoftAuthenticator):
    options = web_post(client, csrf, "/api/v1/auth/session/mfa/webauthn/register/options")
    assert options.status_code == 200
    return web_post(
        client,
        csrf,
        "/api/v1/auth/session/mfa/webauthn/register/verify",
        {"credential": authenticator.register(options.json()["options"]), "name": "Laptop"},
    )


@pytest.mark.django_db
def test_passkey_enrollment_then_passkey_sign_in():
    user = create_staff()
    authenticator = SoftAuthenticator()
    client, csrf = csrf_client()
    web_password_step(client, csrf, user.email)
    enrolled = _enroll_passkey(client, csrf, authenticator)
    assert enrolled.status_code == 200, enrolled.content
    assert enrolled.json()["methods"] == ["webauthn", "recovery"]
    assert WebAuthnCredential.objects.get(user=user).name == "Laptop"

    client, csrf = csrf_client()
    assert web_password_step(client, csrf, user.email).json()["methods"] == [
        "webauthn",
        "recovery",
    ]
    options = web_post(client, csrf, "/api/v1/auth/session/mfa/webauthn/options").json()["options"]
    assertion = authenticator.assert_(options)
    response = web_post(client, csrf, VERIFY, {"method": "webauthn", "credential": assertion})
    assert response.status_code == 200, response.content
    assert client.get(ME).status_code == 200
    assert WebAuthnCredential.objects.get(user=user).sign_count == 1

    # The same assertion (challenge already consumed) cannot be replayed.
    client, csrf = csrf_client()
    web_password_step(client, csrf, user.email)
    web_post(client, csrf, "/api/v1/auth/session/mfa/webauthn/options")
    assert (
        web_post(client, csrf, VERIFY, {"method": "webauthn", "credential": assertion}).status_code
        == 401
    )


@pytest.mark.django_db
def test_passkey_from_a_foreign_origin_is_rejected():
    user = create_staff()
    client, csrf = csrf_client()
    web_password_step(client, csrf, user.email)
    options = web_post(client, csrf, "/api/v1/auth/session/mfa/webauthn/register/options")
    credential = SoftAuthenticator().register(
        options.json()["options"], origin="https://evil.example"
    )
    response = web_post(
        client,
        csrf,
        "/api/v1/auth/session/mfa/webauthn/register/verify",
        {"credential": credential},
    )
    assert response.status_code == 401
    assert not WebAuthnCredential.objects.exists()
    assert client.get(ME).status_code == 401


# --- Mobile ------------------------------------------------------------------------------


@pytest.mark.django_db
def test_mobile_challenge_is_single_use():
    user = create_staff()
    totp = enroll_totp(user)
    client = APIClient()
    challenge = mobile_password_step(client, user.email).json()["challenge"]
    first = client.post(
        "/api/v1/auth/token/mfa/verify",
        {"challenge": challenge, "method": "totp", "code": totp_code(totp, -1)},
        format="json",
    )
    assert first.status_code == 200
    assert {"access", "refresh"} <= first.json().keys()
    second = client.post(
        "/api/v1/auth/token/mfa/verify",
        {"challenge": challenge, "method": "totp", "code": totp_code(totp)},
        format="json",
    )
    assert second.status_code == 401


@pytest.mark.django_db
def test_tampered_or_foreign_challenges_are_rejected():
    user = create_staff()
    totp = enroll_totp(user)
    client = APIClient()
    challenge = mobile_password_step(client, user.email).json()["challenge"]
    for bad in (challenge[:-2] + "xx", "not-a-challenge"):
        response = client.post(
            "/api/v1/auth/token/mfa/verify",
            {"challenge": bad, "method": "totp", "code": totp.now()},
            format="json",
        )
        assert response.status_code == 401


@pytest.mark.django_db
def test_mobile_enrollment_issues_tokens_and_recovery_codes():
    import pyotp

    user = create_staff()
    client = APIClient()
    flow = mobile_password_step(client, user.email).json()
    assert flow["status"] == "mfa_enrollment_required"
    setup = client.post(
        "/api/v1/auth/token/mfa/totp/setup", {"challenge": flow["challenge"]}, format="json"
    )
    assert setup.status_code == 200
    confirm = client.post(
        "/api/v1/auth/token/mfa/totp/confirm",
        {"challenge": flow["challenge"], "code": pyotp.TOTP(setup.json()["secret"]).now()},
        format="json",
    )
    assert confirm.status_code == 200
    assert len(confirm.json()["recovery_codes"]) == 10
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {confirm.json()['access']}")
    assert client.get(ME).status_code == 200


@pytest.mark.django_db
def test_mobile_verify_challenge_cannot_enroll_an_extra_factor():
    user = create_staff()
    enroll_totp(user)
    client = APIClient()
    challenge = mobile_password_step(client, user.email).json()["challenge"]
    response = client.post(
        "/api/v1/auth/token/mfa/totp/setup", {"challenge": challenge}, format="json"
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_mobile_does_not_offer_webauthn():
    user = create_staff()
    WebAuthnCredential.objects.create(user=user, credential_id="x", public_key=b"k", name="Key")
    flow = mobile_password_step(APIClient(), user.email).json()
    assert flow["status"] == "mfa_required"
    assert "webauthn" not in flow["methods"]


# --- Step-up and factor management -------------------------------------------------------


def _age_session(user, minutes: int = 10) -> None:
    UserSession.objects.filter(user=user).update(
        mfa_verified_at=timezone.now() - timedelta(minutes=minutes)
    )


@pytest.mark.django_db
def test_sensitive_mfa_changes_require_recent_step_up():
    user = create_staff()
    totp = enroll_totp(user)
    client, csrf = web_login(user, totp, offset_steps=-1)
    _age_session(user)

    stale = web_post(client, csrf, "/api/v1/auth/mfa/recovery-codes")
    assert stale.status_code == 403
    assert stale.json()["error"]["code"] == "step_up_required"

    step_up = web_post(client, csrf, "/api/v1/auth/step-up", {"method": "totp", "code": totp.now()})
    assert step_up.status_code == 200
    regenerated = web_post(client, csrf, "/api/v1/auth/mfa/recovery-codes")
    assert regenerated.status_code == 200
    assert len(regenerated.json()["recovery_codes"]) == 10
    assert AuditEvent.objects.filter(action="mfa.step_up", actor=user).exists()


@pytest.mark.django_db
def test_mobile_step_up_with_totp():
    user = create_staff()
    totp = enroll_totp(user)
    tokens = mobile_login(user, totp, offset_steps=-1)
    _age_session(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    assert client.post("/api/v1/auth/mfa/recovery-codes").status_code == 403
    assert (
        client.post(
            "/api/v1/auth/step-up", {"method": "totp", "code": totp.now()}, format="json"
        ).status_code
        == 200
    )
    assert client.post("/api/v1/auth/mfa/recovery-codes").status_code == 200


@pytest.mark.django_db
def test_the_last_second_factor_cannot_be_removed():
    user = create_staff()
    totp = enroll_totp(user)
    client, csrf = web_login(user, totp)
    response = client.delete("/api/v1/auth/mfa/totp", HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == 400
    assert TOTPDevice.objects.filter(user=user, confirmed_at__isnull=False).exists()


@pytest.mark.django_db
def test_mfa_status_lists_enrolled_factors():
    user = create_staff()
    totp = enroll_totp(user)
    mfa.generate_recovery_codes(user)
    client, _ = web_login(user, totp)
    body = client.get("/api/v1/auth/mfa").json()
    assert body["methods"] == ["totp", "recovery"]
    assert body["totp_enabled"] is True
    assert body["recovery_codes_remaining"] == 10


# --- Permission layer --------------------------------------------------------------------


@pytest.mark.django_db
def test_forced_authentication_without_mfa_session_is_denied():
    user = create_staff()
    client = APIClient()
    client.force_authenticate(user=user)
    assert client.get(ME).status_code == 403

    unverified = UserSession.objects.create(user=user, kind=UserSession.Kind.WEB)
    client.force_authenticate(user=user, token=unverified)
    assert client.get(ME).status_code == 403


@pytest.mark.django_db
def test_django_admin_password_form_still_cannot_bypass_mfa():
    root = create_staff("root@example.com", is_superuser=True)
    enroll_totp(root)
    client = APIClient()
    client.post("/django-admin/login/", {"username": root.email, "password": PASSWORD})
    assert not Session.objects.exists()
    assert client.get("/django-admin/").status_code == 302


@pytest.mark.django_db
def test_cms_and_media_staff_apis_refuse_sessions_without_mfa():
    from django.contrib.auth.models import Permission

    user = create_staff()
    enroll_totp(user)
    user.user_permissions.add(
        *Permission.objects.filter(codename__in=["view_page", "view_mediaasset"])
    )
    client, csrf = csrf_client()
    web_password_step(client, csrf, user.email)  # password only, MFA pending
    assert client.get("/api/v1/cms/pages").status_code == 401
    assert client.get("/api/v1/media/assets").status_code == 401

    forced = APIClient()
    forced.force_authenticate(user=user)  # authenticated but no MFA-verified session
    assert forced.get("/api/v1/cms/pages").status_code == 403
    assert forced.get("/api/v1/media/assets").status_code == 403
