"""Test helpers for the MFA-protected staff sign-in flows.

Other modules' tests can authenticate a staff user with::

    client.force_authenticate(user=user, token=mfa_session_for(user))

which mirrors what `StaffJWTAuthentication`/`StaffSessionAuthentication` attach to
`request.auth` after a real password + second-factor sign-in.
"""

import base64
import hashlib
import json
import os
from datetime import timedelta
from typing import Any

import cbor2
import pyotp
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import mfa
from apps.accounts.models import TOTPDevice, User, UserSession

PASSWORD = "correct-horse-battery-staple"


def create_staff(email: str = "staff@example.com", **extra: Any) -> User:
    extra.setdefault("is_staff", True)
    return User.objects.create_user(email=email, password=PASSWORD, **extra)


def enroll_totp(user: User) -> pyotp.TOTP:
    """Give the user a confirmed TOTP device; return a generator for its codes."""
    secret, _ = mfa.start_totp_enrollment(user)
    TOTPDevice.objects.filter(user=user).update(confirmed_at=timezone.now())
    return pyotp.TOTP(secret)


def totp_code(totp: pyotp.TOTP, offset_steps: int = 0) -> str:
    return totp.at(timezone.now() + timedelta(seconds=30 * offset_steps))


def mfa_session_for(user: User, kind: str = UserSession.Kind.WEB) -> UserSession:
    """A tracked, MFA-verified session to pass as `token` to `force_authenticate`."""
    return UserSession.objects.create(
        user=user, kind=kind, mfa_method="totp", mfa_verified_at=timezone.now()
    )


def force_staff_login(client: Any, user: User) -> UserSession:
    """Django-session login equivalent to a completed password + MFA sign-in (tests only),
    e.g. for Django admin pages, which require a tracked, MFA-verified web session."""
    from apps.accounts.auth_sessions import SESSION_ID_KEY

    client.force_login(user)
    session = client.session
    tracked = UserSession.objects.create(
        user=user,
        kind=UserSession.Kind.WEB,
        session_key=session.session_key,
        mfa_method="totp",
        mfa_verified_at=timezone.now(),
    )
    session[SESSION_ID_KEY] = tracked.pk
    session.save()
    return tracked


def csrf_client() -> tuple[APIClient, str]:
    client = APIClient(enforce_csrf_checks=True, HTTP_USER_AGENT="Firefox/140 test")
    return client, client.get("/api/v1/auth/csrf").json()["csrfToken"]


def web_post(client: APIClient, csrf: str, path: str, data: Any = None):
    return client.post(path, data or {}, format="json", HTTP_X_CSRFTOKEN=csrf)


def web_password_step(client: APIClient, csrf: str, email: str, password: str = PASSWORD):
    return web_post(
        client, csrf, "/api/v1/auth/session/login", {"email": email, "password": password}
    )


def web_login(user: User, totp: pyotp.TOTP, offset_steps: int = 0) -> tuple[APIClient, str]:
    """Full web sign-in (password + TOTP). Returns the client and a fresh CSRF token."""
    client, csrf = csrf_client()
    assert web_password_step(client, csrf, user.email).status_code == 200
    response = web_post(
        client,
        csrf,
        "/api/v1/auth/session/mfa/verify",
        {"method": "totp", "code": totp_code(totp, offset_steps)},
    )
    assert response.status_code == 200, response.content
    return client, client.get("/api/v1/auth/csrf").json()["csrfToken"]


def mobile_password_step(client: APIClient, email: str, password: str = PASSWORD):
    return client.post(
        "/api/v1/auth/token",
        {"email": email, "password": password},
        format="json",
        HTTP_USER_AGENT="RamoVerdeStaff/1.0 (Android 15)",
    )


def mobile_login(user: User, totp: pyotp.TOTP, offset_steps: int = 0) -> dict[str, str]:
    client = APIClient()
    challenge = mobile_password_step(client, user.email).json()["challenge"]
    response = client.post(
        "/api/v1/auth/token/mfa/verify",
        {"challenge": challenge, "method": "totp", "code": totp_code(totp, offset_steps)},
        format="json",
        HTTP_USER_AGENT="RamoVerdeStaff/1.0 (Android 15)",
    )
    assert response.status_code == 200, response.content
    tokens: dict[str, str] = response.json()
    return tokens


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class SoftAuthenticator:
    """Minimal software WebAuthn authenticator (ES256, `none` attestation) for tests."""

    def __init__(self, rp_id: str = "localhost", origin: str = "http://localhost:5180"):
        self.rp_id = rp_id
        self.origin = origin
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(16)
        self.sign_count = 0

    def _cose_key(self) -> bytes:
        numbers = self.key.public_key().public_numbers()
        return cbor2.dumps(
            {
                1: 2,
                3: -7,
                -1: 1,
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )

    def _client_data(self, kind: str, challenge: str, origin: str | None) -> bytes:
        return json.dumps(
            {"type": kind, "challenge": challenge, "origin": origin or self.origin}
        ).encode()

    def register(self, options: dict[str, Any], origin: str | None = None) -> dict[str, Any]:
        rp_hash = hashlib.sha256(self.rp_id.encode()).digest()
        auth_data = (
            rp_hash
            + bytes([0x45])  # user present + user verified + attested credential data
            + self.sign_count.to_bytes(4, "big")
            + bytes(16)
            + len(self.credential_id).to_bytes(2, "big")
            + self.credential_id
            + self._cose_key()
        )
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        client_data = self._client_data("webauthn.create", options["challenge"], origin)
        return {
            "id": _b64url(self.credential_id),
            "rawId": _b64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": _b64url(client_data),
                "attestationObject": _b64url(attestation),
                "transports": ["internal"],
            },
            "clientExtensionResults": {},
        }

    def assert_(self, options: dict[str, Any], origin: str | None = None) -> dict[str, Any]:
        self.sign_count += 1
        rp_hash = hashlib.sha256(self.rp_id.encode()).digest()
        auth_data = rp_hash + bytes([0x05]) + self.sign_count.to_bytes(4, "big")
        client_data = self._client_data("webauthn.get", options["challenge"], origin)
        signature = self.key.sign(
            auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256())
        )
        return {
            "id": _b64url(self.credential_id),
            "rawId": _b64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": _b64url(client_data),
                "authenticatorData": _b64url(auth_data),
                "signature": _b64url(signature),
            },
            "clientExtensionResults": {},
        }
