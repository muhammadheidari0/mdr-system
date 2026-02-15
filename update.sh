#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.windows.prod.yml)
DB_CONTAINER="${DB_CONTAINER:-mdr_postgres}"
POSTGRES_USER="${POSTGRES_USER:-mdr}"
POSTGRES_DB="${POSTGRES_DB:-mdr_app}"
MDR_DATA_ROOT="${MDR_DATA_ROOT:-/opt/mdr_data}"
BACKUP_DIR="${BACKUP_DIR:-$MDR_DATA_ROOT/backups}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/api/v1/health}"

usage() {
  cat <<'EOF'
Usage:
  ./update.sh <tag>

Example:
  ./update.sh v3.1.1

Behavior:
  1) Fetch tags from origin
  2) Backup PostgreSQL (if DB container is running)
  3) Checkout requested tag (detached)
  4) Rebuild and start stack with Docker Compose
  5) Run local health check
EOF
}

run_compose() {
  docker compose "${COMPOSE_FILES[@]}" "$@"
}

if [[ "${1:-}" == "" ]] || [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
  usage
  exit 1
fi

TAG="$1"

echo "[update] project dir: $PROJECT_DIR"
echo "[update] target tag : $TAG"

echo "[update] fetching tags from origin..."
git fetch origin --tags --prune

if ! git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  echo "[error] tag not found: $TAG"
  exit 2
fi

mkdir -p "$BACKUP_DIR"
TIMESTAMP="$(date +%F_%H%M%S)"
BACKUP_FILE="$BACKUP_DIR/pre_${TAG}_${TIMESTAMP}.dump"

if docker ps --format '{{.Names}}' | grep -qx "$DB_CONTAINER"; then
  echo "[update] creating backup: $BACKUP_FILE"
  docker exec -t "$DB_CONTAINER" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "$BACKUP_FILE"
else
  echo "[warn] DB container '$DB_CONTAINER' not running. Backup skipped."
fi

echo "[update] checking out tag $TAG (detached HEAD)..."
git checkout --detach "$TAG"

echo "[update] rebuilding and starting stack..."
run_compose up -d --build

echo "[update] compose status:"
run_compose ps

if command -v curl >/dev/null 2>&1; then
  echo "[update] running health check: $HEALTH_URL"
  curl -fsS "$HEALTH_URL" >/dev/null
  echo "[update] health check: OK"
else
  echo "[warn] curl not found. Health check skipped."
fi

echo "[done] update completed successfully for tag $TAG"
