# Mandatory MFA for staff (WR-15)

Status: implemented in Sprint 1. Decisions below were taken autonomously by the security executor (no stakeholder available) within the frozen Confluence Stack v1.0 / UserStory v1.0 requirements.

## Requirements covered

- MFA is mandatory for **every** staff account (`is_staff`), including superusers.
- WebAuthn/passkey is the preferred factor, TOTP the fallback, recovery codes (10, single use, stored as HMAC-SHA256 digests) the last resort. SMS is not offered.
- No bypass through web, mobile, password change/reset, token refresh or Django admin.
- Recovery-code use, enrollment, verification failures, lockouts and step-up are audited.
- Sensitive actions require *step-up* (MFA re-verified within `STEP_UP_MAX_AGE`, default 5 min).

## Design decision: "not signed in until the second factor"

Options considered:

1. **Pending state before login (chosen).** The password step only creates a short-lived pending state; Django `login()` / the JWT pair happen only after the second factor.
2. Log in after the password and gate every endpoint on an "MFA verified" flag. Rejected: any endpoint, middleware or Django admin view that forgets the flag becomes a bypass.
3. Third-party packages (django-allauth MFA, django-otp, allauth-headless). Rejected by the Sprint constraints (no second auth backend) and because they would duplicate the session/JWT boundaries already in place.

With option 1 a password-only browser session is an *anonymous* Django session, so `request.user` is anonymous everywhere — DRF, Django admin, any future view. Defence in depth on top:

- `StaffSessionAuthentication` / `StaffJWTAuthentication` accept only a tracked `UserSession` with `mfa_verified_at` set; `IsStaffUser` (the DRF default permission) and `StaffModelPermissions` re-check it.
- `StaffAdminSite.has_permission` requires a tracked, MFA-verified web session; its own password form only redirects.
- Refresh only rotates tokens bound (`sid`) to an MFA-verified mobile session.
- Password reset (WR-16) never signs in; the next sign-in goes through MFA again.

## Flows

| Step | Web (session cookie + CSRF) | Mobile (JWT) |
| --- | --- | --- |
| 1. Password | `POST /auth/session/login` → `{status, methods}`; pending marker stored in the (rotated) anonymous session for 5 min | `POST /auth/token` → `{status, methods, challenge}`; challenge is a signed, 5-minute, single-use token. **No access/refresh token.** |
| 2a. Verify (`mfa_required`) | `POST /auth/session/mfa/verify` with `totp`, `recovery` or `webauthn` (`/auth/session/mfa/webauthn/options` first) | `POST /auth/token/mfa/verify` with `totp` or `recovery` |
| 2b. First enrollment (`mfa_enrollment_required`) | passkey: `/auth/session/mfa/webauthn/register/options` + `/verify`; or TOTP: `/auth/session/mfa/totp/setup` + `/confirm` | TOTP: `/auth/token/mfa/totp/setup` + `/confirm` |
| Result | Django session (key rotated) + tracked `UserSession`; recovery codes shown once after first enrollment | JWT pair bound to a tracked `UserSession`; recovery codes in the response after first enrollment |

The pending state carries the user id, the stage, a nonce and a fingerprint of the password hash: a password change voids it. The stage is recomputed from the database on every call, so the enrollment endpoints refuse to add a factor to an account that already has one — adding or replacing factors requires a full session plus step-up (`/auth/mfa/...`).

Mobile does not support WebAuthn in Sprint 1 (decision recorded in the brief). Mobile users need TOTP or recovery codes; a passkey-only user is told to use the web backoffice and can add TOTP there.

## Factor details

- **TOTP** (`pyotp`): 30 s step, ±1 step tolerance, secret encrypted at rest with Fernet (key derived from `MFA_SECRET_KEY`, default `SECRET_KEY`). Each accepted step is stored (`last_used_step`) with an atomic compare-and-set, so a code is never accepted twice (replay inside the same step is rejected).
- **WebAuthn** (`webauthn` / py_webauthn, Duo): user verification **required**, attestation `none`, origins `WEBAUTHN_ORIGINS`, RP ID `WEBAUTHN_RP_ID`. Challenges live in the server session, are bound to user + purpose, expire in 5 min and are popped on first use. The signature counter is updated with compare-and-set (clone/replay detection).
- **Recovery codes**: 10 codes of 50 bits, shown once, stored as keyed HMAC-SHA256, consumed atomically. They are only accepted when the account also has a real factor; each use is audited with the remaining count.
- At least one of TOTP/WebAuthn must remain: removing the last factor is refused.

## Brute force

Each wrong second-factor proof is audited (`mfa.verify.failure`) and counts toward the per-account progressive lockout (`apps/accounts/lockout.py`: 5 failures → 1 min, doubling up to 1 h, shared DatabaseCache). MFA endpoints are also rate limited per IP (`auth_mfa` scope).

## Step-up

`RequiresRecentMFA` checks `UserSession.mfa_verified_at`; `POST /auth/step-up` (TOTP, recovery code or WebAuthn via `/auth/step-up/webauthn/options`) refreshes it. Used for: adding/replacing/removing factors, regenerating recovery codes, password change (WR-16), role changes, staff creation/deactivation (WR-17). Error code: `step_up_required`.

## Residual risks

- **First enrollment is trust-on-first-use.** Whoever knows the password of a never-enrolled account can enroll a factor. Mitigation: staff accounts are created without a usable password and activated through a single-use reset link (WR-17), so the first password is chosen by the owner; enrollment happens immediately after.
- `MFA_SECRET_KEY` rotation invalidates TOTP secrets and recovery codes; plan it with re-enrollment. Set a dedicated `MFA_SECRET_KEY` in production to decouple it from `SECRET_KEY` rotation.
- No QR code is rendered yet (secret + `otpauth://` link only); the React backoffice UI is Sprint 2.
