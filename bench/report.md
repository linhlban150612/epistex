# Epistex Self-Improvement Report — bench/self-improving

**Date:** 2026-10-11 · **Base commit:** `5f5643b` · **Model (unchanged):** `deepseek/deepseek-chat-v3.1` via OpenRouter · **Budget per arm:** 12 tasks × 3 trials, rework cap 2, temperature 0, seeds `1000+trial+attempt`

## What was audited

Epistex is a prompt-protocol kit for Paseo (LEAD/PEER/SUPERVISOR role prompts + seat
setup), not a program with its own loop. The audited "harness" is therefore the
protocol itself: brief structure, six-cell handoffs, escalation tokens, review
decisions, loop handling. Layer A (52 unittest cases for setup scripts) passes at
base and after every change. Layer C (live Paseo daemon smoke: codex-lead /
codex-peer / amp-supervisor seats registered) passes.

## Baseline (measured, Layer B, grader v1.1)

- first_pass 72.22% · eventual 91.67% · rework 36.8% · turns/trial 1.583
- $0.0522 per 36-trial arm · $0.0017 per successful trial · 780.8 s total latency
- Failure analysis (from saved traces, not guesses):
  1. Briefs not written in first person (lead-brief-01/02/04).
  2. Peer handoff says `Outcome: reopen` without the `REOPEN_REQUEST` token + layer
     — an **internal contradiction in PEER.md** (§ Handoff vs § Independent judgment).
  3. One grader false-negative: `Project / Task ID` vs `Project: X / Task: Y`.

## Changes made (protocol/context-management/verification edits)

| # | File | Change | Grounded in |
|---|------|--------|-------------|
| 1 | bench/graders.py | v1.1: accept `Project:`+`Task:` as the compound label | grader false-negative; baseline re-graded offline from saved outputs — no arm advantage |
| 2 | agents/LEAD.md | "Label each field exactly as above." after the brief template | missing-field failures |
| 3 | agents/LEAD.md | brief is first person — check before sending | first-person failures |
| 4 | agents/LEAD.md | forwarding bullet: open in first person, then third-party framing | lead-brief-04 v1 regression (0/3), diagnosed and fixed in v2 |
| 5 | agents/PEER.md | escalation outcomes must state `REOPEN_REQUEST`/`BLOCKED`/`DEPENDENCY_REQUEST` verbatim + layer | peer-handoff-03 1/3 → 3/3 |

LEAD.md stays under the 16 KiB seat ceiling: 16,208 → **16,379 bytes** (limit 16,384,
enforced by `setup-seats.sh`; verified by the 52-test suite). A candidate that hit
16,395 bytes failed 11 ceiling tests and was trimmed before benchmarking.

## Optimization loop (same model, same budget each arm)

| Arm | first_pass | eventual | rework | turns/trial | cost | cost/success |
|---|---|---|---|---|---|---|
| baseline (grader v1.1) | 72.22% | 91.67% | 36.8% | 1.583 | $0.0522 | $0.0017 |
| candidate-v1 | 83.33% | 86.11% ⚠ | 23.4% | 1.306 | $0.0446 | $0.0014 |
| **candidate-v2 (kept)** | **88.89%** | **97.22%** | **14.3%** | **1.167** | **$0.0396** | **$0.0011** |

- candidate-v1 was **rejected**: it regressed lead-brief-04 (0/3 eventual) — cause
  diagnosed (first-person framing dropped from forwarding paragraphs), fixed, and
  re-run as v2. Only v2 is retained.
- Paired per-task (v2 vs baseline): peer-handoff-03 improved +2 trials; lead-brief-04
  swapped 1-1 (first-pass 0/3 → 2/3) — within noise, not a regression signal; all
  other tasks unchanged pass.
- Costs are per-arm API spend; "cost delta +$0.0396" in compare.py is an artifact of
  the regraded baseline lacking cost fields — the real spend went **down** 24%
  ($0.0522 → $0.0396) because fewer rework turns were needed.

## Verification of the improvements

- Layer A: 52/52 tests pass at the final commit (includes the 16 KiB ceiling checks).
- Layer C: Paseo smoke PASS (3 seats registered on the live daemon).
- Layer B: run three times end-to-end; every claim above comes from the JSONL traces
  in `bench/results/` (full outputs, usage, latency, failed checks per turn).

## Limits (honest)

- n = 36 trials/arm: differences below ~17pp are within noise; first-pass +16.7pp is
  a strong signal but not statistically significant at this n.
- One model only (DeepSeek v3.1); the protocol edits target model-agnostic rules, but
  transfer to Codex/Claude backends is untested.
- Layer B measures protocol compliance on invented coordination scenarios, not live
  multi-agent coding outcomes through Paseo.

## Reproduce

```bash
python3 -m unittest discover -s tests -q                          # Layer A
python3 bench/run_llm.py --label <arm> --trials 3                 # Layer B (needs OPENROUTER_API_KEY)
python3 bench/regrade.py bench/results/<file>.jsonl <label>       # offline re-grade
python3 bench/compare.py bench/results/<a>.jsonl bench/results/<b>.jsonl
python3 bench/run_paseo.py                                       # Layer C smoke
```

## Rollback instructions

All changes live in 2 prompt files + the new `bench/` directory (additive).

```bash
# Full rollback to pre-experiment state:
git checkout main -- agents/LEAD.md agents/PEER.md   # or: git checkout 5f5643b -- agents/
rm -rf bench/                                         # optional: drop the harness too

# Partial rollback (keep harness, revert prompts only):
git diff 5f5643b -- agents/LEAD.md agents/PEER.md | git apply -R -

# Re-verify after rollback:
python3 -m unittest discover -s tests -q
```

The seat setup on a live host is refreshed from the repo prompts by re-running
`bash setup/setup-seats.sh`; the running Paseo daemon picks prompts up per new agent,
so no restart is required to roll back.
