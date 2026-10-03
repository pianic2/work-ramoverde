"""WR-17: RBAC roles mapped to Django permissions, enforced in the backend."""

from datetime import timedelta

import pytest
from auth_helpers import create_staff, mfa_session_for
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import rbac
from apps.accounts.models import User, UserSession
from apps.audit.models import AuditEvent

USERS = "/api/v1/users"


def staff_with_role(email: str, role: str) -> User:
    user = create_staff(email)
    rbac.set_role(user, role)
    return User.objects.get(pk=user.pk)


def api(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user, token=mfa_session_for(user))
    return client


# --- Matrix and synchronisation ----------------------------------------------------------


def test_matrix_defines_exactly_the_six_roles_and_no_admin_flag():
    assert [role.value for role in rbac.Role] == [
        "SUPERADMIN",
        "ADMIN",
        "MANAGER",
        "TECHNICIAN",
        "OPERATOR",
        "CONTENT_EDITOR",
    ]
    for permissions in rbac.ROLE_PERMISSIONS.values():
        assert all("." in perm for perm in permissions)
    assert not hasattr(User, "is_admin")


def test_documented_matrix_matches_code():
    from pathlib import Path

    doc = (Path(__file__).resolve().parents[3] / "docs/security/permission-matrix.md").read_text()
    for perms in rbac.ROLE_PERMISSIONS.values():
        for perm in perms:
            assert f"`{perm}`" in doc, perm


@pytest.mark.django_db
def test_roles_are_groups_holding_exactly_the_matrix_permissions():
    rbac.sync_roles()
    for role, expected in rbac.ROLE_PERMISSIONS.items():
        group = Group.objects.get(name=role.value)
        granted = {
            f"{app}.{codename}"
            for app, codename in group.permissions.values_list(
                "content_type__app_label", "codename"
            )
        }
        assert granted == set(expected), role


@pytest.mark.django_db
def test_sync_is_idempotent_and_picks_up_permissions_created_later():
    content_type = ContentType.objects.get(app_label="cms", model="page")
    Permission.objects.filter(content_type=content_type, codename="publish_page").delete()
    missing = rbac.sync_roles()
    assert "cms.publish_page" in missing
    editor = Group.objects.get(name="CONTENT_EDITOR")
    assert not editor.permissions.filter(codename="publish_page").exists()

    Permission.objects.create(
        content_type=content_type, codename="publish_page", name="Can publish pages"
    )
    call_command("sync_roles", verbosity=0)
    call_command("sync_roles", verbosity=0)
    assert editor.permissions.filter(codename="publish_page").count() == 1


@pytest.mark.django_db
def test_sync_removes_permissions_not_in_the_matrix():
    rbac.sync_roles()
    operator = Group.objects.get(name="OPERATOR")
    operator.permissions.add(Permission.objects.get(codename="delete_page"))
    rbac.sync_roles()
    assert not operator.permissions.filter(codename="delete_page").exists()


# --- Backend enforcement (positive / negative) -------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("role", "allowed"),
    [
        ("SUPERADMIN", True),
        ("ADMIN", True),
        ("CONTENT_EDITOR", True),
        ("MANAGER", False),
        ("TECHNICIAN", False),
        ("OPERATOR", False),
    ],
)
def test_cms_page_editing_follows_the_matrix(role, allowed):
    user = staff_with_role(f"{role.lower()}@example.com", role)
    response = api(user).post(
        "/api/v1/cms/pages", {"title": "Chi siamo", "slug": "chi-siamo"}, format="json"
    )
    assert (response.status_code == 201) is allowed, response.content


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("role", "allowed"),
    [("ADMIN", True), ("MANAGER", True), ("OPERATOR", False), ("CONTENT_EDITOR", False)],
)
def test_staff_directory_follows_the_matrix(role, allowed):
    user = staff_with_role(f"{role.lower()}@example.com", role)
    assert (api(user).get(USERS).status_code == 200) is allowed


@pytest.mark.django_db
def test_staff_without_a_role_has_no_permissions():
    user = create_staff("norole@example.com")
    assert api(user).get("/api/v1/cms/pages").status_code == 403
    assert api(user).get(USERS).status_code == 403


@pytest.mark.django_db
def test_current_user_exposes_role_and_permissions_for_ui_hints_only():
    user = staff_with_role("ed@example.com", "CONTENT_EDITOR")
    body = api(user).get("/api/v1/users/me").json()
    assert body["role"] == "CONTENT_EDITOR"
    assert "cms.publish_page" in body["permissions"]
    assert "accounts.assign_role" not in body["permissions"]


# --- Role assignment rules ---------------------------------------------------------------


@pytest.mark.django_db
def test_admin_assigns_lower_roles_with_step_up_and_audit():
    admin = staff_with_role("admin@example.com", "ADMIN")
    target = staff_with_role("op@example.com", "OPERATOR")
    response = api(admin).post(f"{USERS}/{target.pk}/role", {"role": "MANAGER"}, format="json")
    assert response.status_code == 200, response.content
    assert rbac.get_role(User.objects.get(pk=target.pk)) == rbac.Role.MANAGER
    event = AuditEvent.objects.get(action="role.change")
    assert event.actor == admin
    assert event.metadata == {"from": "OPERATOR", "to": "MANAGER"}


