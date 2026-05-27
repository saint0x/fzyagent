# fzyagent

`fzyagent` is an agentic runtime built in fzy (fozzylang).

It is both a real runtime for tool-using agents, stateful chat, prompt management, browser automation, and custom tool creation, and a compact exhibition of how powerful fzy can be in a production-shaped system.

## Why this project exists

This repo shows what fzy looks like in a production-shaped system. The runtime itself matters, but it also serves as a concrete example of how well the language fits systems work: service boundaries, concurrent workflows, distributed logic, long-lived runtime processes, and explicit service composition.

## Why we use fzy

We use fzy because it makes systems code feel direct and structured without becoming heavy.

- Agent features like `toolsmith` and `promptsmith` map naturally onto fzy's module structure, runtime services, and explicit state handling.
- Distributed and concurrent logic stays readable because the language encourages small, explicit components instead of hidden framework magic.
- The tooling story is strong for production work: deterministic testing, trace replay, host-backed validation, and clear runtime boundaries.
- Idioms like explicit service modules, structured tool execution, and spawn/join-oriented workflows made it straightforward to build this runtime without a lot of incidental complexity.

In practice, that means we can ship real agent runtime features quickly while keeping the codebase inspectable and operationally sane.

## Language features demonstrated

- Module-oriented architecture across runtime, services, model, API, and CLI layers
- Type-safe boundaries and explicit contracts between components
- Concurrent task orchestration for tool execution and runtime workflows
- Native HTTP/server flows and provider integration in language-level code
- Deterministic testing, replay, and trace validation with Fozzy-first workflows
- Structured logging and operational visibility from fzy code paths

## How the language maps to the runtime

- `src/main.fzy` wires the full boot path from config to live service runtime
- `src/services/*` handles HTTP, provider calls, tool execution, prompt control, and session plumbing
- `src/runtime/*` covers supervision, limits, recovery, and worker orchestration
- `src/model/*` keeps contracts and runtime state explicit and inspectable

## Local run

```bash
cp .env.example .env
# set ANTHROPIC_API_KEY in .env

fz check . --json
fz build . --backend cranelift --json
fz build . --release --backend llvm --json
fz audit unsafe . --workspace --json
fozzy doctor --deep --scenario .fz/det/main.det.fozzy.json --runs 5 --seed 4242 --json
fozzy test --det --strict .fz/det/main.det.fozzy.json --json
fz test . --det --strict-verify --seed 4242 --record artifacts/fzyagent.det.trace.fozzy --json
fz run . --backend cranelift --json
fozzy trace verify artifacts/fzyagent.det.trace.fozzy --strict --json
fozzy replay artifacts/fzyagent.det.trace.fozzy --json
fozzy ci artifacts/fzyagent.det.trace.fozzy --json
```

Default listen address is `127.0.0.1:8787`.

## Notes

- Secrets are env-driven (`ANTHROPIC_API_KEY`) and `.env` is gitignored.
- Unsafe audit now emits unsafe inventory/docs artifacts under `.fz/` (JSON + Markdown + HTML).
- Strict unsafe policy for CI is opt-in with `FZ_UNSAFE_STRICT=1`.
- `src/tests/smoke.fzy` exercises first-class unsafe semantics in `det_language_surface` (`unsafe fn` + `unsafe { ... }`).
- `src/tests/smoke.fzy` also exercises production trait/generic semantics (`trait`, concrete `impl`, `fn<T: ...>`, explicit specialization, and `Type.method(...)` dispatch).
- Macro/attribute baseline used in this repo is constrained to supported attributes (`#[repr(...)]`, `#[ffi_panic(...)]` where applicable).
- This repo is intentionally small and focused: it is an exhibition of fzy (fozzylang) in action.
