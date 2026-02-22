#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

COMPOSE_BASE_FILE="${COMPOSE_BASE_FILE:-docker-compose.yml}"
COMPOSE_OVERRIDE_FILE="${COMPOSE_OVERRIDE_FILE:-docker-compose.windows.prod.yml}"
COMPOSE_FILES=(-f "$COMPOSE_BASE_FILE")
if [[ -n "$COMPOSE_OVERRIDE_FILE" ]]; then
  COMPOSE_FILES+=(-f "$COMPOSE_OVERRIDE_FILE")
fi
DB_CONTAINER="${DB_CONTAINER:-mdr_postgres}"
POSTGRES_USER="${POSTGRES_USER:-mdr}"
POSTGRES_DB="${POSTGRES_DB:-mdr_app}"
MDR_DATA_ROOT="${MDR_DATA_ROOT:-/opt/mdr_data}"
BACKUP_DIR="${BACKUP_DIR:-$MDR_DATA_ROOT/backups}"
LOCAL_HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/api/v1/health}"
PUBLIC_HEALTH_URL="${PUBLIC_HEALTH_URL:-}"

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
  4) Validate DATABASE_URL/COMPOSE_DATABASE_URL consistency
  5) Render smart Caddyfile (IP -> HTTP, domain -> HTTPS)
  6) Rebuild and start stack with Docker Compose
  7) Run local + public health checks
EOF
}

run_compose() {
  docker compose "${COMPOSE_FILES[@]}" "$@"
}

env_get() {
  local key="$1"
  local file="$2"
  local line=""
  [[ -f "$file" ]] || { printf ''; return 0; }
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == "${key}="* ]]; then
      printf '%s' "${line#*=}"
      return 0
    fi
  done < "$file"
  printf ''
}

trim_text() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

normalize_mdr_domain() {
  local value
  value="$(trim_text "$1")"
  value="${value#http://}"
  value="${value#https://}"
  value="${value%%/*}"
  if [[ "$value" =~ ^[^/:]+:[0-9]+$ ]]; then
    value="${value%%:*}"
  fi
  printf '%s' "$value"
}

is_ipv4_address() {
  local value="$1"
  local a b c d octet
  [[ "$value" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || return 1
  IFS='.' read -r a b c d <<<"$value"
  for octet in "$a" "$b" "$c" "$d"; do
    ((octet >= 0 && octet <= 255)) || return 1
  done
  return 0
}

compute_public_health_url() {
  local domain_value normalized
  domain_value="$1"
  normalized="$(normalize_mdr_domain "$domain_value")"
  if [[ -z "$normalized" ]]; then
    printf ''
    return 0
  fi
  if is_ipv4_address "$normalized"; then
    printf 'http://%s/api/v1/health' "$normalized"
  else
    printf 'https://%s/api/v1/health' "$normalized"
  fi
}

render_caddyfile_if_available() {
  local env_file=".env"
  local domain_value caddyfile_path output_path

  [[ -f "$env_file" ]] || {
    echo "[warn] .env not found; skipping Caddyfile render."
    return 0
  }

  if [[ ! -f tools/render_caddyfile.sh ]]; then
    echo "[warn] tools/render_caddyfile.sh not found; skipping Caddyfile render."
    return 0
  fi

  domain_value="$(normalize_mdr_domain "$(env_get MDR_DOMAIN "$env_file")")"
  if [[ -z "$domain_value" ]]; then
    echo "[warn] MDR_DOMAIN is empty; skipping Caddyfile render."
    return 0
  fi

  caddyfile_path="$(env_get CADDYFILE_PATH "$env_file")"
  [[ -n "$caddyfile_path" ]] || caddyfile_path="./docker/Caddyfile"

  if [[ "$caddyfile_path" = /* ]]; then
    output_path="$caddyfile_path"
  else
    output_path="${PROJECT_DIR}/${caddyfile_path#./}"
  fi

  echo "[update] rendering Caddyfile for ${domain_value} -> ${output_path}"
  bash ./tools/render_caddyfile.sh --domain "$domain_value" --output "$output_path"
}

validate_env_contract() {
  if [[ ! -f .env ]]; then
    echo "[warn] .env not found. Compose may rely on exported environment variables."
    return 0
  fi

  local database_url compose_database_url
  database_url="$(grep -E '^DATABASE_URL=' .env | head -n1 | cut -d= -f2- || true)"
  compose_database_url="$(grep -E '^COMPOSE_DATABASE_URL=' .env | head -n1 | cut -d= -f2- || true)"

  if [[ -z "$compose_database_url" ]]; then
    echo "[warn] COMPOSE_DATABASE_URL is empty or missing in .env."
    echo "[warn] Set COMPOSE_DATABASE_URL equal to DATABASE_URL to avoid DSN mismatch."
    return 0
  fi

  if [[ -n "$database_url" && "$database_url" != "$compose_database_url" ]]; then
    echo "[error] DATABASE_URL and COMPOSE_DATABASE_URL are different."
    echo "[error] DATABASE_URL        = $database_url"
    echo "[error] COMPOSE_DATABASE_URL= $compose_database_url"
    echo "[error] Fix .env and rerun."
    exit 3
  fi
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

echo "[update] validating env contract..."
validate_env_contract

echo "[update] rendering smart Caddyfile..."
render_caddyfile_if_available

echo "[update] rebuilding and starting stack..."
run_compose up -d --build

echo "[update] compose status:"
run_compose ps

if command -v curl >/dev/null 2>&1; then
  echo "[update] running local health check: $LOCAL_HEALTH_URL"
  local_ok=0
  for i in $(seq 1 30); do
    if curl -fsS "$LOCAL_HEALTH_URL" >/dev/null 2>&1; then
      local_ok=1
      break
    fi
    sleep 2
  done
  if [[ "$local_ok" -ne 1 ]]; then
    echo "[error] local health check failed: $LOCAL_HEALTH_URL"
    exit 4
  fi
  echo "[update] local health check: OK"

  if [[ -z "$PUBLIC_HEALTH_URL" && -f .env ]]; then
    PUBLIC_HEALTH_URL="$(compute_public_health_url "$(env_get MDR_DOMAIN .env)")"
  fi

  if [[ -n "$PUBLIC_HEALTH_URL" ]]; then
    echo "[update] running public health check: $PUBLIC_HEALTH_URL"
    if curl -fsS "$PUBLIC_HEALTH_URL" >/dev/null; then
      echo "[update] public health check: OK"
    else
      echo "[warn] public health check failed: $PUBLIC_HEALTH_URL"
    fi
  else
    echo "[warn] PUBLIC_HEALTH_URL is not set and MDR_DOMAIN is empty; public check skipped."
  fi
else
  echo "[warn] curl not found. Health check skipped."
fi

echo "[done] update completed successfully for tag $TAG"
