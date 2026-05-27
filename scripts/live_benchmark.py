#!/usr/bin/env python3
import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


def now_ms() -> float:
    return time.perf_counter() * 1000.0


def percentile(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def http_request(base_url, method, path, body=None, headers=None, timeout=120):
    data = None
    hdrs = headers or {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs = {"content-type": "application/json", **hdrs}
    req = urllib.request.Request(base_url + path, data=data, headers=hdrs, method=method)
    started = now_ms()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            elapsed = now_ms() - started
            text = raw.decode("utf-8", errors="replace")
            parsed = None
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
            return {
                "ok": True,
                "status": resp.status,
                "latency_ms": elapsed,
                "bytes": len(raw),
                "text": text,
                "json": parsed,
                "error": "",
            }
    except urllib.error.HTTPError as err:
        raw = err.read()
        elapsed = now_ms() - started
        text = raw.decode("utf-8", errors="replace")
        parsed = None
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        return {
            "ok": False,
            "status": err.code,
            "latency_ms": elapsed,
            "bytes": len(raw),
            "text": text,
            "json": parsed,
            "error": str(err),
        }
    except Exception as err:
        elapsed = now_ms() - started
        return {
            "ok": False,
            "status": 0,
            "latency_ms": elapsed,
            "bytes": 0,
            "text": "",
            "json": None,
            "error": str(err),
        }


def run_case(base_url, spec):
    return http_request(
        base_url=base_url,
        method=spec["method"],
        path=spec["path"],
        body=spec.get("body"),
        headers=spec.get("headers"),
        timeout=spec.get("timeout", 120),
    )


def summarize_case(name, expected_status, results):
    latencies = [item["latency_ms"] for item in results]
    statuses = {}
    errors = []
    success_count = 0
    total_bytes = 0
    for item in results:
        key = str(item["status"])
        statuses[key] = statuses.get(key, 0) + 1
        total_bytes += item["bytes"]
        if item["status"] == expected_status:
            success_count += 1
        else:
            errors.append(
                {
                    "status": item["status"],
                    "error": item["error"],
                    "snippet": item["text"][:400],
                }
            )
    return {
        "name": name,
        "expected_status": expected_status,
        "requests": len(results),
        "successes": success_count,
        "failures": len(results) - success_count,
        "success_rate": round(success_count / len(results), 4) if results else 0.0,
        "statuses": statuses,
        "bytes_total": total_bytes,
        "latency_ms": {
            "min": round(min(latencies), 2) if latencies else None,
            "max": round(max(latencies), 2) if latencies else None,
            "mean": round(statistics.mean(latencies), 2) if latencies else None,
            "p50": round(percentile(latencies, 0.50), 2) if latencies else None,
            "p95": round(percentile(latencies, 0.95), 2) if latencies else None,
        },
        "sample_failures": errors[:5],
    }


def run_batch(base_url, name, spec, count, concurrency, expected_status):
    started = now_ms()
    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(run_case, base_url, spec) for _ in range(count)]
        for future in as_completed(futures):
            results.append(future.result())
    summary = summarize_case(name, expected_status, results)
    summary["wall_time_ms"] = round(now_ms() - started, 2)
    return summary


def run_workflow(base_url, workflow_id):
    started = now_ms()
    steps = []

    release_run = http_request(base_url, "POST", "/tools/release_audit/run", timeout=180)
    steps.append({"step": "release_audit", "status": release_run["status"], "latency_ms": round(release_run["latency_ms"], 2)})
    if release_run["status"] != 200:
        return {
            "workflow_id": workflow_id,
            "ok": False,
            "steps": steps,
            "wall_time_ms": round(now_ms() - started, 2),
            "error": release_run["text"][:400],
        }

    run_payload = http_request(base_url, "GET", "/runs/release_audit_latest", timeout=120)
    steps.append({"step": "fetch_release_audit", "status": run_payload["status"], "latency_ms": round(run_payload["latency_ms"], 2)})
    if run_payload["status"] != 200:
        return {
            "workflow_id": workflow_id,
            "ok": False,
            "steps": steps,
            "wall_time_ms": round(now_ms() - started, 2),
            "error": run_payload["text"][:400],
        }

    run_text = run_payload["text"][:6000]
    prompt = (
        "You are validating a live runtime. Summarize this release audit in 3 short bullets, "
        "then give exactly one operational risk and one confidence signal.\n\n"
        + run_text
    )
    llm = http_request(
        base_url,
        "POST",
        "/sessions/demo/messages",
        body={"message": prompt},
        timeout=180,
    )
    steps.append({"step": "anthropic_summary", "status": llm["status"], "latency_ms": round(llm["latency_ms"], 2)})
    return {
        "workflow_id": workflow_id,
        "ok": llm["status"] == 200,
        "steps": steps,
        "wall_time_ms": round(now_ms() - started, 2),
        "response_bytes": llm["bytes"],
        "error": "" if llm["status"] == 200 else llm["text"][:400],
    }


def summarize_workflows(results):
    latencies = [item["wall_time_ms"] for item in results]
    steps = {}
    ok_count = 0
    failures = []
    for item in results:
        if item["ok"]:
            ok_count += 1
        else:
            failures.append(item)
        for step in item["steps"]:
            name = step["step"]
            if name not in steps:
                steps[name] = []
            steps[name].append(step["latency_ms"])
    step_summary = {}
    for name, values in steps.items():
        step_summary[name] = {
            "mean_ms": round(statistics.mean(values), 2),
            "p95_ms": round(percentile(values, 0.95), 2),
            "max_ms": round(max(values), 2),
        }
    return {
        "requests": len(results),
        "successes": ok_count,
        "failures": len(results) - ok_count,
        "success_rate": round(ok_count / len(results), 4) if results else 0.0,
        "wall_time_ms": {
            "min": round(min(latencies), 2) if latencies else None,
            "max": round(max(latencies), 2) if latencies else None,
            "mean": round(statistics.mean(latencies), 2) if latencies else None,
            "p95": round(percentile(latencies, 0.95), 2) if latencies else None,
        },
        "step_latency_ms": step_summary,
        "sample_failures": failures[:3],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8899")
    parser.add_argument("--out", default="artifacts/live_benchmark.latest.json")
    parser.add_argument("--anthropic-runs", type=int, default=4)
    parser.add_argument("--workflow-runs", type=int, default=3)
    args = parser.parse_args()

    batches = [
        ("healthz", {"method": "GET", "path": "/healthz", "timeout": 30}, 40, 8, 200),
        ("tools_list", {"method": "GET", "path": "/tools", "timeout": 30}, 30, 6, 200),
        ("sessions_create", {"method": "POST", "path": "/sessions", "timeout": 30}, 12, 4, 200),
        ("bash_run", {"method": "POST", "path": "/tools/bash/run", "timeout": 60}, 20, 5, 200),
        ("parallel_bash_run", {"method": "POST", "path": "/tools/parallel_bash/run", "timeout": 90}, 12, 4, 200),
        ("parallel_grep_run", {"method": "POST", "path": "/tools/parallel_grep/run", "timeout": 90}, 8, 3, 200),
        ("release_audit_run", {"method": "POST", "path": "/tools/release_audit/run", "timeout": 180}, 6, 2, 200),
        ("timeout_probe", {"method": "POST", "path": "/tools/timeout_probe/run", "timeout": 30}, 4, 2, 500),
        ("anthropic_message", {"method": "POST", "path": "/sessions/demo/messages", "body": {"message": "Give a one-sentence runtime heartbeat."}, "timeout": 180}, args.anthropic_runs, 1, 200),
    ]

    batch_results = []
    for name, spec, count, concurrency, expected_status in batches:
        batch_results.append(run_batch(args.base_url, name, spec, count, concurrency, expected_status))

    workflows = [run_workflow(args.base_url, index + 1) for index in range(args.workflow_runs)]

    report = {
        "base_url": args.base_url,
        "generated_at_epoch_ms": int(time.time() * 1000),
        "batches": batch_results,
        "workflow": summarize_workflows(workflows),
        "workflow_details": workflows,
    }

    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
