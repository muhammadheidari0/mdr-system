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
POSTGRES_USER_DEFAULT="${POSTGRES_USER:-mdr}"
POSTGRES_DB_DEFAULT="${POSTGRES_DB:-mdr_app}"
MDR_DATA_ROOT_DEFAULT="${MDR_DATA_ROOT:-/opt/mdr_data}"
BACKUP_DIR="${BACKUP_DIR:-$MDR_DATA_ROOT_DEFAULT/backups}"
SESSION_DIR="${BACKUP_DIR}/update_sessions"
LOCK_FILE="${LOCK_FILE:-/tmp/mdr_update.lock}"
LOCAL_HEALTH_URL="${LOCAL_HEALTH_URL:-${HEALTH_URL:-http://127.0.0.1:8000/api/v1/health}}"

EXIT_TAG_NOT_FOUND=2
EXIT_ENV_INVALID=3
EXIT_HEALTH_FAIL=4
EXIT_DOCKER_PERMISSION=5
EXIT_DISK_GUARD=6
EXIT_ROLLBACK_FAILED=7

MIN_FREE_GB=10
DRY_RUN=0
AUTO_ROLLBACK=1
USE_LATEST=0
ROLLBACK_MODE=0
TARGET_TAG=""
ROLLBACK_SESSION_ID=""

DOCKER_CMD=(docker)
DOCKER_USING_SUDO=0
MDR_DOMAIN_NORMALIZED=""
PUBLIC_HEALTH_URL=""
PUBLIC_HEALTH_URL_OVERRIDE="${PUBLIC_HEALTH_URL:-}"

SESSION_ID=""
SESSION_FILE=""
PREVIOUS_COMMIT=""
BACKUP_FILE=""
ROLLBACK_ELIGIBLE=0
ROLLBACK_DONE=0
IN_ERR_TRAP=0

usage() {
  cat <<'EOF'
Usage:
  ./update.sh <tag> [--min-free-gb <N>] [--dry-run] [--no-auto-rollback]
  ./update.sh --latest [--min-free-gb <N>] [--dry-run] [--no-auto-rollback]
  ./update.sh --rollback [--session-id <id>] [--dry-run]

Options:
  --latest                Deploy latest semantic tag (v*)
  --rollback              Roll back code + DB to previous deployed session
  --session-id <id>       Roll back using explicit session id (default: last deployed session)
  --min-free-gb <N>       Minimum required free space in GB for guard (default: 10)
  --dry-run               Print commands without mutating system
  --no-auto-rollback      Disable automatic rollback on failed deploy (default: enabled)
  -h, --help              Show this help

Exit codes:
  2 tag not found
  3 env contract invalid
  4 local health failed
  5 docker permission failed
  6 disk guard failed
  7 rollback failed
EOF
}

log_info() { printf '[update] %s\n' "$*"; }
log_warn() { printf '[warn] %s\n' "$*" >&2; }
log_error() { printf '[error] %s\n' "$*" >&2; }

die() {
  local code="$1"
  shift
  log_error "$*"
  exit "$code"
}

print_dry_run() {
  local out=""
  local part=""
  for part in "$@"; do
    out+="$(printf '%q ' "$part")"
  done
  log_info "[dry-run] ${out% }"
}

run_cmd() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    print_dry_run "$@"
    return 0
  fi
  "$@"
}

run_compose() {
  run_cmd "${DOCKER_CMD[@]}" compose "${COMPOSE_FILES[@]}" "$@"
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
  local normalized
  normalized="$(normalize_mdr_domain "$1")"
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

env_get() {
  local key="$1"
  local file="$2"
  local line=""
  [[ -f "$file" ]] || {
    printf ''
    return 0
  }
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == "${key}="* ]]; then
      printf '%s' "${line#*=}"
      return 0
    fi
  done < "$file"
  printf ''
}

