#!/usr/bin/env bash
# Boot smoke: apply committed migrations to PostgreSQL, start the API and require
# /api/v1/health/ready to report the database as reachable.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${DATABASE_URL:?DATABASE_URL must point at a reachable PostgreSQL database}"
port="${SMOKE_API_PORT:-18010}"
log_file="$(mktemp)"
server_pid=""
cleanup() {
  if [[ -n "$server_pid" ]]; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
  rm -f "$log_file"
}
trap cleanup EXIT

cd "$repo_root/apps/backend"
uv run python manage.py migrate --noinput
uv run python manage.py makemigrations --check --dry-run
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1 uv run python manage.py runserver "127.0.0.1:$port" --noreload \
  >"$log_file" 2>&1 &
server_pid=$!

for _ in $(seq 1 30); do
  if ! kill -0 "$server_pid" 2>/dev/null; then
    echo "API exited before readiness:" >&2
    cat "$log_file" >&2
    exit 1
  fi
  if body="$(curl -fsS "http://127.0.0.1:$port/api/v1/health/ready" 2>/dev/null)"; then
    python3 -c 'import json,sys; assert json.loads(sys.argv[1])["dependencies"]["database"] == "ok"' "$body"
    echo "API readiness returned HTTP 200 with database ok on port $port."
    exit 0
  fi
  sleep 1
done
echo "API did not become ready:" >&2
cat "$log_file" >&2
exit 1
