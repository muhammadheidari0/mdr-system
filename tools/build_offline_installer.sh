#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

VERSION=""
OUTPUT_DIR="${REPO_ROOT}/dist"

usage() {
  cat <<'EOF'
Build the MDR offline installer bundle.

Usage:
  tools/build_offline_installer.sh --version <vX.Y.Z> [--output-dir <path>]

Options:
  --version <vX.Y.Z>   Release version tag used for image names and package name
  --output-dir <path>  Directory for the final tar.gz output (default: ./dist)
  -h, --help           Show this help
EOF
}

log_info() { printf '[INFO] %s\n' "$*"; }
log_error() { printf '[ERROR] %s\n' "$*" >&2; }

die() {
  log_error "$*"
  exit 1
}

run() {
  "$@"
}

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || die "Missing required command: $cmd"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --version)
        VERSION="${2:-}"; shift 2 ;;
      --output-dir)
        OUTPUT_DIR="${2:-}"; shift 2 ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "Unknown argument: $1"
        ;;
    esac
  done
}

write_install_wrapper() {
  local target="$1"
  cat > "$target" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/bundle/release/tools/bootstrap_offline.sh" --package-dir "${SCRIPT_DIR}" "$@"
EOF
  chmod +x "$target"
}

write_release_manifest() {
  local target="$1"
  cat > "$target" <<EOF
APP_VERSION=${VERSION}
APP_IMAGE=mdr_app:${VERSION}
POSTGRES_IMAGE=postgres:16-alpine
CADDY_IMAGE=caddy:2.8-alpine
APP_DIR_DEFAULT=/opt/mdr_app
DATA_ROOT_DEFAULT=/opt/mdr_data
COMPOSE_FILE=docker-compose.offline.yml
DEFAULT_TLS_MODE=http
RELEASE_DATE=$(date -u +%FT%TZ)
EOF
}

copy_release_runtime() {
  local package_root="$1"
  local release_root="${package_root}/bundle/release"

  mkdir -p "${release_root}/tools/lib" "${release_root}/docker" "${package_root}/bundle/images"

  cp "${REPO_ROOT}/.env.production.example" "${release_root}/.env.production.example"
  cp "${REPO_ROOT}/docker-compose.offline.yml" "${release_root}/docker-compose.offline.yml"
  cp "${REPO_ROOT}/tools/bootstrap_offline.sh" "${release_root}/tools/bootstrap_offline.sh"
  cp "${REPO_ROOT}/tools/render_caddyfile.sh" "${release_root}/tools/render_caddyfile.sh"
  cp "${REPO_ROOT}/tools/lib/bootstrap_common.sh" "${release_root}/tools/lib/bootstrap_common.sh"
  cp "${REPO_ROOT}/docker/Caddyfile.http.template" "${release_root}/docker/Caddyfile.http.template"
  cp "${REPO_ROOT}/docker/Caddyfile.internal.template" "${release_root}/docker/Caddyfile.internal.template"
  cp "${REPO_ROOT}/docker/Caddyfile.custom.template" "${release_root}/docker/Caddyfile.custom.template"
  cp "${REPO_ROOT}/docker/Caddyfile.public.template" "${release_root}/docker/Caddyfile.public.template"
  chmod +x "${release_root}/tools/bootstrap_offline.sh" "${release_root}/tools/render_caddyfile.sh"
}

build_and_export_images() {
  local package_root="$1"
  local images_root="${package_root}/bundle/images"
  local app_image="mdr_app:${VERSION}"

  log_info "Building application image ${app_image}..."
  run docker build -t "$app_image" "$REPO_ROOT"

  log_info "Pulling supporting images..."
  run docker pull postgres:16-alpine
  run docker pull caddy:2.8-alpine

  log_info "Saving image archives..."
  run docker save -o "${images_root}/mdr_app_${VERSION}.tar" "$app_image"
  run docker save -o "${images_root}/postgres_16-alpine.tar" postgres:16-alpine
  run docker save -o "${images_root}/caddy_2.8-alpine.tar" caddy:2.8-alpine
}

write_checksums() {
  local package_root="$1"
  (
    cd "$package_root"
    find . -type f ! -name 'checksums.txt' -print0 | sort -z | xargs -0 sha256sum > checksums.txt
  )
}

main() {
  parse_args "$@"
  [[ -n "$VERSION" ]] || die "--version is required."

  require_cmd docker
  require_cmd tar
  require_cmd sha256sum
  require_cmd mktemp

  mkdir -p "$OUTPUT_DIR"

  local staging_dir package_name package_root output_file
  staging_dir="$(mktemp -d)"
  package_name="mdr-offline-installer-${VERSION}"
  package_root="${staging_dir}/${package_name}"
  output_file="${OUTPUT_DIR}/${package_name}.tar.gz"

  mkdir -p "$package_root"
  copy_release_runtime "$package_root"
  write_install_wrapper "${package_root}/install.sh"
  write_release_manifest "${package_root}/release_manifest.env"
  build_and_export_images "$package_root"
  write_checksums "$package_root"

  log_info "Creating package ${output_file}..."
  (
    cd "$staging_dir"
    tar -czf "$output_file" "$package_name"
  )

  log_info "Offline installer created: ${output_file}"
}

main "$@"
