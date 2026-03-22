#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/bootstrap_common.sh"

DEFAULT_APP_DIR="/opt/mdr_app"
DEFAULT_DATA_ROOT="/opt/mdr_data"
DEFAULT_ADMIN_FULL_NAME="System Administrator"

APP_DIR="$DEFAULT_APP_DIR"
DATA_ROOT="$DEFAULT_DATA_ROOT"
PACKAGE_DIR=""
DOMAIN=""
TLS_MODE=""
TLS_CERT_SOURCE=""
TLS_KEY_SOURCE=""
ADMIN_EMAIL=""
ADMIN_PASSWORD_FILE=""
POSTGRES_PASSWORD_FILE=""
SECRET_KEY_FILE=""
ADMIN_FULL_NAME="$DEFAULT_ADMIN_FULL_NAME"
SKIP_UFW=0
DRY_RUN=0
DOCKER_USE_SUDO=0
ALLOW_PUBLIC_ACME=0
RESET_DB=0
RENDER_CADDY_TLS_MODE=1
LOCAL_HEALTH_URL="http://127.0.0.1:8000/api/v1/health"

RELEASE_DIR=""
IMAGES_DIR=""
MANIFEST_FILE=""
CHECKSUM_FILE=""
COMPOSE_FILE_NAME="docker-compose.offline.yml"

APP_VERSION=""
APP_IMAGE=""
POSTGRES_IMAGE=""
CADDY_IMAGE=""
DEFAULT_TLS_MODE="http"
ADMIN_PASSWORD=""
POSTGRES_PASSWORD=""
SECRET_KEY=""

usage() {
  cat <<'EOF'
Install MDR from an offline package on Ubuntu Server 24.04 with Docker already installed.

Usage:
  tools/bootstrap_offline.sh --package-dir <path> --domain <domain-or-ip> --admin-email <email> \
    --admin-password-file <path> --postgres-password-file <path> --secret-key-file <path> [options]

Options:
  --package-dir <path>         Offline installer root directory (contains bundle/, checksums.txt, release_manifest.env)
  --app-dir <path>             Application path on server (default: /opt/mdr_app)
  --data-root <path>           Data root path (default: /opt/mdr_data)
  --domain <domain-or-ip>      MDR public domain or IPv4
  --tls-mode <mode>            One of: http, internal, custom, public (default: manifest DEFAULT_TLS_MODE)
  --tls-cert-file <path>       Custom TLS certificate path (required for --tls-mode custom)
  --tls-key-file <path>        Custom TLS key path (required for --tls-mode custom)
  --admin-email <email>        Admin email
  --admin-password-file <path> File containing admin password
  --postgres-password-file <path> File containing PostgreSQL password
  --secret-key-file <path>     File containing app secret key
  --admin-full-name <value>    Admin full name (default: System Administrator)
  --allow-public-acme          Allow public ACME mode for internet-connected DNS
  --skip-ufw                   Skip UFW hardening
  --dry-run                    Print commands without changing system state
  -h, --help                   Show this help
EOF
}

run_docker() {
  if [[ "$DOCKER_USE_SUDO" -eq 1 ]]; then
    run sudo docker "$@"
  else
    run docker "$@"
  fi
}

run_compose() {
  if [[ "$DOCKER_USE_SUDO" -eq 1 ]]; then
    run_in_app sudo docker compose -f "$COMPOSE_FILE_NAME" "$@"
  else
    run_in_app docker compose -f "$COMPOSE_FILE_NAME" "$@"
  fi
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --package-dir)
        PACKAGE_DIR="${2:-}"; shift 2 ;;
      --app-dir)
        APP_DIR="${2:-}"; shift 2 ;;
      --data-root)
        DATA_ROOT="${2:-}"; shift 2 ;;
      --domain)
        DOMAIN="${2:-}"; shift 2 ;;
      --tls-mode)
        TLS_MODE="${2:-}"; shift 2 ;;
      --tls-cert-file)
        TLS_CERT_SOURCE="${2:-}"; shift 2 ;;
      --tls-key-file)
        TLS_KEY_SOURCE="${2:-}"; shift 2 ;;
      --admin-email)
        ADMIN_EMAIL="${2:-}"; shift 2 ;;
      --admin-password-file)
        ADMIN_PASSWORD_FILE="${2:-}"; shift 2 ;;
      --postgres-password-file)
        POSTGRES_PASSWORD_FILE="${2:-}"; shift 2 ;;
      --secret-key-file)
        SECRET_KEY_FILE="${2:-}"; shift 2 ;;
      --admin-full-name)
        ADMIN_FULL_NAME="${2:-}"; shift 2 ;;
      --allow-public-acme)
        ALLOW_PUBLIC_ACME=1; shift ;;
      --skip-ufw)
        SKIP_UFW=1; shift ;;
      --dry-run)
        DRY_RUN=1; shift ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "Unknown argument: $1 (use --help)"
        ;;
    esac
  done
}

