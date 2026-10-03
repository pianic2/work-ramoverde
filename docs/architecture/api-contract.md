# API contract

Django REST Framework plus drf-spectacular is the API source of truth. Versioned operations live below `/api/v1/`; the committed OpenAPI document is `openapi/openapi.yaml`. Run `make api-schema` after changing endpoint behavior or serializers, then `make api-client`. Orval produces TanStack Query v5 hooks, Fetch methods and types in `packages/api-client/src/generated/`.

Both clients import `@ramoverde/api-client`. Generated query hooks provide the default query keys; invalidate `query.queryKey` after mutations rather than defining parallel cache identities. Use generated mutations where no application-specific boundary orchestration is required. Do not define duplicate response/request interfaces in either app. Custom transport behavior lives in `packages/api-client/src/fetcher.ts`. Operation IDs are treated as stable generated function names. CI regenerates schema and code and fails on drift.

Health: `/api/v1/health/live` tests process reachability; `/api/v1/health/ready` also checks PostgreSQL. `/api/v1/users/me` returns the authenticated account. `/api/schema/` serves the live JSON schema for inspection.

## Pipeline guarantees (WR-11)

`Django/DRF → drf-spectacular → openapi/openapi.yaml → Orval → @ramoverde/api-client → web/mobile`

- `make api-schema` runs `spectacular --validate --fail-on-warn`: any schema warning (untyped view, missing serializer, enum collision) fails the build. Fix the view with `extend_schema`/serializers instead of silencing it.
- `apps/backend/tests/test_openapi_contract.py` requires every operation under `/api/v1/` and a unique, explicit camelCase `operation_id` (it becomes the generated function name, so treat it as a public API).
- `make api-check` (CI job `contract`) regenerates schema and client into place and fails on any diff, so hand edits to `openapi/openapi.yaml` or `packages/api-client/src/generated/` are always detected.
- Web and mobile consume only `@ramoverde/api-client`; their typechecks are the compile-time proof the generated client is consumable.
- When two branches both change the API, never hand-merge generated files: merge the Django sources, then rerun `make api-schema api-client`.
