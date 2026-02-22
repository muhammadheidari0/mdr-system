#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DOMAIN_INPUT="${MDR_DOMAIN:-}"
OUTPUT_PATH="${REPO_ROOT}/docker/Caddyfile"

usage() {
  cat <<'EOF'
Render Caddyfile from MDR_DOMAIN with smart IP/domain mode.

Usage:
  tools/render_caddyfile.sh --domain <value> [--output <path>]

Options:
  --domain <value>  MDR public domain or IPv4 (required if MDR_DOMAIN is empty)
  --output <path>   Output file path (default: docker/Caddyfile)
  -h, --help        Show this help
EOF
}

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

normalize_domain() {
  local value
  value="$(trim "$1")"
  value="${value#http://}"
  value="${value#https://}"
  value="${value%%/*}"
  if [[ "$value" =~ ^[^/:]+:[0-9]+$ ]]; then
    value="${value%%:*}"
  fi
  printf '%s' "$value"
}

is_ipv4() {
  local value="$1"
  local a b c d octet
  [[ "$value" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || return 1
  IFS='.' read -r a b c d <<<"$value"
  for octet in "$a" "$b" "$c" "$d"; do
    ((octet >= 0 && octet <= 255)) || return 1
  done
  return 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain)
      DOMAIN_INPUT="${2:-}"
      shift 2
      ;;
    --output)
      OUTPUT_PATH="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

DOMAIN_INPUT="$(normalize_domain "${DOMAIN_INPUT:-}")"
if [[ -z "$DOMAIN_INPUT" ]]; then
  echo "[ERROR] MDR_DOMAIN is required (via --domain or env)." >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT_PATH")"

if is_ipv4 "$DOMAIN_INPUT"; then
  cp "${REPO_ROOT}/docker/Caddyfile.ip.template" "$OUTPUT_PATH"
  echo "[INFO] Rendered IP-mode Caddyfile (HTTP only): $OUTPUT_PATH"
  exit 0
fi

sed "s/__MDR_DOMAIN__/${DOMAIN_INPUT}/g" \
  "${REPO_ROOT}/docker/Caddyfile.domain.template" >"$OUTPUT_PATH"
echo "[INFO] Rendered domain-mode Caddyfile (auto HTTPS): $OUTPUT_PATH"
