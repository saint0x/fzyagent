# Operator Runbook (Production RC)

## Required Environment
- `ANTHROPIC_API_KEY`
- Optional server settings:
  - `AGENT_HOST` (default behavior from runtime)
  - `AGENT_PORT`
  - `AGENT_WORKERS`

## Preflight
```bash
fz check /Users/deepsaint/Desktop/fzyagent --json
fz dx-check /Users/deepsaint/Desktop/fzyagent --strict --json
```

## Deterministic Confidence Gate
```bash
fz test /Users/deepsaint/Desktop/fzyagent --det --strict-verify --seed 150 --json
fz run /Users/deepsaint/Desktop/fzyagent --det --strict-verify --seed 152 --record /Users/deepsaint/Desktop/fzyagent/artifacts/phase8_rc.trace.fozzy --json
fz replay /Users/deepsaint/Desktop/fzyagent/artifacts/phase8_rc.trace.fozzy --json
fz ci /Users/deepsaint/Desktop/fzyagent/artifacts/phase8_rc.trace.fozzy --json
```

## Live Provider Probe Gate
```bash
fz run /Users/deepsaint/Desktop/fzyagent --det --strict-verify --seed 151 --host-backends --record /Users/deepsaint/Desktop/fzyagent/artifacts/phase55_live.trace.fozzy --json
```

## Inspect Anthropic Response
- Open latest run events in `.fozzy/runs/<runId>/events.json`
- Read `proc_spawn.fields.stdout`

## Incident Steps
1. Save exact failing command and output
2. Save `.fozzy/runs/<runId>/` directory
3. Attach trace/report paths in bug report
