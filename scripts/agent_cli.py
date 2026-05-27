#!/usr/bin/env python3
import argparse
import http.client
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional


ROOT = Path("/Users/deepsaint/Desktop/fzyagent")
WORKSPACE_ROOT = Path("/Users/deepsaint/Desktop/fzyagent")
ENV_PATH = WORKSPACE_ROOT / ".env"
ACTIVE_PROMPT_PATH = ROOT / "config" / "agent_system_prompt.md"
DEFAULT_PROMPT_PATH = ROOT / "config" / "agent_system_prompt.default.md"
STATE_DIR = Path("/tmp/fzyagent/cli_sessions")
STATE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR = Path("/tmp/fzyagent")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_TOOL_STATE_DIR = Path("/tmp/fzyagent/cli_tool_calls")
LOCAL_TOOL_STATE_DIR.mkdir(parents=True, exist_ok=True)


class AnthropicRequestError(RuntimeError):
    def __init__(self, status: int, raw: str, parsed: Optional[dict] = None):
        super().__init__(raw)
        self.status = status
        self.raw = raw
        self.parsed = parsed or {}


DEFAULT_SYSTEM_PROMPT = """You are the fzyagent agent CLI.
Use tools whenever they will improve accuracy or grounding.
Prefer:
- bash for concrete shell work in the shared workspace
- grep_search for focused code search
- workspace_digest for broad repo orientation
- release_audit for multi-signal repo checks
- aegis for web browsing, search, DOM inspection, and scripted browser work
- fzydoc for idiomatic FZY syntax, showcase examples, and production guidance
- toolsmith when you need to create a new runtime tool that follows the local tool protocol
- promptsmith when you need to inspect or update your active system prompt

When writing FZY:
- prefer http.body_json(conn) for inbound JSON
- prefer structured proc APIs
- prefer explicit JSON builders
- prefer spawn/join for independent parallel work
- consult fzydoc before writing nontrivial FZY if syntax or idioms are uncertain

Guard rails:
- never claim a tool was created unless toolsmith reports verified registry persistence
- never claim a custom tool works until you have invoked it and checked the result payload
- use verification fields from tool results explicitly when they are present

Be concise, practical, and honest about tool results.
"""


TOOL_SPECS = [
    {
        "name": "bash",
        "description": "Run a shell command in the shared workspace and return stdout/stderr.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute."}
            },
            "required": ["command"],
        },
    },
    {
        "name": "grep_search",
        "description": "Search text in the workspace with grep.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Pattern to search for."},
                "target": {"type": "string", "description": "Target file or directory path, usually src or a subdirectory."},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "workspace_digest",
        "description": "Get a broad, grounded digest of the current workspace and key source files.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "release_audit",
        "description": "Run a parallel audit workflow over shell, grep, and inventory checks.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "project_seed",
        "description": "Assemble a richer context bundle from release_audit and workspace_digest.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "browser_ops_seed",
        "description": "Assemble a browser-oriented context bundle from workspace_digest and aegis.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "aegis",
        "description": "Use the Aegis headless browser runtime for web search, navigation, DOM snapshots, events, eval, and scripted browser automation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["runtime", "manifest", "doctor", "dom", "session", "events", "navigate", "execute", "search_eval", "eval"],
                },
                "url": {"type": "string"},
                "query": {"type": "string"},
                "eval_js": {"type": "string"},
                "commands": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["action"],
        },
    },
    {
        "name": "toolsmith",
        "description": "Create, inspect, list, and document custom runtime tools that follow the local tool protocol.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["protocol", "create", "list", "inspect"]},
                "tool_id": {"type": "string"},
                "description": {"type": "string"},
                "command_template": {"type": "string"},
                "kind": {"type": "string"},
                "mode": {"type": "string"},
                "input_schema": {"type": "object"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "promptsmith",
        "description": "Inspect and update the active agent system prompt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["protocol", "get", "set", "append", "reset"]},
                "content": {"type": "string"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "fzydoc",
        "description": "Search local FZY showcase and idiomatic docs for syntax, patterns, and examples.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_lines": {"type": "string"},
            },
            "required": ["query"],
        },
    },
]