env_set_file() {
  local file="$1"
  local key="$2"
  local value="$3"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    log_info "[dry-run] set ${key} in ${file}"
    return 0
  fi

  local tmp line found
  tmp="$(mktemp)"
  found=0

  if [[ -f "$file" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
      if [[ "$line" == "${key}="* ]]; then
        printf '%s=%s\n' "$key" "$value" >> "$tmp"
        found=1
      else
        printf '%s\n' "$line" >> "$tmp"
      fi
    done < "$file"
  fi

  if [[ "$found" -eq 0 ]]; then
    printf '%s=%s\n' "$key" "$value" >> "$tmp"
  fi

  mv "$tmp" "$file"
}

self_chmod_tools() {
  run_cmd chmod +x "$0" || true
  if [[ -d "$PROJECT_DIR/tools" ]]; then
    run_cmd find "$PROJECT_DIR/tools" -maxdepth 1 -type f -name '*.sh' -exec chmod +x {} +
  fi
}

acquire_lock() {
  if ! command -v flock >/dev/null 2>&1; then
    die 1 "flock is required but not found."
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log_info "[dry-run] lock file check: $LOCK_FILE"
    return 0
  fi
  exec 9>"$LOCK_FILE"
  if ! flock -n 9; then
    die 1 "another update/rollback is running (lock: $LOCK_FILE)."
  fi
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --latest)
        USE_LATEST=1
        shift
        ;;
      --rollback)
        ROLLBACK_MODE=1
        shift
        ;;
      --session-id)
        ROLLBACK_SESSION_ID="${2:-}"
        [[ -n "$ROLLBACK_SESSION_ID" ]] || die 1 "--session-id requires a value."
        shift 2
        ;;
      --min-free-gb)
        MIN_FREE_GB="${2:-}"
        shift 2
        ;;
      --dry-run)
        DRY_RUN=1
        shift
        ;;
      --no-auto-rollback)
        AUTO_ROLLBACK=0
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      -*)
        die 1 "unknown option: $1"
        ;;
      *)
        if [[ -n "$TARGET_TAG" ]]; then
          die 1 "multiple tags provided: '$TARGET_TAG' and '$1'"
        fi
        TARGET_TAG="$1"
        shift
        ;;
    esac
  done

  if [[ "$MIN_FREE_GB" =~ [^0-9] ]] || [[ "$MIN_FREE_GB" -le 0 ]]; then
    die 1 "--min-free-gb must be a positive integer."
  fi

  if [[ "$ROLLBACK_MODE" -eq 1 ]]; then
    if [[ -n "$TARGET_TAG" || "$USE_LATEST" -eq 1 ]]; then
      die 1 "--rollback cannot be combined with tag or --latest."
    fi
    return 0
  fi

  if [[ "$USE_LATEST" -eq 1 && -n "$TARGET_TAG" ]]; then
    die 1 "use either <tag> or --latest, not both."
  fi

  if [[ "$USE_LATEST" -eq 0 && -z "$TARGET_TAG" ]]; then
    usage
    exit 1
  fi
}

configure_docker_cmd() {
  if ! command -v docker >/dev/null 2>&1; then
    die "$EXIT_DOCKER_PERMISSION" "docker command not found."
  fi

  if docker info >/dev/null 2>&1; then
    DOCKER_CMD=(docker)
    return 0
  fi

  if command -v sudo >/dev/null 2>&1 && sudo -n docker info >/dev/null 2>&1; then
    DOCKER_CMD=(sudo docker)
    DOCKER_USING_SUDO=1
    log_warn "docker requires sudo in this session. add user to docker group and relog for passwordless docker."
    return 0
  fi

  die "$EXIT_DOCKER_PERMISSION" "docker daemon not reachable. add user to docker group, relog, then retry."
}

resolve_existing_path() {
  local probe="$1"
  while [[ ! -e "$probe" && "$probe" != "/" ]]; do
    probe="$(dirname "$probe")"
  done
  printf '%s' "$probe"
}

check_disk_guard() {
  local min_bytes
  min_bytes=$((MIN_FREE_GB * 1024 * 1024 * 1024))
  local candidate resolved available

  for candidate in "$PROJECT_DIR" "/var/lib/docker"; do
    resolved="$(resolve_existing_path "$candidate")"
    available="$(df -PB1 "$resolved" | awk 'NR==2{print $4}')"
    if [[ -z "$available" ]]; then
      die "$EXIT_DISK_GUARD" "failed to inspect free disk for $resolved."
    fi
    if (( available < min_bytes )); then
      die "$EXIT_DISK_GUARD" "disk guard failed for $resolved (need >= ${MIN_FREE_GB}GB). cleanup using docker image prune/system df."
    fi
  done
}

