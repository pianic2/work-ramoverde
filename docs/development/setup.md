# Development setup

Install Docker Compose v2, Git, Node 24, Corepack/pnpm, Python 3.13 and uv. Copy `.env.example` to `.env`, then run `make setup`. `make dev` starts PostgreSQL, Django and Vite with hot reload. The example PostgreSQL credentials are local development defaults; replace them for any shared environment. On a fresh database, run `make migrate` in another terminal after the backend starts. `make down` retains database state; `make reset` removes the database volume.

Use `make doctor` to check local tool versions, package peers and environment defaults. `make logs` follows Compose logs. `make migrate` applies committed migrations. Use `make migrations` only after changing Django models and review the result before commit.

Optional local email: `make dev-email` starts Mailpit at SMTP `localhost:1025` and UI `localhost:8025`. Email uses the console backend in the default profile. S3 storage can be enabled with the `storage` Python extra and a product-owned S3-compatible endpoint; no local S3 container is supplied. The backend does not install a queue framework by default.

## RamoVerde local ports

| Service | Host port | Variable |
| --- | --- | --- |
| PostgreSQL | `5440` | `POSTGRES_PORT` |
| Django API | `8010` | `API_PORT` |
| Web (Vite) | `5180` | `WEB_PORT` |

PostgreSQL is the only supported database, locally and in CI. Host-side commands (`make test`, `make api-schema`, `make smoke`) use `DATABASE_URL`, defaulting to `postgresql://app:app@localhost:$(POSTGRES_PORT)/app`; start only the database with `make db`. CI exports `POSTGRES_PORT=5432` for its service container.

Migrations are never applied at startup: run `make migrate` (Compose) or `make smoke` (host: migrate, `makemigrations --check`, boot API, assert `/api/v1/health/ready`). `.env` is git-ignored; `.env.example` contains only local development placeholders.
