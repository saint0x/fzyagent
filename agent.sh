#!/usr/bin/env bash
set -euo pipefail
cd /Users/deepsaint/Desktop/fzyagent
if [[ "${1:-}" == "--help" || "${1:-}" == "help" ]]; then
  exec /Users/deepsaint/Desktop/fzyagent/.fz/build/fzyagent help
fi
/Users/deepsaint/Desktop/fzyagent/.fz/build/fzyagent chat "$@"
