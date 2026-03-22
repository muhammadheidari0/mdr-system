#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DOMAIN_INPUT="${MDR_DOMAIN:-}"
TLS_MODE_INPUT=""
TLS_CERT_FILE_INPUT="${TLS_CERT_FILE:-}"
TLS_KEY_FILE_INPUT="${TLS_KEY_FILE:-}"
OUTPUT_PATH="${REPO_ROOT}/docker/Caddyfile"

usage() {
  cat <<'EOF'
Render Caddyfile from MDR_DOMAIN with explicit TLS mode support.

Usage:
  tools/render_caddyfile.sh --domain <value> [--tls-mode <mode>] [--tls-cert-file <path>] [--tls-key-file <path>] [--output <path>]

Options:
  --domain <value>         MDR public domain or IPv4 (required if MDR_DOMAIN is empty)
  --tls-mode <mode>        One of: http, internal, custom, public
  --tls-cert-file <path>   Certificate path for custom TLS mode
  --tls-key-file <path>    Private key path for custom TLS mode
  --output <path>          Output file path (default: docker/Caddyfile)
  -h, --help               Show this help
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

escape_sed_value() {
  printf '%s' "$1" | sed -e 's/[|&]/\\&/g'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain)
      DOMAIN_INPUT="${2:-}"
      shift 2
      ;;
    --tls-mode)
      TLS_MODE_INPUT="${2:-}"
      shift 2
      ;;
    --tls-cert-file)
      TLS_CERT_FILE_INPUT="${2:-}"
      shift 2
      ;;
    --tls-key-file)
      TLS_KEY_FILE_INPUT="${2:-}"
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

if [[ -z "$TLS_MODE_INPUT" ]]; then
  if is_ipv4 "$DOMAIN_INPUT"; then
    TLS_MODE_INPUT="http"
  else
    TLS_MODE_INPUT="public"
  fi
fi

case "$TLS_MODE_INPUT" in
  http|internal|custom|public)
    ;;
  *)
    echo "[ERROR] Unsupported TLS mode: $TLS_MODE_INPUT" >&2
    exit 1
    ;;
esac

if is_ipv4 "$DOMAIN_INPUT" && [[ "$TLS_MODE_INPUT" != "http" ]]; then
  echo "[ERROR] IPv4 deployments only support --tls-mode http." >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT_PATH")"

case "$TLS_MODE_INPUT" in
  http)
    template_path="${REPO_ROOT}/docker/Caddyfile.http.template"
    if is_ipv4 "$DOMAIN_INPUT"; then
      site_label=":80"
    else
      site_label="http://${DOMAIN_INPUT}"
    fi
    sed "s|__MDR_SITE_LABEL__|$(escape_sed_value "$site_label")|g" "$template_path" > "$OUTPUT_PATH"
    echo "[INFO] Rendered HTTP-only Caddyfile: $OUTPUT_PATH"
    ;;
  internal)
    template_path="${REPO_ROOT}/docker/Caddyfile.internal.template"
    sed "s|__MDR_DOMAIN__|$(escape_sed_value "$DOMAIN_INPUT")|g" "$template_path" > "$OUTPUT_PATH"
    echo "[INFO] Rendered internal-TLS Caddyfile: $OUTPUT_PATH"
    ;;
  custom)
    [[ -n "$TLS_CERT_FILE_INPUT" ]] || {
      echo "[ERROR] --tls-cert-file is required for custom TLS mode." >&2
      exit 1
    }
    [[ -n "$TLS_KEY_FILE_INPUT" ]] || {
      echo "[ERROR] --tls-key-file is required for custom TLS mode." >&2
      exit 1
    }
    template_path="${REPO_ROOT}/docker/Caddyfile.custom.template"
    sed \
      -e "s|__MDR_DOMAIN__|$(escape_sed_value "$DOMAIN_INPUT")|g" \
      -e "s|__TLS_CERT_FILE__|$(escape_sed_value "$TLS_CERT_FILE_INPUT")|g" \
      -e "s|__TLS_KEY_FILE__|$(escape_sed_value "$TLS_KEY_FILE_INPUT")|g" \
      "$template_path" > "$OUTPUT_PATH"
    echo "[INFO] Rendered custom-TLS Caddyfile: $OUTPUT_PATH"
    ;;
  public)
    template_path="${REPO_ROOT}/docker/Caddyfile.public.template"
    sed "s|__MDR_DOMAIN__|$(escape_sed_value "$DOMAIN_INPUT")|g" "$template_path" > "$OUTPUT_PATH"
    echo "[INFO] Rendered public-ACME Caddyfile: $OUTPUT_PATH"
    ;;
esac