validate_env_contract() {
  local env_file="$PROJECT_DIR/.env"
  if [[ ! -f "$env_file" ]]; then
    die "$EXIT_ENV_INVALID" ".env is required."
  fi

  local key value
  local required_keys=(
    MDR_DOMAIN
    DATABASE_URL
    COMPOSE_DATABASE_URL
    POSTGRES_DB
    POSTGRES_USER
    POSTGRES_PASSWORD
  )

  for key in "${required_keys[@]}"; do
    value="$(env_get "$key" "$env_file")"
    if [[ -z "$(trim_text "$value")" ]]; then
      die "$EXIT_ENV_INVALID" "missing required .env key: $key"
    fi
  done

  local database_url compose_database_url
  database_url="$(env_get DATABASE_URL "$env_file")"
  compose_database_url="$(env_get COMPOSE_DATABASE_URL "$env_file")"
  if [[ "$database_url" != "$compose_database_url" ]]; then
    die "$EXIT_ENV_INVALID" "DATABASE_URL and COMPOSE_DATABASE_URL must match."
  fi

  MDR_DOMAIN_NORMALIZED="$(normalize_mdr_domain "$(env_get MDR_DOMAIN "$env_file")")"
  if [[ -z "$MDR_DOMAIN_NORMALIZED" ]]; then
    die "$EXIT_ENV_INVALID" "MDR_DOMAIN is invalid."
  fi

  if [[ -n "$PUBLIC_HEALTH_URL_OVERRIDE" ]]; then
    PUBLIC_HEALTH_URL="$PUBLIC_HEALTH_URL_OVERRIDE"
  else
    PUBLIC_HEALTH_URL="$(compute_public_health_url "$MDR_DOMAIN_NORMALIZED")"
  fi
}

resolve_target_tag() {
  if [[ "$USE_LATEST" -eq 1 ]]; then
    TARGET_TAG="$(git tag --list 'v*' --sort=-version:refname | head -n1)"
    if [[ -z "$TARGET_TAG" ]]; then
      die "$EXIT_TAG_NOT_FOUND" "no semantic tag (v*) found."
    fi
  fi

  if ! git rev-parse -q --verify "refs/tags/$TARGET_TAG" >/dev/null; then
    die "$EXIT_TAG_NOT_FOUND" "tag not found: $TARGET_TAG"
  fi
}

session_set() {
  local key="$1"
  local value="$2"
  [[ -n "$SESSION_FILE" ]] || return 0
  env_set_file "$SESSION_FILE" "$key" "$value"
}

create_update_session() {
  local timestamp
  timestamp="$(date +%Y%m%d_%H%M%S)"
  SESSION_ID="${timestamp}"
  SESSION_FILE="${SESSION_DIR}/${SESSION_ID}.env"

  run_cmd mkdir -p "$BACKUP_DIR" "$SESSION_DIR"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    : > "$SESSION_FILE"
  fi

  PREVIOUS_COMMIT="$(git rev-parse HEAD)"
  BACKUP_FILE="${BACKUP_DIR}/pre_${TARGET_TAG}_${timestamp}.dump"

  session_set session_id "$SESSION_ID"
  session_set mode "update"
  session_set started_at "$(date -u +%FT%TZ)"
  session_set requested_tag "$TARGET_TAG"
  session_set previous_commit "$PREVIOUS_COMMIT"
  session_set backup_file "$BACKUP_FILE"
  session_set auto_rollback "$AUTO_ROLLBACK"
  session_set status "started"
}

ensure_db_running_for_backup() {
  if "${DOCKER_CMD[@]}" ps --format '{{.Names}}' | grep -qx "$DB_CONTAINER"; then
    return 0
  fi
  log_warn "DB container '$DB_CONTAINER' is not running, starting postgres service before backup."
  run_compose up -d postgres
}

backup_database_or_fail() {
  ensure_db_running_for_backup
  local env_file="$PROJECT_DIR/.env"
  local pg_user pg_db
  pg_user="$(env_get POSTGRES_USER "$env_file")"
  pg_db="$(env_get POSTGRES_DB "$env_file")"
  [[ -n "$pg_user" ]] || pg_user="$POSTGRES_USER_DEFAULT"
  [[ -n "$pg_db" ]] || pg_db="$POSTGRES_DB_DEFAULT"

  log_info "creating backup: $BACKUP_FILE"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    print_dry_run "${DOCKER_CMD[@]}" exec -t "$DB_CONTAINER" pg_dump -U "$pg_user" -d "$pg_db" -Fc ">" "$BACKUP_FILE"
    return 0
  fi

  "${DOCKER_CMD[@]}" exec -t "$DB_CONTAINER" pg_dump -U "$pg_user" -d "$pg_db" -Fc > "$BACKUP_FILE"
  if [[ ! -s "$BACKUP_FILE" ]]; then
    die 1 "database backup failed or produced empty dump: $BACKUP_FILE"
  fi
}

auto_stash_local_changes() {
  local message
  message="update-v2-${SESSION_ID}-to-${TARGET_TAG}"
  log_info "auto-stashing local changes (stash kept for audit)..."

  if [[ "$DRY_RUN" -eq 1 ]]; then
    log_info "[dry-run] git stash push -u -m '$message' -- . ':(exclude).env'"
    session_set stash_message "$message"
    return 0
  fi

  if ! git stash push -u -m "$message" -- . ':(exclude).env' >/dev/null 2>&1; then
    die 1 "auto-stash failed. resolve repository state manually."
  fi
  session_set stash_message "$message"
}

