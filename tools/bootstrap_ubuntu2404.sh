#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/bootstrap_common.sh"

SCRIPT_NAME="$(basename "$0")"

DEFAULT_REPO_URL="git@github.com:muhammadheidari0/mdr-system.git"
DEFAULT_REF="v3.2.0"
DEFAULT_APP_DIR="/opt/mdr_app"
DEFAULT_DATA_ROOT="/opt/mdr_data"
DEFAULT_ADMIN_FULL_NAME="System Administrator"

REPO_URL="$DEFAULT_REPO_URL"
REF="$DEFAULT_REF"
APP_DIR="$DEFAULT_APP_DIR"
DATA_ROOT="$DEFAULT_DATA_ROOT"
DOMAIN=""
ADMIN_EMAIL=""
ADMIN_PASSWORD=""
ADMIN_FULL_NAME="$DEFAULT_ADMIN_FULL_NAME"
POSTGRES_PASSWORD=""
SECRET_KEY=""

DATA_ROOT_EXPLICIT=0
ADMIN_FULL_NAME_EXPLICIT=0
POSTGRES_PASSWORD_EXPLICIT=0
SKIP_UFW=0
EXISTING_REPO=0
DRY_RUN=0
RESET_DB=0
DOCKER_GROUP_CHANGED=0
DOCKER_USE_SUDO=0

usage() {
  cat <<'EOF'
Bootstrap MDR stack on a vanilla Ubuntu Server 24.04 LTS host.

Usage:
  tools/bootstrap_ubuntu2404.sh [options]

Options:
  --repo-url <url>            Git repository URL (default: git@github.com:muhammadheidari0/mdr-system.git)
  --ref <ref>                 Git ref to deploy (default pinned tag: v3.2.0)
  --app-dir <path>            Application path on server (default: /opt/mdr_app)
  --data-root <path>          Data root path (default: /opt/mdr_data)
  --domain <domain>           MDR domain (required before deploy)
  --admin-email <email>       Admin email (required before deploy)
  --admin-password <value>    Admin password (required before deploy)
  --admin-full-name <value>   Admin full name (default: System Administrator)
  --postgres-password <value> PostgreSQL password (required before deploy)
  --secret-key <value>        App secret key (required before deploy)
  --skip-ufw                  Skip UFW hardening
  --existing-repo             Use existing git repo in --app-dir instead of clone
  --reset-db                  Drop compose volumes and purge postgres data directory
  --dry-run                   Print commands without changing system state
  -h, --help                  Show this help

Example:
  tools/bootstrap_ubuntu2404.sh \
    --domain esms.example.com \
    --admin-email admin@esms.example.com \
    --admin-password 'CHANGE_ME' \
    --postgres-password 'CHANGE_ME' \
    --secret-key 'CHANGE_ME_LONG_RANDOM_SECRET'
EOF
}

run_compose() {
  if [[ "$DOCKER_USE_SUDO" -eq 1 ]]; then
    run_in_app sudo docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml "$@"
  else
    run_in_app docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml "$@"
  fi
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --repo-url)
        REPO_URL="${2:-}"; shift 2 ;;
      --ref)
        REF="${2:-}"; shift 2 ;;
      --app-dir)
        APP_DIR="${2:-}"; shift 2 ;;
      --data-root)
        DATA_ROOT="${2:-}"; DATA_ROOT_EXPLICIT=1; shift 2 ;;
      --domain)
        DOMAIN="${2:-}"; shift 2 ;;
      --admin-email)
        ADMIN_EMAIL="${2:-}"; shift 2 ;;
      --admin-password)
        ADMIN_PASSWORD="${2:-}"; shift 2 ;;
      --admin-full-name)
        ADMIN_FULL_NAME="${2:-}"; ADMIN_FULL_NAME_EXPLICIT=1; shift 2 ;;
      --postgres-password)
        POSTGRES_PASSWORD="${2:-}"; POSTGRES_PASSWORD_EXPLICIT=1; shift 2 ;;
      --secret-key)
        SECRET_KEY="${2:-}"; shift 2 ;;
      --skip-ufw)
        SKIP_UFW=1; shift ;;
      --existing-repo)
        EXISTING_REPO=1; shift ;;
      --reset-db)
        RESET_DB=1; shift ;;
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

