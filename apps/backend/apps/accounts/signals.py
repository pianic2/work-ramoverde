from typing import Any

from django.contrib.auth.signals import user_logged_out
from django.dispatch import receiver
from django.http import HttpRequest

from apps.audit.services import record_event

from .auth_sessions import active_web_session, revoke_session


@receiver(user_logged_out, dispatch_uid="accounts.revoke_tracked_web_session")
def revoke_tracked_web_session(
    sender: Any, request: HttpRequest | None, user: Any, **kwargs: Any
) -> None:
    """Every Django logout (API or django-admin) revokes the tracked session and is audited."""
    if request is None:
        return
    tracked = active_web_session(request)
    if tracked is None:
        return
    revoke_session(tracked, reason="logout")
    record_event(
        "auth.logout", request=request, actor=user, target=tracked, metadata={"channel": "web"}
    )
