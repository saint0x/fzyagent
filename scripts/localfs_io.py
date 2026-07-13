#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{time.time_ns()}")
    tmp.write_text(value, encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: localfs_io.py <mkdir|write_env|append_env|replace> <path> [arg]", file=sys.stderr)
        return 2

    _, op, raw_path, *rest = sys.argv
    path = Path(raw_path)

    if op == "mkdir":
        path.mkdir(parents=True, exist_ok=True)
        return 0

    if op == "write_env":
        atomic_write_text(path, os.environ.get("FZY_LOCALFS_PAYLOAD", ""))
        return 0

    if op == "append_env":
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(os.environ.get("FZY_LOCALFS_PAYLOAD", ""))
        return 0

    if op == "replace":
        if len(rest) != 1:
            print("usage: localfs_io.py replace <src> <dst>", file=sys.stderr)
            return 2
        dst = Path(rest[0])
        dst.parent.mkdir(parents=True, exist_ok=True)
        path.replace(dst)
        return 0

    print(f"unknown op: {op}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
