#!/usr/bin/env bash
# Phase 1 infrastructure smoke test for Agentic AI Enterprise Lab
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

POSTGRES_USER="${POSTGRES_USER:-agentic_admin}"
POSTGRES_DB="${POSTGRES_DB:-agentic_ai}"
REDIS_PASSWORD="${REDIS_PASSWORD:-change_me_redis}"
N8N_PORT="${N8N_PORT:-5678}"
QDRANT_PORT="${QDRANT_PORT:-6333}"
MINIO_API_PORT="${MINIO_API_PORT:-9000}"
PGADMIN_PORT="${PGADMIN_PORT:-5050}"
N8N_DB_NAME="${N8N_DB_NAME:-agentic_ai}"

PASS=0
FAIL=0
WARN=0

ok() {
  echo "  OK   $1"
  PASS=$((PASS + 1))
}

bad() {
  echo "  FAIL $1"
  FAIL=$((FAIL + 1))
}

warn() {
  echo "  WARN $1"
  WARN=$((WARN + 1))
}

check_url() {
  local name="$1"
  local url="$2"
  if curl -sf --max-time 5 "$url" >/dev/null; then
    ok "$name ($url)"
  else
    bad "$name ($url)"
  fi
}

echo "==> Agentic AI Enterprise Lab — Phase 1 Test"
echo

echo "==> 1. Container status"
REQUIRED_SERVICES=(postgres redis qdrant minio n8n pgadmin)
for svc in "${REQUIRED_SERVICES[@]}"; do
  status="$(docker compose ps --status running --format '{{.Service}}' 2>/dev/null | grep -x "$svc" || true)"
  if [[ -n "$status" ]]; then
    ok "container running: $svc"
  else
    bad "container running: $svc"
  fi
done

if docker compose ps -a --format '{{.Service}} {{.Status}}' 2>/dev/null | grep -q '^minio-init .*Exited (0)'; then
  ok "minio-init completed (Exited 0)"
elif docker compose ps -a --format '{{.Service}}' 2>/dev/null | grep -q '^minio-init$'; then
  warn "minio-init present but not Exited (0) — run: docker compose up minio-init"
else
  warn "minio-init not found — documents bucket may be missing"
fi

echo
echo "==> 2. Health endpoints (localhost)"
check_url "n8n" "http://localhost:${N8N_PORT}/"
check_url "Qdrant" "http://localhost:${QDRANT_PORT}/readyz"
check_url "MinIO API" "http://localhost:${MINIO_API_PORT}/minio/health/live"
check_url "pgAdmin" "http://localhost:${PGADMIN_PORT}/misc/ping"

echo
echo "==> 3. Redis"
if docker compose exec -T redis redis-cli -a "$REDIS_PASSWORD" ping 2>/dev/null | grep -q PONG; then
  ok "Redis PONG"
else
  bad "Redis PONG"
fi

echo
echo "==> 4. PostgreSQL"
if docker compose exec -T postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then
  ok "PostgreSQL pg_isready ($POSTGRES_DB)"
else
  bad "PostgreSQL pg_isready ($POSTGRES_DB)"
fi

echo
echo "==> 5. n8n PostgreSQL tables (not SQLite)"
TABLE_COUNT="$(docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -A -c \
  "SELECT COUNT(*) FROM information_schema.tables
   WHERE table_schema='public'
   AND table_name IN ('workflow_entity','credentials_entity','execution_entity');" 2>/dev/null | tr -d '[:space:]' || echo "0")"

if [[ "$TABLE_COUNT" == "3" ]]; then
  ok "n8n core tables present (workflow_entity, credentials_entity, execution_entity)"
else
  bad "n8n core tables — expected 3, found ${TABLE_COUNT:-0}"
fi

if [[ "$N8N_DB_NAME" == "agentic_ai" ]]; then
  ok "N8N_DB_NAME=agentic_ai"
else
  warn "N8N_DB_NAME=${N8N_DB_NAME} (expected agentic_ai)"
fi

echo
echo "==> 6. Data persistence folders"
DATA_DIRS=(data/postgres/pgdata data/redis data/qdrant data/minio data/n8n)
for dir in "${DATA_DIRS[@]}"; do
  if [[ -d "$dir" ]] && [[ -n "$(ls -A "$dir" 2>/dev/null)" ]]; then
    ok "data persisted: $dir"
  else
    warn "data empty or missing: $dir"
  fi
done

echo
echo "==> 7. Internal Docker networking"
if docker compose exec -T pgadmin getent hosts postgres >/dev/null 2>&1; then
  ok "pgadmin resolves postgres"
else
  bad "pgadmin resolves postgres"
fi

if docker compose exec -T n8n nslookup redis >/dev/null 2>&1; then
  ok "n8n resolves redis"
else
  bad "n8n resolves redis"
fi

echo
echo "==> Summary"
echo "  Passed:   $PASS"
echo "  Failed:   $FAIL"
echo "  Warnings: $WARN"
echo

if [[ "$FAIL" -eq 0 ]]; then
  echo "Phase 1 automated tests PASSED."
  echo
  echo "Manual checks still recommended:"
  echo "  - n8n: create a workflow, restart n8n, confirm it persists"
  echo "  - pgAdmin: connect with host 'postgres', password from POSTGRES_PASSWORD"
  echo "  - MinIO console: http://localhost:9001 — confirm 'documents' bucket"
  exit 0
fi

echo "Phase 1 automated tests FAILED. Review output above."
echo "Logs: docker compose logs <service>"
exit 1
