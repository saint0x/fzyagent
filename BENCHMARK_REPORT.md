# Benchmark Report (Production RC)

Date: 2026-02-24
Project: /Users/deepsaint/Desktop/fzyagent

## Method
- Deterministic tests: `fz test --det --strict-verify`
- Deterministic run + trace lifecycle: `run/replay/ci`
- Host-backed live provider probe: `fz run --det --host-backends`

## Observed Latency Samples
- Host-backed live probe (`seed=151`): 2607 ms
- Host-backed live probe (`seed=142`): 1826 ms
- Host-backed live probe (`seed=107`): 1340 ms
- Deterministic capability run (`seed=152`): 1 ms
- Deterministic capability run (`seed=141`): 5 ms

## Approximate Percentiles (host-backed probe)
- p50: 1826 ms
- p95: 2607 ms
- p99: 2607 ms

## Throughput/Concurrency Notes
- Parallel dispatch and queue/limiter hooks exercised in deterministic suite.
- No thread/scheduler regressions detected across fifo/random/coverage_guided runs.

## Memory/Integrity
- Leak bytes: 0
- Leak allocs: 0
- CI trace integrity: pass

## Conclusion
Runtime is stable for production RC scope with repeatable deterministic and host-backed outcomes.