require_runtime_cmds() {
  require_cmd tar
  require_cmd sha256sum
  require_cmd curl
  require_cmd sed
  require_cmd docker
}

discover_package_paths() {
  if [[ -z "$PACKAGE_DIR" ]]; then
    PACKAGE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
  else
    PACKAGE_DIR="$(cd "$PACKAGE_DIR" && pwd)"
  fi

  RELEASE_DIR="${PACKAGE_DIR}/bundle/release"
  IMAGES_DIR="${PACKAGE_DIR}/bundle/images"
  MANIFEST_FILE="${PACKAGE_DIR}/release_manifest.env"
  CHECKSUM_FILE="${PACKAGE_DIR}/checksums.txt"
}

validate_package_layout() {
  [[ -d "$PACKAGE_DIR" ]] || die "Package directory not found: $PACKAGE_DIR"
  [[ -f "$MANIFEST_FILE" ]] || die "Missing package manifest: $MANIFEST_FILE"
  [[ -f "$CHECKSUM_FILE" ]] || die "Missing package checksums: $CHECKSUM_FILE"
  [[ -d "$RELEASE_DIR" ]] || die "Missing package release directory: $RELEASE_DIR"
  [[ -d "$IMAGES_DIR" ]] || die "Missing package images directory: $IMAGES_DIR"
  [[ -f "${RELEASE_DIR}/.env.production.example" ]] || die "Missing .env.production.example in release bundle."
  [[ -f "${RELEASE_DIR}/tools/render_caddyfile.sh" ]] || die "Missing render_caddyfile.sh in release bundle."
  [[ -f "${RELEASE_DIR}/tools/lib/bootstrap_common.sh" ]] || die "Missing shared bootstrap library in release bundle."
  [[ -f "${RELEASE_DIR}/${COMPOSE_FILE_NAME}" ]] || die "Missing ${COMPOSE_FILE_NAME} in release bundle."
}

verify_checksums() {
  log_info "Verifying package checksums..."
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log_info "[dry-run] (cd ${PACKAGE_DIR} && sha256sum -c checksums.txt)"
    return 0
  fi
  (
    cd "$PACKAGE_DIR"
    sha256sum -c checksums.txt
  )
}

load_release_manifest() {
  # shellcheck disable=SC1090
  source "$MANIFEST_FILE"
  [[ -n "${APP_VERSION:-}" ]] || die "APP_VERSION missing in release manifest."
  [[ -n "${APP_IMAGE:-}" ]] || die "APP_IMAGE missing in release manifest."
  [[ -n "${POSTGRES_IMAGE:-}" ]] || die "POSTGRES_IMAGE missing in release manifest."
  [[ -n "${CADDY_IMAGE:-}" ]] || die "CADDY_IMAGE missing in release manifest."
  [[ -n "${COMPOSE_FILE:-}" ]] || die "COMPOSE_FILE missing in release manifest."
  COMPOSE_FILE_NAME="$COMPOSE_FILE"
  DEFAULT_TLS_MODE="${DEFAULT_TLS_MODE:-http}"
}

read_secret_file() {
  local path="$1"
  [[ -f "$path" ]] || die "Secret file not found: $path"
  local value
  value="$(<"$path")"
  value="${value%$'\r'}"
  printf '%s' "$value"
}

validate_inputs() {
  DOMAIN="$(normalize_mdr_domain "$DOMAIN")"
  [[ -n "$DOMAIN" ]] || die "--domain is required."
  [[ -n "$ADMIN_EMAIL" ]] || die "--admin-email is required."
  [[ -n "$ADMIN_PASSWORD_FILE" ]] || die "--admin-password-file is required."
  [[ -n "$POSTGRES_PASSWORD_FILE" ]] || die "--postgres-password-file is required."
  [[ -n "$SECRET_KEY_FILE" ]] || die "--secret-key-file is required."

  ADMIN_PASSWORD="$(read_secret_file "$ADMIN_PASSWORD_FILE")"
  POSTGRES_PASSWORD="$(read_secret_file "$POSTGRES_PASSWORD_FILE")"
  SECRET_KEY="$(read_secret_file "$SECRET_KEY_FILE")"
  [[ -n "$ADMIN_PASSWORD" ]] || die "Admin password file is empty."
  [[ -n "$POSTGRES_PASSWORD" ]] || die "PostgreSQL password file is empty."
  [[ -n "$SECRET_KEY" ]] || die "Secret key file is empty."

  if [[ -z "$TLS_MODE" ]]; then
    TLS_MODE="$DEFAULT_TLS_MODE"
  fi

  case "$TLS_MODE" in
    http|internal|custom|public)
      ;;
    *)
      die "Unsupported TLS mode: $TLS_MODE"
      ;;
  esac

  if is_ipv4_address "$DOMAIN" && [[ "$TLS_MODE" != "http" ]]; then
    die "IPv4 deployments only support --tls-mode http."
  fi

  if [[ "$TLS_MODE" == "public" && "$ALLOW_PUBLIC_ACME" -ne 1 ]]; then
    die "--tls-mode public requires --allow-public-acme."
  fi

  if [[ "$TLS_MODE" == "custom" ]]; then
    [[ -f "$TLS_CERT_SOURCE" ]] || die "--tls-cert-file is required for custom TLS mode."
    [[ -f "$TLS_KEY_SOURCE" ]] || die "--tls-key-file is required for custom TLS mode."
  fi
}

