"""Password policy validators (WR-16), plugged into AUTH_PASSWORD_VALIDATORS.

Baseline from Django: minimum length 12, user-attribute similarity, the offline list of
20k common/breached passwords (CommonPasswordValidator) and all-numeric rejection.
Added here: an upper bound that still allows long passphrases, and reuse prevention.
"""

from typing import Any

from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError


class MaximumLengthValidator:
    """Long passphrases are welcome; the bound only protects the hasher from abuse."""

    def __init__(self, max_length: int = 1024) -> None:
        self.max_length = max_length

    def validate(self, password: str, user: Any = None) -> None:
        if len(password) > self.max_length:
            raise ValidationError(
                "La password non può superare %(max)d caratteri.",
                code="password_too_long",
                params={"max": self.max_length},
            )

    def get_help_text(self) -> str:
        return f"La password può contenere fino a {self.max_length} caratteri."


class PasswordHistoryValidator:
    """Reject the current password and the last `history` passwords (compared by hash)."""

    def __init__(self, history: int = 5) -> None:
        self.history = history

    def _previous_hashes(self, user: Any) -> list[str]:
        from .models import PasswordHistory

        hashes = list(
            PasswordHistory.objects.filter(user=user)
            .order_by("-created_at", "-id")
            .values_list("password_hash", flat=True)[: self.history]
        )
        if user.password:
            hashes.append(user.password)
        return hashes

    def validate(self, password: str, user: Any = None) -> None:
        if user is None or user.pk is None:
            return
        if any(check_password(password, encoded) for encoded in self._previous_hashes(user)):
            raise ValidationError(
                "Non puoi riutilizzare una delle ultime %(count)d password.",
                code="password_reused",
                params={"count": self.history},
            )

    def password_changed(self, password: str, user: Any = None) -> None:
        """Called by Django after a password change is saved: remember the new hash."""
        from .models import PasswordHistory

        if user is None or user.pk is None or not user.has_usable_password():
            return
        PasswordHistory.objects.create(user=user, password_hash=user.password)
        stale = PasswordHistory.objects.filter(user=user).order_by("-created_at", "-id")[
            self.history :
        ]
        PasswordHistory.objects.filter(pk__in=[entry.pk for entry in stale]).delete()

    def get_help_text(self) -> str:
        return f"Non puoi riutilizzare le ultime {self.history} password."
