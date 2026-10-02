# Authentication architecture

The API exposes replaceable authentication boundaries without custom cryptography. Only staff accounts exist (no public self-registration); the customer portal is out of scope for Sprint 1.

## Browser (staff backoffice)

The web client uses Django session authentication. The login flow first fetches `/api/v1/auth/csrf`, then posts credentials to `/api/v1/auth/session/login` with the returned CSRF token in `X-CSRFToken`. Django rotates the session key (no session fixation) and sets an HttpOnly, `SameSite=Lax` session cookie (`Secure` in production, 8 h lifetime by default via `DJANGO_SESSION_COOKIE_AGE`). The CSRF cookie is also HttpOnly, so the token is read from `/api/v1/auth/csrf`, never from `document.cookie`. Unsafe authenticated requests include the CSRF header; logout posts to `/api/v1/auth/session/logout`. The API client uses `credentials: include`. Never persist browser credentials in localStorage or JavaScript-accessible storage.

Every successful sign-in creates an `accounts.UserSession` (kind `web`) bound to the Django session key, with IP, user agent, `created_at` and `last_seen_at`. `StaffSessionAuthentication` accepts a session cookie only while that row is active, so revoking it (logout, revoke-other-sessions, global logout, password reset) invalidates the browser immediately; the server-side session row is deleted too.

Failed sign-ins always answer `401 authentication_failed` with the same message whether the email is unknown, the password is wrong, the account is inactive or not staff. Sign-in success and failure are recorded in the audit trail (`apps.audit`).

Production must use HTTPS, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, explicit `CSRF_TRUSTED_ORIGINS`, explicit credentialed CORS origins, and same-site-compatible hostnames. If frontend and API are on unrelated sites, evaluate deployment topology and browser third-party cookie policy before enabling it; do not solve that with wildcard CORS.

### Django admin

Django admin is mounted at `/django-admin/` for technical superusers only. It never authenticates anyone itself: its login and password-change views redirect to the staff sign-in (`STAFF_LOGIN_URL`, the React backoffice at web `/admin/login`). `StaffAdminSite.has_permission` requires an active superuser **and** a tracked staff web session, so a Django session created any other way (e.g. `force_login`, the old admin form) is refused. The React backoffice lives at web `/admin/*`.

## Native

Mobile obtains short-lived access and refresh JWTs from `/api/v1/auth/token` and `/api/v1/auth/token/refresh`. SimpleJWT supplies token signing and validation. The app stores credentials in Expo SecureStore through a small auth adapter; it must never use AsyncStorage or Expo public env variables for secrets. The shared Fetch transport retries an authenticated request once after a 401, using the rotating refresh token. Refresh calls omit the access token and skip refresh recursion. Concurrent refresh attempts share one promise. Production deployments still require HTTPS and should review token lifetimes and revocation policy.

## Common contract

Both mechanisms authenticate requests to `/api/v1/users/me`; DRF checks JWT first, then session auth. Permissions remain server-side. Passwords are handled only by Django's configured password hashers. Error responses follow the shared `{error:{code,message,details,request_id}}` shape for DRF exceptions.
