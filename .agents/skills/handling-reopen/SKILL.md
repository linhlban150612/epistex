---
name: handling-reopen
description: Resolves evidence-backed REOPEN_REQUEST and DEPENDENCY_REQUEST reports. Use when a Peer challenges a brief premise or needs another owner, API, or write scope, without waiting for the rework cap.
---

# Handling reopen and dependency requests

The Lead resolves the report; the reporting Peer does not expand its own authority.
This procedure grants no new authority and does not replace the Lead's handback,
cessation, review or acceptance gates.

## Validate before deciding

1. Validate the handback's task, round, baseline/candidate identities and ownership.
   Preserve the baseline and all frozen candidates; explicitly record no candidate if none exists.
   An incomplete handoff needs a resend, not permission to resume writing.
2. Read the cited commands/output and source paths/lines. For `REOPEN_REQUEST`, identify the
   challenged premise and layer: foundation, dependency, lifecycle, API, ownership or verification.
   For `DEPENDENCY_REQUEST`, identify the missing contract/scope, its owner and affected consumers.
   Missing evidence stays unknown: request the missing evidence rather than accepting the claim.
   New investigation needs an explicit authorized round, not a disguised resend request.
3. Compare the evidence with the binding contract and the startup decision authority.
   Record what is verified, what remains assumed and who may change the disputed decision.
   Unknown or conflicting authority → `BLOCKED`; ask the Human via the Supervisor
   (`send_agent_prompt`, ID from the initial prompt), or directly if there is no Supervisor.

## Resolve by authority and ownership

| Finding | Resolution |
|---|---|
| Evidence contradicts a Lead-owned premise | Re-frame the objective, scope or `ALREADY DECIDED` with reasons and evidence. Keep binding constraints intact; issue a revised brief in a new round. |
| Evidence challenges a Human-owned decision or requires a reserved trade-off | Send the Supervisor the premise, evidence, affected work, options and decision needed. No Supervisor → ask the Human directly. Keep affected work `BLOCKED` until an explicit decision; silence and Supervisor opinion are not approval. |
| Work needs another owner's scope or an unsettled API | Route a bounded dependency task/question to that owner through the owning Lead. If owner or contract is unknown, settle it within existing authority or escalate; do not invent an API. Agree the producer/consumer contract and verification before implementation. Keep dependent work blocked until the prerequisite is verified. |
| Evidence does not support the request | Explain the contradiction or missing evidence. Retain the current contract; do not label the request resolved merely because mechanical checks pass. Any further work needs an explicit assignment. |

An API change may need both the Human decision route and the dependency route. Do not
treat routing to an owner as permission to make a Human-reserved decision.

## Resume deliberately

- Record a concise resolution in the task conversation: request/layer, evidence, decision and
  authority, changed brief fields, dependency owner/prerequisite, next round or blocking question.
  Keep startup provenance in Lead coordination context. Peer-facing briefs remain neutral,
  first-person and evidence-based; do not forward Human quotes or provenance as persuasion.
- Resume the same Peer only after validated handback and verified cessation, with one explicit
  next-round `send_agent_prompt` naming task, round, revised brief, feedback, baseline and prior
  frozen candidate (or explicitly none). Findings alone never renew write authority.
- Another owner keeps its own write scope. Scope transfer requires resolving old ownership and
  verifying cessation before a new writer starts; parallel writers use separate worktrees.
  The Lead coordinates and never implements the dependency itself.
- Reverify affected contracts and consumers on the resulting frozen candidate before acceptance.
  A new round is not a new rework budget. At the cap, follow
  `.agents/skills/rework-escalation/SKILL.md`: only its REOPEN re-frame resets the count once;
  second exhaustion is `BLOCKED`. Replacement still requires the confirmed reset procedure.

## Examples

- A brief assumes retries already survive restart; a Peer cites volatile-only storage.
  If this was the Lead's assumption, correct the brief to the required durability outcome,
  leave the mechanism open and assign a new round. Do not mandate a preferred queue.
- A Peer needs a new response field owned by another component. Settle that API with its owner
  and route the producer work separately; do not expand the consumer Peer's scope on its report.
- Evidence suggests dropping a Human-required compatibility guarantee. Relay the trade-off
  and evidence for a Human decision; do not silently remove the guarantee from the next brief.