STATIC_TOOL_NAMES = {tool["name"] for tool in TOOL_SPECS}


def ensure_prompt_files() -> None:
    DEFAULT_PROMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DEFAULT_PROMPT_PATH.exists():
        DEFAULT_PROMPT_PATH.write_text(DEFAULT_SYSTEM_PROMPT, encoding="utf-8")
    if not ACTIVE_PROMPT_PATH.exists():
        ACTIVE_PROMPT_PATH.write_text(DEFAULT_PROMPT_PATH.read_text(encoding="utf-8"), encoding="utf-8")


def load_system_prompt() -> str:
    ensure_prompt_files()
    text = ACTIVE_PROMPT_PATH.read_text(encoding="utf-8").strip()
    if text:
        return text
    fallback = DEFAULT_PROMPT_PATH.read_text(encoding="utf-8").strip()
    return fallback or DEFAULT_SYSTEM_PROMPT


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def http_json(method: str, url: str, body=None, timeout=60):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["content-type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            return resp.status, text, json.loads(text)
    except urllib.error.HTTPError as err:
        raw = err.read()
        text = raw.decode("utf-8", errors="replace")
        parsed = None
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = {"text": text}
        return err.code, text, parsed


def ensure_server(base_url: str, no_launch: bool) -> Optional[subprocess.Popen]:
    try:
        status, _, _ = http_json("GET", base_url + "/healthz", timeout=3)
        if status == 200:
            return None
    except Exception:
        pass
    if no_launch:
        raise RuntimeError(f"agent runtime is not reachable at {base_url}")

    env = os.environ.copy()
    env.setdefault("FZ_DOTENV_PATH", str(ENV_PATH))
    env.setdefault("AGENT_HOST", "127.0.0.1")
    env.setdefault("AGENT_PORT", base_url.rsplit(":", 1)[1])
    env.setdefault("AGENT_WORKERS", "4")
    env.setdefault("AGENT_AUTH_MODE", "env")
    env.setdefault("AGENT_RATE_BUCKET", "default")
    env.setdefault("AGENT_POLICY", "standard")
    env.setdefault("AGENT_SAFETY_MODE", "standard")
    env.setdefault("AGENT_BACKGROUND_MODE", "http")
    env.setdefault("AGENT_OBSERVABILITY_MODE", "minimal")
    log_path = LOG_DIR / "agent_cli.runtime.log"
    handle = log_path.open("ab")
    proc = subprocess.Popen(
        [str(ROOT / ".fz" / "build" / "fzyagent")],
        cwd=str(ROOT),
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            status, _, _ = http_json("GET", base_url + "/healthz", timeout=3)
            if status == 200:
                return proc
        except Exception:
            pass
        time.sleep(0.25)
    raise RuntimeError(f"agent runtime did not become healthy at {base_url}")


def conversation_path(session_name: str) -> Path:
    return STATE_DIR / f"{session_name}.json"


def load_conversation(session_name: str):
    path = conversation_path(session_name)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_conversation(session_name: str, messages) -> None:
    conversation_path(session_name).write_text(json.dumps(messages, ensure_ascii=True, indent=2), encoding="utf-8")


def create_runtime_session(base_url: str):
    try:
        http_json("POST", base_url + "/sessions", {}, timeout=10)
    except Exception:
        pass


def merged_tool_specs(base_url: str):
    specs = list(TOOL_SPECS)
    try:
        status, _, parsed = http_json("GET", base_url + "/tools", timeout=20)
    except Exception:
        return specs
    if status != 200 or not isinstance(parsed, dict):
        return specs
    for tool in parsed.get("tools", []):
        tool_id = tool.get("id", "")
        if not tool_id or tool_id in STATIC_TOOL_NAMES:
            continue
        input_schema = tool.get("input_schema", {"type": "object", "properties": {}})
        if not isinstance(input_schema, dict):
            input_schema = {"type": "object", "properties": {}}
        specs.append(
            {
                "name": tool_id,
                "description": tool.get("description", f"Custom runtime tool: {tool_id}"),
                "input_schema": input_schema,
            }
        )
    return specs


def anthropic_request(model: str, system: str, messages, tools):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    version = os.environ.get("ANTHROPIC_VERSION", "2023-06-01")
    payload = {
        "model": model,
        "max_tokens": 1800,
        "system": system,
        "messages": messages,
        "tools": tools,
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": version,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def style(code: str, text: str) -> str:
    if sys.stdout.isatty():
        return f"\033[{code}m{text}\033[0m"
    return text


def style_err(code: str, text: str) -> str:
    if sys.stderr.isatty():
        return f"\033[{code}m{text}\033[0m"
    return text


def pretty_value(value) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=True)


def render_kv_lines(mapping: dict) -> List[str]:
    lines = []
    for key, value in mapping.items():
        lines.append(f"  {key}: {pretty_value(value)}")
    return lines


def fetch_runtime_registry(base_url: str) -> dict:
    status, _, parsed = http_json("GET", base_url + "/tools", timeout=20)
    if status == 200 and isinstance(parsed, dict):
        return parsed
    return {}


def verify_tool_result(base_url: str, tool_name: str, tool_input: dict, result: dict) -> dict:
    verification = {"ok": False, "checks": []}
    response = result.get("response")
    status = result.get("http_status")
    if not isinstance(response, dict):
        verification["checks"].append("response_not_json_object")
        return verification
    if not isinstance(status, int):
        verification["checks"].append("http_status_missing")
        return verification

    if tool_name == "toolsmith":
        result_node = response.get("result", {})
        action = tool_input.get("action", "protocol")
        if action == "create" and isinstance(result_node, dict):
            created_tool = result_node.get("created_tool", "")
            manifest_path = result_node.get("manifest_path", "")
            registry = fetch_runtime_registry(base_url)
            registry_ids = {tool.get("id", "") for tool in registry.get("tools", []) if isinstance(tool, dict)}
            manifest_exists = bool(manifest_path) and Path(manifest_path).exists()
            in_registry = created_tool in registry_ids if created_tool else False
            result_node["manifest_exists"] = manifest_exists
            result_node["verified_in_registry"] = in_registry
            verification["checks"].append(f"manifest_exists={str(manifest_exists).lower()}")
            verification["checks"].append(f"verified_in_registry={str(in_registry).lower()}")
            verification["ok"] = status == 200 and manifest_exists and in_registry
            return verification
        verification["ok"] = status == 200
        verification["checks"].append("toolsmith_non_create_ok" if status == 200 else "toolsmith_non_create_failed")
        return verification

    if tool_name == "promptsmith":
        result_node = response.get("result", {})
        if isinstance(result_node, dict):
            meta = result_node.get("meta", {})
            active_path = meta.get("active_path", "")
            path_exists = bool(active_path) and Path(active_path).exists()
            verification["checks"].append(f"active_prompt_exists={str(path_exists).lower()}")
            verification["ok"] = status == 200 and path_exists
            return verification

    if tool_name in STATIC_TOOL_NAMES:
        verification["ok"] = status == 200
        verification["checks"].append("builtin_http_ok" if status == 200 else "builtin_http_failed")
        return verification

    result_node = response.get("result", {})
    if isinstance(result_node, dict):
        manifest_path = result_node.get("manifest_path", "")
        reported_tool = result_node.get("tool", "")
        manifest_exists = bool(manifest_path) and Path(manifest_path).exists()
        name_matches = reported_tool == tool_name
        verification["checks"].append(f"manifest_exists={str(manifest_exists).lower()}")
        verification["checks"].append(f"tool_name_matches={str(name_matches).lower()}")
        verification["ok"] = status == 200 and manifest_exists and name_matches
        return verification

    verification["checks"].append("result_missing_for_custom_tool")
    return verification


def run_local_authoring_tool(tool_name: str, payload: dict) -> dict:
    request_path = LOCAL_TOOL_STATE_DIR / f"{tool_name}.request.json"
    response_path = LOCAL_TOOL_STATE_DIR / f"{tool_name}.response.json"
    script_name = "toolsmith_tool.py" if tool_name == "toolsmith" else "promptsmith_tool.py"
    request_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    proc = subprocess.run(
        ["python3", str(ROOT / "scripts" / script_name), str(request_path), str(response_path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    parsed = {}
    if response_path.exists():
        parsed = json.loads(response_path.read_text(encoding="utf-8"))
    elif proc.stdout.strip():
        parsed = json.loads(proc.stdout)
    status = 200 if proc.returncode == 0 else 500
    return {
        "http_status": status,
        "response": {
            "status": "ok" if status == 200 else "error",
            "tool_id": tool_name,
            "run_id": f"{tool_name}_latest",
            "result": parsed,
        },
        "raw_text": proc.stdout or proc.stderr,
    }


def summarize_tool_result(tool_name: str, result: dict) -> str:
    status = result.get("http_status")
    response = result.get("response")
    artifact = result.get("artifact")
    if tool_name == "bash" and isinstance(artifact, dict):
        inner = artifact.get("result", {})
        streams = inner.get("streams", {})
        stdout = streams.get("stdout", "")
        stderr = streams.get("stderr", "")
        command = inner.get("command", "")
        pieces = [f"tool={tool_name}", f"http_status={status}"]
        if command:
            pieces.append(f"command={command}")
        if stdout:
            pieces.append(f"stdout={stdout.strip()}")
        if stderr:
            pieces.append(f"stderr={stderr.strip()}")
        return "\n".join(pieces)
    if tool_name == "bash" and isinstance(response, dict):
        inner = response.get("result", {})
        streams = inner.get("streams", {})
        stdout = streams.get("stdout", "")
        stderr = streams.get("stderr", "")
        command = inner.get("command", "")
        pieces = [f"tool={tool_name}", f"http_status={status}"]
        if command:
            pieces.append(f"command={command}")
        if stdout:
            pieces.append(f"stdout={stdout.strip()}")
        if stderr:
            pieces.append(f"stderr={stderr.strip()}")
        return "\n".join(pieces)
    if tool_name == "aegis":
        source = artifact if isinstance(artifact, dict) else None
        if source is None and isinstance(response, dict):
            result_text = response.get("result_text")
            if isinstance(result_text, str):
                try:
                    source = json.loads(result_text)
                except Exception:
                    source = None
        if isinstance(source, dict):
            response_node = source.get("response", {})
            json_node = response_node.get("json", {})
            results = json_node.get("results", [])
            lines = [f"tool={tool_name}", f"http_status={status}"]
            for item in results:
                value = item.get("value")
                if isinstance(value, str) and value.startswith("http"):
                    lines.append(f"url={value}")
                elif isinstance(value, dict):
                    title = value.get("current_title")
                    url = value.get("current_url")
                    if title:
                        lines.append(f"title={title}")
                    if url:
                        lines.append(f"current_url={url}")
            return "\n".join(lines)
    if tool_name == "toolsmith" and isinstance(response, dict):
        result_node = response.get("result")
        if isinstance(result_node, dict):
            created_tool = result_node.get("created_tool", "")
            manifest_path = result_node.get("manifest_path", "")
            lines = [f"tool={tool_name}", f"http_status={status}"]
            if created_tool:
                lines.append(f"created_tool={created_tool}")
            verified_in_registry = result_node.get("verified_in_registry")
            if verified_in_registry is not None:
                lines.append(f"verified_in_registry={verified_in_registry}")
            manifest_exists = result_node.get("manifest_exists")
            if manifest_exists is not None:
                lines.append(f"manifest_exists={manifest_exists}")
            if manifest_path:
                lines.append(f"manifest_path={manifest_path}")
            return "\n".join(lines)
    if tool_name == "promptsmith" and isinstance(response, dict):
        result_node = response.get("result")
        if isinstance(result_node, dict):
            lines = [f"tool={tool_name}", f"http_status={status}", f"action={result_node.get('action', '')}"]
            meta = result_node.get("meta", {})
            if isinstance(meta, dict):
                active_path = meta.get("active_path", "")
                sha = meta.get("sha256", "")
                if active_path:
                    lines.append(f"active_path={active_path}")
                if sha:
                    lines.append(f"sha256={sha[:12]}")
            return "\n".join(lines)
    if tool_name == "fzydoc" and isinstance(response, dict):
        result_node = response.get("result")
        if isinstance(result_node, dict):
            hits = result_node.get("hits", [])
            lines = [f"tool={tool_name}", f"http_status={status}"]
            for hit in hits[:3]:
                lines.append(f"hit={hit.get('path', '')}:{hit.get('line', '')}")
            return "\n".join(lines)
    if isinstance(response, dict):
        result_node = response.get("result")
        if isinstance(result_node, dict):
            streams = result_node.get("streams", {})
            stdout = streams.get("stdout", "")
            stderr = streams.get("stderr", "")
            command_template = result_node.get("command_template", "")
            pieces = [f"tool={tool_name}", f"http_status={status}"]
            if command_template:
                pieces.append(f"command_template={command_template}")
            if stdout:
                pieces.append(f"stdout={stdout.strip()}")
            if stderr:
                pieces.append(f"stderr={stderr.strip()}")
            if len(pieces) > 2:
                return "\n".join(pieces)
    if isinstance(response, dict):
        result_text = response.get("result_text")
        if isinstance(result_text, str) and result_text.strip():
            trimmed = result_text.strip()
            return trimmed if len(trimmed) <= 6000 else trimmed[:6000] + "\n...[truncated]"
        data = response.get("result")
        if isinstance(data, dict):
            stdout = data.get("stdout", "")
            stderr = data.get("stderr", "")
            exit_code = data.get("exit_code")
            pieces = [f"tool={tool_name}", f"http_status={status}"]
            if exit_code is not None:
                pieces.append(f"exit_code={exit_code}")
            if stdout:
                pieces.append(f"stdout={stdout.strip()}")
            if stderr:
                pieces.append(f"stderr={stderr.strip()}")
            return "\n".join(pieces)
        if artifact is not None:
            serialized = json.dumps(artifact, ensure_ascii=True)
            return serialized if len(serialized) <= 6000 else serialized[:6000] + "...[truncated]"
    raw_text = result.get("raw_text", "")
    if raw_text:
        return raw_text if len(raw_text) <= 6000 else raw_text[:6000] + "\n...[truncated]"
    return json.dumps(result, ensure_ascii=True)


def print_tool_call(tool_name: str, tool_input: dict) -> None:
    header = style_err("1;36", f"tool call: {tool_name}")
    print(f"\n{header}", file=sys.stderr)
    if tool_input:
        for line in render_kv_lines(tool_input):
            print(style_err("36", line), file=sys.stderr)
    else:
        print(style_err("36", "  (no arguments)"), file=sys.stderr)


def print_tool_result(tool_name: str, result: dict) -> None:
    status = result.get("http_status", "?")
    ok = 200 <= int(status) < 300 if isinstance(status, int) else False
    header = style_err("1;32" if ok else "1;31", f"tool result: {tool_name} [{status}]")
    print(header, file=sys.stderr)
    summary = summarize_tool_result(tool_name, result)
    for line in summary.splitlines() or ["(empty)"]:
        print(style_err("90", f"  {line}"), file=sys.stderr)
    verification = result.get("verification", {})
    if isinstance(verification, dict):
        checks = verification.get("checks", [])
        verified = verification.get("ok")
        if verified is not None or checks:
            print(style_err("90", f"  verified={verified}"), file=sys.stderr)
            for check in checks:
                print(style_err("90", f"  check={check}"), file=sys.stderr)


def anthropic_stream_request(model: str, system: str, messages, tools):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    version = os.environ.get("ANTHROPIC_VERSION", "2023-06-01")
    payload = {
        "model": model,
        "max_tokens": 1800,
        "system": system,
        "messages": messages,
        "tools": tools,
        "stream": True,
    }
    body = json.dumps(payload).encode("utf-8")
    conn = http.client.HTTPSConnection("api.anthropic.com", timeout=180)
    conn.request(
        "POST",
        "/v1/messages",
        body=body,
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": version,
            "accept": "text/event-stream",
        },
    )
    resp = conn.getresponse()
    if resp.status >= 400:
        raw = resp.read().decode("utf-8", errors="replace")
        conn.close()
        parsed = None
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = None
        raise AnthropicRequestError(resp.status, raw, parsed)
    return conn, resp


def friendly_anthropic_error(err: Exception) -> str:
    if isinstance(err, AnthropicRequestError):
        parsed = err.parsed if isinstance(err.parsed, dict) else {}
        error_node = parsed.get("error", {}) if isinstance(parsed.get("error", {}), dict) else {}
        message = error_node.get("message", "").strip()
        lowered = message.lower()
        if err.status == 404:
            if "model" in lowered:
                return "\n".join(
                    [
                        f"Anthropic request failed: model `{err.model}` is not available on this account or API surface.",
                        "Fix: set `ANTHROPIC_MODEL` to a model returned by `GET /v1/models` for this same API key.",
                        "Known working Haiku on this machine: `claude-haiku-4-5-20251001`.",
                        f"HTTP status: {err.status}",
                    ]
                )
            return "\n".join(
                [
                    f"Anthropic request failed: resource not found for model `{err.model}`.",
                    "Fix: verify the model id and endpoint for this API key.",
                    f"HTTP status: {err.status}",
                ]
            )
        if "credit balance is too low" in lowered or "purchase credits" in lowered or "plans & billing" in lowered:
            return "\n".join(
                [
                    "Anthropic request failed: your Anthropic account does not currently have enough credits.",
                    "Fix: add credits or change the account/project backing `ANTHROPIC_API_KEY`, then retry the chat.",
                    f"HTTP status: {err.status}",
                ]
            )
        if message:
            return "\n".join(
                [
                    f"Anthropic request failed: {message}",
                    f"HTTP status: {err.status}",
                ]
            )
        return f"Anthropic request failed with HTTP {err.status}."
    return str(err)


def finalize_stream_block(block: dict) -> dict:
    block_type = block.get("type")
    if block_type == "tool_use":
        partial = block.pop("_partial_json", "")
        if partial:
            try:
                block["input"] = json.loads(partial)
            except Exception:
                block["input"] = {"_raw_partial_json": partial}
        elif "input" not in block:
            block["input"] = {}
    return block


def stream_assistant_message(model: str, system: str, messages, tools):
    conn, resp = anthropic_stream_request(model, system, messages, tools)
    content_blocks: Dict[int, dict] = {}
    assistant_text_started = False
    final_stop_reason = None
    usage = {}
    current_event = None
    data_lines: List[str] = []

    def flush_event():
        nonlocal assistant_text_started, final_stop_reason, usage
        if not data_lines:
            return
        raw = "\n".join(data_lines).strip()
        if not raw:
            return
        payload = json.loads(raw)
        event_type = payload.get("type", current_event)
        if event_type == "content_block_start":
            block = dict(payload.get("content_block", {}))
            content_blocks[payload["index"]] = block
            if block.get("type") == "text" and not assistant_text_started:
                sys.stdout.write(style("1;35", "\nassistant> "))
                sys.stdout.flush()
                assistant_text_started = True
        elif event_type == "content_block_delta":
            index = payload["index"]
            delta = payload.get("delta", {})
            block = content_blocks.setdefault(index, {})
            delta_type = delta.get("type")
            if delta_type == "text_delta":
                chunk = delta.get("text", "")
                block["type"] = "text"
                block["text"] = block.get("text", "") + chunk
                if not assistant_text_started:
                    sys.stdout.write(style("1;35", "\nassistant> "))
                    assistant_text_started = True
                sys.stdout.write(chunk)
                sys.stdout.flush()
            elif delta_type == "input_json_delta":
                block["type"] = "tool_use"
                block["_partial_json"] = block.get("_partial_json", "") + delta.get("partial_json", "")
            elif delta_type == "thinking_delta":
                pass
            elif delta_type == "signature_delta":
                pass
        elif event_type == "content_block_stop":
            index = payload["index"]
            if index in content_blocks:
                content_blocks[index] = finalize_stream_block(content_blocks[index])
        elif event_type == "message_delta":
            delta = payload.get("delta", {})
            final_stop_reason = delta.get("stop_reason", final_stop_reason)
            usage = payload.get("usage", usage)
        elif event_type == "message_stop":
            return

    try:
        while True:
            raw_line = resp.readline()
            if not raw_line:
                break
            line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
            if not line:
                flush_event()
                current_event = None
                data_lines = []
                continue
            if line.startswith("event:"):
                current_event = line.split(":", 1)[1].strip()
                continue
            if line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].lstrip())
    finally:
        conn.close()

    if assistant_text_started:
        sys.stdout.write("\n\n")
        sys.stdout.flush()

    ordered = []
    for index in sorted(content_blocks.keys()):
        ordered.append(finalize_stream_block(content_blocks[index]))
    return {"content": ordered, "stop_reason": final_stop_reason, "usage": usage}


def compact_tool_result(tool_name: str, payload: dict) -> str:
    summary = summarize_tool_result(tool_name, payload)
    verification = payload.get("verification", {})
    if isinstance(verification, dict):
        checks = verification.get("checks", [])
        verified = verification.get("ok")
        if verified is not None:
            summary += f"\nverified={verified}"
        for check in checks:
            summary += f"\ncheck={check}"
    return summary


def call_runtime_tool(base_url: str, name: str, tool_input: dict) -> dict:
    if name == "toolsmith":
        payload = {
            "action": tool_input.get("action", "protocol"),
            "tool_id": tool_input.get("tool_id", ""),
            "description": tool_input.get("description", ""),
            "command_template": tool_input.get("command_template", ""),
            "kind": tool_input.get("kind", ""),
            "mode": tool_input.get("mode", ""),
            "input_schema": tool_input.get("input_schema", {}),
        }
        result = run_local_authoring_tool(name, payload)
        result["verification"] = verify_tool_result(base_url, name, tool_input, result)
        return result
    if name == "promptsmith":
        payload = {
            "action": tool_input.get("action", "get"),
            "content": tool_input.get("content", ""),
        }
        result = run_local_authoring_tool(name, payload)
        result["verification"] = verify_tool_result(base_url, name, tool_input, result)
        return result
    body = {}
    if name == "bash":
        body["command"] = tool_input.get("command", "")
    elif name == "grep_search":
        body["pattern"] = tool_input.get("pattern", "")
        body["target"] = tool_input.get("target", "src")
    elif name == "aegis":
        body["action"] = tool_input.get("action", "runtime")
        if "url" in tool_input:
            body["url"] = tool_input["url"]
        if "query" in tool_input:
            body["query"] = tool_input["query"]
        if "eval_js" in tool_input:
            body["eval_js"] = tool_input["eval_js"]
        if "commands" in tool_input:
            body["commands_json"] = json.dumps(tool_input["commands"], ensure_ascii=True)
    elif name == "toolsmith":
        body["op"] = tool_input.get("action", "protocol")
        if "tool_id" in tool_input:
            body["create_tool_id"] = tool_input["tool_id"]
        if "description" in tool_input:
            body["description"] = tool_input["description"]
        if "command_template" in tool_input:
            body["command_template"] = tool_input["command_template"]
        if "kind" in tool_input:
            body["kind"] = tool_input["kind"]
        if "mode" in tool_input:
            body["mode"] = tool_input["mode"]
        if "input_schema" in tool_input:
            body["input_schema_json"] = json.dumps(tool_input["input_schema"], ensure_ascii=True)
    elif name == "promptsmith":
        body["op"] = tool_input.get("action", "get")
        if "content" in tool_input:
            body["content"] = tool_input["content"]
    elif name == "fzydoc":
        body["query"] = tool_input.get("query", "")
        if "max_lines" in tool_input:
            body["max_lines"] = tool_input["max_lines"]
    else:
        body["tool_input_json"] = json.dumps(tool_input, ensure_ascii=True)
    status, text, parsed = http_json("POST", f"{base_url}/tools/{name}/run", body or {}, timeout=240)
    result = {
        "http_status": status,
        "response": parsed,
    }
    artifact_path = parsed.get("artifact_path") if isinstance(parsed, dict) else None
    if artifact_path:
        try:
            result["artifact"] = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
        except Exception:
            result["artifact_text"] = Path(artifact_path).read_text(encoding="utf-8")
    else:
        result["raw_text"] = text
    result["verification"] = verify_tool_result(base_url, name, tool_input, result)
    return result


def assistant_text_blocks(content) -> str:
    chunks = []
    for block in content:
        if block.get("type") == "text":
            chunks.append(block.get("text", ""))
    return "\n".join(chunk for chunk in chunks if chunk).strip()


def run_turn(base_url: str, model: str, session_name: str, user_text: str, messages):
    messages.append({"role": "user", "content": [{"type": "text", "text": user_text}]})
    while True:
        tool_specs = merged_tool_specs(base_url)
        response = stream_assistant_message(model, load_system_prompt(), messages, tool_specs)
        assistant_content = response.get("content", [])
        messages.append({"role": "assistant", "content": assistant_content})
        text = assistant_text_blocks(assistant_content)
        tool_uses = [block for block in assistant_content if block.get("type") == "tool_use"]
        if not tool_uses:
            save_conversation(session_name, messages)
            return messages
        tool_results = []
        for block in tool_uses:
            tool_name = block["name"]
            tool_input = block.get("input", {})
            print_tool_call(tool_name, tool_input)
            result = call_runtime_tool(base_url, tool_name, tool_input)
            print_tool_result(tool_name, result)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": compact_tool_result(tool_name, result),
                }
            )
        messages.append({"role": "user", "content": tool_results})


