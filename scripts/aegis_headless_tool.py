#!/usr/bin/env python3
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


AEGIS_ROOT = Path(os.environ.get("AEGIS_ROOT", "/Users/deepsaint/Desktop/aegis"))
STATE_DIR = Path(os.environ.get("AEGIS_TOOL_STATE_DIR", "/tmp/fzyagent/aegis"))
STATE_DIR.mkdir(parents=True, exist_ok=True)
PID_PATH = STATE_DIR / "serve.pid"
LOG_PATH = STATE_DIR / "serve.log"
LAST_RESPONSE_PATH = STATE_DIR / "last_response.json"
DEFAULT_PORT = int(os.environ.get("AEGIS_PORT", "7979"))
DEFAULT_ADDR = f"127.0.0.1:{DEFAULT_PORT}"


def tcp_ready(host: str, port: int, timeout_s: float = 0.5) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout_s)
    try:
        sock.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def http_request(base_url: str, method: str, path: str, body=None, timeout=120):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["content-type"] = "application/json"
    req = urllib.request.Request(base_url + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            parsed = None
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
            return {
                "ok": True,
                "status": resp.status,
                "text": text,
                "json": parsed,
            }
    except urllib.error.HTTPError as err:
        raw = err.read()
        text = raw.decode("utf-8", errors="replace")
        parsed = None
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        return {
            "ok": False,
            "status": err.code,
            "text": text,
            "json": parsed,
        }
    except Exception as err:
        return {
            "ok": False,
            "status": 0,
            "text": str(err),
            "json": None,
        }


def read_pid():
    if not PID_PATH.exists():
        return None
    try:
        return int(PID_PATH.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def ensure_server():
    host = "127.0.0.1"
    port = DEFAULT_PORT
    pid = read_pid()
    if tcp_ready(host, port):
        return {"started": False, "pid": pid, "addr": DEFAULT_ADDR}
    if pid is not None and not pid_alive(pid):
        try:
            PID_PATH.unlink()
        except FileNotFoundError:
            pass

    env = os.environ.copy()
    env.setdefault("CARGO_TERM_COLOR", "never")
    mode = os.environ.get("AEGIS_MODE", "headless")
    profile = os.environ.get("AEGIS_PROFILE", "default")
    explicit_bin = os.environ.get("AEGIS_BIN", "").strip()
    if explicit_bin:
        cmd = [explicit_bin, "--mode", mode, "--profile", profile]
    else:
        cmd = [
            "cargo",
            "run",
            "--",
            "--mode",
            mode,
            "--profile",
            profile,
        ]
    start_url = os.environ.get("AEGIS_START_URL", "").strip()
    if start_url:
        cmd.extend(["--start-url", start_url])
    cmd.extend(["serve", "--addr", DEFAULT_ADDR])

    with LOG_PATH.open("ab") as log_handle:
        proc = subprocess.Popen(
            cmd,
            cwd=str(AEGIS_ROOT),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
    PID_PATH.write_text(str(proc.pid), encoding="utf-8")

    deadline = time.time() + 45.0
    base_url = f"http://{DEFAULT_ADDR}"
    while time.time() < deadline:
        if tcp_ready(host, port):
            health = http_request(base_url, "GET", "/readyz", timeout=5)
            if health["status"] in (200, 503):
                break
        time.sleep(0.25)
    else:
        raise RuntimeError(f"aegis serve did not become reachable on {DEFAULT_ADDR}")

    ready_deadline = time.time() + 60.0
    while time.time() < ready_deadline:
        ready = http_request(base_url, "GET", "/readyz", timeout=5)
        if ready["status"] == 200:
            return {"started": True, "pid": proc.pid, "addr": DEFAULT_ADDR}
        time.sleep(0.5)
    raise RuntimeError("aegis serve reachable but not command-ready before timeout")


def env_json(name: str, fallback):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return fallback
    return json.loads(raw)


def persist_full_payload(payload):
    LAST_RESPONSE_PATH.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def summarize_result(action: str, payload: dict, result: dict):
    summary = {
        "tool": "aegis",
        "action": action,
        "server": payload["server"],
        "artifact_path": str(LAST_RESPONSE_PATH),
        "response": {
            "ok": result["ok"],
            "status": result["status"],
        },
    }
    parsed = result.get("json")
    if isinstance(parsed, dict):
        diagnostics = parsed.get("diagnostics")
        runtime = None
        if isinstance(diagnostics, dict):
            summary["response"]["state"] = diagnostics.get("state")
            runtime = diagnostics.get("runtime")
        if isinstance(runtime, dict):
            summary["response"]["current_url"] = runtime.get("current_url")
            summary["response"]["current_title"] = runtime.get("current_title")
            summary["response"]["dom_nodes"] = runtime.get("dom_nodes")
            summary["response"]["retained_event_count"] = runtime.get("retained_event_count")
        if action == "dom" and isinstance(parsed.get("nodes"), list):
            summary["response"]["node_count"] = len(parsed["nodes"])
        if action == "events" and isinstance(parsed.get("events"), list):
            summary["response"]["event_count"] = len(parsed["events"])
        if action == "execute" and isinstance(parsed.get("results"), list):
            summary["response"]["result_count"] = len(parsed["results"])
    if "state" not in summary["response"]:
        summary["response"]["text_preview"] = result["text"][:400]
    return summary


def main():
    action = os.environ.get("AEGIS_ACTION", "runtime").strip() or "runtime"
    boot = ensure_server()
    base_url = f"http://{boot['addr']}"
    payload = {
        "tool": "aegis",
        "action": action,
        "server": {
            "addr": boot["addr"],
            "pid": boot["pid"],
            "started_this_run": boot["started"],
            "log_path": str(LOG_PATH),
            "launch_mode": "explicit_bin" if os.environ.get("AEGIS_BIN", "").strip() else "cargo_run",
        },
    }

    if action == "runtime":
        result = http_request(base_url, "GET", "/runtime")
    elif action == "manifest":
        result = http_request(base_url, "GET", "/manifest")
    elif action == "doctor":
        result = http_request(base_url, "GET", "/doctor")
    elif action == "dom":
        result = http_request(base_url, "GET", "/dom")
    elif action == "session":
        result = http_request(base_url, "GET", "/session")
    elif action == "events":
        since = os.environ.get("AEGIS_SINCE", "0")
        result = http_request(base_url, "GET", f"/events?since={urllib.parse.quote(since)}")
    elif action == "navigate":
        url = os.environ.get("AEGIS_URL", "").strip()
        if not url:
            raise RuntimeError("AEGIS_URL is required for navigate")
        result = http_request(base_url, "POST", "/navigate", {"url": url}, timeout=180)
    elif action == "execute":
        commands = env_json("AEGIS_COMMANDS_JSON", [])
        result = http_request(base_url, "POST", "/execute", {"commands": commands}, timeout=240)
    elif action == "search_eval":
        query = os.environ.get("AEGIS_QUERY", "").strip()
        if not query:
            raise RuntimeError("AEGIS_QUERY is required for search_eval")
        encoded_query = urllib.parse.quote_plus(query)
        target_url = f"https://duckduckgo.com/?q={encoded_query}"
        commands = [
            {"type": "eval", "code": f"window.location.href = {json.dumps(target_url)};"},
            {"type": "wait_for", "url_contains": encoded_query, "timeout_ms": 15000},
        ]
        result = http_request(base_url, "POST", "/execute", {"commands": commands}, timeout=240)
    elif action == "eval":
        script = os.environ.get("AEGIS_EVAL_JS", "").strip()
        if not script:
            raise RuntimeError("AEGIS_EVAL_JS is required for eval")
        commands = [{"type": "eval", "code": script}]
        result = http_request(base_url, "POST", "/execute", {"commands": commands}, timeout=240)
    else:
        raise RuntimeError(f"unsupported AEGIS_ACTION={action}")

    payload["response"] = {
        "ok": result["ok"],
        "status": result["status"],
        "json": result["json"],
        "text": result["text"][:20000],
    }
    persist_full_payload(payload)
    print(json.dumps(summarize_result(action, payload, result)))


if __name__ == "__main__":
    main()
