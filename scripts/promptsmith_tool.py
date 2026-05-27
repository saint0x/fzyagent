#!/usr/bin/env python3
import hashlib
import json
import os
import sys
from pathlib import Path


ROOT = Path("/Users/deepsaint/Desktop/fzyagent")
CONFIG_DIR = ROOT / "config"
ACTIVE_PATH = CONFIG_DIR / "agent_system_prompt.md"
DEFAULT_PATH = CONFIG_DIR / "agent_system_prompt.default.md"
STATE_PATH = Path("/tmp/fzyagent/tools/promptsmith.json")


def ensure_files() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not DEFAULT_PATH.exists():
        DEFAULT_PATH.write_text("You are the fzyagent agent CLI.\n", encoding="utf-8")
    if not ACTIVE_PATH.exists():
        ACTIVE_PATH.write_text(DEFAULT_PATH.read_text(encoding="utf-8"), encoding="utf-8")


def read_request_payload() -> str:
    raw_body = os.environ.get("PROMPTSMITH_BODY_JSON", "{}")
    request_path = os.environ.get("PROMPTSMITH_REQUEST_PATH", "").strip()
    if len(sys.argv) > 1:
        request_path = sys.argv[1]
    if request_path and Path(request_path).exists():
        raw_body = Path(request_path).read_text(encoding="utf-8")
    return raw_body


def prompt_meta(text: str) -> dict:
    lines = text.splitlines()
    preview = "\n".join(lines[:8])
    return {
        "active_path": str(ACTIVE_PATH),
        "default_path": str(DEFAULT_PATH),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "chars": len(text),
        "lines": len(lines),
        "preview": preview,
    }


def protocol_payload() -> dict:
    return {
        "tool": "promptsmith",
        "status": "ok",
        "actions": ["protocol", "get", "set", "append", "reset"],
        "requirements": {
            "content": "full prompt text for set, or appended text for append",
        },
        "example": {
            "action": "append",
            "content": "When using a newly created custom tool, verify it with a real invocation before claiming success.",
        },
    }


def get_payload() -> dict:
    text = ACTIVE_PATH.read_text(encoding="utf-8")
    return {
        "tool": "promptsmith",
        "status": "ok",
        "action": "get",
        "content": text,
        "meta": prompt_meta(text),
    }


def set_payload(content: str) -> dict:
    if not content.strip():
        raise ValueError("content is required for set")
    ACTIVE_PATH.write_text(content, encoding="utf-8")
    return {
        "tool": "promptsmith",
        "status": "ok",
        "action": "set",
        "content": content,
        "meta": prompt_meta(content),
    }


def append_payload(content: str) -> dict:
    if not content.strip():
        raise ValueError("content is required for append")
    current = ACTIVE_PATH.read_text(encoding="utf-8").rstrip()
    updated = current + "\n\n" + content.strip() + "\n"
    ACTIVE_PATH.write_text(updated, encoding="utf-8")
    return {
        "tool": "promptsmith",
        "status": "ok",
        "action": "append",
        "content": updated,
        "meta": prompt_meta(updated),
    }


def reset_payload() -> dict:
    default_text = DEFAULT_PATH.read_text(encoding="utf-8")
    ACTIVE_PATH.write_text(default_text, encoding="utf-8")
    return {
        "tool": "promptsmith",
        "status": "ok",
        "action": "reset",
        "content": default_text,
        "meta": prompt_meta(default_text),
    }


def write_payload(payload: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    response_path = os.environ.get("PROMPTSMITH_RESPONSE_PATH", "").strip()
    if len(sys.argv) > 2:
        response_path = sys.argv[2]
    if response_path:
        Path(response_path).parent.mkdir(parents=True, exist_ok=True)
        Path(response_path).write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def main() -> None:
    ensure_files()
    raw_body = read_request_payload()
    try:
        data = json.loads(raw_body or "{}")
    except Exception:
        data = {}
    action = os.environ.get("PROMPTSMITH_ACTION", "").strip() or str(data.get("action", "")).strip() or "protocol"
    content = os.environ.get("PROMPTSMITH_CONTENT", "")
    if not content:
        content = str(data.get("content", ""))

    if action == "protocol":
        payload = protocol_payload()
    elif action == "get":
        payload = get_payload()
    elif action == "set":
        payload = set_payload(content)
    elif action == "append":
        payload = append_payload(content)
    elif action == "reset":
        payload = reset_payload()
    else:
        raise ValueError(f"unsupported promptsmith action: {action}")

    write_payload(payload)
    print(json.dumps(payload, ensure_ascii=True))


if __name__ == "__main__":
    main()
