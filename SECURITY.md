# Security policy

Report vulnerabilities privately to the repository maintainers. Do not disclose exploitable issues in public issues.

## Deployment requirements

- Keep `.env` and production secrets out of Git. `.env.example` contains development placeholders only.
- Use a unique Django secret from a secret manager, `DEBUG=False`, explicit hosts, HTTPS and explicit CORS/CSRF origins.
- Browser sessions are HttpOnly and Secure in production; unsafe cookie-authenticated requests require CSRF. Never use localStorage for browser auth secrets.
- Mobile tokens belong in Expo SecureStore. Never embed secrets in `EXPO_PUBLIC_*` variables.
- Login and token endpoints use scoped DRF throttles (10 attempts/minute for login, 60 refreshes/hour, and 10 logouts/minute). DRF uses Django's configured cache, which is process-local by default; multi-worker deployments should use shared cache or enforce an additional edge rate limit.
- At the trusted proxy, overwrite client-supplied `X-Forwarded-For` and enforce an edge rate limit. DRF's process-local throttle is defense in depth and must not be the sole brute-force control.
- Treat user uploads as untrusted; validate size/type, scan where appropriate, and serve from a separate origin with safe content headers.
- Django limits non-file request data to 2.5 MiB, form submissions to 1,000 fields, and uploads to 20 files per request. Uploads larger than 2.5 MiB are streamed to temporary storage; configure the reverse proxy or hosting platform with the product's total request/file size limit and bound temporary disk space.
- Production containers run non-root where practical. Migrations run as a deployment step.
- Keep dependencies current through Dependabot and review security alerts. CI runs CodeQL.
- `make security-check` audits the locked Python graph, including optional storage, and blocks high-severity production JavaScript advisories. Review lower-severity findings with their actual usage paths.

See `docs/architecture/authentication.md` and `docs/deployment/production.md` before exposing the API publicly.
