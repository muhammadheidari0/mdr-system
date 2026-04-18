#!/usr/bin/env bash
set -euo pipefail

log_info() { printf '[INFO] %s\n' "$*"; }
log_warn() { printf '[WARN] %s\n' "$*" >&2; }
log_error() { printf '[ERROR] %s\n' "$*" >&2; }

die() {
  local code=1
  if [[ $# -gt 1 && "$1" =~ ^[0-9]+$ ]]; then
    code="$1"
    shift
  fi
  log_error "$*"
  exit "$code"
}

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || die "Missing required command: $cmd"
}

run() {
  if [[ "${DRY_RUN:-0}" -eq 1 ]]; then
    log_info "[dry-run] $*"
    return 0
  fi
  "$@"
}

run_sudo() {
  if [[ "${DRY_RUN:-0}" -eq 1 ]]; then
    log_info "[dry-run] sudo $*"
    return 0
  fi
  sudo "$@"
}

run_sudo_shell() {
  local cmd="$1"
  if [[ "${DRY_RUN:-0}" -eq 1 ]]; then
    log_info "[dry-run] sudo bash -lc \"$cmd\""
    return 0
  fi
  sudo bash -lc "$cmd"
}

run_in_app() {
  local -a cmd=("$@")
  if [[ "${DRY_RUN:-0}" -eq 1 ]]; then
    log_info "[dry-run] (cd ${APP_DIR} && ${cmd[*]})"
    return 0
  fi
  (cd "$APP_DIR" && "${cmd[@]}")
}

validate_runtime() {
  [[ "${EUID}" -eq 0 ]] && die "Run as a non-root sudo-enabled user."
  require_cmd sudo

  [[ -r /etc/os-release ]] || die "Cannot read /etc/os-release."
  # shellcheck disable=SC1091
  source /etc/os-release
  [[ "${ID:-}" == "ubuntu" ]] || die "This script only supports Ubuntu."
  [[ "${VERSION_ID:-}" == "24.04" ]] || die "This script requires Ubuntu 24.04 LTS."

  if [[ "${DRY_RUN:-0}" -eq 0 ]]; then
    sudo -v >/dev/null 2>&1 || die "Sudo validation failed."
  fi
}

configure_docker_access() {
  if [[ "${DRY_RUN:-0}" -eq 1 ]]; then
    DOCKER_USE_SUDO=0
    return 0
  fi

  if docker info >/dev/null 2>&1; then
    DOCKER_USE_SUDO=0
    return 0
  fi

  if sudo docker info >/dev/null 2>&1; then
    DOCKER_USE_SUDO=1
    log_warn "Docker requires sudo in this session. Re-login later to use docker without sudo."
    return 0
  fi

  die "Docker daemon is not reachable (neither docker nor sudo docker works)."
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
    line="${line%$'\r'}"
    if [[ "$line" == "${key}="* ]]; then
      printf '%s' "${line#*=}"
      return 0
    fi
  done < "$file"
  printf ''
}

env_set() {
  local key="$1"
  local value="$2"
  local file="$3"

  if [[ "${DRY_RUN:-0}" -eq 1 ]]; then
    log_info "[dry-run] update .env key: $key"
    return 0
  fi

  local tmp found line
  tmp="$(mktemp)"
  found=0

  if [[ -f "$file" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
      line="${line%$'\r'}"
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

trim_text() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

url_encode() {
  local value="$1"
  python3 - "$value" <<'PY'
import sys
from urllib.parse import quote

print(quote(sys.argv[1], safe=""), end="")
PY
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

public_health_url_for_mode() {
  local normalized tls_mode
  normalized="$(normalize_mdr_domain "$1")"
  tls_mode="$(trim_text "${2:-}")"
  if [[ -z "$normalized" ]]; then
    printf ''
    return 0
  fi

  case "$tls_mode" in
    http)
      printf 'http://%s/api/v1/health' "$normalized"
      ;;
    internal|custom|public)
      printf 'https://%s/api/v1/health' "$normalized"
      ;;
    *)
      if is_ipv4_address "$normalized"; then
        printf 'http://%s/api/v1/health' "$normalized"
      else
        printf 'https://%s/api/v1/health' "$normalized"
      fi
      ;;
  esac
}

is_placeholder_value() {
  local key="$1"
  local value
  value="$(trim_text "${2:-}")"

  [[ -z "$value" ]] && return 0

  case "$key" in
    MDR_DOMAIN)
      [[ "$value" == "esms.example.com" || "$value" == *"your-domain"* ]] && return 0
      ;;
    ADMIN_EMAIL)
      [[ "$value" == "admin@your-domain.com" || "$value" == "admin@example.com" ]] && return 0
      ;;
    SECRET_KEY)
      [[ "$value" == "change-me-in-production" || "$value" == "change-me" || "$value" == "CHANGE_ME_LONG_RANDOM_SECRET" ]] && return 0
      ;;
    ADMIN_PASSWORD|POSTGRES_PASSWORD)
      [[ "$value" == "CHANGE_ME" || "$value" == *"CHANGE_ME"* ]] && return 0
      ;;
    DATABASE_URL|COMPOSE_DATABASE_URL)
      [[ "$value" == *"CHANGE_ME"* ]] && return 0
      ;;
  esac

  return 1
}