install_prerequisites() {
  log_info "Installing host prerequisites and Docker..."

  run_sudo apt-get update
  run_sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ca-certificates curl gnupg lsb-release git openssh-client ufw jq

  run_sudo install -m 0755 -d /etc/apt/keyrings
  if [[ "$DRY_RUN" -eq 1 || ! -f /etc/apt/keyrings/docker.gpg ]]; then
    run_sudo_shell "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg"
  fi
  run_sudo chmod a+r /etc/apt/keyrings/docker.gpg

  local arch codename docker_list_line
  arch="$(dpkg --print-architecture)"
  codename="$(. /etc/os-release && echo "${VERSION_CODENAME}")"
  docker_list_line="deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${codename} stable"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    run_sudo_shell "echo '${docker_list_line}' > /etc/apt/sources.list.d/docker.list"
  else
    if [[ ! -f /etc/apt/sources.list.d/docker.list ]] || ! grep -Fqx "$docker_list_line" /etc/apt/sources.list.d/docker.list; then
      printf '%s\n' "$docker_list_line" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
    fi
  fi

  run_sudo apt-get update
  run_sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

  run_sudo systemctl enable --now docker

  if ! id -nG "$USER" | tr ' ' '\n' | grep -qx docker; then
    run_sudo usermod -aG docker "$USER"
    DOCKER_GROUP_CHANGED=1
  fi
}

prepare_paths() {
  log_info "Preparing filesystem paths..."
  run_sudo mkdir -p "$APP_DIR"

  if [[ "$DATA_ROOT_EXPLICIT" -eq 0 ]]; then
    local existing_env="${APP_DIR}/.env"
    local existing_root
    existing_root="$(env_get MDR_DATA_ROOT "$existing_env")"
    if [[ -n "$existing_root" ]]; then
      DATA_ROOT="$existing_root"
    fi
  fi

  run_sudo mkdir -p \
    "$DATA_ROOT/postgres" \
    "$DATA_ROOT/database" \
    "$DATA_ROOT/data_store" \
    "$DATA_ROOT/archive_storage" \
    "$DATA_ROOT/logs" \
    "$DATA_ROOT/backups"
  run_sudo chown -R "$USER:$USER" "$APP_DIR" "$DATA_ROOT"
}

fetch_code() {
  log_info "Preparing application repository..."
  if [[ "$EXISTING_REPO" -eq 1 ]]; then
    [[ -d "$APP_DIR/.git" ]] || die "--existing-repo set but $APP_DIR is not a git repository."
  else
    if [[ -d "$APP_DIR/.git" ]]; then
      log_info "Git repository already exists at $APP_DIR."
    else
      if [[ -d "$APP_DIR" ]] && [[ -n "$(ls -A "$APP_DIR" 2>/dev/null)" ]]; then
        die "$APP_DIR is not empty and not a git repo. Use --existing-repo or clean the directory."
      fi
      run git clone "$REPO_URL" "$APP_DIR"
    fi
  fi

  run_in_app git fetch origin --tags --prune

  if [[ "$DRY_RUN" -eq 1 ]]; then
    run_in_app git checkout --detach "$REF"
    return 0
  fi

  if git -C "$APP_DIR" rev-parse -q --verify "refs/tags/$REF" >/dev/null; then
    run_in_app git checkout --detach "$REF"
  elif git -C "$APP_DIR" show-ref --verify --quiet "refs/remotes/origin/$REF"; then
    run_in_app git checkout --detach "origin/$REF"
  elif git -C "$APP_DIR" rev-parse -q --verify "$REF^{commit}" >/dev/null; then
    run_in_app git checkout --detach "$REF"
  else
    die "Ref not found: $REF"
  fi

  local commit_hash
  commit_hash="$(git -C "$APP_DIR" rev-parse HEAD)"
  log_info "Checked out commit: $commit_hash"
}

