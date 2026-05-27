## Idiomatic FZY Quick Guide

This repo keeps the agent on the modern production-shaped Fozzi path.

### HTTP

- Prefer `http.read(conn)` followed by `http.body_json(conn)` for inbound JSON.
- Use `http.body(conn)` only when you intentionally need the raw transport body.
- Build JSON with explicit builders and `json.raw(...)` only for already-encoded JSON fragments.

### Process Work

- Prefer structured process APIs like `proc.spawn_cmd(...)`, `proc.wait(...)`, `proc.stdout(...)`, `proc.stderr(...)`, and `proc.exit_code(...)`.
- Treat nonzero exit, timeout, and malformed output as distinct failure classes.

### Concurrency

- Prefer `spawn(...)` and `join(...)` for independent work that can run in parallel.
- Join spawned tasks explicitly and write combined results with status metadata.
- Avoid hidden background loops in request-serving mode unless they are config-gated.

### Runtime Services

- Keep live HTTP handlers small and explicit.
- Persist artifacts intentionally; avoid excessive hot-path writes in production mode.
- Prefer stable request-time control flow over clever dynamic dispatch.

### Agent Tool Protocol

- First-class tools should expose:
  - stable `id`
  - human description
  - `kind`
  - `mode`
  - JSON input schema
  - deterministic artifact path for latest run output
- Tool results should summarize the important signal, not dump transport envelopes.

### Good Defaults For This Repo

- Use `fzydoc` before writing nontrivial FZY when you want syntax or idiom examples.
- Use `toolsmith` when you want to create a new runtime tool without editing the core registry by hand.
- Use `aegis` for live browser/search/DOM scripting.
