"""Two-step staff sign-in: password, then a mandatory second factor.

After the password step nobody is authenticated: the web gets an "MFA pending" marker
in its (anonymous) Django session, mobile gets a short-lived signed challenge. Only a
successful second factor (or first-time enrollment of one) creates a tracked
`UserSession`, i.e. a Django login or a JWT pair. Every staff permission requires that
session, so no endpoint, refresh or Django admin page is reachable with a password alone.
"""

import secrets
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.http import HttpRequest
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from apps.audit.models import AuditEvent
from apps.audit.services import record_event

from . import lockout, mfa
from .auth_sessions import start_mobile_session, start_web_session
from .models import User, UserSession

VERIFY = "verify"
ENROLL = "enroll"
PENDING_KEY = "_mfa_pending"
WEBAUTHN_KEY = "_webauthn_challenge"
CHALLENGE_SALT = "accounts.mfa-challenge"


class FlowError(Exception):
    """The pending sign-in cannot continue. Views answer 401 with a generic message."""


@dataclass(frozen=True)
class Pending:
    user: User
    stage: str
    nonce: str


def stage_for(user: User) -> str:
    return VERIFY if mfa.has_mfa(user) else ENROLL


def _fingerprint(user: User) -> str:
    """Binds a pending state to the current password hash: a password change voids it."""
    return salted_hmac("accounts.mfa-pending", user.password).hexdigest()[:32]


def _load(data: Any, stage: str | None) -> Pending:
    if not isinstance(data, dict):
        raise FlowError
    uid = data.get("uid")
    if not isinstance(uid, int):
        raise FlowError
    user = User.objects.filter(pk=uid).first()
    if user is None or not (user.is_active and user.is_staff):
        raise FlowError
    if not constant_time_compare(str(data.get("pwd", "")), _fingerprint(user)):
        raise FlowError
    current_stage = stage_for(user)
    # The stage is re-derived from the database: an "enroll" state can never be used to add
    # a factor once the account has one (enrollment needs step-up from a full session).
    if data.get("stage") != current_stage or (stage is not None and stage != current_stage):
        raise FlowError
    if lockout.is_locked(user.email):
        raise FlowError
    return Pending(user=user, stage=current_stage, nonce=str(data.get("nonce", "")))


# --- Web (Django session) ----------------------------------------------------------------


def begin_web(request: HttpRequest, user: User) -> str:
    stage = stage_for(user)
    request.session.cycle_key()
    request.session[PENDING_KEY] = {
        "uid": user.pk,
        "stage": stage,
        "pwd": _fingerprint(user),
        "nonce": secrets.token_urlsafe(16),
        "exp": timezone.now().timestamp() + settings.MFA_PENDING_TTL_SECONDS,
    }
    return stage


def web_pending(request: HttpRequest, stage: str | None = None) -> Pending:
    data = request.session.get(PENDING_KEY)
    if not isinstance(data, dict) or float(data.get("exp", 0)) < timezone.now().timestamp():
        request.session.pop(PENDING_KEY, None)
        raise FlowError
    return _load(data, stage)


def complete_web(request: HttpRequest, pending: Pending, method: str) -> UserSession:
    request.session.pop(PENDING_KEY, None)
    request.session.pop(WEBAUTHN_KEY, None)
    tracked = start_web_session(request, pending.user, mfa_method=method)
    _signed_in(request, pending.user, tracked, method, "web")
    return tracked


# --- Mobile (signed challenge) -----------------------------------------------------------


def begin_mobile(user: User) -> tuple[str, str]:
    stage = stage_for(user)
    payload = {
        "uid": user.pk,
        "stage": stage,
        "pwd": _fingerprint(user),
        "nonce": secrets.token_urlsafe(16),
    }
    return stage, signing.dumps(payload, salt=CHALLENGE_SALT, compress=True)


