# Snippet for a repository's `AGENTS.md`

> `AGENTS.md` is the shared contract that both Lead and Peer read in the target repository. Keep
> only clauses with a real constraint; each clause should have a reproducible reason and a condition
> for reconsidering it.

## Product boundary

- application/domain core:
- adapter/transport boundary (translate the protocol only; do not own workflow or policy):
- execution/runtime boundary:
- generated/runtime data must live outside Git:

## Canonical documentation

- product intent / roadmap:
- architecture / security:
- development / verification:
- operations:

Add new documentation only when it belongs to no canonical document and cannot be placed beside the code it describes.

## Contract boundary

- settled seam (use it without asking again):
- seam that must be decided before a test crosses it; if undecided, report `BLOCKED`:

## Authority

- decisions you may make independently:
- decisions that always require asking the Human:
- environment boundaries (ports, DB, network, data):
- artifacts allowed to be committed / required to stay outside Git:

## Verification

- commands for routine changes (for example `./verify quick`; see `examples/target-repo/`):
- commands before the Lead accepts (for example `./verify full`; state who may hold Docker/port/DB):
- evidence for UX or other subjective quality:

## Example clause with a review trigger

```md
- Any change touching `store/migrations/` requires Human review of the exact candidate.
  Reason: a migration once destroyed development data without being detected by unit tests.
  Review trigger: remove this requirement when CI runs migrations against a representative data copy.
```

## Heuristics / anti-patterns

Record only engineering heuristics this repository actually enforces, each with a reason drawn from
this repository and a reconsideration trigger. Examples to adapt or delete:

```md
- No intermediate interface while only one implementation of <component> exists.
  Reason: <indirection that hid behaviour or slowed review in this repo>.
  Review trigger: a second real implementation is required, not merely anticipated.
- Tests for <persistence path> run against a real local <database>, not a mocked API.
  Reason: <a mocked test that passed while the real query/migration failed>.
  Review trigger: <the database can no longer run locally or in CI within budget>.
- Bootstrap a flat MVP: no layered architecture, DI container or ORM reflection at startup.
  Reason: <cost observed at current scale: startup time, indirection, onboarding>.
  Review trigger: <measured scale signal, e.g. N modules, M contributors, a second deploy target>.
- Refactor toward structure only when scale demands it, as its own task with its own evidence.
  Reason: <speculative structure that had to be undone>.
  Review trigger: <the same change repeatedly touches more than N unrelated files>.
```

## Lessons recorded from Peer evals

Lessons enter this file only through Human review, with the evidence that produced them (eval run
or real task), never through a ledger or memory outside Git. Examples from `eval/` on a Spring Boot
repo (2026-10-22), to adapt or delete:

```md
- A premise stated in a brief is a claim; verify it against the code before changing behaviour,
  and report `REOPEN_REQUEST` when it is false.
  Reason: a false premise produced a silent behaviour change that passed every mechanical gate.
  Review trigger: the brief carries a `Verified facts` line for every premise the Lead checked.
- Do not write or commit before a round is assigned; report `BLOCKED` with `Round: not assigned`.
  Reason: Peers created and committed a test file with no round in 2 of 5 runs.
  Review trigger: the handoff gate rejects every candidate without a round.
- Use the literal status words `REOPEN_REQUEST`, `DEPENDENCY_REQUEST`, `BLOCKED`; prose such as
  "blocked" or "cannot proceed" is not a status.
  Review trigger: the handoff gate parses the status cell.
- Commits are required or forbidden, never "allowed".
  Reason: "allowed" produced uncommitted snapshots the gate cannot verify.
```

## Repository-specific risks

- hard-to-reverse decisions:
- external side effects:

Do not copy a seat's persona or handoff schema here. Add only repository constraints; for a client that does not load seat prompts, include any necessary instructions under that client's own contract. Paseo is the agent control plane; do not introduce a parallel desk, patrol, timers, schedules or heartbeats.