@pytest.mark.django_db
@pytest.mark.parametrize("new_role", ["ADMIN", "SUPERADMIN"])
def test_admin_cannot_grant_its_own_rank_or_higher(new_role):
    admin = staff_with_role("admin@example.com", "ADMIN")
    target = staff_with_role("op@example.com", "OPERATOR")
    response = api(admin).post(f"{USERS}/{target.pk}/role", {"role": new_role}, format="json")
    assert response.status_code == 403
    assert rbac.get_role(User.objects.get(pk=target.pk)) == rbac.Role.OPERATOR


@pytest.mark.django_db
def test_admin_cannot_change_peers_superiors_or_itself():
    admin = staff_with_role("admin@example.com", "ADMIN")
    peer = staff_with_role("peer@example.com", "ADMIN")
    boss = staff_with_role("boss@example.com", "SUPERADMIN")
    for target in (peer, boss, admin):
        response = api(admin).post(f"{USERS}/{target.pk}/role", {"role": "OPERATOR"}, format="json")
        assert response.status_code == 403, target.email


@pytest.mark.django_db
def test_only_superadmin_can_create_superadmins():
    boss = staff_with_role("boss@example.com", "SUPERADMIN")
    target = staff_with_role("admin@example.com", "ADMIN")
    response = api(boss).post(f"{USERS}/{target.pk}/role", {"role": "SUPERADMIN"}, format="json")
    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["MANAGER", "CONTENT_EDITOR", "TECHNICIAN", "OPERATOR"])
def test_non_privileged_roles_cannot_assign_roles(role):
    actor = staff_with_role("actor@example.com", role)
    target = staff_with_role("op@example.com", "OPERATOR")
    response = api(actor).post(f"{USERS}/{target.pk}/role", {"role": "TECHNICIAN"}, format="json")
    assert response.status_code == 403


@pytest.mark.django_db
def test_role_changes_require_recent_mfa():
    admin = staff_with_role("admin@example.com", "ADMIN")
    target = staff_with_role("op@example.com", "OPERATOR")
    session = mfa_session_for(admin)
    UserSession.objects.filter(pk=session.pk).update(
        mfa_verified_at=timezone.now() - timedelta(hours=1)
    )
    session.refresh_from_db()
    client = APIClient()
    client.force_authenticate(user=admin, token=session)
    response = client.post(f"{USERS}/{target.pk}/role", {"role": "MANAGER"}, format="json")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "step_up_required"


# --- Staff accounts ----------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_creates_staff_without_password_and_sends_a_setup_link():
    admin = staff_with_role("admin@example.com", "ADMIN")
    response = api(admin).post(
        USERS,
        {
            "email": "new@example.com",
            "first_name": "Nuovo",
            "last_name": "Tecnico",
            "role": "TECHNICIAN",
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    created = User.objects.get(email="new@example.com")
    assert created.is_staff and not created.is_superuser
    assert not created.has_usable_password()
    assert rbac.get_role(created) == rbac.Role.TECHNICIAN
    assert mail.outbox and "reset-password?uid=" in mail.outbox[-1].body
    assert AuditEvent.objects.filter(action="account.create", actor=admin).exists()


@pytest.mark.django_db
def test_staff_creation_respects_rank_and_permission():
    admin = staff_with_role("admin@example.com", "ADMIN")
    manager = staff_with_role("manager@example.com", "MANAGER")
    body = {"email": "x@example.com", "role": "ADMIN"}
    assert api(admin).post(USERS, body, format="json").status_code == 403
    body["role"] = "OPERATOR"
    assert api(manager).post(USERS, body, format="json").status_code == 403
    assert not User.objects.filter(email="x@example.com").exists()


@pytest.mark.django_db
def test_deactivation_revokes_sessions_and_is_rank_bound():
    admin = staff_with_role("admin@example.com", "ADMIN")
    target = staff_with_role("op@example.com", "OPERATOR")
    victim_session = mfa_session_for(target)
    boss = staff_with_role("boss@example.com", "SUPERADMIN")

    assert api(admin).post(f"{USERS}/{boss.pk}/deactivate").status_code == 403
    assert api(admin).post(f"{USERS}/{admin.pk}/deactivate").status_code == 403
    assert api(admin).post(f"{USERS}/{target.pk}/deactivate").status_code == 204

    target.refresh_from_db()
    victim_session.refresh_from_db()
    assert not target.is_active
    assert victim_session.revoked_at is not None
    assert AuditEvent.objects.filter(action="account.deactivate", actor=admin).exists()


@pytest.mark.django_db
def test_security_reset_revokes_access_removes_factors_and_requires_a_new_password():
    from auth_helpers import enroll_totp

    from apps.accounts import mfa

    admin = staff_with_role("admin@example.com", "ADMIN")
    target = staff_with_role("lost@example.com", "TECHNICIAN")
    enroll_totp(target)
    session = mfa_session_for(target)
    boss = staff_with_role("boss@example.com", "SUPERADMIN")

    assert api(admin).post(f"{USERS}/{boss.pk}/security-reset").status_code == 403
    manager = staff_with_role("manager@example.com", "MANAGER")
    assert api(manager).post(f"{USERS}/{target.pk}/security-reset").status_code == 403

    assert api(admin).post(f"{USERS}/{target.pk}/security-reset").status_code == 204
    target.refresh_from_db()
    session.refresh_from_db()
    assert session.revoked_at is not None
    assert not mfa.has_mfa(target)
    assert not target.has_usable_password()
    assert "reset-password?uid=" in mail.outbox[-1].body
    assert AuditEvent.objects.filter(action="account.security_reset", actor=admin).exists()
