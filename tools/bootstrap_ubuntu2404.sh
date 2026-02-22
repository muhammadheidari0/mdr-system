#!/usr/bin/env bash
set -euo pipefail

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


log_info() { printf '[INFO] %s\n' "$*"; }
log_warn() { printf '[WARN] %s\n' "$*" >&2; }
log_error() { printf '[ERROR] %s\n' "$*" >&2; }

die() {
  log_error "$*"
  exit 1
}

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || die "Missing required command: $cmd"
}

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log_info "[dry-run] $*"
    return 0
  fi
  "$@"
}

run_sudo() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log_info "[dry-run] sudo $*"
    return 0
  fi
  sudo "$@"
}

run_sudo_shell() {
  local cmd="$1"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log_info "[dry-run] sudo bash -lc \"$cmd\""
    return 0
  fi
  sudo bash -lc "$cmd"
}

run_in_app() {
  local -a cmd=("$@")
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log_info "[dry-run] (cd $APP_DIR && ${cmd[*]})"
    return 0
  fi
  (cd "$APP_DIR" && "${cmd[@]}")
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
        usage; exit 0 ;;
      *)
        die "Unknown argument: $1 (use --help)"
        ;;
    esac
  done
}

validate_runtime() {
  [[ "$EUID" -eq 0 ]] && die "Run as a non-root sudo-enabled user."
  require_cmd sudo

  [[ -r /etc/os-release ]] || die "Cannot read /etc/os-release."
  # shellcheck disable=SC1091
  source /etc/os-release
  [[ "${ID:-}" == "ubuntu" ]] || die "This script only supports Ubuntu."
  [[ "${VERSION_ID:-}" == "24.04" ]] || die "This script requires Ubuntu 24.04 LTS."

  if [[ "$DRY_RUN" -eq 0 ]]; then
    sudo -v >/dev/null 2>&1 || die "Sudo validation failed."
  fi
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

configure_docker_access() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
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
  [[ -f "$file" ]] || { printf ''; return 0; }
  while IFS= read -r line || [[ -n "$line" ]]; do
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

  if [[ "$DRY_RUN" -eq 1 ]]; then
    log_info "[dry-run] update .env key: $key"
    return 0
  fi

  local tmp found line
  tmp="$(mktemp)"
  found=0

  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == "${key}="* ]]; then
      printf '%s=%s\n' "$key" "$value" >> "$tmp"
      found=1
    else
      printf '%s\n' "$line" >> "$tmp"
    fi
  done < "$file"

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

public_health_url() {
  local domain_value normalized
  domain_value="$1"
  normalized="$(normalize_mdr_domain "$domain_value")"
  if is_ipv4_address "$normalized"; then
    printf 'http://%s/api/v1/health' "$normalized"
  else
    printf 'https://%s/api/v1/health' "$normalized"
  fi
}

is_placeholder_value() {
  local key="$1"
  local value="$2"
  local v
  v="$(printf '%s' "$value" | tr -d '\r\n')"

  [[ -z "$v" ]] && return 0
  [[ "$v" == \<* ]] && return 0

  case "$v" in
    CHANGE_ME*|change_me*|change-me*|REPLACE_ME*)
      return 0
      ;;
  esac

  case "$key" in
    MDR_DOMAIN)
      [[ "$v" == "esms.example.com" || "$v" == *"your-domain"* ]] && return 0
      ;;
    ADMIN_EMAIL)
      [[ "$v" == "admin@your-domain.com" || "$v" == "admin@example.com" ]] && return 0
      ;;
    SECRET_KEY)
      [[ "$v" == "change-me-in-production" || "$v" == "change-me" ]] && return 0
      ;;
    DATABASE_URL|COMPOSE_DATABASE_URL)
      [[ "$v" == *"CHANGE_ME"* ]] && return 0
      ;;
  esac

  return 1
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
    local pg_user pg_db db_url
    pg_user="$(env_get POSTGRES_USER "$env_file")"
    pg_db="$(env_get POSTGRES_DB "$env_file")"
    [[ -n "$pg_user" ]] || pg_user="mdr"
    [[ -n "$pg_db" ]] || pg_db="mdr_app"
    db_url="postgresql+psycopg://${pg_user}:${POSTGRES_PASSWORD}@postgres:5432/${pg_db}"
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

