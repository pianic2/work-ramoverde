import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from rest_framework.test import APIRequestFactory

from apps.accounts.permissions import IsStaffUser, StaffModelPermissions

User = get_user_model()


class _View:
    def get_queryset(self):
        return User.objects.all()


def _request(method: str, user):
    request = getattr(APIRequestFactory(), method)("/")
    request.user = user
    return request


@pytest.mark.django_db
def test_staff_permission_rejects_anonymous_and_non_staff():
    member = User.objects.create_user(email="member@example.com", password="x" * 16)
    assert not IsStaffUser().has_permission(_request("get", AnonymousUser()), _View())
    assert not IsStaffUser().has_permission(_request("get", member), _View())


@pytest.mark.django_db
def test_model_permissions_require_staff_and_view_permission_for_reads():
    staff = User.objects.create_user(email="staff@example.com", password="x" * 16, is_staff=True)
    permission = StaffModelPermissions()
    assert not permission.has_permission(_request("get", staff), _View())

    staff.user_permissions.add(Permission.objects.get(codename="view_user"))
    staff = User.objects.get(pk=staff.pk)
    assert permission.has_permission(_request("get", staff), _View())
    assert not permission.has_permission(_request("post", staff), _View())

    staff.is_staff = False
    assert not permission.has_permission(_request("get", staff), _View())
