#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"
if [[ "${1:-}" == "--help" || "${1:-}" == "help" ]]; then
  exec "${SCRIPT_DIR}/.fz/build/fzyagent" help
fi
exec "${SCRIPT_DIR}/.fz/build/fzyagent" chat "$@"