validate_compose_runtime() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log_info "[dry-run] docker compose version"
    return 0
  fi
  if docker compose version >/dev/null 2>&1; then
    return 0
  fi
  if sudo docker compose version >/dev/null 2>&1; then
    DOCKER_USE_SUDO=1
    return 0
  fi
  die "docker compose plugin is not available."
}

prepare_paths() {
  log_info "Preparing filesystem paths..."
  run_sudo mkdir -p "$APP_DIR"
  run_sudo mkdir -p \
    "$DATA_ROOT/postgres" \
    "$DATA_ROOT/database" \
    "$DATA_ROOT/data_store" \
    "$DATA_ROOT/archive_storage" \
    "$DATA_ROOT/logs" \
    "$DATA_ROOT/backups"
  run_sudo chown -R "$USER:$USER" "$APP_DIR" "$DATA_ROOT"
}

copy_release_runtime() {
  log_info "Copying offline runtime bundle into $APP_DIR..."
  run cp -R "${RELEASE_DIR}/." "$APP_DIR/"
}

prepare_env_file_offline() {
  local env_file="${APP_DIR}/.env"
  local template_file="${APP_DIR}/.env.production.example"
  local pg_user pg_db db_url

  if [[ ! -f "$env_file" ]]; then
    run cp "$template_file" "$env_file"
  fi

  pg_user="$(env_get POSTGRES_USER "$env_file")"
  pg_db="$(env_get POSTGRES_DB "$env_file")"
  [[ -n "$pg_user" ]] || pg_user="mdr"
  [[ -n "$pg_db" ]] || pg_db="mdr_app"
  db_url="postgresql+psycopg://${pg_user}:${POSTGRES_PASSWORD}@postgres:5432/${pg_db}"

  env_set MDR_DOMAIN "$DOMAIN" "$env_file"
  env_set MDR_DATA_ROOT "$DATA_ROOT" "$env_file"
  env_set POSTGRES_PASSWORD "$POSTGRES_PASSWORD" "$env_file"
  env_set DATABASE_URL "$db_url" "$env_file"
  env_set COMPOSE_DATABASE_URL "$db_url" "$env_file"
  env_set SECRET_KEY "$SECRET_KEY" "$env_file"
  env_set ADMIN_EMAIL "$ADMIN_EMAIL" "$env_file"
  env_set ADMIN_PASSWORD "$ADMIN_PASSWORD" "$env_file"
  env_set ADMIN_FULL_NAME "$ADMIN_FULL_NAME" "$env_file"
  env_set APP_VERSION "$APP_VERSION" "$env_file"
  env_set APP_IMAGE "$APP_IMAGE" "$env_file"
  env_set POSTGRES_IMAGE "$POSTGRES_IMAGE" "$env_file"
  env_set CADDY_IMAGE "$CADDY_IMAGE" "$env_file"
  env_set CADDY_TLS_MODE "$TLS_MODE" "$env_file"
  env_set CADDYFILE_PATH "./docker/Caddyfile.generated" "$env_file"
  env_set STORAGE_ALLOWED_ROOTS "/app/archive_storage,/app/data_store" "$env_file"
  env_set STORAGE_REQUIRE_ABSOLUTE_PATHS "true" "$env_file"
  env_set STORAGE_VALIDATE_WRITABLE_ON_SAVE "true" "$env_file"
  env_set CADDY_HTTP_PORT_BIND "80:80" "$env_file"

  if [[ "$TLS_MODE" == "http" ]]; then
    env_set CADDY_HTTPS_PORT_BIND "127.0.0.1:8443:443" "$env_file"
    env_set TLS_CERT_FILE "" "$env_file"
    env_set TLS_KEY_FILE "" "$env_file"
  elif [[ "$TLS_MODE" == "custom" ]]; then
    env_set CADDY_HTTPS_PORT_BIND "443:443" "$env_file"
    env_set TLS_CERT_FILE "/opt/mdr_app/docker/certs/server.crt" "$env_file"
    env_set TLS_KEY_FILE "/opt/mdr_app/docker/certs/server.key" "$env_file"
  else
    env_set CADDY_HTTPS_PORT_BIND "443:443" "$env_file"
    env_set TLS_CERT_FILE "" "$env_file"
    env_set TLS_KEY_FILE "" "$env_file"
  fi
}

