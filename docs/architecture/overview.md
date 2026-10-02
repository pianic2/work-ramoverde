# Architecture overview

This is a modular monorepo, not a universal UI framework. Django owns persistence and HTTP behavior. `openapi/openapi.yaml` is the cross-platform contract. Orval generates Fetch clients in `packages/api-client`; web and mobile own their rendering and consume those functions. `packages/shared` may contain only environment-neutral pure TypeScript.

PostgreSQL is the only database. Models and migrations live under `apps/backend`. Development runs services in Compose, while Expo runs on the host so developers can use native simulators/devices. Mailpit is optional through a Compose profile. S3 storage uses an optional backend extra and a product-owned endpoint. No queue is installed until a real product requires one.

Production uses a Gunicorn backend image and an unprivileged static Nginx web image. Production infrastructure, TLS termination, managed database and secrets are deployment-provider concerns; see [deployment](../deployment/production.md).
