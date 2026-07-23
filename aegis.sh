#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="${SCRIPT_DIR}"
AEGIS_ROOT="${AEGIS_ROOT:-$(cd "${WORKSPACE_ROOT}/../aegis" 2>/dev/null && pwd || true)}"
LOCAL_BIN_DIR="${WORKSPACE_ROOT}/.local/bin"
LOCAL_AEGIS="${LOCAL_BIN_DIR}/aegis"
BUILD_AEGIS="${AEGIS_ROOT}/target/release/aegis"

usage() {
  cat <<'EOF'
Usage:
  ./aegis.sh rebuild
  ./aegis.sh --rebuild
  ./aegis.sh <aegis arguments...>

Behavior:
  rebuild / --rebuild  Build the local Aegis CLI and native Release runtime from
                       the aegis repo, then replace .local/bin/aegis atomically.
  anything else        Run the locally installed Aegis binary with the provided args.

Examples:
  ./aegis.sh rebuild
  ./aegis.sh --mode headless serve --addr 127.0.0.1:7979
  ./aegis.sh native doctor
EOF
}

log() {
  printf '[aegis.sh] %s\n' "$1"
}

ensure_paths() {
  if [[ ! -d "${AEGIS_ROOT}" ]]; then
    printf 'aegis repo not found at %s\n' "${AEGIS_ROOT}" >&2
    exit 1
  fi
  mkdir -p "${LOCAL_BIN_DIR}"
}

verify_binary() {
  local candidate="$1"

  if [[ ! -f "${candidate}" ]]; then
    printf 'aegis candidate missing: %s\n' "${candidate}" >&2
    exit 1
  fi

  chmod +x "${candidate}"

  local artifact_type
  artifact_type="$(file "${candidate}" 2>/dev/null || true)"
  if [[ "${artifact_type}" != *"executable"* ]]; then
    printf 'unexpected aegis artifact type for %s\n' "${candidate}" >&2
    printf '%s\n' "${artifact_type}" >&2
    exit 1
  fi

  "${candidate}" --help >/dev/null
}

safe_replace_local_aegis() {
  local tmp_target="${LOCAL_AEGIS}.tmp.$$"
  cp "${BUILD_AEGIS}" "${tmp_target}"
  verify_binary "${tmp_target}"
  mv "${tmp_target}" "${LOCAL_AEGIS}"
  chmod +x "${LOCAL_AEGIS}"
}

rebuild_local_aegis() {
  ensure_paths
  log "building release aegis CLI from ${AEGIS_ROOT}"
  cargo build --release --manifest-path "${AEGIS_ROOT}/Cargo.toml"

  log "building release native host runtime"
  cargo run --manifest-path "${AEGIS_ROOT}/Cargo.toml" -- native build --configuration release --target aegis_host

  log "building release native app runtime"
  cargo run --manifest-path "${AEGIS_ROOT}/Cargo.toml" -- native build --configuration release

  if [[ ! -f "${BUILD_AEGIS}" ]]; then
    printf 'build finished but aegis CLI was not found at %s\n' "${BUILD_AEGIS}" >&2
    exit 1
  fi

  log "verifying fresh aegis artifact"
  verify_binary "${BUILD_AEGIS}"

  log "replacing ${LOCAL_AEGIS} atomically"
  safe_replace_local_aegis

  log "aegis ready"
}

run_local_aegis() {
  ensure_paths

  if [[ ! -x "${LOCAL_AEGIS}" ]]; then
    log "local aegis binary missing, rebuilding first"
    rebuild_local_aegis
  fi

  export AEGIS_WORKSPACE_ROOT="${AEGIS_ROOT}"
  exec "${LOCAL_AEGIS}" "$@"
}

main() {
  if [[ $# -eq 0 ]]; then
    usage
    exit 0
  fi

  case "$1" in
    rebuild|--rebuild)
      rebuild_local_aegis
      ;;
    --help|-h)
      usage
      ;;
    *)
      run_local_aegis "$@"
      ;;
  esac
}

main "$@"
