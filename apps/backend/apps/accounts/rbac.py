"""RBAC for RamoVerde staff (WR-17): the single source of truth for roles.

A role is a Django `Group` named after `Role`; its permissions are exactly the codenames
listed in `ROLE_PERMISSIONS` (kept in sync by `sync_roles()`, run after every `migrate`
and by `manage.py sync_roles`). Authorization always checks Django permissions
(`StaffModelPermissions`, `user.has_perm`), never the role name, so every module that
declares model permissions is covered. The human-readable matrix is
`docs/security/permission-matrix.md`; a test keeps it aligned with this file.

Codenames of other modules are referenced as strings and resolved at sync time, so this
module never imports them and tolerates permissions that do not exist yet.
"""

from enum import StrEnum
from typing import Any

from django.contrib.auth.models import Group, Permission
from django.db import transaction

from .models import User


class Role(StrEnum):
    SUPERADMIN = "SUPERADMIN"
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    TECHNICIAN = "TECHNICIAN"
    OPERATOR = "OPERATOR"
    CONTENT_EDITOR = "CONTENT_EDITOR"


ROLE_LABELS = {
    Role.SUPERADMIN: "Super amministratore",
    Role.ADMIN: "Amministratore",
    Role.MANAGER: "Responsabile",
    Role.TECHNICIAN: "Tecnico",
    Role.OPERATOR: "Operatore",
    Role.CONTENT_EDITOR: "Redattore contenuti",
}

# Assignment hierarchy: an actor may only assign or manage roles ranked strictly below its
# own; SUPERADMIN is the only role that may assign SUPERADMIN (and manage other SUPERADMINs).
ROLE_RANK = {
    Role.SUPERADMIN: 100,
    Role.ADMIN: 80,
    Role.MANAGER: 60,
    Role.TECHNICIAN: 40,
    Role.OPERATOR: 40,
    Role.CONTENT_EDITOR: 40,
}

ACCOUNTS_ADMIN = (
    "accounts.view_user",
    "accounts.add_user",
    "accounts.change_user",
    "accounts.deactivate_user",
    "accounts.assign_role",
    "accounts.manage_user_security",
)
AUDIT_VIEW = ("audit.view_auditevent",)
CMS_VIEW = (
    "cms.view_page",
    "cms.view_pagesection",
    "cms.view_navigationmenu",
    "cms.view_navigationitem",
    "cms.view_sitesettings",
    "cms.view_seosettings",
)
CMS_EDIT = (
    "cms.add_page",
    "cms.change_page",
    "cms.delete_page",
    "cms.publish_page",
    "cms.add_pagesection",
    "cms.change_pagesection",
    "cms.delete_pagesection",
    "cms.add_navigationmenu",
    "cms.change_navigationmenu",
    "cms.delete_navigationmenu",
    "cms.add_navigationitem",
    "cms.change_navigationitem",
    "cms.delete_navigationitem",
    "cms.add_sitesettings",
    "cms.change_sitesettings",
    "cms.add_seosettings",
    "cms.change_seosettings",
)
MEDIA_VIEW = ("media.view_mediaasset",)
MEDIA_UPLOAD = ("media.add_mediaasset",)
MEDIA_EDIT = ("media.change_mediaasset",)
MEDIA_ADMIN = (
    "media.delete_mediaasset",
    "media.approve_mediaasset",
    "media.download_private_mediaasset",
)

ROLE_PERMISSIONS: dict[Role, tuple[str, ...]] = {
    Role.SUPERADMIN: ACCOUNTS_ADMIN
    + AUDIT_VIEW
    + CMS_VIEW
    + CMS_EDIT
    + MEDIA_VIEW
    + MEDIA_UPLOAD
    + MEDIA_EDIT
    + MEDIA_ADMIN,
    Role.ADMIN: ACCOUNTS_ADMIN
    + AUDIT_VIEW
    + CMS_VIEW
    + CMS_EDIT
    + MEDIA_VIEW
    + MEDIA_UPLOAD
    + MEDIA_EDIT
    + MEDIA_ADMIN,
    Role.MANAGER: ("accounts.view_user",)
    + CMS_VIEW
    + MEDIA_VIEW
    + MEDIA_UPLOAD
    + ("media.download_private_mediaasset",),
    Role.TECHNICIAN: MEDIA_VIEW + MEDIA_UPLOAD + ("media.download_private_mediaasset",),
    Role.OPERATOR: MEDIA_VIEW + MEDIA_UPLOAD,
    Role.CONTENT_EDITOR: CMS_VIEW + CMS_EDIT + MEDIA_VIEW + MEDIA_UPLOAD + MEDIA_EDIT,
}


class RoleAssignmentDenied(Exception):
    """The actor may not perform this role or account operation."""


def _split(perm: str) -> tuple[str, str]:
    app_label, codename = perm.split(".", 1)
    return app_label, codename


@transaction.atomic
def sync_roles() -> set[str]:
    """Create the role groups and set exactly the matrix permissions. Idempotent.

    Returns the codenames that do not exist (yet) in the database; they are granted on a
    later sync, e.g. after the declaring module's migrations ran.
    """
    missing: set[str] = set()
    for role, perms in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=role.value)
        resolved = []
        for perm in perms:
            app_label, codename = _split(perm)
            permission = Permission.objects.filter(
                content_type__app_label=app_label, codename=codename
            ).first()
            if permission is None:
                missing.add(perm)
            else:
                resolved.append(permission)
        group.permissions.set(resolved)
    return missing


def get_role(user: Any) -> Role | None:
    names = set(user.groups.values_list("name", flat=True))
    for role in Role:
        if role.value in names:
            return role
    return None


def set_role(user: User, role: str | Role) -> None:
    """Make `role` the user's only role group (no authorization check: use `assign_role`)."""
    role = Role(role)
    group, created = Group.objects.get_or_create(name=role.value)
    if created:
        sync_roles()
    role_groups = Group.objects.filter(name__in=[r.value for r in Role])
    user.groups.remove(*role_groups)
    user.groups.add(group)
    if not user.is_staff:
        user.is_staff = True
        user.save(update_fields=["is_staff"])


def _rank(user: User) -> int:
    role = get_role(user)
    return ROLE_RANK[role] if role is not None else 0


def check_can_manage(actor: User, target: User | None, new_role: Role | None) -> None:
    """Anti-escalation rules shared by role assignment, account creation and deactivation."""
    actor_role = get_role(actor)
    if actor_role is None:
        raise RoleAssignmentDenied
    if target is not None and target.pk == actor.pk:
        raise RoleAssignmentDenied  # nobody changes their own role or deactivates themselves
    is_superadmin = actor_role is Role.SUPERADMIN
    own_rank = ROLE_RANK[actor_role]
    if new_role is not None and not is_superadmin and ROLE_RANK[new_role] >= own_rank:
        raise RoleAssignmentDenied
    if target is not None and not is_superadmin and _rank(target) >= own_rank:
        raise RoleAssignmentDenied