force_checkout_tag() {
  log_info "checking out tag $TARGET_TAG in detached mode (force)..."
  run_cmd git checkout -f --detach "$TARGET_TAG"
  session_set deployed_tag "$TARGET_TAG"
  session_set deployed_commit "$(git rev-parse HEAD)"
}

render_caddyfile_required() {
  local renderer="$PROJECT_DIR/tools/render_caddyfile.sh"
  if [[ ! -f "$renderer" ]]; then
    die "$EXIT_ENV_INVALID" "tools/render_caddyfile.sh not found."
  fi

  local env_file="$PROJECT_DIR/.env"
  local caddyfile_path output_path
  caddyfile_path="$(env_get CADDYFILE_PATH "$env_file")"
  [[ -n "$caddyfile_path" ]] || caddyfile_path="./docker/Caddyfile"

  if [[ "$caddyfile_path" = /* ]]; then
    output_path="$caddyfile_path"
  else
    output_path="${PROJECT_DIR}/${caddyfile_path#./}"
  fi

  log_info "rendering smart Caddyfile..."
  run_cmd bash "$renderer" --domain "$MDR_DOMAIN_NORMALIZED" --output "$output_path"
}

compose_up_build() {
  log_info "rebuilding and starting stack..."
  run_compose up -d --build
  run_compose ps
}

local_health_check() {
  local i
  for i in $(seq 1 30); do
    if curl -fsS "$LOCAL_HEALTH_URL" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

local_health_check_or_fail() {
  if ! command -v curl >/dev/null 2>&1; then
    die "$EXIT_HEALTH_FAIL" "curl not found; cannot run local health check."
  fi
  log_info "running local health check: $LOCAL_HEALTH_URL"
  if local_health_check; then
    log_info "local health check: OK"
    return 0
  fi
  die "$EXIT_HEALTH_FAIL" "local health check failed: $LOCAL_HEALTH_URL"
}

public_health_check_warn_only() {
  if [[ -z "$PUBLIC_HEALTH_URL" ]]; then
    log_warn "public health URL is empty; skipped."
    return 0
  fi
  log_info "running public health check: $PUBLIC_HEALTH_URL"
  if curl -fsS "$PUBLIC_HEALTH_URL" >/dev/null 2>&1; then
    log_info "public health check: OK"
  else
    log_warn "public health check failed (warning only): $PUBLIC_HEALTH_URL"
  fi
}

rollback_restore_database() {
  local backup_file="$1"
  local env_file="$PROJECT_DIR/.env"
  local pg_user pg_db pg_password
  pg_user="$(env_get POSTGRES_USER "$env_file")"
  pg_db="$(env_get POSTGRES_DB "$env_file")"
  pg_password="$(env_get POSTGRES_PASSWORD "$env_file")"
  [[ -n "$pg_user" ]] || pg_user="$POSTGRES_USER_DEFAULT"
  [[ -n "$pg_db" ]] || pg_db="$POSTGRES_DB_DEFAULT"

  run_compose up -d postgres

  if [[ "$DRY_RUN" -eq 1 ]]; then
    log_info "[dry-run] wait for pg_isready and restore $backup_file"
    return 0
  fi

  local i
  for i in $(seq 1 30); do
    if run_compose exec -T postgres pg_isready -U "$pg_user" -d "$pg_db" >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done

  if [[ "$i" -eq 30 ]]; then
    return 1
  fi

  if ! run_compose exec -T -e PGPASSWORD="$pg_password" postgres \
    psql -h 127.0.0.1 -U "$pg_user" -d "$pg_db" -c "select 1;" >/dev/null 2>&1; then
    return 1
  fi

  cat "$backup_file" | "${DOCKER_CMD[@]}" exec -i "$DB_CONTAINER" \
    pg_restore -U "$pg_user" -d "$pg_db" --clean --if-exists --no-owner --no-privileges
}

rollback_from_session_file() {
  local session_file="$1"
  local rollback_source="$2"
  local previous_commit backup_file deployed_tag

  previous_commit="$(env_get previous_commit "$session_file")"
  backup_file="$(env_get backup_file "$session_file")"
  deployed_tag="$(env_get deployed_tag "$session_file")"

  if [[ -z "$previous_commit" || -z "$backup_file" ]]; then
    log_error "rollback metadata is incomplete in $session_file"
    return 1
  fi
  if [[ "$DRY_RUN" -eq 0 && ! -f "$backup_file" ]]; then
    log_error "backup file not found for rollback: $backup_file"
    return 1
  fi

  log_warn "starting ${rollback_source} rollback from session $(basename "$session_file" .env)..."
  run_cmd git checkout -f --detach "$previous_commit"
  render_caddyfile_required

  if ! rollback_restore_database "$backup_file"; then
    log_error "database restore failed during rollback."
    return 1
  fi

  compose_up_build
  if ! local_health_check; then
    log_error "local health failed after rollback rebuild."
    return 1
  fi

  env_set_file "$session_file" rollback_status "success"
  env_set_file "$session_file" rollback_at "$(date -u +%FT%TZ)"
  env_set_file "$session_file" status "rolled_back"
  env_set_file "$session_file" rollback_source "$rollback_source"
  if [[ -n "$deployed_tag" ]]; then
    env_set_file "$session_file" rolled_back_from_tag "$deployed_tag"
  fi
  log_warn "rollback completed successfully."
  return 0
}

find_last_deployed_session() {
  local file status
  [[ -d "$SESSION_DIR" ]] || return 1
  while IFS= read -r file; do
    status="$(env_get status "$file")"
    if [[ "$status" == "deployed" ]]; then
      printf '%s' "$file"
      return 0
    fi
  done < <(ls -1t "$SESSION_DIR"/*.env 2>/dev/null || true)
  return 1
}

run_manual_rollback_flow() {
  local session_file
  if [[ -n "$ROLLBACK_SESSION_ID" ]]; then
    session_file="$SESSION_DIR/${ROLLBACK_SESSION_ID}.env"
    [[ -f "$session_file" ]] || die "$EXIT_ROLLBACK_FAILED" "session id not found: $ROLLBACK_SESSION_ID"
  else
    if ! session_file="$(find_last_deployed_session)"; then
      die "$EXIT_ROLLBACK_FAILED" "no deployed session found for rollback."
    fi
  fi

  validate_env_contract
  if rollback_from_session_file "$session_file" "manual"; then
    log_info "manual rollback completed."
  else
    die "$EXIT_ROLLBACK_FAILED" "manual rollback failed."
  fi
}

on_error_trap() {
  local exit_code="$?"
  if [[ "$IN_ERR_TRAP" -eq 1 ]]; then
    exit "$exit_code"
  fi
  IN_ERR_TRAP=1

  if [[ "$ROLLBACK_MODE" -eq 0 && "$AUTO_ROLLBACK" -eq 1 && "$ROLLBACK_ELIGIBLE" -eq 1 && "$ROLLBACK_DONE" -eq 0 ]]; then
    log_error "update failed; attempting auto rollback..."
    ROLLBACK_DONE=1
    if rollback_from_session_file "$SESSION_FILE" "auto"; then
      session_set rollback_status "success"
      log_warn "auto rollback succeeded. inspect logs and fix issue before next update."
      exit "$exit_code"
    fi
    session_set rollback_status "failed"
    log_error "auto rollback failed."
    exit "$EXIT_ROLLBACK_FAILED"
  fi

  if [[ "$ROLLBACK_MODE" -eq 0 && -n "$SESSION_FILE" ]]; then
    session_set status "failed"
    session_set failed_at "$(date -u +%FT%TZ)"
  fi

  exit "$exit_code"
}

run_update_flow() {
  log_info "project dir: $PROJECT_DIR"
  if [[ "$USE_LATEST" -eq 1 ]]; then
    log_info "target tag : --latest"
  else
    log_info "target tag : $TARGET_TAG"
  fi

  log_info "fetching tags from origin..."
  run_cmd git fetch origin --tags --prune
  resolve_target_tag
  log_info "resolved tag: $TARGET_TAG"

  validate_env_contract
  check_disk_guard
  create_update_session
  backup_database_or_fail
  auto_stash_local_changes

  ROLLBACK_ELIGIBLE=1
  force_checkout_tag
  render_caddyfile_required
  compose_up_build
  local_health_check_or_fail
  public_health_check_warn_only

  session_set status "deployed"
  session_set deployed_at "$(date -u +%FT%TZ)"
  session_set local_health "ok"
  session_set public_health_url "$PUBLIC_HEALTH_URL"
  log_info "update completed successfully for tag $TARGET_TAG"
}

main() {
  parse_args "$@"
  self_chmod_tools
  acquire_lock
  configure_docker_cmd
  trap on_error_trap ERR

  if [[ "$ROLLBACK_MODE" -eq 1 ]]; then
    run_manual_rollback_flow
  else
    run_update_flow
  fi
}

main "$@"
