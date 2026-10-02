---
name: django-backend
description: Implement or review Django REST API behavior, models, auth, settings, tests, and migrations.
---

# Django backend

- **Trigger:** A task changes Django or PostgreSQL behavior.
- **Inputs:** Acceptance criteria, `apps/backend/AGENTS.md`, current API and tests.
- **Steps:** Trace the owning model/view/serializer; keep auth boundaries explicit; use ORM and framework facilities; add reviewed migrations; annotate API changes; avoid SQLite assumptions.
- **Validation:** Use `uv`; run targeted pytest, Ruff and Django checks against PostgreSQL.
- **Expected output:** Scoped code, migration if needed, tests, and commands/evidence.
