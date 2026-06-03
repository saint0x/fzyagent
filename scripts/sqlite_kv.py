#!/usr/bin/env python3
import sqlite3
import sys
import json
import time
from pathlib import Path


def connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=FULL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def atomic_write_text(path, value: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp-{time.time_ns()}")
    tmp.write_text(value, encoding="utf-8")
    tmp.replace(target)


def cmd_boot(db_path: str) -> int:
    with connect(db_path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_kv_key ON kv(key)")
        conn.commit()
    return 0


def cmd_get(db_path: str, key: str) -> int:
    with connect(db_path) as conn:
        row = conn.execute("SELECT value FROM kv WHERE key = ? LIMIT 1", (key,)).fetchone()
    if row is None:
        return 0
    sys.stdout.write(row[0])
    return 0


def cmd_getfile(db_path: str, key: str, out_path: str) -> int:
    with connect(db_path) as conn:
        row = conn.execute("SELECT value FROM kv WHERE key = ? LIMIT 1", (key,)).fetchone()
    value = "" if row is None else row[0]
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(value, encoding="utf-8")
    return 0


def cmd_put(db_path: str, key: str, value: str) -> int:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO kv(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
    return 0


def cmd_delete(db_path: str, key: str) -> int:
    with connect(db_path) as conn:
        conn.execute("DELETE FROM kv WHERE key = ?", (key,))
        conn.commit()
    return 0


def _kv_get(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute("SELECT value FROM kv WHERE key = ? LIMIT 1", (key,)).fetchone()
    return "" if row is None else row[0]


def _kv_put(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO kv(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def _load_progress(conn: sqlite3.Connection, key: str) -> list[dict]:
    raw = _kv_get(conn, key)
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []

def _load_object(conn: sqlite3.Connection, key: str) -> dict:
    raw = _kv_get(conn, key)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _count_active_runs(raw: str) -> int:
    if not raw:
        return 0
    return len([line for line in raw.splitlines() if line.strip()])


def _summary_doc(
    conn: sqlite3.Connection,
    summary_key: str,
    active_runs_key: str,
    latest_run_id: str,
    latest_status: str,
) -> dict:
    current = _load_object(conn, summary_key)
    completed = int(str(current.get("completed_runs", "0") or "0"))
    failed = int(str(current.get("failed_runs", "0") or "0"))
    cancelled = int(str(current.get("cancelled_runs", "0") or "0"))
    if latest_status == "completed":
        completed += 1
    elif latest_status == "failed":
        failed += 1
    elif latest_status == "cancelled":
        cancelled += 1
    active_runs = _count_active_runs(_kv_get(conn, active_runs_key))
    return {
        "status": "ok",
        "active_runs": str(active_runs),
        "completed_runs": str(completed),
        "failed_runs": str(failed),
        "cancelled_runs": str(cancelled),
        "latest_run_id": latest_run_id,
        "latest_status": latest_status,
    }


def _mono_ms() -> str:
    return str(time.time_ns() // 1_000_000)


def _write_debug(path: str, payload: object) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False))


def _run_dir(run_id: str) -> Path:
    return Path("/tmp/fzyagent/longrange/runs") / run_id


def _session_active_run_path(session_id: str) -> Path:
    return Path("/tmp/fzyagent/longrange/sessions") / session_id / "active_run.txt"


def _active_runs_path() -> Path:
    return Path("/tmp/fzyagent/longrange/active_runs.txt")


def _summary_path() -> Path:
    return Path("/tmp/fzyagent/longrange/summary.json")


def _summary_last_write_path() -> Path:
    return Path("/tmp/fzyagent/longrange/summary.json.last.write.json")


def _summary_debug_path() -> Path:
    return Path("/tmp/fzyagent/longrange/summary.rebuild.debug.json")


def _active_run_freshness_window_ms() -> int:
    return 600_000


def _materialize_run_docs(run_id: str, state_doc: dict, progress_doc: object) -> None:
    base = _run_dir(run_id)
    base.mkdir(parents=True, exist_ok=True)
    atomic_write_text(base / "state.materialized.json", json.dumps(state_doc, separators=(",", ":")))
    atomic_write_text(base / "progress.materialized.json", json.dumps(progress_doc, separators=(",", ":")))


def _load_json_file(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _run_status_from_progress_doc(progress_doc) -> str:
    if not isinstance(progress_doc, list):
        return "missing"
    last = ""
    for item in progress_doc:
        if not isinstance(item, dict):
            continue
        phase = str(item.get("phase", "") or "")
        if phase:
            last = phase
    if last == "completed":
        return "completed"
    if last == "failed":
        return "failed"
    if last == "cancelled":
        return "cancelled"
    if last in ("plan_created", "turn_completed", "turn_failed"):
        return "active"
    if last == "started":
        return "planning"
    return "missing"


def _run_status_from_local(run_id: str) -> str:
    state_doc = _load_json_file(_run_dir(run_id) / "state.materialized.json")
    if isinstance(state_doc, dict):
        status = str(state_doc.get("run_status", "") or "")
        if status:
            return status
    return _run_status_from_progress_doc(_load_json_file(_run_dir(run_id) / "progress.materialized.json"))


def _run_stamp(run_id: str) -> int:
    state_doc = _load_json_file(_run_dir(run_id) / "state.materialized.json")
    if not isinstance(state_doc, dict):
        return 0
    raw = (
        str(state_doc.get("completed_at", "") or "")
        or str(state_doc.get("updated_at", "") or "")
        or str(state_doc.get("created_at", "") or "")
    )
    try:
        return int(raw)
    except Exception:
        return 0


def _run_is_freshly_active(run_id: str) -> bool:
    status = _run_status_from_local(run_id)
    if status not in ("planning", "active"):
        return False
    updated_at = _run_stamp(run_id)
    if updated_at <= 0:
        return False
    age = _mono_ms_as_int() - updated_at
    if age < 0:
        return True
    return age <= _active_run_freshness_window_ms()


def _mono_ms_as_int() -> int:
    try:
        return int(_mono_ms())
    except Exception:
        return 0


def cmd_longrange_rebuild_projection(db_path: str) -> int:
    del db_path
    sessions_root = Path("/tmp/fzyagent/longrange/sessions")
    active_ids: list[str] = []
    if sessions_root.exists():
        for active_path in sorted(sessions_root.glob("*/active_run.txt")):
            run_id = active_path.read_text(encoding="utf-8").strip()
            if not run_id:
                continue
            if _run_is_freshly_active(run_id):
                if run_id not in active_ids:
                    active_ids.append(run_id)
            else:
                try:
                    active_path.unlink()
                except FileNotFoundError:
                    pass
    active_payload = ""
    if active_ids:
        active_payload = "\n".join(active_ids) + "\n"
    atomic_write_text(_active_runs_path(), active_payload)
    completed = 0
    failed = 0
    cancelled = 0
    latest_run_id = ""
    latest_status = "idle"
    latest_stamp = 0
    runs_root = Path("/tmp/fzyagent/longrange/runs")
    if runs_root.exists():
        for run_dir in sorted(runs_root.iterdir()):
            if not run_dir.is_dir():
                continue
            run_id = run_dir.name
            status = _run_status_from_local(run_id)
            if status == "missing":
                continue
            if status == "completed":
                completed += 1
            elif status == "failed":
                failed += 1
            elif status == "cancelled":
                cancelled += 1
            stamp = _run_stamp(run_id)
            if not latest_run_id or stamp >= latest_stamp:
                latest_run_id = run_id
                latest_status = status
                latest_stamp = stamp
    summary_doc = {
        "status": "ok",
        "active_runs": str(len(active_ids)),
        "completed_runs": str(completed),
        "failed_runs": str(failed),
        "cancelled_runs": str(cancelled),
        "latest_run_id": latest_run_id,
        "latest_status": latest_status,
    }
    payload = json.dumps(summary_doc, separators=(",", ":"))
    atomic_write_text(_summary_debug_path(), payload)
    atomic_write_text(_summary_last_write_path(), payload)
    atomic_write_text(_summary_path(), payload)
    _write_debug(
        "/tmp/fzyagent/last_longrange_rebuild_projection.json",
        {"active_ids": active_ids, "summary_doc": summary_doc},
    )
    return 0


def _append_unique_line(path: Path, line: str) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = [item.strip() for item in existing.splitlines() if item.strip()]
    if line not in lines:
        lines.append(line)
    payload = ""
    if lines:
        payload = "\n".join(lines) + "\n"
    atomic_write_text(path, payload)


def cmd_longrange_bootstrap_run(
    db_path: str,
    state_key: str,
    progress_key: str,
    run_id: str,
    session_id: str,
    goal: str,
    task_class: str,
    completion_mode: str,
    expected_total_turns: str,
    execution_outlook: str,
    planning_style: str,
    request_id: str,
    created_at: str,
) -> int:
    if not run_id:
        run_id = session_id
    if not state_key and run_id:
        state_key = f"kv:longrange:state:{run_id}"
    if not progress_key and run_id:
        progress_key = f"kv:longrange:progress:{run_id}"
    commit_stamp = created_at or _mono_ms()
    if not created_at:
        created_at = commit_stamp
    _write_debug(
        "/tmp/fzyagent/last_longrange_bootstrap_run_args.json",
        {
            "state_key": state_key,
            "progress_key": progress_key,
            "run_id": run_id,
            "session_id": session_id,
            "goal": goal,
            "task_class": task_class,
            "completion_mode": completion_mode,
            "expected_total_turns": expected_total_turns,
            "execution_outlook": execution_outlook,
            "planning_style": planning_style,
            "request_id": request_id,
            "created_at": created_at,
        },
    )
    state_doc = {
        "status": "ok",
        "run_id": run_id,
        "session_id": session_id,
        "goal": goal,
        "run_status": "planning",
        "plan_status": "missing",
        "task_class": task_class,
        "turns_completed": "0",
        "failure_count": "0",
        "last_progress_score": "0",
        "consecutive_low_score": "0",
        "last_evidence_count": "0",
        "completed_step_count": "0",
        "auto_continue_pending": "true",
        "active_message_kind": "start",
        "latest_summary": "",
        "created_at": created_at,
        "updated_at": commit_stamp,
        "last_request_id": request_id,
    }
    progress_doc = [{
        "run_id": run_id,
        "phase": "started",
        "message_kind": "start",
        "recorded_at": commit_stamp,
        "progress_score": "0",
        "evidence_count": "0",
        "request_id": request_id,
        "detail": goal,
    }]
    meta_doc = {
        "session_id": session_id,
        "goal": goal,
        "created_at": created_at,
    }
    plan_doc = {
        "status": "ok",
        "run_id": run_id,
        "goal_summary": "",
        "finished_definition": "",
        "difficulty": "",
        "estimated_effort": "",
        "task_class": task_class,
        "completion_mode": completion_mode,
        "expected_total_turns": expected_total_turns,
        "execution_outlook": execution_outlook,
        "planning_style": planning_style,
        "plan_summary": "",
        "steps": [],
        "updated_at": commit_stamp,
    }
    with connect(db_path) as conn:
        _write_debug(
            "/tmp/fzyagent/last_longrange_bootstrap_run_commit.json",
            {
                "state_doc": state_doc,
                "progress_doc": progress_doc,
                "meta_doc": meta_doc,
                "plan_doc": plan_doc,
            },
        )
        _kv_put(conn, state_key, json.dumps(state_doc, separators=(",", ":")))
        _kv_put(conn, progress_key, json.dumps(progress_doc, separators=(",", ":")))
        conn.commit()
    base = _run_dir(run_id)
    base.mkdir(parents=True, exist_ok=True)
    atomic_write_text(base / "meta.json", json.dumps(meta_doc, separators=(",", ":")))
    atomic_write_text(base / "session_id.txt", session_id)
    atomic_write_text(base / "goal.txt", goal)
    atomic_write_text(base / "created_at.txt", created_at)
    atomic_write_text(base / "plan.json", json.dumps(plan_doc, separators=(",", ":")))
    atomic_write_text(base / "queue.jsonl", "")
    if session_id:
        atomic_write_text(_session_active_run_path(session_id), run_id)
    if run_id:
        _append_unique_line(_active_runs_path(), run_id)
        atomic_write_text("/tmp/fzyagent/last_longrange_bootstrap_active_runs.txt", _active_runs_path().read_text(encoding="utf-8"))
    _materialize_run_docs(run_id, state_doc, progress_doc)
    return 0


def cmd_longrange_update_turn(
    db_path: str,
    state_key: str,
    progress_key: str,
    run_id: str,
    session_id: str,
    goal: str,
    run_status: str,
    plan_status: str,
    task_class: str,
    turns_completed: str,
    failure_count: str,
    last_progress_score: str,
    consecutive_low_score: str,
    last_evidence_count: str,
    completed_step_count: str,
    auto_continue_pending: str,
    active_message_kind: str,
    latest_summary: str,
    created_at: str,
    updated_at: str,
    current_step_id: str,
    last_request_id: str,
    completed_at: str,
    progress_phase: str,
    progress_message_kind: str,
    progress_recorded_at: str,
    progress_score: str,
    progress_evidence_count: str,
    progress_request_id: str,
    progress_detail: str,
) -> int:
    if not run_id:
        run_id = session_id
    if not state_key and run_id:
        state_key = f"kv:longrange:state:{run_id}"
    if not progress_key and run_id:
        progress_key = f"kv:longrange:progress:{run_id}"
    _write_debug(
        "/tmp/fzyagent/last_longrange_update_turn_args.json",
        {
            "state_key": state_key,
            "progress_key": progress_key,
            "run_id": run_id,
            "session_id": session_id,
            "goal": goal,
            "run_status": run_status,
            "plan_status": plan_status,
            "task_class": task_class,
            "turns_completed": turns_completed,
            "failure_count": failure_count,
            "last_progress_score": last_progress_score,
            "consecutive_low_score": consecutive_low_score,
            "last_evidence_count": last_evidence_count,
            "completed_step_count": completed_step_count,
            "auto_continue_pending": auto_continue_pending,
            "active_message_kind": active_message_kind,
            "latest_summary": latest_summary,
            "created_at": created_at,
            "updated_at": updated_at,
            "current_step_id": current_step_id,
            "last_request_id": last_request_id,
            "completed_at": completed_at,
            "progress_phase": progress_phase,
            "progress_message_kind": progress_message_kind,
            "progress_recorded_at": progress_recorded_at,
            "progress_score": progress_score,
            "progress_evidence_count": progress_evidence_count,
            "progress_request_id": progress_request_id,
            "progress_detail": progress_detail,
        },
    )
    commit_stamp = updated_at or progress_recorded_at or created_at or _mono_ms()
    if not created_at:
        created_at = commit_stamp
    effective_updated_at = updated_at or commit_stamp
    effective_recorded_at = progress_recorded_at or effective_updated_at
    effective_completed_at = completed_at
    if run_status in ("failed", "completed", "cancelled") and not effective_completed_at:
        effective_completed_at = effective_updated_at
    state_doc = {
        "status": "ok",
        "run_id": run_id,
        "session_id": session_id,
        "goal": goal,
        "run_status": run_status,
        "plan_status": plan_status,
        "task_class": task_class,
        "turns_completed": turns_completed,
        "failure_count": failure_count,
        "last_progress_score": last_progress_score,
        "consecutive_low_score": consecutive_low_score,
        "last_evidence_count": last_evidence_count,
        "completed_step_count": completed_step_count,
        "auto_continue_pending": auto_continue_pending,
        "active_message_kind": active_message_kind,
        "latest_summary": latest_summary,
        "created_at": created_at,
        "updated_at": effective_updated_at,
    }
    if current_step_id:
        state_doc["current_step_id"] = current_step_id
    if last_request_id:
        state_doc["last_request_id"] = last_request_id
    if effective_completed_at:
        state_doc["completed_at"] = effective_completed_at
    progress_doc = {
        "run_id": run_id,
        "phase": progress_phase,
        "message_kind": progress_message_kind,
        "recorded_at": effective_recorded_at,
        "progress_score": progress_score,
        "evidence_count": progress_evidence_count,
    }
    if progress_request_id:
        progress_doc["request_id"] = progress_request_id
    if progress_detail:
        progress_doc["detail"] = progress_detail
    with connect(db_path) as conn:
        progress_before = _load_progress(conn, progress_key)
        progress = list(progress_before)
        progress.append(progress_doc)
        _write_debug(
            "/tmp/fzyagent/last_longrange_update_turn_commit.json",
            {
                "commit_stamp": commit_stamp,
                "state_doc": state_doc,
                "progress_before": progress_before,
                "progress_after": progress,
            },
        )
        _kv_put(conn, state_key, json.dumps(state_doc, separators=(",", ":")))
        _kv_put(conn, progress_key, json.dumps(progress, separators=(",", ":")))
        conn.commit()
    _materialize_run_docs(run_id, state_doc, progress)
    return 0


def cmd_longrange_terminalize(
    db_path: str,
    state_key: str,
    progress_key: str,
    session_active_key: str,
    summary_key: str,
    active_runs_key: str,
    run_id: str,
    session_id: str,
    goal: str,
    run_status: str,
    plan_status: str,
    task_class: str,
    turns_completed: str,
    failure_count: str,
    last_progress_score: str,
    consecutive_low_score: str,
    last_evidence_count: str,
    completed_step_count: str,
    active_message_kind: str,
    latest_summary: str,
    created_at: str,
    current_step_id: str,
    last_request_id: str,
    progress_phase: str,
    progress_message_kind: str,
    progress_score: str,
    progress_evidence_count: str,
    progress_request_id: str,
    progress_detail: str,
) -> int:
    if not run_id:
        run_id = session_id
    if not state_key and run_id:
        state_key = f"kv:longrange:state:{run_id}"
    if not progress_key and run_id:
        progress_key = f"kv:longrange:progress:{run_id}"
    _write_debug(
        "/tmp/fzyagent/last_longrange_terminalize_args.json",
        {
            "state_key": state_key,
            "progress_key": progress_key,
            "session_active_key": session_active_key,
            "summary_key": summary_key,
            "active_runs_key": active_runs_key,
            "run_id": run_id,
            "session_id": session_id,
            "goal": goal,
            "run_status": run_status,
            "plan_status": plan_status,
            "task_class": task_class,
            "turns_completed": turns_completed,
            "failure_count": failure_count,
            "last_progress_score": last_progress_score,
            "consecutive_low_score": consecutive_low_score,
            "last_evidence_count": last_evidence_count,
            "completed_step_count": completed_step_count,
            "active_message_kind": active_message_kind,
            "latest_summary": latest_summary,
            "created_at": created_at,
            "current_step_id": current_step_id,
            "last_request_id": last_request_id,
            "progress_phase": progress_phase,
            "progress_message_kind": progress_message_kind,
            "progress_score": progress_score,
            "progress_evidence_count": progress_evidence_count,
            "progress_request_id": progress_request_id,
            "progress_detail": progress_detail,
        },
    )
    commit_stamp = _mono_ms()
    if not created_at:
        created_at = commit_stamp
    state_doc = {
        "status": "ok",
        "run_id": run_id,
        "session_id": session_id,
        "goal": goal,
        "run_status": run_status,
        "plan_status": plan_status,
        "task_class": task_class,
        "turns_completed": turns_completed,
        "failure_count": failure_count,
        "last_progress_score": last_progress_score,
        "consecutive_low_score": consecutive_low_score,
        "last_evidence_count": last_evidence_count,
        "completed_step_count": completed_step_count,
        "auto_continue_pending": "false",
        "active_message_kind": active_message_kind,
        "latest_summary": latest_summary,
        "created_at": created_at,
        "updated_at": commit_stamp,
        "completed_at": commit_stamp,
    }
    if current_step_id:
        state_doc["current_step_id"] = current_step_id
    if last_request_id:
        state_doc["last_request_id"] = last_request_id
    progress_doc = {
        "run_id": run_id,
        "phase": progress_phase,
        "message_kind": progress_message_kind,
        "recorded_at": commit_stamp,
        "progress_score": progress_score,
        "evidence_count": progress_evidence_count,
    }
    if progress_request_id:
        progress_doc["request_id"] = progress_request_id
    if progress_detail:
        progress_doc["detail"] = progress_detail
    with connect(db_path) as conn:
        progress = _load_progress(conn, progress_key)
        progress.append(progress_doc)
        _kv_put(conn, state_key, json.dumps(state_doc, separators=(",", ":")))
        _kv_put(conn, progress_key, json.dumps(progress, separators=(",", ":")))
        if _kv_get(conn, session_active_key) == run_id:
            conn.execute("DELETE FROM kv WHERE key = ?", (session_active_key,))
        summary = _summary_doc(conn, summary_key, active_runs_key, run_id, run_status)
        _kv_put(conn, summary_key, json.dumps(summary, separators=(",", ":")))
        conn.commit()
    _materialize_run_docs(run_id, state_doc, progress)
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: sqlite_kv.py <boot|get|put|delete|longrange_bootstrap_run|longrange_rebuild_projection|longrange_update_turn|longrange_terminalize> <db_path> [...]", file=sys.stderr)
        return 2
    op = argv[1]
    db_path = argv[2]
    if op == "boot":
        return cmd_boot(db_path)
    if op == "get":
        if len(argv) != 4:
            print("usage: sqlite_kv.py get <db_path> <key>", file=sys.stderr)
            return 2
        return cmd_get(db_path, argv[3])
    if op == "put":
        if len(argv) != 5:
            print("usage: sqlite_kv.py put <db_path> <key> <value>", file=sys.stderr)
            return 2
        return cmd_put(db_path, argv[3], argv[4])
    if op == "getfile":
        if len(argv) != 5:
            print("usage: sqlite_kv.py getfile <db_path> <key> <out_path>", file=sys.stderr)
            return 2
        return cmd_getfile(db_path, argv[3], argv[4])
    if op == "delete":
        if len(argv) != 4:
            print("usage: sqlite_kv.py delete <db_path> <key>", file=sys.stderr)
            return 2
        return cmd_delete(db_path, argv[3])
    if op == "longrange_bootstrap_run":
        if len(argv) != 15:
            print("usage: sqlite_kv.py longrange_bootstrap_run <db_path> <state_key> <progress_key> <run_id> <session_id> <goal> <task_class> <completion_mode> <expected_total_turns> <execution_outlook> <planning_style> <request_id> <created_at>", file=sys.stderr)
            return 2
        return cmd_longrange_bootstrap_run(
            argv[2], argv[3], argv[4], argv[5], argv[6], argv[7], argv[8], argv[9], argv[10],
            argv[11], argv[12], argv[13], argv[14]
        )
    if op == "longrange_rebuild_projection":
        if len(argv) != 3:
            print("usage: sqlite_kv.py longrange_rebuild_projection <db_path>", file=sys.stderr)
            return 2
        return cmd_longrange_rebuild_projection(argv[2])
    if op == "longrange_update_turn":
        if len(argv) != 32:
            print("usage: sqlite_kv.py longrange_update_turn <db_path> <state_key> <progress_key> <run_id> <session_id> <goal> <run_status> <plan_status> <task_class> <turns_completed> <failure_count> <last_progress_score> <consecutive_low_score> <last_evidence_count> <completed_step_count> <auto_continue_pending> <active_message_kind> <latest_summary> <created_at> <updated_at> <current_step_id> <last_request_id> <completed_at> <progress_phase> <progress_message_kind> <progress_recorded_at> <progress_score> <progress_evidence_count> <progress_request_id> <progress_detail>", file=sys.stderr)
            return 2
        return cmd_longrange_update_turn(
            argv[2], argv[3], argv[4], argv[5], argv[6], argv[7], argv[8], argv[9], argv[10],
            argv[11], argv[12], argv[13], argv[14], argv[15], argv[16], argv[17], argv[18],
            argv[19], argv[20], argv[21], argv[22], argv[23], argv[24], argv[25], argv[26],
            argv[27], argv[28], argv[29], argv[30], argv[31]
        )
    if op == "longrange_terminalize":
        if len(argv) != 31:
            print("usage: sqlite_kv.py longrange_terminalize <db_path> <state_key> <progress_key> <session_active_key> <summary_key> <active_runs_key> <run_id> <session_id> <goal> <run_status> <plan_status> <task_class> <turns_completed> <failure_count> <last_progress_score> <consecutive_low_score> <last_evidence_count> <completed_step_count> <active_message_kind> <latest_summary> <created_at> <current_step_id> <last_request_id> <progress_phase> <progress_message_kind> <progress_score> <progress_evidence_count> <progress_request_id> <progress_detail>", file=sys.stderr)
            return 2
        return cmd_longrange_terminalize(
            argv[2], argv[3], argv[4], argv[5], argv[6], argv[7], argv[8], argv[9], argv[10],
            argv[11], argv[12], argv[13], argv[14], argv[15], argv[16], argv[17], argv[18],
            argv[19], argv[20], argv[21], argv[22], argv[23], argv[24], argv[25], argv[26],
            argv[27], argv[28], argv[29], argv[30]
        )
    print(f"unknown op: {op}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
