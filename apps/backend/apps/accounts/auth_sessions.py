"""Tracked sign-in sessions (web and mobile) and their revocation."""

from datetime import timedelta
from typing import Any, cast

from django.conf import settings
from django.contrib.auth import login
from django.contrib.sessions.backends.base import SessionBase
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone
from rest_framework_simplejwt.exceptions import TokenBackendError, TokenError
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.state import token_backend
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.utils import get_md5_hash_password

from apps.audit.models import AuditEvent
from apps.audit.services import USER_AGENT_MAX_LENGTH, client_ip, record_event

from .models import User, UserSession

SESSION_ID_KEY = "_staff_session_id"
SESSION_CLAIM = "sid"
LAST_SEEN_RESOLUTION = timedelta(minutes=1)


def _metadata(request: Any) -> dict[str, Any]:
    meta = getattr(request, "META", {})
    return {
        "ip_address": client_ip(request),
        "user_agent": str(meta.get("HTTP_USER_AGENT", ""))[:USER_AGENT_MAX_LENGTH],
    }


def start_web_session(request: HttpRequest, user: User) -> UserSession:
    """Log the user into Django's session (rotating its key) and track it."""
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    session: SessionBase = request.session
    if session.session_key is None:
        session.save()
    tracked = UserSession.objects.create(
        user=user,
        kind=UserSession.Kind.WEB,
        session_key=session.session_key or "",
        **_metadata(request),
    )
    session[SESSION_ID_KEY] = tracked.pk
    return tracked


def active_web_session(request: HttpRequest) -> UserSession | None:
    """The tracked session behind this Django session, if it is still active."""
    user = getattr(request, "user", None)
    session = getattr(request, "session", None)
    if user is None or session is None or not user.is_authenticated or not user.is_active:
        return None
    session_id = session.get(SESSION_ID_KEY)
    if session_id is None or session.session_key is None:
        return None
    return (
        UserSession.objects.select_related("user")
        .filter(
            pk=session_id,
            user_id=user.pk,
            kind=UserSession.Kind.WEB,
            session_key=session.session_key,
            revoked_at__isnull=True,
        )
        .first()
    )


def start_mobile_session(request: Any, user: User) -> tuple[UserSession, dict[str, str]]:
    """Track a new mobile device and issue its first access/refresh pair (`sid` claim)."""
    tracked = UserSession.objects.create(
        user=user, kind=UserSession.Kind.MOBILE, **_metadata(request)
    )
    refresh = RefreshToken.for_user(user)
    refresh[SESSION_CLAIM] = tracked.pk
    return tracked, {"access": str(refresh.access_token), "refresh": str(refresh)}


def is_staff_account_active(user: Any) -> bool:
    """SimpleJWT USER_AUTHENTICATION_RULE: only active staff accounts hold tokens."""
    return bool(user is not None and user.is_active and user.is_staff)


class RefreshRejected(Exception):
    """The refresh token cannot be used; the caller answers 401 without details."""


def _verified_refresh_payload(raw: str) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = token_backend.decode(cast(Any, raw), verify=True)
    except TokenBackendError as error:
        raise RefreshRejected from error
    if payload.get(jwt_settings.TOKEN_TYPE_CLAIM) != "refresh":
        raise RefreshRejected
    return payload


def rotate_mobile_refresh(request: Any, raw: str) -> dict[str, str]:
    """Rotate a refresh token of an active mobile session.

    A signature-valid refresh token that was already rotated or revoked is treated as
    stolen: the whole session (token family) is revoked and the event audited.
    The session row is locked so two concurrent uses of one token cannot both rotate.
    """
    payload = _verified_refresh_payload(raw)
    session_id = payload.get(SESSION_CLAIM)
    with transaction.atomic():
        locked = (
            UserSession.objects.select_for_update().filter(pk=session_id).first()
            if isinstance(session_id, int)
            else None
        )
        jti = payload.get(jwt_settings.JTI_CLAIM)
        if not BlacklistedToken.objects.filter(token__jti=jti).exists():
            return _rotate(payload, raw)
    if locked is not None and locked.is_active:
        revoke_session(locked, reason="refresh_reuse")
        record_event(
            "auth.token.reuse_detected",
            request=request,
            actor=locked.user,
            target=locked,
            outcome=AuditEvent.Outcome.FAILURE,
        )
    raise RefreshRejected


def _rotate(payload: dict[str, Any], raw: str) -> dict[str, str]:
    tracked = active_mobile_session(
        payload.get(SESSION_CLAIM), payload.get(jwt_settings.USER_ID_CLAIM)
    )
    if tracked is None or not (tracked.user.is_active and tracked.user.is_staff):
        raise RefreshRejected
    expected_hash = get_md5_hash_password(tracked.user.password)
    if payload.get(jwt_settings.REVOKE_TOKEN_CLAIM) != expected_hash:
        raise RefreshRejected
    try:
        refresh = RefreshToken(cast(Any, raw))
    except TokenError as error:
        raise RefreshRejected from error
    refresh.blacklist()
    refresh.set_jti()
    refresh.set_exp()
    refresh.set_iat()
    refresh.outstand()
    touch(tracked)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def end_mobile_session(request: Any, raw: str) -> None:
    """Logout: blacklist the presented refresh token and revoke its session."""
    payload = _verified_refresh_payload(raw)
    tracked = active_mobile_session(
        payload.get(SESSION_CLAIM), payload.get(jwt_settings.USER_ID_CLAIM)
    )
    try:
        RefreshToken(cast(Any, raw)).blacklist()
    except TokenError as error:
        raise RefreshRejected from error
    if tracked is not None:
        revoke_session(tracked, reason="logout")
        record_event(
            "auth.logout",
            request=request,
            actor=tracked.user,
            target=tracked,
            metadata={"channel": "mobile"},
        )


def active_mobile_session(session_id: Any, user_id: Any) -> UserSession | None:
    if not isinstance(session_id, int):
        return None
    return (
        UserSession.objects.select_related("user")
        .filter(
            pk=session_id,
            user_id=user_id,
            kind=UserSession.Kind.MOBILE,
            revoked_at__isnull=True,
            created_at__gt=timezone.now() - settings.MOBILE_SESSION_MAX_AGE,
        )
        .first()
    )


def touch(tracked: UserSession) -> None:
    now = timezone.now()
    if now - tracked.last_seen_at >= LAST_SEEN_RESOLUTION:
        UserSession.objects.filter(pk=tracked.pk).update(last_seen_at=now)
        tracked.last_seen_at = now


def revoke_session(tracked: UserSession, reason: str) -> None:
    """Revoke one tracked session and destroy the server-side web session behind it."""
    from django.contrib.sessions.models import Session

    UserSession.objects.filter(pk=tracked.pk, revoked_at__isnull=True).update(
        revoked_at=timezone.now(), revoked_reason=reason
    )
    tracked.refresh_from_db(fields=["revoked_at", "revoked_reason"])
    if tracked.kind == UserSession.Kind.WEB and tracked.session_key:
        Session.objects.filter(session_key=tracked.session_key).delete()


def blacklist_refresh_tokens(user: User) -> None:
    """Blacklist every outstanding refresh token of the user (defence in depth on top of
    session revocation, which already makes `sid`-bound tokens unusable)."""
    outstanding = OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True)
    BlacklistedToken.objects.bulk_create(
        [BlacklistedToken(token=token) for token in outstanding], ignore_conflicts=True
    )
