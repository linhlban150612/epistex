# Historical checkpoint and known limitations

This file is a dated historical record, not current operational status or a release claim.
Git history owns the detailed implementation/review narrative. Check current code and tests
for behavior, and inspect live state independently before any operation. Do not infer that
historical agent IDs, daemon/timer status, ledgers, or rollout locations remain valid.

## Durable cautions retained from the checkpoint

- Epistex coordinates roles running as the same Unix user; role scope and tool visibility
  are not an OS sandbox. Paseo owns agent lifecycle and topology.
- `setup/codex-room-sync` preserves private runtime data and canonical Codex configuration,
  disables native Codex multi-agent features, and rejects ambiguous or symlinked runtimes.
  These are current implementation contracts; see `README.md`, `SETUP.md`, and the focused
  runtime regression tests for current behavior.
- The desk control plane and patrol installer were removed; Paseo is the sole agent control plane.
- Historical references to desk state and patrol behavior below are retained only to explain
  checkpoint provenance, not as operational instructions.
- The checkpoint documented limitations in ACP child-exit handling, systemd path quoting,
  and the absence of a general uncertain-outcome recovery command. These were observations
  at the checkpoint, not assertions that the defects remain unresolved. Reproduce against
  current code before relying on them.
- Historical live daemon, timer, ledger and session details were deliberately removed from
  this current-facing checkpoint. They are retained, if needed, in Git history and must not
  be treated as instructions to inspect, mutate, or recover retained external state.

## Provenance

This compact checkpoint replaces execution diaries, review transcripts, stale agent/worktree
identifiers, unrelated chrome-cdp history, superseded plans, and historical test totals. The
repository's current acceptance commands and product/setup owners are documented in `README.md`
and `SETUP.md`.
