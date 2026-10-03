"""Second factors: WebAuthn/passkeys (preferred), TOTP (fallback) and recovery codes.

No custom cryptography: TOTP uses `pyotp`, WebAuthn uses `webauthn` (py_webauthn),
secrets at rest use Fernet from `cryptography`, recovery codes use HMAC-SHA256.
Keys derive from `MFA_SECRET_KEY` (defaults to `SECRET_KEY`); rotating it invalidates
TOTP secrets and recovery codes, so rotate it together with an MFA re-enrollment.
"""

import base64
import hashlib
import hmac
import secrets
from datetime import datetime
from typing import Any

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from .models import RecoveryCode, TOTPDevice, User, WebAuthnCredential

TOTP = "totp"
WEBAUTHN = "webauthn"
RECOVERY = "recovery"
RECOVERY_CODE_COUNT = 10
RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I ambiguity


class MfaError(Exception):
    """A second-factor proof was invalid. Callers answer with a generic message."""


def _key(purpose: str) -> bytes:
    return hashlib.sha256(f"ramoverde.{purpose}:{settings.MFA_SECRET_KEY}".encode()).digest()


def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(_key("mfa.totp-secret")))


# --- Methods -----------------------------------------------------------------------------


def enrolled_methods(user: User) -> list[str]:
    """Usable second factors, strongest first. Recovery codes count only alongside another."""
    methods = []
    if WebAuthnCredential.objects.filter(user=user).exists():
        methods.append(WEBAUTHN)
    if TOTPDevice.objects.filter(user=user, confirmed_at__isnull=False).exists():
        methods.append(TOTP)
    if methods and remaining_recovery_codes(user):
        methods.append(RECOVERY)
    return methods


def has_mfa(user: User) -> bool:
    return any(method in (WEBAUTHN, TOTP) for method in enrolled_methods(user))


# --- TOTP --------------------------------------------------------------------------------


def start_totp_enrollment(user: User) -> tuple[str, str]:
    """Create an unconfirmed device; return (secret, otpauth URI) to show once."""
    TOTPDevice.objects.filter(user=user, confirmed_at__isnull=True).delete()
    secret = pyotp.random_base32(32)
    TOTPDevice.objects.create(
        user=user, encrypted_secret=_fernet().encrypt(secret.encode()).decode()
    )
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=settings.MFA_ISSUER)
    return secret, uri


def _secret(device: TOTPDevice) -> str:
    try:
        return _fernet().decrypt(device.encrypted_secret.encode()).decode()
    except InvalidToken as error:
        raise MfaError from error


def _accept_totp(device: TOTPDevice, code: str, now: datetime | None = None) -> bool:
    code = code.strip().replace(" ", "")
    if len(code) != 6 or not code.isdigit():
        return False
    totp = pyotp.TOTP(_secret(device))
    current = totp.timecode(now or timezone.now())
    for step in (current - 1, current, current + 1):
        if hmac.compare_digest(totp.generate_otp(step), code):
            # Atomic compare-and-set: the same or an older step can never be accepted again.
            return (
                TOTPDevice.objects.filter(pk=device.pk, last_used_step__lt=step).update(
                    last_used_step=step
                )
                == 1
            )
    return False


def confirm_totp_enrollment(user: User, code: str) -> bool:
    device = TOTPDevice.objects.filter(user=user, confirmed_at__isnull=True).order_by("-id").first()
    if device is None or not _accept_totp(device, code):
        return False
    with transaction.atomic():
        TOTPDevice.objects.filter(user=user).exclude(pk=device.pk).delete()
        TOTPDevice.objects.filter(pk=device.pk).update(confirmed_at=timezone.now())
    return True


def verify_totp(user: User, code: str) -> bool:
    device = TOTPDevice.objects.filter(user=user, confirmed_at__isnull=False).first()
    return device is not None and _accept_totp(device, code)


def remove_totp(user: User) -> None:
    TOTPDevice.objects.filter(user=user).delete()


def remove_all_factors(user: User) -> None:
    """Administrative reset: the user must enroll MFA again at next sign-in."""
    TOTPDevice.objects.filter(user=user).delete()
    WebAuthnCredential.objects.filter(user=user).delete()
    RecoveryCode.objects.filter(user=user).delete()


