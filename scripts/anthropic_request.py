#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 8:
        print("usage: anthropic_request.py <endpoint> <api_key> <version> <payload_path> <out_path> <meta_path> <timeout_s>", file=sys.stderr)
        return 2

    _, endpoint, api_key, version, payload_path, out_path, meta_path, timeout_s = sys.argv
    payload = os.environ.get("ANTHROPIC_INLINE_PAYLOAD", "")
    if not payload:
        payload = Path(payload_path).read_text(encoding="utf-8")
    Path(payload_path).write_text(payload, encoding="utf-8")
    req = urllib.request.Request(
        endpoint,
        data=payload.encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": version,
        },
    )

    status = 0
    error = ""
    body = ""
    try:
        with urllib.request.urlopen(req, timeout=max(1, int(timeout_s))) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        error = str(exc)
        body = exc.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        error = str(exc)

    Path(out_path).write_text(body, encoding="utf-8")
    Path(meta_path).write_text(json.dumps({"status": str(status), "error": error}), encoding="utf-8")
    sys.stdout.write(body)
    return 0 if body or status else 1


if __name__ == "__main__":
    raise SystemExit(main())
