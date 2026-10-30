---
name: dual-lane-review
description: Independent two-lane review for complex or review-class tasks. Use when the Lead needs two read-only Peers from different model families to review the same frozen candidate blindly against one property checklist, then reconcile shared findings and divergences.
---

# Dual-Lane review

Two independent lanes review one frozen candidate so one reviewer's blind spot is caught by
the other. Both lanes check the same property list, so their findings can be matched.

## The rule

**The two Peers must belong to two different model families.** That is the only selection
rule this skill adds; its purpose is independent judgment between the lanes.
`WORKSPACE_PROTOCOL.md` §Routing may restrict the pool further, for example: both lanes differ
from the Lead's family. Unknown or ambiguous family identity counts as the same family. No valid
pair → report `BLOCKED`; never run one lane.

## When to use

- The task is classed **complex / review**: a large or cross-cutting candidate, a security- or
  lifecycle-sensitive change, or a review whose conclusion drives a hard-to-reverse decision.
- Creating the two Peers needs agent-creation authority: an implementation request covers it;
  a read-only review request needs explicit Human authorization — otherwise propose it
  (`COMMON.md` §Authority: review requests are read-only; agent creation needs specific authority).

## Properties

Each lane checks every property below. A property is one thing the candidate must get right.

| ID | Property | The candidate fails when |
|---|---|---|
| `P1-behavior` | Preserves observable behavior outside task scope | Output, API, config, CLI or error behavior changes outside the stated task |
| `P2-scope` | No intent drift | It edits files or concerns outside the owned scope, or does work the brief did not ask for |
| `P3-artifacts` | No agent artifacts | It leaves reasoning comments, TODOs from the agent, temp files, debug output or stray logs |
| `P4-tests` | Tests are not weakened | It deletes or loosens assertions, skips or marks tests expected-to-fail, or mocks the behavior under test |
| `P5-complete` | Does the whole task | A requirement in the brief is not done, or the evidence does not prove it |
| `P6-transitional` | Transitional code is declared | It adds an adapter, shim, compat layer, flag or fallback that the handoff's `Unknown / risk` cell does not name with a removal condition |

The brief may add task-specific properties (`P7-…`). Keep each new property to one check.
Do not remove `P1`–`P6`. A finding that fits no property uses `P0-other`.

When the reviewed candidate has no Peer writer (a review-only request on an existing commit,
snapshot or decision), the gate in step 0 still applies: the Lead confirms the required checks
from checks the brief or the Human authorized the Lead to run, or from the Human's evidence,
instead of a handoff. `P2-scope` and
`P3-artifacts` are `not-checked (no writer)`; `P1`, `P4`, `P5` and `P6` still apply, `P5` against
the requirements the review brief states and `P6` against the transitional code the review brief
declares.

Judge evidence by the common proof rule (`COMMON.md` §Evidence): if the behavior disappeared
and the proof would still pass, it is not evidence. Exit 0 and "tests pass" are signals, not
proof.

## Finding format

Each lane reports every finding in this format. One finding has one property and one location.

```text
- id: F-<n>                 # F-1, F-2 …; the Lead prefixes the lane's agent ID when matching
  property: <P-id>
  location: <path>:<line or range> | <commit/snapshot path> | brief:<requirement>
  severity: blocker | major | minor
  evidence: <quoted code, command and real output, or diff hunk>
  claim: <one sentence: what is wrong>
```

`location` points into the frozen candidate, never the working tree: for commits read the file
from the object (`git show "$candidate":path`), for snapshots from the checksummed path
(`LEAD.md` §Ownership). A `P5-complete` finding for a missing requirement has no path; its
location is the requirement in the brief: `brief:<requirement>`.

Each lane also reports one line for each property: `<P-id>: pass | fail | not-checked (reason)`.