# --- Recovery codes ----------------------------------------------------------------------


def _normalize_recovery(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def _recovery_hash(code: str) -> str:
    return hmac.new(_key("mfa.recovery"), _normalize_recovery(code).encode(), "sha256").hexdigest()


def generate_recovery_codes(user: User) -> list[str]:
    """Replace all recovery codes; the plaintext is returned once and never stored."""
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    with transaction.atomic():
        RecoveryCode.objects.filter(user=user).delete()
        RecoveryCode.objects.bulk_create(
            [RecoveryCode(user=user, code_hash=_recovery_hash(code)) for code in codes]
        )
    return codes


def use_recovery_code(user: User, code: str) -> bool:
    """Consume one unused code atomically (single use even under concurrency)."""
    return (
        RecoveryCode.objects.filter(
            user=user, code_hash=_recovery_hash(code), used_at__isnull=True
        ).update(used_at=timezone.now())
        == 1
    )


def remaining_recovery_codes(user: User) -> int:
    return RecoveryCode.objects.filter(user=user, used_at__isnull=True).count()


# --- WebAuthn ----------------------------------------------------------------------------


def _descriptors(user: User) -> list[PublicKeyCredentialDescriptor]:
    descriptors = []
    for credential in WebAuthnCredential.objects.filter(user=user):
        transports = []
        for value in credential.transports:
            try:
                transports.append(AuthenticatorTransport(value))
            except ValueError:
                continue
        descriptors.append(
            PublicKeyCredentialDescriptor(
                id=base64url_to_bytes(credential.credential_id), transports=transports or None
            )
        )
    return descriptors


def webauthn_registration_options(user: User) -> tuple[dict[str, Any], str]:
    """Return (PublicKeyCredentialCreationOptions JSON, base64url challenge)."""
    options = generate_registration_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=hashlib.sha256(f"user:{user.pk}".encode()).digest(),
        user_name=user.email,
        user_display_name=user.get_full_name() or user.email,
        exclude_credentials=_descriptors(user),
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        attestation=AttestationConveyancePreference.NONE,
    )
    return _as_json(options), bytes_to_base64url(options.challenge)


def register_webauthn_credential(
    user: User, credential: dict[str, Any], challenge: str, name: str
) -> WebAuthnCredential:
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge),
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.WEBAUTHN_ORIGINS,
            require_user_verification=True,
        )
    except (InvalidRegistrationResponse, KeyError, TypeError, ValueError) as error:
        raise MfaError from error
    credential_id = bytes_to_base64url(verified.credential_id)
    if WebAuthnCredential.objects.filter(credential_id=credential_id).exists():
        raise MfaError
    transports = credential.get("response", {}).get("transports") or []
    return WebAuthnCredential.objects.create(
        user=user,
        credential_id=credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        transports=[str(value) for value in transports][:8],
        name=name[:64] or "Passkey",
    )


def webauthn_authentication_options(user: User) -> tuple[dict[str, Any], str]:
    options = generate_authentication_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        allow_credentials=_descriptors(user),
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return _as_json(options), bytes_to_base64url(options.challenge)


def verify_webauthn_assertion(user: User, credential: dict[str, Any], challenge: str) -> bool:
    stored = WebAuthnCredential.objects.filter(
        user=user, credential_id=credential.get("id")
    ).first()
    if stored is None:
        return False
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge),
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.WEBAUTHN_ORIGINS,
            credential_public_key=bytes(stored.public_key),
            credential_current_sign_count=stored.sign_count,
            require_user_verification=True,
        )
    except (InvalidAuthenticationResponse, KeyError, TypeError, ValueError):
        return False
    # Compare-and-set on the counter so a cloned authenticator / replay cannot race.
    return (
        WebAuthnCredential.objects.filter(pk=stored.pk, sign_count=stored.sign_count).update(
            sign_count=verified.new_sign_count, last_used_at=timezone.now()
        )
        == 1
    )


def _as_json(options: Any) -> dict[str, Any]:
    import json

    parsed: dict[str, Any] = json.loads(options_to_json(options))
    return parsed