validate_env() {
  local env_file="${1:-${APP_DIR}/.env}"
  local -a required_keys missing
  required_keys=(
    MDR_DOMAIN
    MDR_DATA_ROOT
    POSTGRES_PASSWORD
    DATABASE_URL
    COMPOSE_DATABASE_URL
    SECRET_KEY
    ADMIN_EMAIL
    ADMIN_PASSWORD
    ADMIN_FULL_NAME
  )
  missing=()

  local key value
  for key in "${required_keys[@]}"; do
    value="$(env_get "$key" "$env_file")"
    if is_placeholder_value "$key" "$value"; then
      missing+=("$key")
    fi
  done

  local domain_value normalized_domain
  domain_value="$(env_get MDR_DOMAIN "$env_file")"
  normalized_domain="$(normalize_mdr_domain "$domain_value")"
  if [[ -z "$normalized_domain" ]]; then
    missing+=("MDR_DOMAIN (invalid)")
  fi

  local database_url compose_database_url
  database_url="$(env_get DATABASE_URL "$env_file")"
  compose_database_url="$(env_get COMPOSE_DATABASE_URL "$env_file")"
  if [[ -n "$database_url" && -n "$compose_database_url" && "$database_url" != "$compose_database_url" ]]; then
    missing+=("COMPOSE_DATABASE_URL (must match DATABASE_URL)")
  fi

  if [[ ${#missing[@]} -gt 0 ]]; then
    printf '[ERROR] Missing/placeholder env keys:\n' >&2
    printf '  - %s\n' "${missing[@]}" >&2
    die "Fix .env values before deploy."
  fi

  local admin_password admin_password_bytes
  admin_password="$(env_get ADMIN_PASSWORD "$env_file")"
  admin_password_bytes="$(printf '%s' "$admin_password" | wc -c | tr -d ' ')"
  if [[ "${admin_password_bytes:-0}" -gt 72 ]]; then
    die "ADMIN_PASSWORD exceeds bcrypt 72-byte limit (${admin_password_bytes} bytes)."
  fi
}

render_caddyfile_runtime() {
  local env_file="${1:-${APP_DIR}/.env}"
  local domain_value normalized_domain caddyfile_path output_path tls_mode tls_cert tls_key
  domain_value="$(env_get MDR_DOMAIN "$env_file")"
  normalized_domain="$(normalize_mdr_domain "$domain_value")"
  [[ -n "$normalized_domain" ]] || die "MDR_DOMAIN is required to render Caddyfile."
  env_set MDR_DOMAIN "$normalized_domain" "$env_file"

  caddyfile_path="$(env_get CADDYFILE_PATH "$env_file")"
  [[ -n "$caddyfile_path" ]] || caddyfile_path="./docker/Caddyfile.generated"
  env_set CADDYFILE_PATH "$caddyfile_path" "$env_file"

  if [[ "$caddyfile_path" = /* ]]; then
    output_path="$caddyfile_path"
  else
    output_path="${APP_DIR}/${caddyfile_path#./}"
  fi

  if [[ "${DRY_RUN:-0}" -eq 1 ]]; then
    log_info "[dry-run] would render Caddyfile for ${normalized_domain} -> ${output_path}"
    return 0
  fi

  local -a render_args
  render_args=(bash ./tools/render_caddyfile.sh --domain "$normalized_domain" --output "$output_path")

  if [[ "${RENDER_CADDY_TLS_MODE:-0}" -eq 1 ]]; then
    tls_mode="$(env_get CADDY_TLS_MODE "$env_file")"
    tls_cert="$(env_get TLS_CERT_FILE "$env_file")"
    tls_key="$(env_get TLS_KEY_FILE "$env_file")"
    if [[ -n "$tls_mode" ]]; then
      render_args+=(--tls-mode "$tls_mode")
    fi
    if [[ "$tls_mode" == "custom" ]]; then
      [[ -n "$tls_cert" ]] && render_args+=(--tls-cert-file "$tls_cert")
      [[ -n "$tls_key" ]] && render_args+=(--tls-key-file "$tls_key")
    fi
  fi

  run_in_app "${render_args[@]}"
}

postgres_preflight() {
  local env_file="${1:-${APP_DIR}/.env}"
  local pg_user pg_db pg_password
  pg_user="$(env_get POSTGRES_USER "$env_file")"
  pg_db="$(env_get POSTGRES_DB "$env_file")"
  pg_password="$(env_get POSTGRES_PASSWORD "$env_file")"
  [[ -n "$pg_user" ]] || pg_user="mdr"
  [[ -n "$pg_db" ]] || pg_db="mdr_app"

  log_info "Starting PostgreSQL preflight..."
  run_compose up -d postgres

  if [[ "${DRY_RUN:-0}" -eq 1 ]]; then
    log_info "[dry-run] would wait for pg_isready and verify DB credentials."
    return 0
  fi

  local i
  for i in $(seq 1 40); do
    if run_compose exec -T postgres pg_isready -U "$pg_user" -d "$pg_db" >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done
  if [[ "$i" -eq 40 ]]; then
    die "PostgreSQL did not become ready in time."
  fi

  if run_compose exec -T -e PGPASSWORD="$pg_password" postgres \
    psql -h 127.0.0.1 -U "$pg_user" -d "$pg_db" -c "select 1;" >/dev/null 2>&1; then
    log_info "PostgreSQL credential preflight passed."
    return 0
  fi

  if [[ "${RESET_DB:-0}" -eq 1 ]]; then
    die "PostgreSQL credential preflight failed even with --reset-db; verify POSTGRES_* and .env."
  fi
  die "PostgreSQL auth mismatch detected. Update .env credentials or rerun with --reset-db."
}

post_deploy_checks() {
  local env_file="${1:-${APP_DIR}/.env}"
  local domain_value tls_mode public_url
  domain_value="$(env_get MDR_DOMAIN "$env_file")"
  tls_mode="$(env_get CADDY_TLS_MODE "$env_file")"
  public_url="$(public_health_url_for_mode "$domain_value" "$tls_mode")"

  if [[ "${DRY_RUN:-0}" -eq 1 ]]; then
    log_info "[dry-run] would run health checks for ${LOCAL_HEALTH_URL:-http://127.0.0.1:8000/api/v1/health} and ${public_url}"
    return 0
  fi

  local local_url
  local_url="${LOCAL_HEALTH_URL:-http://127.0.0.1:8000/api/v1/health}"

  log_info "Running local health check..."
  local i
  for i in $(seq 1 30); do
    if curl -fsS "$local_url" >/dev/null 2>&1; then
      log_info "Local health check passed."
      break
    fi
    sleep 2
  done
  if [[ "$i" -eq 30 ]]; then
    die "Local health check failed at $local_url"
  fi

  if [[ -z "$public_url" ]]; then
    log_warn "Public health check skipped because URL is empty."
    return 0
  fi

  if curl -fsS "$public_url" >/dev/null 2>&1; then
    log_info "Public health check passed: ${public_url}"
  else
    log_warn "Public health check failed (warning only): ${public_url}"
  fi
}

sync_admin_account() {
  local env_file="${1:-${APP_DIR}/.env}"
  local admin_email admin_password admin_full_name admin_password_bytes
  admin_email="$(env_get ADMIN_EMAIL "$env_file")"
  admin_password="$(env_get ADMIN_PASSWORD "$env_file")"
  admin_full_name="$(env_get ADMIN_FULL_NAME "$env_file")"
  admin_password_bytes="$(printf '%s' "$admin_password" | wc -c | tr -d ' ')"

  if [[ "${admin_password_bytes:-0}" -gt 72 ]]; then
    die "ADMIN_PASSWORD exceeds bcrypt 72-byte limit (${admin_password_bytes} bytes)."
  fi

  if [[ "${DRY_RUN:-0}" -eq 1 ]]; then
    log_info "[dry-run] would sync admin account via create_admin.py"
    return 0
  fi

  log_info "Syncing admin account..."
  run_compose exec -T \
    -e ADMIN_EMAIL="$admin_email" \
    -e ADMIN_PASSWORD="$admin_password" \
    -e ADMIN_FULL_NAME="$admin_full_name" \
    web python create_admin.py
}