configure_custom_tls_assets() {
  if [[ "$TLS_MODE" != "custom" ]]; then
    return 0
  fi

  local cert_dir="${APP_DIR}/docker/certs"
  run mkdir -p "$cert_dir"
  run cp "$TLS_CERT_SOURCE" "${cert_dir}/server.crt"
  run cp "$TLS_KEY_SOURCE" "${cert_dir}/server.key"
  run chmod 0644 "${cert_dir}/server.crt"
  run chmod 0600 "${cert_dir}/server.key"
}

load_image_archives() {
  log_info "Loading Docker images from offline package..."
  local archive found
  found=0
  for archive in "${IMAGES_DIR}"/*.tar; do
    [[ -e "$archive" ]] || continue
    found=1
    run_docker load -i "$archive"
  done
  [[ "$found" -eq 1 ]] || die "No image archives found in ${IMAGES_DIR}."

  if [[ "$DRY_RUN" -eq 1 ]]; then
    return 0
  fi

  local image
  for image in "$APP_IMAGE" "$POSTGRES_IMAGE" "$CADDY_IMAGE"; do
    if [[ "$DOCKER_USE_SUDO" -eq 1 ]]; then
      sudo docker image inspect "$image" >/dev/null 2>&1 || die "Required image tag not loaded: $image"
    else
      docker image inspect "$image" >/dev/null 2>&1 || die "Required image tag not loaded: $image"
    fi
  done
}

apply_firewall_offline() {
  if [[ "$SKIP_UFW" -eq 1 ]]; then
    log_info "Skipping UFW changes (--skip-ufw)."
    return 0
  fi
  if ! command -v ufw >/dev/null 2>&1; then
    log_warn "ufw is not installed; skipping firewall configuration."
    return 0
  fi

  log_info "Applying offline UFW hardening..."
  run_sudo ufw --force default deny incoming
  run_sudo ufw --force default allow outgoing
  run_sudo ufw allow OpenSSH
  run_sudo ufw allow 80/tcp
  if [[ "$TLS_MODE" == "http" ]]; then
    run_sudo ufw deny 443/tcp
  else
    run_sudo ufw allow 443/tcp
  fi
  run_sudo ufw deny 8000/tcp
  run_sudo ufw deny 5432/tcp

  if [[ "$DRY_RUN" -eq 0 ]]; then
    if sudo ufw status | head -n1 | grep -qi "inactive"; then
      run_sudo ufw --force enable
    fi
  else
    log_info "[dry-run] would enable UFW if inactive."
  fi

  run_sudo ufw status verbose
}

deploy_stack_offline() {
  log_info "Deploying offline stack..."
  run_compose config
  run_compose up -d --no-build
  run_compose ps
}

print_summary() {
  local public_url
  public_url="$(public_health_url_for_mode "$DOMAIN" "$TLS_MODE")"
  log_info "Offline bootstrap completed."
  log_info "Version: ${APP_VERSION}"
  log_info "TLS mode: ${TLS_MODE}"
  log_info "Application path: ${APP_DIR}"
  log_info "Data root: ${DATA_ROOT}"
  log_info "Health URL: ${public_url}"
  if [[ "$TLS_MODE" == "internal" ]]; then
    log_warn "Clients must trust the Caddy internal CA before HTTPS health checks will succeed without warnings."
  elif [[ "$TLS_MODE" == "custom" ]]; then
    log_warn "Clients must trust the provided internal certificate chain before HTTPS health checks will succeed without warnings."
  fi
}

main() {
  parse_args "$@"
  discover_package_paths
  validate_runtime
  require_runtime_cmds
  validate_package_layout
  verify_checksums
  load_release_manifest
  validate_inputs
  configure_docker_access
  validate_compose_runtime
  prepare_paths
  copy_release_runtime
  prepare_env_file_offline
  configure_custom_tls_assets
  validate_env "${APP_DIR}/.env"
  render_caddyfile_runtime "${APP_DIR}/.env"
  load_image_archives
  apply_firewall_offline
  postgres_preflight "${APP_DIR}/.env"
  deploy_stack_offline
  post_deploy_checks "${APP_DIR}/.env"
  sync_admin_account "${APP_DIR}/.env"
  print_summary
}

main "$@"
