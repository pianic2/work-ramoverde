from typing import Any

from django.contrib.auth.signals import user_logged_out
from django.db.models.signals import post_migrate
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


@receiver(post_migrate, dispatch_uid="accounts.sync_roles")
def sync_roles_after_migrate(sender: Any, **kwargs: Any) -> None:
    """Keep role groups aligned with the RBAC matrix after every migrate (idempotent).

    Runs for every app so permissions declared by apps migrated after `accounts` are
    granted too."""
    from .rbac import sync_roles

    sync_roles()
