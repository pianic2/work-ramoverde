from typing import Any, cast

from django.contrib.auth import authenticate, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit.models import AuditEvent
from apps.audit.services import record_event

from .auth_sessions import (
    RefreshRejected,
    end_mobile_session,
    rotate_mobile_refresh,
    start_mobile_session,
    start_web_session,
)
from .authentication import StaffSessionAuthentication
from .models import User
from .serializers import (
    CsrfTokenSerializer,
    MobileCredentialsSerializer,
    MobileLogoutSerializer,
    MobileRefreshSerializer,
    MobileTokenResponseSerializer,
    SessionLoginSerializer,
    UserSerializer,
)

# One message for every failure so responses never reveal whether an account exists.
INVALID_CREDENTIALS = "Credenziali non valide."
INVALID_SESSION = "Sessione non valida o scaduta."


class PublicAuthView(APIView):
    """Unauthenticated auth endpoint that reports failures as 401 with a generic message."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]

    def get_authenticate_header(self, request: Request) -> str:
        # Report failures as 401 (not DRF's 403 fallback for header-less authentication).
        return 'Bearer realm="api"'


def verify_staff_credentials(request: Request, data: dict[str, Any], channel: str) -> User:
    user = authenticate(request=request._request, username=data["email"], password=data["password"])
    if user is None or not user.is_staff:
        record_event(
            "auth.login.failure",
            request=request,
            outcome=AuditEvent.Outcome.FAILURE,
            metadata={"channel": channel},
        )
        raise AuthenticationFailed(INVALID_CREDENTIALS)
    return user


class CurrentUserView(APIView):
    @extend_schema(operation_id="getUsersMe", responses=UserSerializer)
    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        return Response(UserSerializer(user).data)


class MobileTokenObtainView(PublicAuthView):
    throttle_scope = "auth_token_obtain"

    @extend_schema(
        operation_id="postAuthToken",
        request=MobileCredentialsSerializer,
        responses=MobileTokenResponseSerializer,
    )
    def post(self, request: Request) -> Response:
        serializer = MobileCredentialsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = verify_staff_credentials(request, serializer.validated_data, "mobile")
        tracked, tokens = start_mobile_session(request, user)
        record_event(
            "auth.login.success",
            request=request,
            actor=user,
            target=tracked,
            metadata={"channel": "mobile"},
        )
        return Response(tokens)


class MobileTokenRefreshView(PublicAuthView):
    throttle_scope = "auth_token_refresh"

    @extend_schema(
        operation_id="postAuthTokenRefresh",
        request=MobileRefreshSerializer,
        responses=MobileTokenResponseSerializer,
    )
    def post(self, request: Request) -> Response:
        serializer = MobileRefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            tokens = rotate_mobile_refresh(request, serializer.validated_data["refresh"])
        except RefreshRejected as error:
            raise AuthenticationFailed(INVALID_SESSION) from error
        return Response(tokens)


class MobileTokenLogoutView(PublicAuthView):
    throttle_scope = "auth_token_logout"

    @extend_schema(
        operation_id="postAuthTokenLogout", request=MobileLogoutSerializer, responses={204: None}
    )
    def post(self, request: Request) -> Response:
        serializer = MobileLogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            end_mobile_session(request, serializer.validated_data["refresh"])
        except RefreshRejected as error:
            raise AuthenticationFailed(INVALID_SESSION) from error
        return Response(status=status.HTTP_204_NO_CONTENT)


class CsrfView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(operation_id="getAuthCsrf", responses=CsrfTokenSerializer)
    def get(self, request: Request) -> Response:
        return Response({"csrfToken": get_token(request._request)})


@method_decorator(csrf_protect, name="dispatch")
class SessionLoginView(PublicAuthView):
    throttle_scope = "auth_session_login"

    def get_authenticate_header(self, request: Request) -> str:
        return 'Session realm="api"'

    @extend_schema(
        operation_id="postAuthSessionLogin",
        request=SessionLoginSerializer,
        responses=UserSerializer,
    )
    def post(self, request: Request) -> Response:
        serializer = SessionLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = verify_staff_credentials(request, serializer.validated_data, "web")
        tracked = start_web_session(request._request, user)
        record_event(
            "auth.login.success",
            request=request,
            actor=user,
            target=tracked,
            metadata={"channel": "web"},
        )
        return Response(UserSerializer(user).data)


@method_decorator(csrf_protect, name="dispatch")
class SessionLogoutView(APIView):
    authentication_classes = [StaffSessionAuthentication]

    @extend_schema(operation_id="postAuthSessionLogout", request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)
