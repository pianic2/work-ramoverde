# Authentication architecture

The API exposes replaceable authentication boundaries without custom cryptography.

## Browser

The web client uses Django session authentication. The login flow first fetches `/api/v1/auth/csrf`, then posts credentials to `/api/v1/auth/session/login` with the returned CSRF token. Django sets an HttpOnly session cookie. Unsafe authenticated requests include the CSRF header; logout posts to `/api/v1/auth/session/logout`. The API client uses `credentials: include`. Never persist browser credentials in localStorage or JavaScript-accessible storage.

Production must use HTTPS, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, explicit `CSRF_TRUSTED_ORIGINS`, explicit credentialed CORS origins, and same-site-compatible hostnames. If frontend and API are on unrelated sites, evaluate deployment topology and browser third-party cookie policy before enabling it; do not solve that with wildcard CORS.

## Native

Mobile obtains short-lived access and refresh JWTs from `/api/v1/auth/token` and `/api/v1/auth/token/refresh`. SimpleJWT supplies token signing and validation. The app stores credentials in Expo SecureStore through a small auth adapter; it must never use AsyncStorage or Expo public env variables for secrets. The shared Fetch transport retries an authenticated request once after a 401, using the rotating refresh token. Refresh calls omit the access token and skip refresh recursion. Concurrent refresh attempts share one promise. Production deployments still require HTTPS and should review token lifetimes and revocation policy.

## Common contract

Both mechanisms authenticate requests to `/api/v1/users/me`; DRF checks JWT first, then session auth. Permissions remain server-side. Passwords are handled only by Django's configured password hashers. Error responses follow the shared `{error:{code,message,details,request_id}}` shape for DRF exceptions.
