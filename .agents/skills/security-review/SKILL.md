---
name: security-review
description: Review authentication, deployment settings, dependencies, storage and input handling.
---

# Security review

- **Trigger:** Auth, settings, uploads, dependencies, containers, CORS/CSRF, or deployment changes.
- **Inputs:** Diff, threat boundary, current `SECURITY.md` and settings.
- **Steps:** Check secret handling, permission defaults, CSRF/session behavior, JWT expiry/storage, origin allowlists, HTTPS, upload trust, container user and dependency posture.
- **Validation:** Tests for affected boundaries, deployment checks, secret scan/CodeQL CI.
- **Expected output:** Findings first with paths and severity; otherwise concise review evidence.
