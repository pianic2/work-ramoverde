"""Tracked sign-in sessions (web and mobile) and their revocation."""

from datetime import timedelta
from typing import Any

from django.contrib.auth import login
from django.contrib.sessions.backends.base import SessionBase
from django.http import HttpRequest
from django.utils import timezone

from apps.audit.services import USER_AGENT_MAX_LENGTH, client_ip

from .models import User, UserSession

SESSION_ID_KEY = "_staff_session_id"
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
