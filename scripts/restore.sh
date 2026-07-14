#!/usr/bin/env bash
# Restore from a backup created by scripts/backup.sh
# Usage: ./scripts/restore.sh backups/20260101-120000
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BACKUP_DIR="${1:-}"
if [[ -z "$BACKUP_DIR" || ! -d "$BACKUP_DIR" ]]; then
  echo "Usage: $0 backups/<timestamp>"
  echo "Example: $0 backups/20260101-120000"
  exit 1
fi

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

POSTGRES_USER="${POSTGRES_USER:-agentic_admin}"
POSTGRES_DB="${POSTGRES_DB:-agentic_ai}"

echo "==> Stopping services..."
docker compose down

if [[ -f "${BACKUP_DIR}/data.tar.gz" ]]; then
  echo "==> Restoring data/ from archive..."
  rm -rf data/postgres data/n8n data/redis data/qdrant data/minio
  mkdir -p data/postgres data/n8n data/redis data/qdrant data/minio
  tar -xzf "${BACKUP_DIR}/data.tar.gz"
fi

echo "==> Starting PostgreSQL..."
docker compose up -d postgres
sleep 5

if [[ -f "${BACKUP_DIR}/agentic_ai.sql" ]]; then
  echo "==> Restoring PostgreSQL dump..."
  docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    < "${BACKUP_DIR}/agentic_ai.sql"
fi

if [[ -f "${BACKUP_DIR}/workflows-n8n.tar.gz" ]]; then
  echo "==> Restoring workflows/n8n/..."
  mkdir -p workflows/n8n
  tar -xzf "${BACKUP_DIR}/workflows-n8n.tar.gz"
fi

echo "==> Starting all services..."
docker compose up -d

echo "==> Restore complete from ${BACKUP_DIR}"
