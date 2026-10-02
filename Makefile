SHELL := /bin/bash
.DEFAULT_GOAL := help
COMPOSE := docker compose
BACKEND := cd apps/backend && uv run
# Host-side PostgreSQL used by tests, schema generation and smoke checks. CI exports
# POSTGRES_PORT=5432; locally the Compose service publishes 5440 (see .env.example).
POSTGRES_PORT ?= 5440
DATABASE_URL ?= postgresql://app:app@localhost:$(POSTGRES_PORT)/app
export DATABASE_URL

.PHONY: help setup db dev dev-email down logs reset doctor smoke \
        migrate migrations shell lint typecheck test check api-schema api-client api-check \
        web-test web-e2e mobile-check docker-build format security-check

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*##"}; /^[a-zA-Z_-]+:.*##/ {printf "%-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Install Python and JavaScript dependencies
	cd apps/backend && uv sync --locked --all-groups
	corepack pnpm install --frozen-lockfile

db: ## Start only the local PostgreSQL service (for host-side tests and tooling)
	$(COMPOSE) up -d --wait postgres

dev: ## Start PostgreSQL, Django API and web app
	$(COMPOSE) up --build postgres backend web

dev-email: ## Start the core stack with the optional Mailpit inbox
	EMAIL_ENABLED=true $(COMPOSE) --profile email up --build

down: ## Stop services without deleting persistent data
	$(COMPOSE) down

logs: ## Follow service logs
	$(COMPOSE) logs -f --tail=100

reset: ## Remove development containers and database volume
	$(COMPOSE) down --volumes --remove-orphans

doctor: ## Check required tools, environment and mobile compatibility metadata
	python3 scripts/doctor.py

migrate: ## Apply database migrations
	$(COMPOSE) exec backend python manage.py migrate

migrations: ## Create Django migrations for model changes
	$(BACKEND) python manage.py makemigrations

shell: ## Open a Django shell
	$(COMPOSE) exec backend python manage.py shell

api-schema: ## Generate OpenAPI from Django
	cd apps/backend && uv run python manage.py spectacular --file ../../openapi/openapi.yaml --validate

api-client: ## Generate TypeScript clients from the committed OpenAPI contract
	corepack pnpm exec orval --config orval.config.ts
	corepack pnpm exec prettier --write packages/api-client/src/generated

api-check: ## Regenerate schema and client and fail on drift
	bash scripts/api-check.sh

lint: ## Run Python and JavaScript lint checks
	cd apps/backend && uv run ruff check . ../../scripts && uv run ruff format --check . ../../scripts
	corepack pnpm exec eslint apps packages

typecheck: ## Type-check backend, web, mobile, and shared packages
	cd apps/backend && uv run mypy config apps
	corepack pnpm --filter @ramoverde/api-client typecheck
	corepack pnpm --filter @ramoverde/web typecheck
	corepack pnpm --filter @ramoverde/mobile typecheck
	corepack pnpm --filter @ramoverde/shared typecheck

web-test: ## Run web unit and component tests
	corepack pnpm --filter @ramoverde/web exec vitest run

web-e2e: ## Run the Playwright browser smoke test (requires installed Chromium)
	corepack pnpm --filter @ramoverde/web test:e2e

mobile-check: ## Validate Expo config, dependencies, types and Android Metro bundle
	corepack pnpm --filter @ramoverde/mobile exec expo-doctor
	corepack pnpm --filter @ramoverde/mobile typecheck
	corepack pnpm --filter @ramoverde/mobile test
	EXPO_PUBLIC_API_URL=https://api.example.com/api/v1 corepack pnpm --filter @ramoverde/mobile exec expo export --platform android

security-check: ## Audit locked Python dependencies and high-severity production JavaScript advisories
	cd apps/backend && uv audit --locked
	corepack pnpm audit --prod --audit-level high

test: ## Run backend, web, mobile, and repository script tests
	cd apps/backend && uv run pytest
	corepack pnpm --filter @ramoverde/web exec vitest run
	corepack pnpm --filter @ramoverde/mobile test
	python3 -m unittest discover -s scripts/tests -v

format: ## Format Python and TypeScript sources
	cd apps/backend && uv run ruff check --fix . && uv run ruff format .
	corepack pnpm exec prettier --write .

check: ## Run the repository quality gate (requires Docker for PostgreSQL)
	$(MAKE) lint typecheck test api-check mobile-check
	corepack pnpm --filter @ramoverde/web build
	cd apps/backend && uv run python manage.py makemigrations --check --dry-run
	cd apps/backend && DJANGO_SECRET_KEY=ci-only-not-a-secret-ci-only-not-a-secret-ci-only-not-a-secret DJANGO_ALLOWED_HOSTS=example.com DJANGO_CORS_ALLOWED_ORIGINS=https://example.com DJANGO_CSRF_TRUSTED_ORIGINS=https://example.com uv run python manage.py check --deploy --settings=config.settings.production
	python3 scripts/validate_mobile_library.py
	$(COMPOSE) config --quiet
	DATABASE_URL=postgresql://app:ci-only@localhost:5432/app DJANGO_SECRET_KEY=ci-only-not-a-secret-ci-only-not-a-secret-ci-only-not-a-secret DJANGO_ALLOWED_HOSTS=example.com DJANGO_CORS_ALLOWED_ORIGINS=https://example.com DJANGO_CSRF_TRUSTED_ORIGINS=https://example.com VITE_API_BASE_URL=https://api.example.com/api/v1 $(COMPOSE) -f compose.production.yaml config --quiet
	$(MAKE) smoke

smoke: ## Migrate PostgreSQL, boot the API and assert database readiness
	bash scripts/boot-smoke.sh

docker-build: ## Build production backend and web images
	docker build --target production -f infra/docker/Dockerfile.backend -t ramoverde-backend:production .
	docker build --target production -f infra/docker/Dockerfile.web -t ramoverde-web:production .
