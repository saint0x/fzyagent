# Operator Runbook (Production RC)

## Required Environment
- `AGENT_PROVIDER=openai_compat`
- `AGENT_MODEL`
- `OPENAI_COMPAT_ENDPOINT`
- Optional server settings:
  - `AGENT_HOST` (default behavior from runtime)
  - `AGENT_PORT`
  - `AGENT_WORKERS`

## Preflight
```bash
fz check . --json
fz dx-check . --strict --json
```

## Deterministic Confidence Gate
```bash
fz test . --det --strict-verify --seed 150 --json
fz run . --det --strict-verify --seed 152 --record artifacts/phase8_rc.trace.fozzy --json
fz replay artifacts/phase8_rc.trace.fozzy --json
fz ci artifacts/phase8_rc.trace.fozzy --json
```

## Live Provider Probe Gate
```bash
fz run . --det --strict-verify --seed 151 --host-backends --record artifacts/phase55_live.trace.fozzy --json
```

## Inspect Provider Response
- Open latest run events in `.fozzy/runs/<runId>/events.json`
- Read `proc_spawn.fields.stdout`

## Incident Steps
1. Save exact failing command and output
2. Save `.fozzy/runs/<runId>/` directory
3. Attach trace/report paths in bug report
