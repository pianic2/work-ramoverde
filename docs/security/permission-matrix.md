# RBAC permission matrix (WR-17)

Single source of truth in code: [`apps/backend/apps/accounts/rbac.py`](../../apps/backend/apps/accounts/rbac.py) (`ROLE_PERMISSIONS`). `tests/test_rbac.py` fails if a codename in the code is missing from this page. Roles are Django groups kept in sync after every `migrate` and by `manage.py sync_roles` (idempotent; codenames that do not exist yet are granted on a later sync).

Principles:

- No `is_admin` flag. Authorization checks Django permissions (`StaffModelPermissions`, `user.has_perm`), never role names. `is_superuser` is a separate technical flag that only opens Django admin (`/django-admin/`).
- Every staff endpoint also requires an MFA-verified session and a non-expired password (`IsStaffUser`).
- The UI may hide actions using `/users/me` (`role`, `permissions`), but it never replaces backend authorization.
- One role per staff account. A staff account without a role has no permissions.

## Roles

| Role | Purpose | Rank |
| --- | --- | --- |
| `SUPERADMIN` | Owner of the platform; full matrix; only role that can assign `SUPERADMIN`. | 100 |
| `ADMIN` | Staff accounts, roles below ADMIN, security management, audit, CMS, media approval. | 80 |
| `MANAGER` | Oversight: staff directory (read), CMS (read), media, business domains (TBD). | 60 |
| `TECHNICIAN` | Field work: media upload and private documents; inspections (TBD). | 40 |
| `OPERATOR` | Front office: media upload; leads/customers/conversations (TBD). | 40 |
| `CONTENT_EDITOR` | Public site content: CMS editing and publishing, media upload/edit. | 40 |

## Assignment rules (anti-escalation)

- Assigning roles needs `accounts.assign_role` (SUPERADMIN, ADMIN) and a recent MFA verification (step-up).
- An actor may assign only roles ranked **strictly below** its own, and may only manage accounts whose current role is strictly below its own. Exception: `SUPERADMIN` may assign any role, including `SUPERADMIN`, and manage other superadmins.
- Nobody can change their own role or deactivate themselves.
- Creating a staff account (`accounts.add_user` + `accounts.assign_role`) follows the same rules. The account has no usable password: the owner sets it through a single-use link, then enrolls MFA at first sign-in.
- Deactivation (`accounts.deactivate_user`) follows the same rank rules and revokes every session and refresh token.
- All of these are audited (`account.create`, `role.change` with from/to, `account.deactivate`).

## Matrix (implemented modules)

Legend: ✓ granted, — not granted.

### Accounts and audit

| Permission | SUPERADMIN | ADMIN | MANAGER | TECHNICIAN | OPERATOR | CONTENT_EDITOR |
| --- | --- | --- | --- | --- | --- | --- |
| `accounts.view_user` | ✓ | ✓ | ✓ | — | — | — |
| `accounts.add_user` | ✓ | ✓ | — | — | — | — |
| `accounts.change_user` | ✓ | ✓ | — | — | — | — |
| `accounts.deactivate_user` | ✓ | ✓ | — | — | — | — |
| `accounts.assign_role` | ✓ | ✓ | — | — | — | — |
| `accounts.manage_user_security` | ✓ | ✓ | — | — | — | — |
| `audit.view_auditevent` | ✓ | ✓ | — | — | — | — |

Own account actions (own sessions, own MFA factors, own password) need no permission: every authenticated staff member can manage their own security.

### CMS

| Permission | SUPERADMIN | ADMIN | MANAGER | TECHNICIAN | OPERATOR | CONTENT_EDITOR |
| --- | --- | --- | --- | --- | --- | --- |
| `cms.view_page` | ✓ | ✓ | ✓ | — | — | ✓ |
| `cms.view_pagesection` | ✓ | ✓ | ✓ | — | — | ✓ |
| `cms.view_navigationmenu` | ✓ | ✓ | ✓ | — | — | ✓ |
| `cms.view_navigationitem` | ✓ | ✓ | ✓ | — | — | ✓ |
| `cms.view_sitesettings` | ✓ | ✓ | ✓ | — | — | ✓ |
| `cms.view_seosettings` | ✓ | ✓ | ✓ | — | — | ✓ |
| `cms.add_page` | ✓ | ✓ | — | — | — | ✓ |
| `cms.change_page` | ✓ | ✓ | — | — | — | ✓ |
| `cms.delete_page` | ✓ | ✓ | — | — | — | ✓ |
| `cms.publish_page` | ✓ | ✓ | — | — | — | ✓ |
| `cms.add_pagesection` | ✓ | ✓ | — | — | — | ✓ |
| `cms.change_pagesection` | ✓ | ✓ | — | — | — | ✓ |
| `cms.delete_pagesection` | ✓ | ✓ | — | — | — | ✓ |
| `cms.add_navigationmenu` | ✓ | ✓ | — | — | — | ✓ |
| `cms.change_navigationmenu` | ✓ | ✓ | — | — | — | ✓ |
| `cms.delete_navigationmenu` | ✓ | ✓ | — | — | — | ✓ |
| `cms.add_navigationitem` | ✓ | ✓ | — | — | — | ✓ |
| `cms.change_navigationitem` | ✓ | ✓ | — | — | — | ✓ |
| `cms.delete_navigationitem` | ✓ | ✓ | — | — | — | ✓ |
| `cms.add_sitesettings` | ✓ | ✓ | — | — | — | ✓ |
| `cms.change_sitesettings` | ✓ | ✓ | — | — | — | ✓ |
| `cms.add_seosettings` | ✓ | ✓ | — | — | — | ✓ |
| `cms.change_seosettings` | ✓ | ✓ | — | — | — | ✓ |

Singleton settings have no delete permission in any role.

### Media

| Permission | SUPERADMIN | ADMIN | MANAGER | TECHNICIAN | OPERATOR | CONTENT_EDITOR |
| --- | --- | --- | --- | --- | --- | --- |
| `media.view_mediaasset` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `media.add_mediaasset` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `media.change_mediaasset` | ✓ | ✓ | — | — | — | ✓ |
| `media.delete_mediaasset` | ✓ | ✓ | — | — | — | — |
| `media.approve_mediaasset` | ✓ | ✓ | — | — | — | — |
| `media.download_private_mediaasset` | ✓ | ✓ | ✓ | ✓ | — | — |

Approval of media for public use is kept away from content editors (four-eyes: an editor uploads, an admin approves).

## Planned modules (TBD — no codenames defined yet)

These domains have no models in Sprint 1. When a module is built it declares its model permissions (`Meta.permissions` plus Django's add/change/delete/view), this matrix and `ROLE_PERMISSIONS` are extended in the same change, and `sync_roles` grants them.

| Domain | SUPERADMIN | ADMIN | MANAGER | TECHNICIAN | OPERATOR | CONTENT_EDITOR |
| --- | --- | --- | --- | --- | --- | --- |
| Leads (`leads`) | full | full | full + assignment | read assigned | create/update | — |
| Customers (`customers`) | full | full | full | read assigned | create/update | — |
| Inspections (`inspections`) | full | full | schedule/assign | read/update assigned | schedule | — |
| Conversations (`conversations`) | full | full | read all | assigned threads | assigned threads | — |
| Services / projects / certifications | full | full | read | — | — | edit + publish |
| Notifications | own | own | own | own | own | own |

"Assigned" scoping is object-level and will need row-level checks in those modules (not expressible with model permissions alone).
