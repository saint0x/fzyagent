#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path("/Users/deepsaint/Desktop/fzyagent")
CUSTOM_TOOLS_DIR = ROOT / "custom_tools"
STATE_ROOT = Path("/tmp/fzyagent/custom_tools")


def fail(message: str, code: int = 13):
    print(message, file=sys.stderr)
    raise SystemExit(code)


def sanitize_env_key(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name).upper()


def load_manifest(tool_id: str):
    path = CUSTOM_TOOLS_DIR / tool_id / "tool.json"
    if not path.exists():
        fail(f"custom tool manifest not found for {tool_id}")
    return json.loads(path.read_text(encoding="utf-8")), path


def main():
    tool_id = os.environ.get("CUSTOM_TOOL_ID", "").strip()
    raw_input = os.environ.get("CUSTOM_TOOL_INPUT_JSON", "{}")
    request_path = os.environ.get("CUSTOM_TOOL_REQUEST_PATH", "").strip()
    if len(sys.argv) > 1:
        request_path = sys.argv[1]
    if request_path and Path(request_path).exists():
        request_payload = json.loads(Path(request_path).read_text(encoding="utf-8"))
        tool_id = request_payload.get("tool_id", tool_id)
        raw_input = json.dumps(request_payload.get("tool_input", json.loads(raw_input or "{}")), ensure_ascii=True)
    if not tool_id:
        fail("CUSTOM_TOOL_ID is required")
    manifest, manifest_path = load_manifest(tool_id)
    try:
        tool_input = json.loads(raw_input)
    except Exception:
        tool_input = {}

    env = os.environ.copy()
    env["TOOL_INPUT_JSON"] = raw_input
    for key, value in tool_input.items():
        env[f"TOOL_ARG_{sanitize_env_key(key)}"] = value if isinstance(value, str) else json.dumps(value, ensure_ascii=True)

    cmd = manifest.get("command_template", "").strip()
    if not cmd:
        fail(f"custom tool {tool_id} is missing command_template")

    proc = subprocess.run(
        ["/bin/sh", "-lc", cmd],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    state_dir = STATE_ROOT / tool_id
    state_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = state_dir / "last.json"
    response_path = os.environ.get("CUSTOM_TOOL_RESPONSE_PATH", "").strip()
    if len(sys.argv) > 2:
        response_path = sys.argv[2]
    if response_path:
        artifact_path = Path(response_path)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "tool": tool_id,
        "status": "ok" if proc.returncode == 0 else "failed",
        "manifest_path": str(manifest_path),
        "command_template": cmd,
        "input": tool_input,
        "streams": {
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        },
        "meta": {
            "runner": manifest.get("runner", "shell"),
            "exit_code": proc.returncode,
        },
    }
    artifact_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=True))
    raise SystemExit(0 if proc.returncode == 0 else 13)


if __name__ == "__main__":
    main()
