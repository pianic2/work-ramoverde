from django.urls import path

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
    path("auth/token", MobileTokenObtainView.as_view(), name="token-obtain"),
    path("auth/token/refresh", MobileTokenRefreshView.as_view(), name="token-refresh"),
    path("auth/token/logout", MobileTokenLogoutView.as_view(), name="token-logout"),
    path("auth/csrf", CsrfView.as_view(), name="csrf-token"),
    path("auth/session/login", SessionLoginView.as_view(), name="session-login"),
    path("auth/session/logout", SessionLogoutView.as_view(), name="session-logout"),
    path("users/me", CurrentUserView.as_view(), name="current-user"),
]
