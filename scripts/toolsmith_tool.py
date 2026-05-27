#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path


ROOT = Path("/Users/deepsaint/Desktop/fzyagent")
CUSTOM_TOOLS_DIR = ROOT / "custom_tools"
STATE_PATH = Path("/tmp/fzyagent/tools/toolsmith.json")
REGISTRY_SCRIPT = ROOT / "scripts" / "custom_tool_registry.py"
REGISTRY_PATH = Path("/tmp/fzyagent/registry.json")


def valid_tool_id(tool_id: str) -> bool:
    return bool(re.fullmatch(r"[a-z][a-z0-9_]{1,63}", tool_id))


def protocol_payload():
    return {
        "tool": "toolsmith",
        "status": "ok",
        "actions": ["protocol", "create", "list", "inspect"],
        "requirements": {
            "tool_id": "lowercase snake_case, starts with a letter",
            "command_template": "shell command that uses TOOL_ARG_<FIELD> env vars",
            "input_schema": "JSON schema object with properties and optional required list",
        },
        "example": {
            "tool_id": "git_status_short",
            "description": "Show git status in short mode.",
            "kind": "process",
            "mode": "single",
            "command_template": "git status --short",
            "input_schema": {"type": "object", "properties": {}},
        },
    }


def load_registry_tool_ids():
    if not REGISTRY_PATH.exists():
        return set()
    try:
        payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return set()
    tools = payload.get("tools", [])
    ids = set()
    for tool in tools:
        if isinstance(tool, dict):
            tool_id = tool.get("id", "")
            if tool_id:
                ids.add(tool_id)
    return ids


def create_payload(raw_body: str):
    data = json.loads(raw_body or "{}")
    meta = data.get("meta", {})
    tool_id = os.environ.get("TOOLSMITH_TOOL_ID", "").strip() or meta.get("tool_id", "").strip() or data.get("create_tool_id", "").strip() or data.get("tool_id", "").strip()
    description = os.environ.get("TOOLSMITH_DESCRIPTION", "").strip() or meta.get("description", "").strip() or data.get("description", "").strip()
    command_template = os.environ.get("TOOLSMITH_COMMAND_TEMPLATE", "").strip() or meta.get("command_template", "").strip() or data.get("command_template", "").strip()
    kind = os.environ.get("TOOLSMITH_KIND", "").strip() or meta.get("kind", "process").strip() or data.get("kind", "process").strip() or "process"
    mode = os.environ.get("TOOLSMITH_MODE", "").strip() or meta.get("mode", "single").strip() or data.get("mode", "single").strip() or "single"
    input_schema = data.get("input_schema", {"type": "object", "properties": {}})
    input_schema_json = os.environ.get("TOOLSMITH_INPUT_SCHEMA_JSON", "").strip()
    if input_schema_json:
        input_schema = json.loads(input_schema_json)

    if not valid_tool_id(tool_id):
        raise ValueError("tool_id must be lowercase snake_case and start with a letter")
    if not description:
        raise ValueError("description is required")
    if not command_template:
        raise ValueError("command_template is required")
    if not isinstance(input_schema, dict):
        raise ValueError("input_schema must be a JSON object")

    tool_dir = CUSTOM_TOOLS_DIR / tool_id
    tool_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "id": tool_id,
        "description": description,
        "kind": kind,
        "mode": mode,
        "runner": "shell",
        "command_template": command_template,
        "input_schema": input_schema,
    }
    (tool_dir / "tool.json").write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")
    (tool_dir / "README.md").write_text(
        "\n".join(
            [
                f"# {tool_id}",
                "",
                description,
                "",
                "## Command Template",
                "",
                "```sh",
                command_template,
                "```",
                "",
                "## Input Schema",
                "",
                "```json",
                json.dumps(input_schema, ensure_ascii=True, indent=2),
                "```",
            ]
        ),
        encoding="utf-8",
    )
    os.system(f'python3 "{REGISTRY_SCRIPT}" >/dev/null')
    registry_ids = load_registry_tool_ids()
    return {
        "tool": "toolsmith",
        "status": "ok",
        "action": "create",
        "created_tool": tool_id,
        "manifest_path": str(tool_dir / "tool.json"),
        "readme_path": str(tool_dir / "README.md"),
        "manifest_exists": (tool_dir / "tool.json").exists(),
        "readme_exists": (tool_dir / "README.md").exists(),
        "verified_in_registry": tool_id in registry_ids,
    }


def list_payload():
    items = []
    for manifest in sorted(CUSTOM_TOOLS_DIR.glob("*/tool.json")):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            continue
        items.append(
            {
                "id": data.get("id", ""),
                "description": data.get("description", ""),
                "kind": data.get("kind", "process"),
                "mode": data.get("mode", "single"),
                "manifest_path": str(manifest),
            }
        )
    return {"tool": "toolsmith", "status": "ok", "action": "list", "tools": items}


def inspect_payload(raw_body: str):
    data = json.loads(raw_body or "{}")
    meta = data.get("meta", {})
    tool_id = os.environ.get("TOOLSMITH_TOOL_ID", "").strip() or meta.get("tool_id", "").strip() or data.get("create_tool_id", "").strip() or data.get("tool_id", "").strip()
    if not valid_tool_id(tool_id):
        raise ValueError("tool_id must be provided for inspect")
    manifest = CUSTOM_TOOLS_DIR / tool_id / "tool.json"
    if not manifest.exists():
        raise ValueError(f"custom tool {tool_id} not found")
    return {
        "tool": "toolsmith",
        "status": "ok",
        "action": "inspect",
        "manifest": json.loads(manifest.read_text(encoding="utf-8")),
        "manifest_path": str(manifest),
        "manifest_exists": True,
    }


def main():
    CUSTOM_TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    raw_body = os.environ.get("TOOLSMITH_BODY_JSON", "{}")
    request_path = os.environ.get("TOOLSMITH_REQUEST_PATH", "").strip()
    if len(sys.argv) > 1:
        request_path = sys.argv[1]
    if request_path and Path(request_path).exists():
        raw_body = Path(request_path).read_text(encoding="utf-8")
    action = os.environ.get("TOOLSMITH_ACTION", "").strip()
    if not action:
        try:
            action = json.loads(raw_body or "{}").get("action", "").strip()
        except Exception:
            action = ""
    if not action:
        action = "protocol"
    if action == "protocol":
        payload = protocol_payload()
    elif action == "create":
        payload = create_payload(raw_body)
    elif action == "list":
        payload = list_payload()
    elif action == "inspect":
        payload = inspect_payload(raw_body)
    else:
        raise ValueError(f"unsupported toolsmith action: {action}")
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    response_path = os.environ.get("TOOLSMITH_RESPONSE_PATH", "").strip()
    if len(sys.argv) > 2:
        response_path = sys.argv[2]
    if response_path:
        Path(response_path).parent.mkdir(parents=True, exist_ok=True)
        Path(response_path).write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=True))


if __name__ == "__main__":
    main()
