#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
WORKSPACE_ROOT="${SCRIPT_DIR}"
FOZZYLANG_ROOT="/Users/deepsaint/Desktop/fozzylang"
LOCAL_BIN_DIR="${WORKSPACE_ROOT}/.local/bin"
LOCAL_FZ="${LOCAL_BIN_DIR}/fz"
BUILD_FZ="${FOZZYLANG_ROOT}/target/debug/fz"

usage() {
  cat <<'EOF'
Usage:
  ./compiler.sh rebuild
  ./compiler.sh --rebuild
  ./compiler.sh <fz arguments...>

Behavior:
  rebuild / --rebuild  Build the local fz compiler from the fozzylang repo and
                       replace .local/bin/fz atomically after verification.
  anything else        Run the locally installed compiler with the provided args.
EOF
}

log() {
  printf '[compiler.sh] %s\n' "$1"
}

ensure_paths() {
  if [[ ! -d "${FOZZYLANG_ROOT}" ]]; then
    printf 'fozzylang repo not found at %s\n' "${FOZZYLANG_ROOT}" >&2
    exit 1
  fi
  mkdir -p "${LOCAL_BIN_DIR}"
}

verify_binary() {
  local candidate="$1"

  if [[ ! -f "${candidate}" ]]; then
    printf 'compiler candidate missing: %s\n' "${candidate}" >&2
    exit 1
  fi

  chmod +x "${candidate}"

  if ! file "${candidate}" | grep -q 'Mach-O 64-bit executable arm64'; then
    printf 'unexpected compiler artifact type for %s\n' "${candidate}" >&2
    file "${candidate}" >&2 || true
    exit 1
  fi

  "${candidate}" --version >/dev/null
}

safe_replace_local_fz() {
  local tmp_target="${LOCAL_FZ}.tmp.$$"
  cp "${BUILD_FZ}" "${tmp_target}"
  verify_binary "${tmp_target}"
  mv "${tmp_target}" "${LOCAL_FZ}"
  chmod +x "${LOCAL_FZ}"
}

rebuild_local_fz() {
  ensure_paths
  log "building fz from ${FOZZYLANG_ROOT}"
  cargo build -p fz --manifest-path "${FOZZYLANG_ROOT}/Cargo.toml"

  if [[ ! -f "${BUILD_FZ}" ]]; then
    printf 'build finished but compiler was not found at %s\n' "${BUILD_FZ}" >&2
    exit 1
  fi

  log "verifying fresh compiler artifact"
  verify_binary "${BUILD_FZ}"

  log "replacing ${LOCAL_FZ} atomically"
  safe_replace_local_fz

  log "compiler ready: $(${LOCAL_FZ} --version)"
}

run_local_fz() {
  ensure_paths

  if [[ ! -x "${LOCAL_FZ}" ]]; then
    log "local compiler missing, rebuilding first"
    rebuild_local_fz
  fi

  exec "${LOCAL_FZ}" "$@"
}

main() {
  if [[ $# -eq 0 ]]; then
    usage
    exit 0
  fi

  case "$1" in
    rebuild|--rebuild)
      rebuild_local_fz
      ;;
    --help|-h)
      usage
      ;;
    *)
      run_local_fz "$@"
      ;;
  esac
}

main "$@"
