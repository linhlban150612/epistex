# Workspace Protocol

> Repository-specific coordination policy. The Lead reads it before routing a task; Peers do
> not need to read this file. Keep policy proportional to repository risks. Do not include
> task-specific file lists or model IDs that may become stale. This is an operating policy,
> not automatically a product artifact to commit. If the repository prohibits process documents,
> keep this file local/ignored or in a location managed by the Human.

## Status

- owner: Human/project owner
- version: 1
- last reviewed: YYYY-MM-DD
- applies to: `<repository-root>`
- readers: Lead

## Project characteristics

- criticality:
- dominant risks:
- expensive-to-reverse decisions:
- external side effects:
- canonical docs (if any):
- repository artifacts that must not be committed:

## Authority

Refer to Authority in `AGENTS.md`; record only additional coordination decisions here:

- An implementation request authorizes the Lead to assign a Peer and conduct review/rework
  within scope, unless the Human limits delegation. A read-only request does not authorize
  creating agents. If delegation is prohibited, implementation is blocked; the Lead does not
  take over implementation.
- topology requiring Human approval:

## Task classes

### Tiny / bounded

- One Peer Engineer holds write authority, including tightly coupled work or a one-line fix.
- Targeted verification; Human review is optional.

### Cross-module / lifecycle-sensitive

- Use a read-only Architect before implementation when foundation or ownership is unclear.
- One Engineer holds each moving write scope; concurrent writers use separate worktrees.
- Require Human review of the stable candidate when risk warrants it.

### Architecture lock-in

- Obtain independent advice in neutral briefs and state reversal conditions.
- The Lead makes one project-level decision (verdict); the Human decides difficult-to-reverse
  product/cost tradeoffs.

## Ownership and workspace

- The Lead coordinates, reads, verifies and accepts or requests rework. The Peer is the sole
  writer for task artifacts, including tests/configuration/documentation and conflict resolution.
  If the Peer is blocked, the Lead does not write in their place.
- This is a role contract, not a filesystem sandbox.
- repository-specific worktree location/convention:
- integration owner:

## Routing

- Discover currently available providers/models; do not hard-code model IDs that may become stale.
- Use the model/effort selected by the Human. Task risk may justify proposing a change, but change
  only with Human approval; discovery does not grant authority to switch.
- Paseo manages sessions, parentage, lifecycle and workspace; this protocol governs tactics.

## Verification

Canonical commands and proof requirements are in Verification of `AGENTS.md`; do not duplicate
those here.

- task class: required/optional check groups in `AGENTS.md`:
- additional Human-review triggers (beyond the Lead's default gate):
- coordination of test/port/DB lanes among agents:

## Project-specific anti-patterns

- signal:
- evidence required:
- allowed response:
- conditions for reconsidering this policy:

## Evolution

- Change policy only with causal evidence or changed repository architecture/risk.
- The Human approves material authority changes; retain version history and review date.
- Do not create evidence folders, review packets or status ledgers in Git solely for orchestration.
