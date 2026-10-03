"""MFA endpoints: pending sign-in (web + mobile), step-up and factor management."""

from typing import Any, cast

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit.services import record_event

from . import login_flow, mfa
from .login_flow import ENROLL, VERIFY, FlowError, Pending
from .models import User, UserSession, WebAuthnCredential
from .permissions import IsStaffUser, RequiresRecentMFA, staff_session
from .serializers import (
    MfaStatusSerializer,
    MfaVerifySerializer,
    MobileChallengeSerializer,
    MobileMfaVerifySerializer,
    MobileTokenResponseSerializer,
    MobileTotpConfirmSerializer,
    RecoveryCodesSerializer,
    SessionAuthFlowSerializer,
    StepUpResponseSerializer,
    TotpConfirmSerializer,
    TotpSetupSerializer,
    UserSerializer,
    WebAuthnOptionsSerializer,
    WebAuthnRegisterSerializer,
)

MFA_FAILED = "Verifica non riuscita. Ricomincia l'accesso se il problema persiste."
LAST_FACTOR = "Non puoi rimuovere l'ultimo secondo fattore: aggiungine prima un altro."
WEBAUTHN_LOGIN = "login"
WEBAUTHN_REGISTER = "register"
WEBAUTHN_STEP_UP = "step-up"


