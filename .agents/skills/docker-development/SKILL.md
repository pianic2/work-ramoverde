---
name: docker-development
description: Change Compose services, development containers, and production Dockerfiles.
---

# Docker development

- **Trigger:** A task changes local infrastructure, compose profiles, or images.
- **Inputs:** Required services, production/development contexts, environment contract.
- **Steps:** Keep default services limited to PostgreSQL/backend/web; make optional services profile-gated; use health checks, persistent volumes and non-root production users; never run migrations implicitly in production startup.
- **Validation:** `docker compose config`, startup/health checks where available, and production image build.
- **Expected output:** Reproducible compose/image change, tested config, and profile enablement instructions.
