#!/usr/bin/env bash
set -euo pipefail
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
mkdir -p "$tmp_dir/generated"
cp openapi/openapi.yaml "$tmp_dir/openapi.yaml"
cp -a packages/api-client/src/generated/. "$tmp_dir/generated/" 2>/dev/null || true
make api-schema
make api-client
diff -u "$tmp_dir/openapi.yaml" openapi/openapi.yaml
diff -ru "$tmp_dir/generated" packages/api-client/src/generated
echo "OpenAPI and generated TypeScript client are up to date."
