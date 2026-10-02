---
name: api-contract
description: Change the Django API contract and regenerate OpenAPI and TypeScript clients deterministically.
---

# API contract

- **Trigger:** An API route, serializer, auth response, or schema change.
- **Inputs:** Django behavior, affected web/mobile consumers, OpenAPI operation IDs.
- **Steps:** Change backend first; run `make api-schema`; inspect schema diff; run `make api-client`; use only generated models/functions; update both clients as required.
- **Validation:** `make api-check` must reproduce committed schema and generated output exactly.
- **Expected output:** Backend code/tests, contract, generated client, and drift-free regeneration evidence.
