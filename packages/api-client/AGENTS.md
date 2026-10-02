# API client instructions

OpenAPI is authoritative. Never hand-edit `src/generated/`. Run `make api-schema`, `make api-client`, then `make api-check`. Keep transport customization in `src/fetcher.ts`; do not add manually duplicated endpoint/request/response models.
