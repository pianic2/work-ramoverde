"""Password change and reset (WR-16). Neither path signs anyone in or skips MFA."""

import hashlib
from typing import Any

from django.conf import settings
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.audit.models import AuditEvent
from apps.audit.services import record_event

from .auth_sessions import blacklist_refresh_tokens, reissue_mobile_tokens, revoke_all_sessions
from .models import User, UserSession

RESET_EMAIL_INTERVAL_SECONDS = 5 * 60


class PasswordChangeRejected(Exception):
    def __init__(self, field: str, messages: list[str]) -> None:
        super().__init__(field)
        self.field = field
        self.messages = messages


def change_password(
    request: Any, user: User, tracked: UserSession, current: str, new: str
) -> dict[str, str] | None:
    """Change the password of a signed-in (MFA + step-up verified) user.

    Keeps the current session alive, revokes every other session and refresh token.
    Returns a fresh token pair when the current session is a mobile one.
    """
    if not user.check_password(current):
        record_event(
            "password.change",
            request=request,
            actor=user,
            target=user,
            outcome=AuditEvent.Outcome.FAILURE,
            metadata={"reason": "wrong_current_password"},
        )
        raise PasswordChangeRejected("current_password", ["La password attuale non è corretta."])
    _validate(new, user, "new_password")
    user.set_password(new)
    user.save()
    revoked = revoke_all_sessions(user, reason="password_change", keep=tracked)
    record_event(
        "password.change",
        request=request,
        actor=user,
        target=user,
        metadata={"revoked_sessions": revoked},
    )
    if tracked.kind == UserSession.Kind.WEB:
        update_session_auth_hash(request._request, user)  # rotates the session key
        UserSession.objects.filter(pk=tracked.pk).update(
            session_key=request._request.session.session_key or ""
        )
        return None
    return reissue_mobile_tokens(tracked)


def request_reset(request: Any, email: str) -> None:
    """Email a single-use reset link if an active staff account exists. Always silent."""
    user = User.objects.filter(email__iexact=email.strip(), is_active=True, is_staff=True).first()
    if user is None:
        record_event(
            "password.reset.request",
            request=request,
            outcome=AuditEvent.Outcome.FAILURE,
            metadata={"reason": "unknown_account"},
        )
        return
    # At most one email per account every few minutes (mailbox flooding protection).
    digest = hashlib.sha256(user.email.lower().encode()).hexdigest()
    if not cache.add(f"password-reset-mail:{digest}", True, RESET_EMAIL_INTERVAL_SECONDS):
        return
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = f"{settings.STAFF_PASSWORD_RESET_URL}?uid={uid}&token={token}"
    minutes = settings.PASSWORD_RESET_TIMEOUT // 60
    send_mail(
        subject="RamoVerde — reimposta la password",
        message=(
            "È stata richiesta la reimpostazione della password del tuo account staff "
            "RamoVerde.\n\n"
            f"Apri questo collegamento entro {minutes} minuti (vale una sola volta):\n{link}\n\n"
            "Dopo la reimpostazione dovrai accedere di nuovo con la verifica in due passaggi. "
            "Se non sei stato tu, ignora questo messaggio e avvisa l'amministratore."
        ),
        from_email=None,
        recipient_list=[user.email],
    )
    record_event("password.reset.request", request=request, actor=user, target=user)


def confirm_reset(request: Any, uid: str, token: str, new: str) -> None:
    """Set a new password from a valid reset link. Never signs in; revokes every session."""
    user = _user_from_uid(uid)
    if user is None or not default_token_generator.check_token(user, token):
        record_event(
            "password.reset.complete",
            request=request,
            outcome=AuditEvent.Outcome.FAILURE,
            metadata={"reason": "invalid_or_expired_link"},
        )
        raise PasswordChangeRejected("token", ["Collegamento non valido o scaduto."])
    _validate(new, user, "new_password")
    user.set_password(new)  # changes the hash: the token can never be used again
    user.save()
    revoke_all_sessions(user, reason="password_reset")
    blacklist_refresh_tokens(user)
    record_event("password.reset.complete", request=request, actor=user, target=user)


def _user_from_uid(uid: str) -> User | None:
    try:
        pk = int(force_str(urlsafe_base64_decode(uid)))
    except (TypeError, ValueError, OverflowError):
        return None
    return User.objects.filter(pk=pk, is_active=True, is_staff=True).first()


def _validate(password: str, user: User, field: str) -> None:
    from django.core.exceptions import ValidationError

    try:
        validate_password(password, user)
    except ValidationError as error:
        raise PasswordChangeRejected(field, list(error.messages)) from error