A lane returns both inside its six-cell handoff (`PEER.md` §Handoff): property lines and
findings under `Verification`, the reviewed candidate identity under `Candidate`, and `Scope`
with `Changed:` empty — a lane writes nothing. `Outcome` keeps its standard form
(`complete | partial | BLOCKED | REOPEN_REQUEST | DEPENDENCY_REQUEST; Done: …`) plus `blockers: <n>`.

- `blocker`: the lane judges the candidate unsafe to accept.
- `major`: rework is necessary, but the change is not unsafe.
- `minor`: an optional improvement.

Two findings **match** when their locations overlap and their claims describe the same defect.
The property may differ: `P1-behavior` and `P2-scope` overlap, so one lane may file a change
outside scope under `P1` and the other under `P2`. Record the matched finding under the property
both lanes used; when they differ, keep both and note the difference. Severity can differ;
record the higher one.

## Steps

0. **Deterministic gate.** Confirm from the handoff that every required check for the task
   class (as `AGENTS.md` and `WORKSPACE_PROTOCOL.md` §Verification define them) passed on the
   exact frozen candidate, with real output. Rerun only checks you are authorized to run. A
   check that is not authorized or cannot run stays `pending`; `pending` is not a pass. Open
   lanes only when every required check passed, or the Human explicitly waived or deferred the
   rest. A **failed** check → after validating the writer's handback, request rework from the
writer per `LEAD.md` §Acceptance. A
   **`pending`** check → ask the Human to authorize, waive or defer it (`COMMON.md` §Evidence:
   only the Human may waive/defer); the writer cannot resolve it, so do not send rework for it.
1. Open two read-only Peers (Architect or Scout) from different model families. Record each
   lane's model ID and family evidence.
2. Send both lanes an identical neutral brief on the same frozen candidate, in the `LEAD.md`
   §Delegation assignment format: first person, blind, with `Authority: read-only, no commits`.
   The brief contains the task, round, candidate identity (`COMMON.md` §Ownership and candidate
   identity: base + candidate SHA, branch, worktree; or snapshot checksums + paths), the
   reviewed scope (the writer's owned scope when there is one), the property list, the finding
   format and the gate results from step 0. Neither lane holds the test lane: the gate results
   stand in for the suite, and a lane runs only read-only checks that need no ports or test DB
   (`COMMON.md` §Evidence: one shared test lane). Neither brief mentions the other lane; neither
   Peer sees the other's output until both have handed back.
3. Match the findings of the two lanes. Matched findings are **high-confidence**. A property one
   lane marks `not-checked` and the other `pass` is a **coverage gap**, not a divergence: record
   it with the lane's reason in the accept summary; it does not go to cross-critique.
4. Divergences go to **blind cross-critique**. A divergence is a finding raised by one lane only,
   a contradictory claim, or a property one lane marks `pass` and the other marks `fail`. Send each
   Peer the other's divergent findings framed as third-party, naming task, round, candidate
   and property. **At most 2 rounds.** After each round a lane hands back its full property
   lines and findings again: a withdrawn finding keeps its id with `status: withdrawn` and the
   reason, an upheld one is unchanged, a new one takes the next id, and each property line is
   updated to match. The Lead matches against the latest handoff from each lane.
5. The Lead is the final arbiter: record anything still divergent as an unresolved finding,
   with its property. No third Peer, no tie-breaker. Archive both Peers when done.

Findings are review input, not rework authority (`COMMON.md` §Ownership and candidate
identity). Every unresolved finding gets one line in the accept summary, with its property
(`LEAD.md` §Acceptance). The Lead answers every `blocker`: upheld → request rework from the
**Peer writer**, never from a lane (lanes are read-only), as a next-round assignment to the same
writer, counted against the `LEAD.md` §Acceptance rework cap of 2 rework rounds per task;
refuted → cite the evidence. With no writer, an upheld `blocker` goes to the Human as a finding.

## Scope limits

- Keep one lane per model family. Do not open one Peer per property: this skill allows exactly
  two lanes, so there is no third Peer.
- The property list is a checklist inside each lane, not a separate reviewer.

Dual-Lane does not replace the Human review gate (`LEAD.md` §Review gate).
