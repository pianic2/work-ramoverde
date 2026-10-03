from django.urls import path

from . import mfa_views, security_views, staff_views
from .views import (
    CsrfView,
    CurrentUserView,
    MobileTokenLogoutView,
    MobileTokenObtainView,
    MobileTokenRefreshView,
    SessionLoginView,
    SessionLogoutView,
)

urlpatterns = [
    # Mobile: password step -> MFA challenge -> JWT pair.
    path("auth/token", MobileTokenObtainView.as_view(), name="token-obtain"),
    path("auth/token/mfa/verify", mfa_views.MobileMfaVerifyView.as_view(), name="token-mfa-verify"),
    path(
        "auth/token/mfa/totp/setup",
        mfa_views.MobileTotpSetupView.as_view(),
        name="token-mfa-totp-setup",
    ),
    path(
        "auth/token/mfa/totp/confirm",
        mfa_views.MobileTotpConfirmView.as_view(),
        name="token-mfa-totp-confirm",
    ),
    path("auth/token/refresh", MobileTokenRefreshView.as_view(), name="token-refresh"),
    path("auth/token/logout", MobileTokenLogoutView.as_view(), name="token-logout"),
    # Web: CSRF + password step -> MFA (pending session) -> Django session.
    path("auth/csrf", CsrfView.as_view(), name="csrf-token"),
    path("auth/session/login", SessionLoginView.as_view(), name="session-login"),
    path(
        "auth/session/mfa/verify",
        mfa_views.SessionMfaVerifyView.as_view(),
        name="session-mfa-verify",
    ),
    path(
        "auth/session/mfa/webauthn/options",
        mfa_views.SessionWebAuthnOptionsView.as_view(),
        name="session-mfa-webauthn-options",
    ),
    path(
        "auth/session/mfa/totp/setup",
        mfa_views.SessionTotpSetupView.as_view(),
        name="session-mfa-totp-setup",
    ),
    path(
        "auth/session/mfa/totp/confirm",
        mfa_views.SessionTotpConfirmView.as_view(),
        name="session-mfa-totp-confirm",
    ),
    path(
        "auth/session/mfa/webauthn/register/options",
        mfa_views.SessionWebAuthnRegisterOptionsView.as_view(),
        name="session-mfa-webauthn-register-options",
    ),
    path(
        "auth/session/mfa/webauthn/register/verify",
        mfa_views.SessionWebAuthnRegisterVerifyView.as_view(),
        name="session-mfa-webauthn-register-verify",
    ),
    path("auth/session/logout", SessionLogoutView.as_view(), name="session-logout"),
    # Authenticated: MFA status, step-up and factor management.
    path("auth/mfa", mfa_views.MfaStatusView.as_view(), name="mfa-status"),
    path("auth/step-up", mfa_views.StepUpView.as_view(), name="step-up"),
    path(
        "auth/step-up/webauthn/options",
        mfa_views.StepUpWebAuthnOptionsView.as_view(),
        name="step-up-webauthn-options",
    ),
    path("auth/mfa/totp", mfa_views.TotpRemoveView.as_view(), name="mfa-totp-remove"),
    path("auth/mfa/totp/setup", mfa_views.TotpSetupView.as_view(), name="mfa-totp-setup"),
    path("auth/mfa/totp/confirm", mfa_views.TotpConfirmView.as_view(), name="mfa-totp-confirm"),
    path(
        "auth/mfa/webauthn/register/options",
        mfa_views.WebAuthnRegisterOptionsView.as_view(),
        name="mfa-webauthn-register-options",
    ),
    path(
        "auth/mfa/webauthn/register/verify",
        mfa_views.WebAuthnRegisterVerifyView.as_view(),
        name="mfa-webauthn-register-verify",
    ),
    path(
        "auth/mfa/webauthn/<int:pk>",
        mfa_views.WebAuthnRemoveView.as_view(),
        name="mfa-webauthn-remove",
    ),
    path(
        "auth/mfa/recovery-codes",
        mfa_views.RecoveryCodesView.as_view(),
        name="mfa-recovery-codes",
    ),
    # Passwords (WR-16).
    path(
        "auth/password/change",
        security_views.PasswordChangeView.as_view(),
        name="password-change",
    ),
    path(
        "auth/password/reset",
        security_views.PasswordResetRequestView.as_view(),
        name="password-reset",
    ),
    path(
        "auth/password/reset/confirm",
        security_views.PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    # Sessions / devices (WR-16).
    path("auth/sessions", security_views.SessionListView.as_view(), name="sessions"),
    path(
        "auth/sessions/revoke-others",
        security_views.SessionRevokeOthersView.as_view(),
        name="sessions-revoke-others",
    ),
    path(
        "auth/sessions/revoke-all",
        security_views.SessionRevokeAllView.as_view(),
        name="sessions-revoke-all",
    ),
    path(
        "auth/sessions/<int:pk>",
        security_views.SessionRevokeView.as_view(),
        name="session-revoke",
    ),
    path("users/me", CurrentUserView.as_view(), name="current-user"),
    # Staff accounts and RBAC (WR-17).
    path("roles", staff_views.RoleListView.as_view(), name="roles"),
    path("users", staff_views.StaffUserListView.as_view(), name="users"),
    path("users/<int:pk>/role", staff_views.StaffRoleView.as_view(), name="user-role"),
    path(
        "users/<int:pk>/deactivate",
        staff_views.StaffDeactivateView.as_view(),
        name="user-deactivate",
    ),
    path(
        "users/<int:pk>/security-reset",
        staff_views.StaffSecurityResetView.as_view(),
        name="user-security-reset",
    ),
]
