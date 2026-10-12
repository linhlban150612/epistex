# Epistex Benchmark & Self-Improvement Harness

Turns Epistex into a measurable system: a frozen protocol-compliance task suite,
deterministic graders, an LLM-in-the-loop runner with a simulated rework loop,
and paired before/after comparison for prompt changes.

## What is being evaluated

Epistex is a prompt-protocol kit (LEAD/PEER/SUPERVISOR role prompts + seat setup),
not a program with its own agent loop. Its end-to-end effectiveness is therefore
**how reliably an LLM agent given a role prompt produces protocol-conformant
coordination artifacts** (delegation briefs, six-cell handoffs, escalation
reports, review decisions), and how many rework rounds that takes.

Layers:

- **Layer A — deterministic repo tests** (`python3 -m unittest discover -s tests`).
  Zero cost, always reproducible. 52 tests at the baseline commit.
- **Layer B — protocol compliance (primary, quantitative).**
  `bench/tasks/tasks.json` (frozen suite `epistex-bench-1.0`, 12 tasks) run
  against a pinned OpenRouter model with `agents/LEAD.md` or `agents/PEER.md`
  as system prompt, temperature 0, 3 trials per task. Graders in
  `bench/graders.py` are structural/rule-based — no LLM judge, so the system
  under test cannot drift its own scoring rule (CS2680 agent-evaluation note:
  keep the agent harness and the evaluation harness separate).
- **Layer C — live Paseo smoke (optional, qualitative).** The repo's seats are
  installed on this host (`paseo provider ls` shows codex-lead/codex-peer);
  `bench/run_paseo.py` is a thin smoke check, not part of the score.

## Metrics (per CS2680 cost-effective-agents notes)

- `first_pass_rate` — grader passes on the first output (no rework round).
- `eventual_success_rate` — passes within the rework cap (initial + 2 rounds,
  mirroring LEAD.md's rework cap).
- `rework_rate` — rework turns / total attempts.
- `avg_turns_per_trial`, `total_latency_s`, `tokens_in/out`, `cost_usd`,
  `cost_per_successful_trial`.

## Reproduce

```bash
cd <repo>
python3 -m unittest discover -s tests -q              # Layer A
python3 bench/run_llm.py --label <name> --trials 3    # Layer B baseline
# after editing agents/*.md:
python3 bench/run_llm.py --label candidate --trials 3
python3 bench/compare.py bench/results/<baseline>.jsonl bench/results/<candidate>.jsonl
```

`OPENROUTER_API_KEY` is read from the environment, falling back to the shared
workspace `.env` (never committed to this repo).

## Protocol rules baked into the harness

- Frozen task set; the model never sees grader expectations except through the
  rework feedback, which names only the failed checks (exactly what a Lead
  would send).
- Rework cap = 2 rounds, matching LEAD.md; after that the trial fails.
- Every trial records the full output, usage, latency and failed checks as
  JSONL in `bench/results/` — the trace is the evidence.
- Paired comparison: same tasks, same seeds (`1000 + trial + attempt`), same
  model; per-task outcomes are compared pairwise, not just aggregate rates.

## Limits

- Layer B measures protocol compliance of the prompts on coordination
  scenarios, not coding ability of the backends and not live Paseo behavior.
- Scenario fixtures are invented illustrations (CS2680 style), not data from
  any real project.
- Temperature 0 does not make API output fully deterministic; 3 trials per
  task bound the observed variance but small differences (< ~17 points on a
  12-task suite) are within noise and must not be over-read.
