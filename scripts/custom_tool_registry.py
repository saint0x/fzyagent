#!/usr/bin/env python3
import json
from pathlib import Path


ROOT = Path("/Users/deepsaint/Desktop/fzyagent")
CUSTOM_TOOLS_DIR = ROOT / "custom_tools"
REGISTRY_PATH = Path("/tmp/fzyagent/registry.json")
TOOLS_ARRAY_PATH = Path("/tmp/fzyagent/registry.tools.json")
ANTHROPIC_TOOLS_ARRAY_PATH = Path("/tmp/fzyagent/registry.anthropic.tools.json")


BUILTINS = [
    {
        "id": "bash",
        "kind": "process",
        "health": "ready",
        "mode": "single",
        "description": "Run a shell command in the shared workspace.",
        "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
    },
    {
        "id": "parallel_bash",
        "kind": "process",
        "health": "ready",
        "mode": "parallel",
        "description": "Run two shell commands in parallel.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "id": "grep_search",
        "kind": "process",
        "health": "ready",
        "mode": "search",
        "description": "Search the workspace with grep.",
        "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}, "target": {"type": "string"}}, "required": ["pattern"]},
    },
    {
        "id": "parallel_grep",
        "kind": "process",
        "health": "ready",
        "mode": "parallel",
        "description": "Run two grep searches in parallel.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "id": "release_audit",
        "kind": "workflow",
        "health": "ready",
        "mode": "parallel",
        "description": "Run a release-oriented multi-signal workflow.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "id": "timeout_probe",
        "kind": "process",
        "health": "ready",
        "mode": "bounded",
        "description": "Intentionally probe timeout/error behavior.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "id": "workspace_digest",
        "kind": "process",
        "health": "ready",
        "mode": "analysis",
        "description": "Summarize the current workspace.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "id": "project_seed",
        "kind": "workflow",
        "health": "ready",
        "mode": "parallel",
        "description": "Assemble a richer project context bundle.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "id": "aegis",
        "kind": "browser",
        "health": "ready",
        "mode": "headless",
        "description": "Use the Aegis browser runtime.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "url": {"type": "string"},
                "query": {"type": "string"},
                "eval_js": {"type": "string"},
                "commands_json": {"type": "string"},
            },
            "required": ["action"],
        },
    },
    {
        "id": "browser_ops_seed",
        "kind": "workflow",
        "health": "ready",
        "mode": "parallel",
        "description": "Assemble a browser-oriented context bundle.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "id": "toolsmith",
        "kind": "workflow",
        "health": "ready",
        "mode": "authoring",
        "description": "Create and inspect custom runtime tools.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "tool_id": {"type": "string"},
                "description": {"type": "string"},
                "command_template": {"type": "string"},
                "input_schema_json": {"type": "string"},
                "kind": {"type": "string"},
                "mode": {"type": "string"},
            },
            "required": ["action"],
        },
    },
    {
        "id": "promptsmith",
        "kind": "workflow",
        "health": "ready",
        "mode": "authoring",
        "description": "Inspect and update the agent system prompt.",
        "input_schema": {"type": "object", "properties": {"action": {"type": "string"}, "content": {"type": "string"}}, "required": ["action"]},
    },
    {
        "id": "fzydoc",
        "kind": "docs",
        "health": "ready",
        "mode": "analysis",
        "description": "Search local FZY docs and showcase material.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "max_lines": {"type": "string"}}, "required": ["query"]},
    },
]


def load_custom_tools():
    tools = []
    if not CUSTOM_TOOLS_DIR.exists():
        return tools
    for manifest in sorted(CUSTOM_TOOLS_DIR.glob("*/tool.json")):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            continue
        tool_id = data.get("id", "")
        if not tool_id:
            continue
        tools.append(
            {
                "id": tool_id,
                "description": data.get("description", ""),
                "kind": data.get("kind", "process"),
                "health": "ready",
                "mode": data.get("mode", "single"),
                "origin": "custom",
                "input_schema": data.get("input_schema", {"type": "object", "properties": {}}),
            }
        )
    return tools


def build_registry():
    tools = BUILTINS + load_custom_tools()
    for tool in tools:
        if "name" not in tool:
            tool["name"] = tool.get("id", "")
        if "input_schema" not in tool:
            tool["input_schema"] = {"type": "object", "properties": {}}
    return {
        "status": "ok",
        "tools": tools,
        "meta": {
            "registry_version": "2026-05-27",
            "provider": "anthropic",
            "deterministic": "true",
            "project": "fzyagent",
        },
    }


def anthropic_tools(tools):
    out = []
    for tool in tools:
        out.append(
            {
                "name": tool.get("name", tool.get("id", "")),
                "description": tool.get("description", ""),
                "input_schema": tool.get("input_schema", {"type": "object", "properties": {}}),
            }
        )
    return out


def main():
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = build_registry()
    REGISTRY_PATH.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    TOOLS_ARRAY_PATH.write_text(json.dumps(payload["tools"], ensure_ascii=True), encoding="utf-8")
    ANTHROPIC_TOOLS_ARRAY_PATH.write_text(json.dumps(anthropic_tools(payload["tools"]), ensure_ascii=True), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=True))


if __name__ == "__main__":
    main()
