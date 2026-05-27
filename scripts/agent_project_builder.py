#!/usr/bin/env python3
import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


def request(base_url, method, path, body=None, timeout=240):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["content-type"] = "application/json"
    req = urllib.request.Request(base_url + path, data=data, headers=headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            elapsed = round((time.perf_counter() - started) * 1000.0, 2)
            return resp.status, text, elapsed
    except urllib.error.HTTPError as err:
        text = err.read().decode("utf-8", errors="replace")
        elapsed = round((time.perf_counter() - started) * 1000.0, 2)
        return err.code, text, elapsed


def ensure_ok(status, text, label):
    if status != 200:
        raise RuntimeError(f"{label} failed: status={status} body={text[:800]}")


def ask_agent(base_url, prompt):
    status, text, elapsed = request(
        base_url,
        "POST",
        "/sessions/demo/messages",
        {"message": prompt},
        timeout=360,
    )
    ensure_ok(status, text, "agent_message")
    payload = json.loads(text)
    response_raw = payload["data"]["response"]
    response_json = json.loads(response_raw)
    content = response_json.get("content", [])
    text_parts = [item.get("text", "") for item in content if item.get("type") == "text"]
    return {
        "elapsed_ms": elapsed,
        "text": "\n".join(text_parts).strip(),
        "raw": payload,
    }


def run_tool(base_url, tool_id):
    status, text, elapsed = request(base_url, "POST", f"/tools/{tool_id}/run", timeout=240)
    ensure_ok(status, text, f"tool:{tool_id}")
    return {"elapsed_ms": elapsed, "raw": json.loads(text)}


def get_run(base_url, run_id):
    status, text, elapsed = request(base_url, "GET", f"/runs/{run_id}", timeout=120)
    ensure_ok(status, text, f"run:{run_id}")
    return {"elapsed_ms": elapsed, "raw": json.loads(text), "text": text}


def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8902")
    parser.add_argument("--out-dir", default="/Users/deepsaint/Desktop/fzyagent/generated/agent_runtime_handbook")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    metrics = {
        "base_url": args.base_url,
        "started_at_epoch_ms": int(time.time() * 1000),
        "tools": {},
        "messages": {},
    }

    project_seed = run_tool(args.base_url, "project_seed")
    workspace_digest = run_tool(args.base_url, "workspace_digest")
    release_audit = run_tool(args.base_url, "release_audit")
    parallel_grep = run_tool(args.base_url, "parallel_grep")

    metrics["tools"]["project_seed"] = project_seed["elapsed_ms"]
    metrics["tools"]["workspace_digest"] = workspace_digest["elapsed_ms"]
    metrics["tools"]["release_audit"] = release_audit["elapsed_ms"]
    metrics["tools"]["parallel_grep"] = parallel_grep["elapsed_ms"]

    seed_doc = get_run(args.base_url, "project_seed_latest")
    digest_doc = get_run(args.base_url, "workspace_digest_latest")
    audit_doc = get_run(args.base_url, "release_audit_latest")
    grep_doc = get_run(args.base_url, "parallel_grep_latest")

    context_bundle = (
        "PROJECT SEED\n" + seed_doc["text"][:12000] +
        "\n\nWORKSPACE DIGEST\n" + digest_doc["text"][:12000] +
        "\n\nRELEASE AUDIT\n" + audit_doc["text"][:12000] +
        "\n\nPARALLEL GREP\n" + grep_doc["text"][:12000]
    )

    readme_prompt = (
        "Create a concise README for a project called Agent Runtime Handbook. "
        "It should explain what this handbook is, what evidence it is based on, "
        "and how an operator should use it. Use markdown with short sections.\n\n"
        + context_bundle
    )
    architecture_prompt = (
        "Write an architecture overview document in markdown for this runtime. "
        "Cover HTTP flow, tool execution flow, concurrency model, persistence, and observability. "
        "Keep it practical and grounded in the provided evidence.\n\n"
        + context_bundle
    )
    operations_prompt = (
        "Write an operations runbook in markdown. Include startup, health validation, key live endpoints, "
        "how to inspect generated artifacts, and a short incident checklist. Use only the provided evidence.\n\n"
        + context_bundle
    )
    roadmap_prompt = (
        "Write a production hardening roadmap in markdown with 8 concrete items. "
        "Separate app-level work from language/runtime-facing risks. Keep each item short and actionable.\n\n"
        + context_bundle
    )

    readme = ask_agent(args.base_url, readme_prompt)
    architecture = ask_agent(args.base_url, architecture_prompt)
    operations = ask_agent(args.base_url, operations_prompt)
    roadmap = ask_agent(args.base_url, roadmap_prompt)

    metrics["messages"]["readme_ms"] = readme["elapsed_ms"]
    metrics["messages"]["architecture_ms"] = architecture["elapsed_ms"]
    metrics["messages"]["operations_ms"] = operations["elapsed_ms"]
    metrics["messages"]["roadmap_ms"] = roadmap["elapsed_ms"]

    write_text(out_dir / "README.md", readme["text"])
    write_text(out_dir / "ARCHITECTURE.md", architecture["text"])
    write_text(out_dir / "OPERATIONS.md", operations["text"])
    write_text(out_dir / "ROADMAP.md", roadmap["text"])
    write_text(out_dir / "context.project_seed.json", json.dumps(seed_doc["raw"], indent=2))
    write_text(out_dir / "context.workspace_digest.json", json.dumps(digest_doc["raw"], indent=2))
    write_text(out_dir / "context.release_audit.json", json.dumps(audit_doc["raw"], indent=2))
    write_text(out_dir / "context.parallel_grep.json", json.dumps(grep_doc["raw"], indent=2))

    metrics["finished_at_epoch_ms"] = int(time.time() * 1000)
    write_text(out_dir / "build_metrics.json", json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
