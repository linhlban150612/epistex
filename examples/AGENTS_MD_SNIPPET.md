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

- commands for routine changes:
- commands before the Lead accepts:
- evidence for UX or other subjective quality:

## Example clause with a review trigger

```md
- Any change touching `store/migrations/` requires Human review of the exact candidate.
  Reason: a migration once destroyed development data without being detected by unit tests.
  Review trigger: remove this requirement when CI runs migrations against a representative data copy.
```

## Repository-specific risks

- hard-to-reverse decisions:
- external side effects:

Do not copy a seat's persona or handoff schema here. Add only repository constraints; for a client that does not load seat prompts, include any necessary instructions under that client's own contract.
