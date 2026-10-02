from typing import cast

from django.contrib.auth import authenticate, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenBlacklistView, TokenObtainPairView, TokenRefreshView

from apps.audit.models import AuditEvent
from apps.audit.services import record_event

from .auth_sessions import start_web_session
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


class CurrentUserView(APIView):
    @extend_schema(operation_id="getUsersMe", responses=UserSerializer)
    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        return Response(UserSerializer(user).data)


@extend_schema_view(
    post=extend_schema(
        operation_id="postAuthToken",
        request=MobileCredentialsSerializer,
        responses=MobileTokenResponseSerializer,
    )
)
class MobileTokenObtainView(TokenObtainPairView):
    # SimpleJWT annotates this base attribute as tuple[()], too narrowly for explicit AllowAny.
    permission_classes = (AllowAny,)  # type: ignore[assignment]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_token_obtain"


@extend_schema_view(
    post=extend_schema(
        operation_id="postAuthTokenRefresh",
        request=MobileRefreshSerializer,
        responses=MobileTokenResponseSerializer,
    )
)
class MobileTokenRefreshView(TokenRefreshView):
    # SimpleJWT annotates this base attribute as tuple[()], too narrowly for explicit AllowAny.
    permission_classes = (AllowAny,)  # type: ignore[assignment]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_token_refresh"


@extend_schema_view(
    post=extend_schema(
        operation_id="postAuthTokenLogout",
        request=MobileLogoutSerializer,
        responses={200: None},
    )
)
class MobileTokenLogoutView(TokenBlacklistView):
    # SimpleJWT annotates this base attribute as tuple[()], too narrowly for explicit AllowAny.
    permission_classes = (AllowAny,)  # type: ignore[assignment]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_token_logout"


class CsrfView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(operation_id="getAuthCsrf", responses=CsrfTokenSerializer)
    def get(self, request: Request) -> Response:
        return Response({"csrfToken": get_token(request._request)})


@method_decorator(csrf_protect, name="dispatch")
class SessionLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_session_login"

    def get_authenticate_header(self, request: Request) -> str:
        # Report failed sign-in as 401 (not DRF's 403 fallback for header-less auth).
        return 'Session realm="api"'

    @extend_schema(
        operation_id="postAuthSessionLogin",
        request=SessionLoginSerializer,
        responses=UserSerializer,
    )
    def post(self, request: Request) -> Response:
        serializer = SessionLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        credentials = serializer.validated_data
        user = authenticate(
            request=request._request,
            username=credentials["email"],
            password=credentials["password"],
        )
        if user is None or not user.is_staff:
            record_event(
                "auth.login.failure",
                request=request,
                outcome=AuditEvent.Outcome.FAILURE,
                metadata={"channel": "web"},
            )
            raise AuthenticationFailed(INVALID_CREDENTIALS)
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
