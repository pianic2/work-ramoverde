from typing import Any

from rest_framework import serializers

from .models import User, UserSession, WebAuthnCredential

MFA_METHODS = [("totp", "TOTP"), ("recovery", "Recovery code"), ("webauthn", "WebAuthn")]
MOBILE_MFA_METHODS = [("totp", "TOTP"), ("recovery", "Recovery code")]
AUTH_FLOW_STATUSES = [
    ("mfa_required", "Second factor required"),
    ("mfa_enrollment_required", "Second factor enrollment required"),
    ("authenticated", "Authenticated"),
]


class UserSerializer(serializers.ModelSerializer[User]):
    password_change_required = serializers.BooleanField(source="password_expired", read_only=True)
    password_expires_at = serializers.DateTimeField(read_only=True, allow_null=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "password_change_required",
            "password_expires_at",
        ]
        read_only_fields = fields


class CurrentUserSerializer(UserSerializer):
    """`/users/me`: role and effective permissions are UI hints only; the API enforces."""

    role = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = [*UserSerializer.Meta.fields, "role", "permissions"]
        read_only_fields = fields

    def get_role(self, obj: User) -> str | None:
        from .rbac import get_role

        role = get_role(obj)
        return role.value if role else None

    def get_permissions(self, obj: User) -> list[str]:
        return sorted(obj.get_all_permissions())


class SessionLoginSerializer(serializers.Serializer[dict[str, Any]]):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, write_only=True, max_length=4096)


class CsrfTokenSerializer(serializers.Serializer[dict[str, Any]]):
    csrfToken = serializers.CharField()


class MobileCredentialsSerializer(serializers.Serializer[dict[str, Any]]):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, write_only=True, max_length=4096)


class MobileTokenResponseSerializer(serializers.Serializer[dict[str, Any]]):
    access = serializers.CharField()
    refresh = serializers.CharField()
    recovery_codes = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Only after first MFA enrollment: show once, never stored by the app.",
    )


class MobileRefreshSerializer(serializers.Serializer[dict[str, Any]]):
    refresh = serializers.CharField()


class MobileLogoutSerializer(serializers.Serializer[dict[str, Any]]):
    refresh = serializers.CharField(write_only=True)


# --- MFA ---------------------------------------------------------------------------------


class SessionAuthFlowSerializer(serializers.Serializer[dict[str, Any]]):
    status = serializers.ChoiceField(choices=AUTH_FLOW_STATUSES)
    methods = serializers.ListField(child=serializers.ChoiceField(choices=MFA_METHODS))
    user = UserSerializer(required=False)
    recovery_codes = serializers.ListField(child=serializers.CharField(), required=False)


class MobileAuthFlowSerializer(serializers.Serializer[dict[str, Any]]):
    status = serializers.ChoiceField(choices=AUTH_FLOW_STATUSES)
    methods = serializers.ListField(child=serializers.ChoiceField(choices=MFA_METHODS))
    challenge = serializers.CharField(help_text="Short-lived, single-use MFA challenge.")


class MfaVerifySerializer(serializers.Serializer[dict[str, Any]]):
    method = serializers.ChoiceField(choices=MFA_METHODS)
    code = serializers.CharField(required=False, allow_blank=True, max_length=32, write_only=True)
    credential = serializers.JSONField(required=False, write_only=True)


class MobileMfaVerifySerializer(serializers.Serializer[dict[str, Any]]):
    challenge = serializers.CharField(max_length=2048, write_only=True)
    method = serializers.ChoiceField(choices=MOBILE_MFA_METHODS)
    code = serializers.CharField(max_length=32, write_only=True)


class MobileChallengeSerializer(serializers.Serializer[dict[str, Any]]):
    challenge = serializers.CharField(max_length=2048, write_only=True)


class MobileTotpConfirmSerializer(serializers.Serializer[dict[str, Any]]):
    challenge = serializers.CharField(max_length=2048, write_only=True)
    code = serializers.CharField(max_length=32, write_only=True)


class TotpConfirmSerializer(serializers.Serializer[dict[str, Any]]):
    code = serializers.CharField(max_length=32, write_only=True)


class TotpSetupSerializer(serializers.Serializer[dict[str, Any]]):
    secret = serializers.CharField()
    otpauth_uri = serializers.CharField()


class WebAuthnOptionsSerializer(serializers.Serializer[dict[str, Any]]):
    options = serializers.JSONField(help_text="PublicKeyCredential options for the browser.")


class WebAuthnRegisterSerializer(serializers.Serializer[dict[str, Any]]):
    credential = serializers.JSONField(write_only=True)
    name = serializers.CharField(max_length=64, required=False, default="Passkey")


class WebAuthnCredentialSerializer(serializers.ModelSerializer[WebAuthnCredential]):
    class Meta:
        model = WebAuthnCredential
        fields = ["id", "name", "created_at", "last_used_at"]
        read_only_fields = fields


class MfaStatusSerializer(serializers.Serializer[dict[str, Any]]):
    methods = serializers.ListField(child=serializers.ChoiceField(choices=MFA_METHODS))
    totp_enabled = serializers.BooleanField()
    webauthn_credentials = WebAuthnCredentialSerializer(many=True)
    recovery_codes_remaining = serializers.IntegerField()


class RecoveryCodesSerializer(serializers.Serializer[dict[str, Any]]):
    recovery_codes = serializers.ListField(child=serializers.CharField())


class StepUpResponseSerializer(serializers.Serializer[dict[str, Any]]):
    mfa_verified_at = serializers.DateTimeField()


# --- Passwords and sessions (WR-16) -------------------------------------------------------


class PasswordChangeSerializer(serializers.Serializer[dict[str, Any]]):
    current_password = serializers.CharField(
        trim_whitespace=False, write_only=True, max_length=4096
    )
    new_password = serializers.CharField(trim_whitespace=False, write_only=True, max_length=4096)


class PasswordChangeResponseSerializer(serializers.Serializer[dict[str, Any]]):
    """Returned only to mobile sessions: their token pair is re-issued."""

    access = serializers.CharField()
    refresh = serializers.CharField()


class PasswordResetRequestSerializer(serializers.Serializer[dict[str, Any]]):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer[dict[str, Any]]):
    uid = serializers.CharField(max_length=64, write_only=True)
    token = serializers.CharField(max_length=128, write_only=True)
    new_password = serializers.CharField(trim_whitespace=False, write_only=True, max_length=4096)


class DetailSerializer(serializers.Serializer[dict[str, Any]]):
    detail = serializers.CharField()


class UserSessionSerializer(serializers.ModelSerializer[UserSession]):
    current = serializers.SerializerMethodField()

    class Meta:
        model = UserSession
        fields = [
            "id",
            "kind",
            "created_at",
            "last_seen_at",
            "ip_address",
            "user_agent",
            "mfa_method",
            "current",
        ]
        read_only_fields = fields

    def get_current(self, obj: UserSession) -> bool:
        current = self.context.get("current")
        return bool(current is not None and current.pk == obj.pk)
