# API contract

Django REST Framework plus drf-spectacular is the API source of truth. Versioned operations live below `/api/v1/`; the committed OpenAPI document is `openapi/openapi.yaml`. Run `make api-schema` after changing endpoint behavior or serializers, then `make api-client`. Orval produces TanStack Query v5 hooks, Fetch methods and types in `packages/api-client/src/generated/`.

Both clients import `@ramoverde/api-client`. Generated query hooks provide the default query keys; invalidate `query.queryKey` after mutations rather than defining parallel cache identities. Use generated mutations where no application-specific boundary orchestration is required. Do not define duplicate response/request interfaces in either app. Custom transport behavior lives in `packages/api-client/src/fetcher.ts`. Operation IDs are treated as stable generated function names. CI regenerates schema and code and fails on drift.

Health: `/api/v1/health/live` tests process reachability; `/api/v1/health/ready` also checks PostgreSQL. `/api/v1/users/me` returns the authenticated account. `/api/schema/` serves the live JSON schema for inspection.
