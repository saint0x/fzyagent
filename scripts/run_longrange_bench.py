#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path("/Users/deepsaint/Desktop/fzyagent")
DEFAULT_BIN = ROOT / ".fz/build/fzyagent"
DEFAULT_TEMPLATE = ROOT / "bench/longrange/fzl_desktop_project.goal.md"
DEFAULT_FZL_SOURCE_DIR = Path("/Users/deepsaint/Desktop/fozzylang/src")
DEFAULT_FZL_SHOWCASE_PATH = Path("/Users/deepsaint/Desktop/fozzylang/fzl-showcase.html")


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or "bench"


def load_template(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def fill_template(template: str, *, target_project_dir: Path, fzl_source_dir: Path, fzl_showcase_path: Path) -> str:
    return (
        template.replace("__TARGET_PROJECT_DIR__", str(target_project_dir))
        .replace("__FZL_SOURCE_DIR__", str(fzl_source_dir))
        .replace("__FZL_SHOWCASE_PATH__", str(fzl_showcase_path))
    )


def parse_longrange_stdout(stdout: str) -> dict[str, str]:
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if "{" not in line or not line.endswith("}"):
            continue
        candidate = line[line.find("{") :]
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if payload.get("tool") == "longrange_start":
            return {
                "run_id": str(payload.get("run_id", "")),
                "status": str(payload.get("status", "")),
                "summary": str(payload.get("summary", "")),
            }
    return {"run_id": "", "status": "", "summary": ""}


def read_optional_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the checked-in long-range FZY/FZL benchmark harness against a selected model."
    )
    parser.add_argument("--model", default="claude-fable-5", help="Anthropic model name to use.")
    parser.add_argument("--session", default="", help="Optional explicit long-range session id.")
    parser.add_argument("--state-root", default="", help="Optional AGENT_STATE_DIR override.")
    parser.add_argument("--target-project-dir", default="", help="Where the benchmarked model should create the FZY project.")
    parser.add_argument("--goal-template", default=str(DEFAULT_TEMPLATE), help="Goal template path.")
    parser.add_argument("--bin", default=str(DEFAULT_BIN), help="Path to the fzyagent binary.")
    parser.add_argument("--output", default="", help="Optional JSON result path.")
    parser.add_argument("--dry-run", action="store_true", help="Render the goal and exit without running the model.")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    model_slug = slugify(args.model)
    session_id = args.session or f"longrange-{model_slug}-{stamp}"
    target_project_dir = Path(
        args.target_project_dir or f"/Users/deepsaint/Desktop/{model_slug}-fzl-bench-{stamp}"
    )
    state_root = Path(args.state_root or f"/tmp/fzyagent/longrangebench/{model_slug}/{stamp}")
    output_path = Path(args.output or state_root / "result.json")
    template_path = Path(args.goal_template)
    bin_path = Path(args.bin)

    goal = fill_template(
        load_template(template_path),
        target_project_dir=target_project_dir,
        fzl_source_dir=DEFAULT_FZL_SOURCE_DIR,
        fzl_showcase_path=DEFAULT_FZL_SHOWCASE_PATH,
    )

    if args.dry_run:
        print(goal)
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["AGENT_PROVIDER"] = "anthropic"
    env["AGENT_MODEL"] = args.model
    env["AGENT_PROJECT_DIR"] = str(ROOT)
    env["AGENT_STATE_DIR"] = str(state_root)
    env["AGENT_OBSERVABILITY_MODE"] = "verbose"

    cmd = [
        str(bin_path),
        "longrange-start",
        "--session",
        session_id,
        "--goal",
        goal,
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True)
    summary = parse_longrange_stdout(proc.stdout)
    run_id = summary["run_id"]

    longrange_root = state_root / "longrange"
    run_dir = longrange_root / "runs" / run_id if run_id else Path("")
    result = {
        "schema_version": "fzyagent.longrangebench.v1",
        "started_at": now.isoformat(),
        "model": args.model,
        "session_id": session_id,
        "target_project_dir": str(target_project_dir),
        "state_root": str(state_root),
        "fzl_source_dir": str(DEFAULT_FZL_SOURCE_DIR),
        "fzl_showcase_path": str(DEFAULT_FZL_SHOWCASE_PATH),
        "command": cmd,
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "goal": goal,
        "run_id": run_id,
        "status": summary["status"],
        "summary": summary["summary"],
        "artifacts": {
            "longrange_summary": str(longrange_root / "summary.json"),
            "run_dir": str(run_dir) if run_id else "",
            "run_plan": str(run_dir / "plan.json") if run_id else "",
            "run_state": str(run_dir / "state.materialized.json") if run_id else "",
            "run_progress": str(run_dir / "progress.materialized.json") if run_id else "",
            "provider_dispatch": str(state_root / "provider.dispatch.json"),
            "provider_dispatch_result": str(state_root / "provider.dispatch.result.json"),
        },
        "artifact_contents": {
            "longrange_summary": read_optional_text(longrange_root / "summary.json"),
            "run_plan": read_optional_text(run_dir / "plan.json") if run_id else "",
            "run_state": read_optional_text(run_dir / "state.materialized.json") if run_id else "",
            "run_progress": read_optional_text(run_dir / "progress.materialized.json") if run_id else "",
        },
    }
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "ok" if proc.returncode == 0 else "error",
                "model": args.model,
                "run_id": run_id,
                "longrange_status": summary["status"],
                "summary": summary["summary"],
                "result_path": str(output_path),
            }
        )
    )
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
