# Password policy and session management (WR-16)

## Password policy

| Rule | Implementation |
| --- | --- |
| Mandatory change every 30 days | `PASSWORD_MAX_AGE_DAYS` (env, default 30). `User.password_changed_at` is stamped by `set_password`; unknown age counts as expired. |
| Strong minimum, long passphrases | `MinimumLengthValidator(12)`; `MaximumLengthValidator(1024)` only bounds hashing cost. |
| Compromised/common passwords | Django `CommonPasswordValidator` (offline list of ~20k breached/common passwords) plus `UserAttributeSimilarityValidator` and `NumericPasswordValidator`. No online HIBP lookup (offline baseline chosen: no third-party call, no fail-open logic). |
| No reuse of recent passwords | `PasswordHistoryValidator`: current + last 5 hashes (`PASSWORD_HISTORY_COUNT`), compared with Django's hashers; history stores hashes only. |
| Current password required to change | `POST /api/v1/auth/password/change` checks it (failure audited) and also requires a recent MFA verification (step-up). |
| Reset token single use, limited lifetime | Django `default_token_generator` (bound to the password hash and last login, so it dies after use), `PASSWORD_RESET_TIMEOUT` = 30 min. At most one reset email per account every 5 minutes; the request always answers 202 with the same text. |
| Sessions invalidated after reset | Reset revokes every tracked session (web sessions deleted, mobile `sid` revoked) and blacklists every refresh token; `CHECK_REVOKE_TOKEN` also kills access tokens. |
| Change/reset never bypass MFA | Reset never signs in; change requires an MFA-verified session plus step-up. The next sign-in always goes through the second factor. |

### Expired passwords

The password step records `password.expired`; sign-in still requires the second factor. Afterwards `IsStaffUser`/`StaffModelPermissions` answer `403 password_change_required` on every endpoint except those that opt in with `allow_expired_password = True`: `GET /users/me` (exposes `password_change_required` and `password_expires_at`), `POST /auth/password/change`, step-up and logout. Django admin refuses expired passwords too. The web backoffice and the mobile app show a mandatory change form.

A password change keeps the current session (the web session key is rotated by Django and re-bound; a mobile session receives a new token pair in the `200` response) and revokes every other session.

## Sessions and devices

Every completed sign-in is an `accounts.UserSession` (`web` = one Django session, `mobile` = one refresh-token family) with `created_at`, `last_seen_at` (updated at most once a minute), IP, user agent and the MFA method.

| Endpoint | Effect |
| --- | --- |
| `GET /api/v1/auth/sessions` | Own active sessions, `current` flags the caller. Session keys/tokens are never returned. |
| `DELETE /api/v1/auth/sessions/{id}` | Revoke one own session (`session.revoke`). |
| `POST /api/v1/auth/sessions/revoke-others` | Keep the current session, revoke the rest (`session.revoke_others`). |
| `POST /api/v1/auth/sessions/revoke-all` | Global logout: all web sessions **and** all mobile refresh tokens, including the caller (`session.revoke_all`). |

Revocation is immediate: both authentication classes look up the active `UserSession` on every request.

## Residual risks

- No online breached-password check (HIBP): only the offline Django list. Can be added later as an extra validator that must fail open and stay disabled in tests.
- Reset emails use the configured `EMAIL_BACKEND` (console in development). Production must configure SMTP with TLS.
