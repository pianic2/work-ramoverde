from datetime import timedelta

import pytest
from auth_helpers import mfa_session_for
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.accounts.models import UserSession
from apps.accounts.permissions import IsStaffUser, RequiresRecentMFA, StaffModelPermissions

User = get_user_model()


class _View:
    def get_queryset(self):
        return User.objects.all()


def _request(method: str, user, session=None) -> Request:
    request = Request(getattr(APIRequestFactory(), method)("/"))
    request.user = user
    request.auth = session
    return request


@pytest.mark.django_db
def test_staff_permission_rejects_anonymous_non_staff_and_sessions_without_mfa():
    member = User.objects.create_user(email="member@example.com", password="x" * 16)
    staff = User.objects.create_user(email="staff@example.com", password="x" * 16, is_staff=True)
    unverified = UserSession.objects.create(user=staff, kind=UserSession.Kind.WEB)
    revoked = mfa_session_for(staff)
    revoked.revoked_at = timezone.now()

    assert not IsStaffUser().has_permission(_request("get", AnonymousUser()), _View())
    assert not IsStaffUser().has_permission(
        _request("get", member, mfa_session_for(member)), _View()
    )
    assert not IsStaffUser().has_permission(_request("get", staff), _View())
    assert not IsStaffUser().has_permission(_request("get", staff, unverified), _View())
    assert not IsStaffUser().has_permission(_request("get", staff, revoked), _View())
    other = User.objects.create_user(email="o@example.com", password="x" * 16, is_staff=True)
    assert not IsStaffUser().has_permission(_request("get", staff, mfa_session_for(other)), _View())
    assert IsStaffUser().has_permission(_request("get", staff, mfa_session_for(staff)), _View())


@pytest.mark.django_db
def test_model_permissions_require_mfa_staff_session_and_view_permission_for_reads():
    staff = User.objects.create_user(email="staff@example.com", password="x" * 16, is_staff=True)
    session = mfa_session_for(staff)
    permission = StaffModelPermissions()
    assert not permission.has_permission(_request("get", staff, session), _View())

    staff.user_permissions.add(Permission.objects.get(codename="view_user"))
    staff = User.objects.get(pk=staff.pk)
    session.user = staff
    assert permission.has_permission(_request("get", staff, session), _View())
    assert not permission.has_permission(_request("get", staff), _View())
    assert not permission.has_permission(_request("post", staff, session), _View())

    staff.is_staff = False
    assert not permission.has_permission(_request("get", staff, session), _View())


@pytest.mark.django_db
def test_recent_mfa_permission_enforces_step_up_window(settings):
    staff = User.objects.create_user(email="staff@example.com", password="x" * 16, is_staff=True)
    session = mfa_session_for(staff)
    assert RequiresRecentMFA().has_permission(_request("post", staff, session), _View())
    session.mfa_verified_at = timezone.now() - settings.STEP_UP_MAX_AGE - timedelta(seconds=1)
    assert not RequiresRecentMFA().has_permission(_request("post", staff, session), _View())
