from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields: Any) -> "User":
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields: Any) -> "User":
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(
        self, email: str, password: str | None = None, **extra_fields: Any
    ) -> "User":
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True or extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_staff=True and is_superuser=True")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None  # type: ignore[assignment]
    email = models.EmailField(unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    # Set on every password change; null means unknown age and is treated as expired.
    password_changed_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()  # type: ignore[assignment,misc]

    def set_password(self, raw_password: str | None) -> None:
        super().set_password(raw_password)
        self.password_changed_at = timezone.now()

    @property
    def password_expires_at(self) -> datetime | None:
        if self.password_changed_at is None:
            return None
        return self.password_changed_at + timedelta(days=settings.PASSWORD_MAX_AGE_DAYS)

    @property
    def password_expired(self) -> bool:
        """Mandatory change every PASSWORD_MAX_AGE_DAYS (default 30)."""
        expires_at = self.password_expires_at
        return expires_at is None or timezone.now() >= expires_at


class PasswordHistory(models.Model):
    """Previous password hashes (Django hasher format) used to prevent reuse."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_history")
    password_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"Password history {self.pk}"


class UserSession(models.Model):
    """A signed-in device: one Django web session or one mobile refresh-token family.

    Every staff request is authenticated against an active row, so revoking it here
    immediately invalidates the browser session or the mobile access/refresh tokens.
    """

    class Kind(models.TextChoices):
        WEB = "web", "Web"
        MOBILE = "mobile", "Mobile"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="auth_sessions")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    session_key = models.CharField(max_length=40, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=64, blank=True)
    # Second factor that created the session and the time of the latest MFA check
    # (sign-in or step-up). Staff permissions require it; sensitive actions require it recent.
    mfa_method = models.CharField(max_length=16, blank=True)
    mfa_verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_seen_at", "-id"]
        indexes = [models.Index(fields=["user", "revoked_at"])]

    def __str__(self) -> str:
        return f"{self.kind} session {self.pk}"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class TOTPDevice(models.Model):
    """RFC 6238 authenticator app. The shared secret is encrypted at rest (see `mfa.py`)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="totp_devices")
    encrypted_secret = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    # Highest accepted time step: a code is never accepted twice (replay protection).
    last_used_step = models.BigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(confirmed_at__isnull=False),
                name="accounts_one_confirmed_totp_per_user",
            )
        ]

    def __str__(self) -> str:
        return f"TOTP device {self.pk}"


class RecoveryCode(models.Model):
    """Single-use recovery code, stored only as a keyed HMAC-SHA256 digest."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="recovery_codes")
    code_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Recovery code {self.pk}"


class WebAuthnCredential(models.Model):
    """Passkey / security key registered through WebAuthn (preferred second factor)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="webauthn_credentials")
    credential_id = models.CharField(max_length=1024, unique=True)  # base64url
    public_key = models.BinaryField()
    sign_count = models.PositiveBigIntegerField(default=0)
    transports = models.JSONField(default=list, blank=True)
    name = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return self.name
