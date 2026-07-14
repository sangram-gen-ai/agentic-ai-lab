#!/usr/bin/env bash
# Backup PostgreSQL dump + data/ bind-mount directories
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
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="backups/${STAMP}"

mkdir -p "$BACKUP_DIR"

echo "==> Backing up PostgreSQL (${POSTGRES_DB})..."
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  > "${BACKUP_DIR}/agentic_ai.sql"

echo "==> Archiving data/ directories..."
tar -czf "${BACKUP_DIR}/data.tar.gz" data/

if [[ -d workflows/n8n ]] && [[ -n "$(ls -A workflows/n8n 2>/dev/null)" ]]; then
  echo "==> Archiving workflows/n8n/..."
  tar -czf "${BACKUP_DIR}/workflows-n8n.tar.gz" workflows/n8n/
fi

cat > "${BACKUP_DIR}/manifest.txt" <<EOF
backup_date=${STAMP}
postgres_db=${POSTGRES_DB}
postgres_user=${POSTGRES_USER}
files:
  - agentic_ai.sql
  - data.tar.gz
EOF

echo "==> Backup complete: ${BACKUP_DIR}"