def mobile_pending(challenge: str, stage: str | None = None) -> Pending:
    try:
        data = signing.loads(
            challenge, salt=CHALLENGE_SALT, max_age=settings.MFA_PENDING_TTL_SECONDS
        )
    except signing.BadSignature as error:
        raise FlowError from error
    pending = _load(data, stage)
    if cache.get(_used_key(pending.nonce)):
        raise FlowError
    return pending


def _used_key(nonce: str) -> str:
    return f"mfa-challenge-used:{nonce}"


def complete_mobile(request: Any, pending: Pending, method: str) -> dict[str, str]:
    # Single use: the first completion wins, any replay of the challenge is refused.
    if not cache.add(_used_key(pending.nonce), True, settings.MFA_PENDING_TTL_SECONDS + 60):
        raise FlowError
    tracked, tokens = start_mobile_session(request, pending.user, mfa_method=method)
    _signed_in(request, pending.user, tracked, method, "mobile")
    return tokens


# --- Shared ------------------------------------------------------------------------------


def _signed_in(request: Any, user: User, tracked: UserSession, method: str, channel: str) -> None:
    lockout.reset(user.email)
    record_event(
        "auth.login.success",
        request=request,
        actor=user,
        target=tracked,
        metadata={"channel": channel, "mfa_method": method},
    )


def check_second_factor(
    request: Any,
    user: User,
    method: str,
    *,
    code: str = "",
    credential: dict[str, Any] | None = None,
    webauthn_challenge: str | None = None,
) -> None:
    """Verify one second-factor proof or raise FlowError. Failures count toward lockout."""
    if lockout.is_locked(user.email):
        raise FlowError
    if method == mfa.TOTP:
        valid = mfa.verify_totp(user, code)
    elif method == mfa.RECOVERY:
        valid = mfa.has_mfa(user) and mfa.use_recovery_code(user, code)
    elif method == mfa.WEBAUTHN:
        valid = bool(
            credential
            and webauthn_challenge
            and mfa.verify_webauthn_assertion(user, credential, webauthn_challenge)
        )
    else:
        valid = False
    if not valid:
        record_event(
            "mfa.verify.failure",
            request=request,
            actor=user,
            target=user,
            outcome=AuditEvent.Outcome.FAILURE,
            metadata={"method": method},
        )
        if lockout.register_failure(user.email):
            record_event(
                "auth.lockout",
                request=request,
                actor=user,
                target=user,
                outcome=AuditEvent.Outcome.FAILURE,
                metadata={"reason": "mfa_failures"},
            )
        raise FlowError
    metadata: dict[str, Any] = {"method": method}
    if method == mfa.RECOVERY:
        metadata["remaining"] = mfa.remaining_recovery_codes(user)
        record_event(
            "mfa.recovery_used", request=request, actor=user, target=user, metadata=metadata
        )
    record_event("mfa.verify.success", request=request, actor=user, target=user, metadata=metadata)


def pop_webauthn_challenge(request: HttpRequest, purpose: str, user: User) -> str | None:
    data = request.session.pop(WEBAUTHN_KEY, None)
    if (
        not isinstance(data, dict)
        or data.get("purpose") != purpose
        or data.get("uid") != user.pk
        or float(data.get("exp", 0)) < timezone.now().timestamp()
    ):
        return None
    challenge = data.get("challenge")
    return challenge if isinstance(challenge, str) else None


def store_webauthn_challenge(
    request: HttpRequest, purpose: str, user: User, challenge: str
) -> None:
    request.session[WEBAUTHN_KEY] = {
        "purpose": purpose,
        "uid": user.pk,
        "challenge": challenge,
        "exp": timezone.now().timestamp() + settings.MFA_PENDING_TTL_SECONDS,
    }


def mark_step_up(tracked: UserSession, method: str) -> None:
    now = timezone.now()
    UserSession.objects.filter(pk=tracked.pk).update(mfa_verified_at=now, mfa_method=method)
    tracked.mfa_verified_at = now
    tracked.mfa_method = method
