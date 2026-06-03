# LONGRANGEBENCH

## Scope

This file records the fresh long-range benchmark rerun from `2026-06-03`.

Older ad hoc bench history was intentionally discarded. The current report keeps only the deterministic rerun that reflects the hardened long-range runtime as it exists now.

## Harness

- runtime: `/Users/deepsaint/Desktop/fzyagent/.fz/build/fzyagent`
- mode: deterministic `longrange-start` harness
- shape: `create_run(...)` followed by long-range drain
- repo under test: `/Users/deepsaint/Desktop/fzyagent`
- runs: `21` total
- matrix: `3` models x `7` cases
- result source: `/tmp/fzyagent/longrangebench_20260603.json`

Why this harness:

- the old `.fz/build/fzyagent chat --once` startup path was still noisy enough to make benchmark publication misleading
- the deterministic `longrange-start` path exercises the hardened long-range controller directly and leaves a much cleaner truth surface

## Cases

| ID | Shape |
| --- | --- |
| `A` | Light planning with implied completion |
| `B` | Tiny plan-only completion |
| `C` | Moderate 2-file code inspection |
| `D` | Stress 6-file architecture summary |
| `E` | Minimal 2-step plan then complete |
| `F` | Micro README inspect and summarize |
| `G` | Deep runtime architecture summary |

## Models

### `liquid/lfm2.5-1.2b`

- provider: `openai_compat`
- endpoint: `http://127.0.0.1:1234`

| Case | Status | Turns | Failures | Duration ms | Summary |
| --- | --- | --- | --- | --- | --- |
| `A` | `failed` | `9` | `1` | `44191` | `empty_assistant_followup` |
| `B` | `planning` | `4` | `0` | `34153` | non-terminal planning churn |
| `C` | `failed` | `6` | `1` | `42827` | `empty_assistant_followup` |
| `D` | `failed` | `7` | `1` | `73675` | `empty_assistant_followup` |
| `E` | `failed` | `2` | `1` | `22011` | `empty_assistant_followup` |
| `F` | `failed` | `3` | `1` | `29461` | `empty_assistant_followup` |
| `G` | `planning` | `8` | `0` | `45013` | non-terminal planning churn |

Read:

- strongest coverage of the controller, with several multi-turn runs
- still fails to convert planning into a clean finish
- most truthful failure mode is now fail-closed `empty_assistant_followup`, not runtime corruption

### `claude-haiku-4-5-20251001`

- provider: `anthropic`

| Case | Status | Turns | Failures | Duration ms | Summary |
| --- | --- | --- | --- | --- | --- |
| `A` | `failed` | `1` | `1` | `15722` | `empty_assistant_followup` |
| `B` | `active` | `2` | `0` | `19645` | tool work completed without final message |
| `C` | `failed` | `1` | `1` | `17094` | `empty_assistant_followup` |
| `D` | `failed` | `1` | `1` | `18336` | `empty_assistant_followup` |
| `E` | `failed` | `1` | `1` | `18488` | `empty_assistant_followup` |
| `F` | `active` | `2` | `0` | `15604` | tool work completed without final message |
| `G` | `failed` | `1` | `1` | `15804` | `empty_assistant_followup` |

Read:

- very fast control-plane behavior
- usually exits immediately into truthful failure
- still has a separate “tool work happened but no final assistant message” seam on smaller tasks

### `claude-opus-4-8`

- provider: `anthropic`

| Case | Status | Turns | Failures | Duration ms | Summary |
| --- | --- | --- | --- | --- | --- |
| `A` | `failed` | `1` | `1` | `21476` | `empty_assistant_followup` |
| `B` | `failed` | `1` | `1` | `27665` | `empty_assistant_followup` |
| `C` | `failed` | `1` | `1` | `26071` | `empty_assistant_followup` |
| `D` | `failed` | `1` | `1` | `30484` | `empty_assistant_followup` |
| `E` | `failed` | `2` | `1` | `23510` | `empty_assistant_followup` |
| `F` | `failed` | `1` | `1` | `23313` | `empty_assistant_followup` |
| `G` | `failed` | `1` | `1` | `23060` | `empty_assistant_followup` |

Read:

- most uniform model in this rerun
- every case failed closed
- no evidence of control-plane corruption, but no successful long-range completion either

## Current Read

What the rerun proves:

- fresh run birth is stable
- failed terminalization is stable
- summary and active-run projection are stable enough for benchmarking
- stale historical actives no longer poison reuse

What the rerun still says about model/runtime behavior:

- no model cleared the full deterministic sweep
- the dominant remaining production behavior is truthful fail-close, not lying local state
- the next real quality seam is completion behavior after valid tool work, especially on smaller tasks
