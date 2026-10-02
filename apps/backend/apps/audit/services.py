"""Public API of the audit module: `record_event()`."""

from collections.abc import Mapping
from typing import Any

from django.db import models

from .models import AuditEvent

REDACTED = "[redacted]"
# Metadata keys whose values must never be persisted (case-insensitive substring match).
SENSITIVE_KEY_PARTS = (
    "password",
    "secret",
    "token",
    "otp",
    "code",
    "cookie",
    "authorization",
    "credential",
    "challenge",
    "session_key",
)
USER_AGENT_MAX_LENGTH = 512


def sanitize_metadata(value: Any) -> Any:
    """Recursively replace values stored under sensitive-looking keys."""
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if _is_sensitive(str(key)) else sanitize_metadata(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [sanitize_metadata(item) for item in value]
    return value


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def client_ip(request: Any) -> str | None:
    """Peer address. Forwarded headers are not trusted: behind a TLS proxy, configure the
    WSGI server to rewrite REMOTE_ADDR from the trusted proxy only."""
    meta = getattr(request, "META", {})
    return meta.get("REMOTE_ADDR") or None


def record_event(
    action: str,
    *,
    request: Any | None = None,
    actor: Any | None = None,
    target: models.Model | None = None,
    outcome: str = AuditEvent.Outcome.SUCCESS,
    metadata: Mapping[str, Any] | None = None,
) -> AuditEvent:
    """Persist one audit event. Never pass secrets; sensitive keys are redacted regardless."""
    meta = getattr(request, "META", {}) if request is not None else {}
    if actor is not None and not getattr(actor, "is_authenticated", False):
        actor = None
    return AuditEvent.objects.create(
        action=action,
        outcome=outcome,
        actor=actor,
        target_type=target._meta.label_lower if target is not None else "",
        target_id=str(target.pk) if target is not None else "",
        ip_address=client_ip(request) if request is not None else None,
        user_agent=str(meta.get("HTTP_USER_AGENT", ""))[:USER_AGENT_MAX_LENGTH],
        request_id=str(getattr(request, "request_id", "") or "")[:128],
        metadata=sanitize_metadata(dict(metadata or {})),
    )