validate_env() {
  local env_file="${APP_DIR}/.env"
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
  local env_file="${APP_DIR}/.env"
  local domain_value normalized_domain caddyfile_path output_path
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

  if [[ "$DRY_RUN" -eq 1 ]]; then
    log_info "[dry-run] would render Caddyfile for ${normalized_domain} -> ${output_path}"
    return 0
  fi

  run_in_app bash ./tools/render_caddyfile.sh --domain "$normalized_domain" --output "$output_path"
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

postgres_preflight() {
  local env_file="${APP_DIR}/.env"
  local pg_user pg_db pg_password
  pg_user="$(env_get POSTGRES_USER "$env_file")"
  pg_db="$(env_get POSTGRES_DB "$env_file")"
  pg_password="$(env_get POSTGRES_PASSWORD "$env_file")"
  [[ -n "$pg_user" ]] || pg_user="mdr"
  [[ -n "$pg_db" ]] || pg_db="mdr_app"

  log_info "Starting PostgreSQL preflight..."
  run_compose up -d postgres

  if [[ "$DRY_RUN" -eq 1 ]]; then
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

  if [[ "$RESET_DB" -eq 1 ]]; then
    die "PostgreSQL credential preflight failed even with --reset-db; verify POSTGRES_* and .env."
  fi
  die "PostgreSQL auth mismatch detected. Update .env credentials or rerun with --reset-db."
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

post_deploy_checks() {
  local env_file="${APP_DIR}/.env"
  local domain_value public_url
  domain_value="$(env_get MDR_DOMAIN "$env_file")"
  public_url="$(public_health_url "$domain_value")"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    log_info "[dry-run] would run health checks for local and ${public_url}"
    return 0
  fi

  log_info "Running local health check..."
  local i
  for i in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:8000/api/v1/health" >/dev/null 2>&1; then
      log_info "Local health check passed."
      break
    fi
    sleep 2
  done
  if [[ "$i" -eq 30 ]]; then
    die "Local health check failed at http://127.0.0.1:8000/api/v1/health"
  fi

  if curl -fsS "$public_url" >/dev/null 2>&1; then
    log_info "Public health check passed: ${public_url}"
  else
    log_warn "Public health check failed (DNS/TLS/network may still be propagating): ${public_url}"
  fi
}

sync_admin_account() {
  local env_file="${APP_DIR}/.env"
  local admin_email admin_password admin_full_name admin_password_bytes
  admin_email="$(env_get ADMIN_EMAIL "$env_file")"
  admin_password="$(env_get ADMIN_PASSWORD "$env_file")"
  admin_full_name="$(env_get ADMIN_FULL_NAME "$env_file")"
  admin_password_bytes="$(printf '%s' "$admin_password" | wc -c | tr -d ' ')"

  if [[ "${admin_password_bytes:-0}" -gt 72 ]]; then
    die "ADMIN_PASSWORD exceeds bcrypt 72-byte limit (${admin_password_bytes} bytes)."
  fi

  if [[ "$DRY_RUN" -eq 1 ]]; then
    log_info "[dry-run] would sync admin account via create_admin.py"
    return 0
  fi

  log_info "Syncing admin account..."
  if [[ "$DOCKER_USE_SUDO" -eq 1 ]]; then
    run_in_app sudo docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml exec -T \
      -e ADMIN_EMAIL="$admin_email" \
      -e ADMIN_PASSWORD="$admin_password" \
      -e ADMIN_FULL_NAME="$admin_full_name" \
      web python create_admin.py
  else
    run_in_app docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml exec -T \
      -e ADMIN_EMAIL="$admin_email" \
      -e ADMIN_PASSWORD="$admin_password" \
      -e ADMIN_FULL_NAME="$admin_full_name" \
      web python create_admin.py
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
  validate_env
  render_caddyfile_runtime
  reset_database_if_requested
  apply_firewall
  postgres_preflight
  deploy_stack
  post_deploy_checks
  sync_admin_account
  print_next_steps
}

main "$@"