class PendingAuthView(APIView):
    """Unauthenticated step of the sign-in flow; failures are generic 401s."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_mfa"

    def get_authenticate_header(self, request: Request) -> str:
        return 'Session realm="api"'


def _flow_failed(error: Exception | None = None) -> AuthenticationFailed:
    return AuthenticationFailed(MFA_FAILED, code="mfa_failed")


def _authenticated_flow(pending: Pending, recovery_codes: list[str] | None = None) -> Response:
    body: dict[str, Any] = {
        "status": "authenticated",
        "methods": mfa.enrolled_methods(pending.user),
        "user": UserSerializer(pending.user).data,
    }
    if recovery_codes is not None:
        body["recovery_codes"] = recovery_codes
    return Response(body)


def _first_enrollment(request: Request, user: User, method: str) -> list[str]:
    record_event(
        "mfa.enroll", request=request, actor=user, target=user, metadata={"method": method}
    )
    codes = mfa.generate_recovery_codes(user)
    record_event("mfa.recovery_regenerated", request=request, actor=user, target=user)
    return codes


# --- Web: pending sign-in ----------------------------------------------------------------


@method_decorator([csrf_protect, never_cache], name="dispatch")
class SessionMfaVerifyView(PendingAuthView):
    @extend_schema(
        operation_id="postAuthSessionMfaVerify",
        request=MfaVerifySerializer,
        responses=SessionAuthFlowSerializer,
    )
    def post(self, request: Request) -> Response:
        serializer = MfaVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            pending = login_flow.web_pending(request._request, VERIFY)
            challenge = None
            if data["method"] == mfa.WEBAUTHN:
                challenge = login_flow.pop_webauthn_challenge(
                    request._request, WEBAUTHN_LOGIN, pending.user
                )
            login_flow.check_second_factor(
                request,
                pending.user,
                data["method"],
                code=data.get("code", ""),
                credential=_credential(data),
                webauthn_challenge=challenge,
            )
        except FlowError as error:
            raise _flow_failed(error) from error
        login_flow.complete_web(request._request, pending, data["method"])
        return _authenticated_flow(pending)


@method_decorator([csrf_protect, never_cache], name="dispatch")
class SessionWebAuthnOptionsView(PendingAuthView):
    @extend_schema(
        operation_id="postAuthSessionMfaWebauthnOptions",
        request=None,
        responses=WebAuthnOptionsSerializer,
    )
    def post(self, request: Request) -> Response:
        try:
            pending = login_flow.web_pending(request._request, VERIFY)
        except FlowError as error:
            raise _flow_failed(error) from error
        options, challenge = mfa.webauthn_authentication_options(pending.user)
        login_flow.store_webauthn_challenge(
            request._request, WEBAUTHN_LOGIN, pending.user, challenge
        )
        return Response({"options": options})


@method_decorator([csrf_protect, never_cache], name="dispatch")
class SessionTotpSetupView(PendingAuthView):
    @extend_schema(
        operation_id="postAuthSessionMfaTotpSetup", request=None, responses=TotpSetupSerializer
    )
    def post(self, request: Request) -> Response:
        try:
            pending = login_flow.web_pending(request._request, ENROLL)
        except FlowError as error:
            raise _flow_failed(error) from error
        secret, uri = mfa.start_totp_enrollment(pending.user)
        return Response({"secret": secret, "otpauth_uri": uri})


@method_decorator([csrf_protect, never_cache], name="dispatch")
class SessionTotpConfirmView(PendingAuthView):
    @extend_schema(
        operation_id="postAuthSessionMfaTotpConfirm",
        request=TotpConfirmSerializer,
        responses=SessionAuthFlowSerializer,
    )
    def post(self, request: Request) -> Response:
        serializer = TotpConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            pending = login_flow.web_pending(request._request, ENROLL)
        except FlowError as error:
            raise _flow_failed(error) from error
        if not mfa.confirm_totp_enrollment(pending.user, serializer.validated_data["code"]):
            raise _flow_failed()
        codes = _first_enrollment(request, pending.user, mfa.TOTP)
        login_flow.complete_web(request._request, pending, mfa.TOTP)
        return _authenticated_flow(pending, codes)


@method_decorator([csrf_protect, never_cache], name="dispatch")
class SessionWebAuthnRegisterOptionsView(PendingAuthView):
    @extend_schema(
        operation_id="postAuthSessionMfaWebauthnRegisterOptions",
        request=None,
        responses=WebAuthnOptionsSerializer,
    )
    def post(self, request: Request) -> Response:
        try:
            pending = login_flow.web_pending(request._request, ENROLL)
        except FlowError as error:
            raise _flow_failed(error) from error
        options, challenge = mfa.webauthn_registration_options(pending.user)
        login_flow.store_webauthn_challenge(
            request._request, WEBAUTHN_REGISTER, pending.user, challenge
        )
        return Response({"options": options})


@method_decorator([csrf_protect, never_cache], name="dispatch")
class SessionWebAuthnRegisterVerifyView(PendingAuthView):
    @extend_schema(
        operation_id="postAuthSessionMfaWebauthnRegisterVerify",
        request=WebAuthnRegisterSerializer,
        responses=SessionAuthFlowSerializer,
    )
    def post(self, request: Request) -> Response:
        serializer = WebAuthnRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            pending = login_flow.web_pending(request._request, ENROLL)
            challenge = login_flow.pop_webauthn_challenge(
                request._request, WEBAUTHN_REGISTER, pending.user
            )
            if challenge is None:
                raise FlowError
            mfa.register_webauthn_credential(
                pending.user,
                _credential(serializer.validated_data) or {},
                challenge,
                serializer.validated_data["name"],
            )
        except (FlowError, mfa.MfaError) as error:
            raise _flow_failed(error) from error
        codes = _first_enrollment(request, pending.user, mfa.WEBAUTHN)
        login_flow.complete_web(request._request, pending, mfa.WEBAUTHN)
        return _authenticated_flow(pending, codes)


# --- Mobile: pending sign-in -------------------------------------------------------------


@method_decorator(never_cache, name="dispatch")
class MobileMfaVerifyView(PendingAuthView):
    @extend_schema(
        operation_id="postAuthTokenMfaVerify",
        request=MobileMfaVerifySerializer,
        responses=MobileTokenResponseSerializer,
    )
    def post(self, request: Request) -> Response:
        serializer = MobileMfaVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            pending = login_flow.mobile_pending(data["challenge"], VERIFY)
            login_flow.check_second_factor(request, pending.user, data["method"], code=data["code"])
            tokens = login_flow.complete_mobile(request, pending, data["method"])
        except FlowError as error:
            raise _flow_failed(error) from error
        return Response(tokens)


@method_decorator(never_cache, name="dispatch")
class MobileTotpSetupView(PendingAuthView):
    @extend_schema(
        operation_id="postAuthTokenMfaTotpSetup",
        request=MobileChallengeSerializer,
        responses=TotpSetupSerializer,
    )
    def post(self, request: Request) -> Response:
        serializer = MobileChallengeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            pending = login_flow.mobile_pending(serializer.validated_data["challenge"], ENROLL)
        except FlowError as error:
            raise _flow_failed(error) from error
        secret, uri = mfa.start_totp_enrollment(pending.user)
        return Response({"secret": secret, "otpauth_uri": uri})


@method_decorator(never_cache, name="dispatch")
class MobileTotpConfirmView(PendingAuthView):
    @extend_schema(
        operation_id="postAuthTokenMfaTotpConfirm",
        request=MobileTotpConfirmSerializer,
        responses=MobileTokenResponseSerializer,
    )
    def post(self, request: Request) -> Response:
        serializer = MobileTotpConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            pending = login_flow.mobile_pending(data["challenge"], ENROLL)
            if not mfa.confirm_totp_enrollment(pending.user, data["code"]):
                raise FlowError
            codes = _first_enrollment(request, pending.user, mfa.TOTP)
            tokens = login_flow.complete_mobile(request, pending, mfa.TOTP)
        except FlowError as error:
            raise _flow_failed(error) from error
        return Response({**tokens, "recovery_codes": codes})


# --- Authenticated: status, step-up, factor management ----------------------------------


def _session(request: Request) -> UserSession:
    tracked = staff_session(request)
    assert tracked is not None  # guaranteed by IsStaffUser
    return tracked


def _status_body(user: User) -> dict[str, Any]:
    return {
        "methods": mfa.enrolled_methods(user),
        "totp_enabled": mfa.TOTP in mfa.enrolled_methods(user),
        "webauthn_credentials": WebAuthnCredential.objects.filter(user=user),
        "recovery_codes_remaining": mfa.remaining_recovery_codes(user),
    }


class MfaStatusView(APIView):
    @extend_schema(operation_id="getAuthMfa", responses=MfaStatusSerializer)
    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        return Response(MfaStatusSerializer(_status_body(user)).data)


@method_decorator(never_cache, name="dispatch")
class StepUpView(APIView):
    permission_classes = [IsStaffUser]
    allow_expired_password = True
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_mfa"

    @extend_schema(
        operation_id="postAuthStepUp",
        request=MfaVerifySerializer,
        responses=StepUpResponseSerializer,
    )
    def post(self, request: Request) -> Response:
        serializer = MfaVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = cast(User, request.user)
        tracked = _session(request)
        challenge = None
        if data["method"] == mfa.WEBAUTHN:
            challenge = login_flow.pop_webauthn_challenge(request._request, WEBAUTHN_STEP_UP, user)
        try:
            login_flow.check_second_factor(
                request,
                user,
                data["method"],
                code=data.get("code", ""),
                credential=_credential(data),
                webauthn_challenge=challenge,
            )
        except FlowError as error:
            raise ValidationError({"code": [MFA_FAILED]}, code="mfa_failed") from error
        login_flow.mark_step_up(tracked, data["method"])
        record_event("mfa.step_up", request=request, actor=user, target=tracked)
        return Response({"mfa_verified_at": tracked.mfa_verified_at})


class StepUpWebAuthnOptionsView(APIView):
    allow_expired_password = True

    @extend_schema(
        operation_id="postAuthStepUpWebauthnOptions",
        request=None,
        responses=WebAuthnOptionsSerializer,
    )
    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        options, challenge = mfa.webauthn_authentication_options(user)
        login_flow.store_webauthn_challenge(request._request, WEBAUTHN_STEP_UP, user, challenge)
        return Response({"options": options})


class SensitiveMfaView(APIView):
    """Changing second factors requires a recent MFA verification (step-up)."""

    permission_classes = [IsStaffUser, RequiresRecentMFA]


class TotpSetupView(SensitiveMfaView):
    @extend_schema(operation_id="postAuthMfaTotpSetup", request=None, responses=TotpSetupSerializer)
    def post(self, request: Request) -> Response:
        secret, uri = mfa.start_totp_enrollment(cast(User, request.user))
        return Response({"secret": secret, "otpauth_uri": uri})


class TotpConfirmView(SensitiveMfaView):
    @extend_schema(
        operation_id="postAuthMfaTotpConfirm",
        request=TotpConfirmSerializer,
        responses=MfaStatusSerializer,
    )
    def post(self, request: Request) -> Response:
        serializer = TotpConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = cast(User, request.user)
        if not mfa.confirm_totp_enrollment(user, serializer.validated_data["code"]):
            raise ValidationError({"code": [MFA_FAILED]}, code="mfa_failed")
        record_event(
            "mfa.enroll", request=request, actor=user, target=user, metadata={"method": "totp"}
        )
        return Response(MfaStatusSerializer(_status_body(user)).data)


class TotpRemoveView(SensitiveMfaView):
    @extend_schema(operation_id="deleteAuthMfaTotp", request=None, responses={204: None})
    def delete(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not WebAuthnCredential.objects.filter(user=user).exists():
            raise ValidationError({"detail": [LAST_FACTOR]}, code="last_factor")
        mfa.remove_totp(user)
        record_event(
            "mfa.disable", request=request, actor=user, target=user, metadata={"method": "totp"}
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class WebAuthnRegisterOptionsView(SensitiveMfaView):
    @extend_schema(
        operation_id="postAuthMfaWebauthnRegisterOptions",
        request=None,
        responses=WebAuthnOptionsSerializer,
    )
    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        options, challenge = mfa.webauthn_registration_options(user)
        login_flow.store_webauthn_challenge(request._request, WEBAUTHN_REGISTER, user, challenge)
        return Response({"options": options})


class WebAuthnRegisterVerifyView(SensitiveMfaView):
    @extend_schema(
        operation_id="postAuthMfaWebauthnRegisterVerify",
        request=WebAuthnRegisterSerializer,
        responses=MfaStatusSerializer,
    )
    def post(self, request: Request) -> Response:
        serializer = WebAuthnRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = cast(User, request.user)
        challenge = login_flow.pop_webauthn_challenge(request._request, WEBAUTHN_REGISTER, user)
        try:
            if challenge is None:
                raise mfa.MfaError
            mfa.register_webauthn_credential(
                user,
                _credential(serializer.validated_data) or {},
                challenge,
                serializer.validated_data["name"],
            )
        except mfa.MfaError as error:
            raise ValidationError({"credential": [MFA_FAILED]}, code="mfa_failed") from error
        record_event(
            "mfa.enroll", request=request, actor=user, target=user, metadata={"method": "webauthn"}
        )
        return Response(MfaStatusSerializer(_status_body(user)).data)


class WebAuthnRemoveView(SensitiveMfaView):
    @extend_schema(operation_id="deleteAuthMfaWebauthn", request=None, responses={204: None})
    def delete(self, request: Request, pk: int) -> Response:
        user = cast(User, request.user)
        credential = WebAuthnCredential.objects.filter(user=user, pk=pk).first()
        if credential is None:
            raise ValidationError({"detail": ["Credenziale non trovata."]}, code="not_found")
        others = WebAuthnCredential.objects.filter(user=user).exclude(pk=pk).exists()
        if not others and mfa.TOTP not in mfa.enrolled_methods(user):
            raise ValidationError({"detail": [LAST_FACTOR]}, code="last_factor")
        credential.delete()
        record_event(
            "mfa.disable", request=request, actor=user, target=user, metadata={"method": "webauthn"}
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(never_cache, name="dispatch")
class RecoveryCodesView(SensitiveMfaView):
    @extend_schema(
        operation_id="postAuthMfaRecoveryCodes", request=None, responses=RecoveryCodesSerializer
    )
    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        codes = mfa.generate_recovery_codes(user)
        record_event("mfa.recovery_regenerated", request=request, actor=user, target=user)
        return Response({"recovery_codes": codes})


def _credential(data: dict[str, Any]) -> dict[str, Any] | None:
    credential = data.get("credential")
    return credential if isinstance(credential, dict) else None