def repl(base_url: str, model: str, session_name: str, once: Optional[str]):
    create_runtime_session(base_url)
    messages = load_conversation(session_name)
    if once:
        try:
            run_turn(base_url, model, session_name, once, messages)
        except Exception as err:
            print(style_err("1;31", "agent error"), file=sys.stderr)
            for line in friendly_anthropic_error(err).splitlines():
                print(style_err("31", f"  {line}"), file=sys.stderr)
            raise SystemExit(1)
        return
    print(f"fzyagent agent cli | session={session_name} | model={model}")
    print("type /exit to quit, /reset to clear saved history")
    while True:
        try:
            user_text = input("you> ").strip()
        except EOFError:
            print()
            return
        if not user_text:
            continue
        if user_text == "/exit":
            return
        if user_text == "/reset":
            messages = []
            save_conversation(session_name, messages)
            print("session reset")
            continue
        try:
            messages = run_turn(base_url, model, session_name, user_text, messages)
        except Exception as err:
            print(style_err("1;31", "agent error"), file=sys.stderr)
            for line in friendly_anthropic_error(err).splitlines():
                print(style_err("31", f"  {line}"), file=sys.stderr)


def main():
    load_dotenv(ENV_PATH)
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8905)
    parser.add_argument("--model", default=os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"))
    parser.add_argument("--session", default="default")
    parser.add_argument("--once")
    parser.add_argument("--no-launch", action="store_true")
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    ensure_server(base_url, args.no_launch)
    repl(base_url, args.model, args.session, args.once)


if __name__ == "__main__":
    main()
