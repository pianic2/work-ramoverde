"""Progressive per-account lockout after repeated authentication failures.

State lives in the shared Django cache (DatabaseCache on PostgreSQL, so every worker
sees it). Keys are derived from a hash of the normalized email, so unknown and existing
accounts behave identically and responses never reveal whether an account exists.
After `AUTH_LOCKOUT_THRESHOLD` consecutive failures the account is locked for
`AUTH_LOCKOUT_BASE_SECONDS`, doubling with each further failure up to
`AUTH_LOCKOUT_MAX_SECONDS`. A successful sign-in resets the counter.
"""

import hashlib
import time
from typing import Any

from django.conf import settings
from django.core.cache import cache

STATE_TTL_SECONDS = 24 * 60 * 60


def _key(identity: str) -> str:
    digest = hashlib.sha256(identity.strip().lower().encode()).hexdigest()
    return f"auth-lockout:{digest}"


def _state(identity: str) -> dict[str, Any]:
    state = cache.get(_key(identity))
    return state if isinstance(state, dict) else {"failures": 0, "locked_until": 0.0}


def locked_for(identity: str) -> float:
    """Seconds the identity remains locked (0 when not locked)."""
    return max(0.0, float(_state(identity)["locked_until"]) - time.time())


def is_locked(identity: str) -> bool:
    return locked_for(identity) > 0


def register_failure(identity: str) -> bool:
    """Count a failure; return True when this failure (re)locks the identity."""
    state = _state(identity)
    state["failures"] = int(state["failures"]) + 1
    threshold = settings.AUTH_LOCKOUT_THRESHOLD
    locked_now = bool(state["failures"] >= threshold)
    if locked_now:
        delay = settings.AUTH_LOCKOUT_BASE_SECONDS * 2 ** (state["failures"] - threshold)
        state["locked_until"] = time.time() + min(delay, settings.AUTH_LOCKOUT_MAX_SECONDS)
    cache.set(_key(identity), state, STATE_TTL_SECONDS)
    return locked_now


def reset(identity: str) -> None:
    cache.delete(_key(identity))
