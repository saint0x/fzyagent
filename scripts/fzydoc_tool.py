#!/usr/bin/env python3
import html
import json
import os
import re
from pathlib import Path


ROOT = Path("/Users/deepsaint/Desktop/fzyagent")
DOCS_DIR = ROOT / "docs" / "fzy"
STATE_PATH = Path("/tmp/fzyagent/tools/fzydoc.json")


def strip_html(text: str) -> str:
    text = re.sub(r"<script.*?</script>", "", text, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", "", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    return html.unescape(text)


def normalize_lines(path: Path):
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".html":
        raw = strip_html(raw)
    return raw.splitlines()


def search_docs(query: str, max_lines: int):
    q = query.lower()
    hits = []
    for path in sorted(DOCS_DIR.glob("*")):
        if not path.is_file():
            continue
        lines = normalize_lines(path)
        for idx, line in enumerate(lines, start=1):
            if q in line.lower():
                start = max(1, idx - 2)
                end = min(len(lines), idx + 2)
                snippet = "\n".join(f"{n}: {lines[n - 1]}" for n in range(start, end + 1) if lines[n - 1].strip())
                hits.append({"path": str(path), "line": idx, "snippet": snippet})
                if len(hits) >= max_lines:
                    return hits
    return hits


def main():
    query = os.environ.get("FZYDOC_QUERY", "").strip() or "spawn"
    max_lines = int(os.environ.get("FZYDOC_MAX_LINES", "6"))
    payload = {
        "tool": "fzydoc",
        "status": "ok",
        "query": query,
        "docs_dir": str(DOCS_DIR),
        "hits": search_docs(query, max_lines),
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=True))


if __name__ == "__main__":
    main()
