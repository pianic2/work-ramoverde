#!/usr/bin/env bash
set -euo pipefail

prefix="ramoverde-production-smoke-$$"
network_name="$prefix"
postgres_name="$prefix-postgres"
backend_name="$prefix-backend"
web_name="$prefix-web"

cleanup() {
  docker rm --force "$backend_name" "$web_name" "$postgres_name" >/dev/null 2>&1 || true
  docker network rm "$network_name" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker network create "$network_name" >/dev/null
docker run --detach --rm \
  --name "$postgres_name" \
  --network "$network_name" \
  --network-alias postgres \
  --tmpfs /var/lib/postgresql:rw,nosuid,size=512m \
  --env POSTGRES_DB=app \
  --env POSTGRES_USER=app \
  --env POSTGRES_PASSWORD=app \
  postgres:18.4-alpine@sha256:9a8afca54e7861fd90fab5fdf4c42477a6b1cb7d293595148e674e0a3181de15 >/dev/null

postgres_ready=false
for attempt in $(seq 1 30); do
  if docker exec "$postgres_name" pg_isready -U app -d app >/dev/null 2>&1; then
    postgres_ready=true
    break
  fi
  sleep 1
done
if [ "$postgres_ready" != true ]; then
  docker logs "$postgres_name"
  exit 1
fi

docker run --detach --rm \
  --name "$backend_name" \
  --network "$network_name" \
  --user 10001:10001 \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --env DATABASE_URL=postgresql://app:app@postgres:5432/app \
  --env DJANGO_SETTINGS_MODULE=config.settings.production \
  --env DJANGO_DEBUG=false \
  --env DJANGO_SECRET_KEY=ci-only-not-a-secret-ci-only-not-a-secret-ci-only-not-a-secret \
  --env DJANGO_ALLOWED_HOSTS=example.com \
  --env DJANGO_CORS_ALLOWED_ORIGINS=https://example.com \
  --env DJANGO_CSRF_TRUSTED_ORIGINS=https://example.com \
  ramoverde-backend:production >/dev/null

backend_ready=false
for attempt in $(seq 1 30); do
  if docker exec "$backend_name" python -c '
import json, urllib.request
request = urllib.request.Request(
    "http://127.0.0.1:8000/api/v1/health/ready",
    headers={"Host": "example.com", "X-Forwarded-Proto": "https"},
)
with urllib.request.urlopen(request, timeout=4) as response:
    assert json.load(response)["status"] == "ok"
' >/dev/null 2>&1; then
    backend_ready=true
    break
  fi
  sleep 1
done
if [ "$backend_ready" != true ]; then
  docker logs "$backend_name"
  exit 1
fi
docker exec "$backend_name" python -c 'from pathlib import Path; p=Path("/tmp/smoke-write"); p.write_text("ok"); p.unlink()'
test "$(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "$backend_name")" = true

docker run --detach --rm \
  --name "$web_name" \
  --network "$network_name" \
  --user 101:101 \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  ramoverde-web:production >/dev/null

web_ready=false
for attempt in $(seq 1 30); do
  if docker exec "$web_name" sh -c 'wget -q -O /dev/null http://127.0.0.1:8080/'; then
    web_ready=true
    break
  fi
  sleep 1
done
if [ "$web_ready" != true ]; then
  docker logs "$web_name"
  exit 1
fi
docker exec "$web_name" sh -c 'touch /tmp/smoke-write && rm /tmp/smoke-write'
test "$(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "$web_name")" = true

echo "Hardened production backend and web containers passed startup, health, and writable-tmp checks."
