#!/usr/bin/env python3
import json
from pathlib import Path


ROOT = Path("/Users/deepsaint/Desktop/fzyagent")
CUSTOM_TOOLS_DIR = ROOT / "custom_tools"
REGISTRY_PATH = Path("/tmp/fzyagent/registry.json")


BUILTINS = [
    {"id": "bash", "kind": "process", "health": "ready", "mode": "single", "description": "Run a shell command in the shared workspace."},
    {"id": "parallel_bash", "kind": "process", "health": "ready", "mode": "parallel", "description": "Run two shell commands in parallel."},
    {"id": "grep_search", "kind": "process", "health": "ready", "mode": "search", "description": "Search the workspace with grep."},
    {"id": "parallel_grep", "kind": "process", "health": "ready", "mode": "parallel", "description": "Run two grep searches in parallel."},
    {"id": "release_audit", "kind": "workflow", "health": "ready", "mode": "parallel", "description": "Run a release-oriented multi-signal workflow."},
    {"id": "timeout_probe", "kind": "process", "health": "ready", "mode": "bounded", "description": "Intentionally probe timeout/error behavior."},
    {"id": "workspace_digest", "kind": "process", "health": "ready", "mode": "analysis", "description": "Summarize the current workspace."},
    {"id": "project_seed", "kind": "workflow", "health": "ready", "mode": "parallel", "description": "Assemble a richer project context bundle."},
    {"id": "aegis", "kind": "browser", "health": "ready", "mode": "headless", "description": "Use the Aegis browser runtime."},
    {"id": "browser_ops_seed", "kind": "workflow", "health": "ready", "mode": "parallel", "description": "Assemble a browser-oriented context bundle."},
    {"id": "toolsmith", "kind": "workflow", "health": "ready", "mode": "authoring", "description": "Create and inspect custom runtime tools."},
    {"id": "promptsmith", "kind": "workflow", "health": "ready", "mode": "authoring", "description": "Inspect and update the agent system prompt."},
    {"id": "fzydoc", "kind": "docs", "health": "ready", "mode": "analysis", "description": "Search local FZY docs and showcase material."},
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


def main():
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = build_registry()
    REGISTRY_PATH.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=True))


if __name__ == "__main__":
    main()