prepare_env_file() {
  local env_file="${APP_DIR}/.env"
  local template_file="${APP_DIR}/.env.production.example"
  local env_created=0

  if [[ ! -f "$env_file" ]]; then
    [[ -f "$template_file" ]] || die "Missing template file: $template_file"
    run cp "$template_file" "$env_file"
    env_created=1
  fi

  if [[ -n "$DOMAIN" ]]; then
    DOMAIN="$(normalize_mdr_domain "$DOMAIN")"
    env_set MDR_DOMAIN "$DOMAIN" "$env_file"
  else
    local existing_domain normalized_existing_domain
    existing_domain="$(env_get MDR_DOMAIN "$env_file")"
    normalized_existing_domain="$(normalize_mdr_domain "$existing_domain")"
    if [[ -n "$normalized_existing_domain" && "$normalized_existing_domain" != "$existing_domain" ]]; then
      env_set MDR_DOMAIN "$normalized_existing_domain" "$env_file"
    fi
  fi
  if [[ "$DATA_ROOT_EXPLICIT" -eq 1 ]]; then env_set MDR_DATA_ROOT "$DATA_ROOT" "$env_file"; fi
  if [[ -n "$ADMIN_EMAIL" ]]; then env_set ADMIN_EMAIL "$ADMIN_EMAIL" "$env_file"; fi
  if [[ -n "$ADMIN_PASSWORD" ]]; then env_set ADMIN_PASSWORD "$ADMIN_PASSWORD" "$env_file"; fi
  if [[ "$ADMIN_FULL_NAME_EXPLICIT" -eq 1 ]]; then env_set ADMIN_FULL_NAME "$ADMIN_FULL_NAME" "$env_file"; fi
  if [[ -n "$SECRET_KEY" ]]; then env_set SECRET_KEY "$SECRET_KEY" "$env_file"; fi

  if [[ "$POSTGRES_PASSWORD_EXPLICIT" -eq 1 ]]; then
    env_set POSTGRES_PASSWORD "$POSTGRES_PASSWORD" "$env_file"
    local pg_user pg_db pg_password_encoded db_url
    pg_user="$(env_get POSTGRES_USER "$env_file")"
    pg_db="$(env_get POSTGRES_DB "$env_file")"
    [[ -n "$pg_user" ]] || pg_user="mdr"
    [[ -n "$pg_db" ]] || pg_db="mdr_app"
    pg_password_encoded="$(url_encode "$POSTGRES_PASSWORD")"
    db_url="postgresql+psycopg://${pg_user}:${pg_password_encoded}@postgres:5432/${pg_db}"
    env_set DATABASE_URL "$db_url" "$env_file"
    env_set COMPOSE_DATABASE_URL "$db_url" "$env_file"
  fi

  env_set STORAGE_ALLOWED_ROOTS "/app/archive_storage,/app/data_store" "$env_file"
  env_set STORAGE_REQUIRE_ABSOLUTE_PATHS "true" "$env_file"
  env_set STORAGE_VALIDATE_WRITABLE_ON_SAVE "true" "$env_file"
  env_set CADDYFILE_PATH "./docker/Caddyfile.generated" "$env_file"

  if [[ "$env_created" -eq 1 && "$DRY_RUN" -eq 0 ]]; then
    log_info "Created ${env_file} from template."
  fi
}

reset_database_if_requested() {
  local pg_data_dir="${DATA_ROOT}/postgres"
  if [[ "$RESET_DB" -ne 1 ]]; then
    return 0
  fi

  log_warn "--reset-db enabled: removing compose volumes and purging ${pg_data_dir}"
  run_compose down -v --remove-orphans
  run_sudo mkdir -p "$pg_data_dir"
  run_sudo find "$pg_data_dir" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  run_sudo chown -R "$USER:$USER" "$pg_data_dir"
}

apply_firewall() {
  if [[ "$SKIP_UFW" -eq 1 ]]; then
    log_info "Skipping UFW changes (--skip-ufw)."
    return 0
  fi

  log_info "Applying UFW hardening..."
  run_sudo ufw --force default deny incoming
  run_sudo ufw --force default allow outgoing
  run_sudo ufw allow OpenSSH
  run_sudo ufw allow 80/tcp
  run_sudo ufw allow 443/tcp
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

deploy_stack() {
  local first_run=0
  local existing_names=""
  if [[ "$DRY_RUN" -eq 1 ]]; then
    first_run=1
  else
    if [[ "$DOCKER_USE_SUDO" -eq 1 ]]; then
      existing_names="$(run_in_app sudo docker ps -a --format '{{.Names}}' || true)"
    else
      existing_names="$(run_in_app docker ps -a --format '{{.Names}}' || true)"
    fi
    if ! printf '%s\n' "$existing_names" | grep -Eq '^(mdr_postgres|mdr_app|mdr_worker|mdr_caddy)$'; then
      first_run=1
    fi
  fi

  log_info "Deploying containers..."
  run_compose config
  run_compose up -d --build
  run_compose ps

  if [[ "$first_run" -eq 1 ]]; then
    run_compose logs --tail=120 web || true
    run_compose logs --tail=120 worker || true
    run_compose logs --tail=120 caddy || true
  fi
}

print_next_steps() {
  log_info "Bootstrap completed."
  if [[ "$DOCKER_GROUP_CHANGED" -eq 1 ]]; then
    log_warn "Docker group membership changed. Re-login is required for non-sudo docker commands."
  fi
  log_info "Admin account has been synced during bootstrap."
}

main() {
  parse_args "$@"
  validate_runtime
  prepare_paths
  install_prerequisites
  configure_docker_access
  fetch_code
  prepare_env_file
  validate_env "${APP_DIR}/.env"
  render_caddyfile_runtime "${APP_DIR}/.env"
  reset_database_if_requested
  apply_firewall
  postgres_preflight "${APP_DIR}/.env"
  deploy_stack
  post_deploy_checks "${APP_DIR}/.env"
  sync_admin_account "${APP_DIR}/.env"
  print_next_steps
}

main "$@"
