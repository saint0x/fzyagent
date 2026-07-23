# API and Integration Reference (Production RC)

## Runtime Server
- Server path: `runtime.server.run` -> `services.http.start_server`
- Config sources: `AGENT_HOST`, `AGENT_PORT`, `AGENT_WORKERS`
- Graceful stop hook: `services.http.graceful_stop`

## Modeled HTTP Endpoints
- `POST /sessions`
- `GET /sessions/:id`
- `POST /sessions/:id/messages`
- `GET /tools`
- `POST /tools`
- `DELETE /tools/:id`
- `POST /tools/:id/run`
- `GET /runs/:id`

## Core Modules
- Provider: `src/services/provider.fzy`, `src/services/anthropic.fzy`
- Registry: `src/services/registry.fzy`
- Tool runtime: `src/services/tools.fzy`
- Safety/auth/rate-limit: `src/services/safety.fzy`, `src/services/security.fzy`
- Persistence/recovery: `src/services/persistence.fzy`, `src/runtime/recovery.fzy`
- Server/runtime config: `src/runtime/server.fzy`, `src/runtime/config.fzy`
- Native RPC contract: `src/api/rpc.fzy`

## Generated Interface Artifacts
- Header: `artifacts/phase8_runtime.h`
- ABI: `artifacts/phase8_runtime.abi.json`
- RPC schema/stubs: `artifacts/native_rpc/`

## Production Smoke Command
```bash
fz run . --det --strict-verify --seed 151 --host-backends --json
```
