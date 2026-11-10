---
name: rework-escalation
description: Lead procedure when a task exhausts its rework cap. Use when the third candidate for one task fails review and the Lead must choose between REOPEN, one replacement Peer, or BLOCKED.
---

# Rework escalation

The cap is **2 rework rounds per task across Peers**: candidate 1, rework 1, rework 2. When the
third candidate fails, stop iterating and escalate by the kind of failure.

## What counts as a round

- **Task ID** names one scope with one candidate. A new step or a new scope is a new Task ID,
  `<root>-S<n>` (for example `R15048-S3`), and starts again at Round 1.
- **Round** counts sends of the same Task ID: Round 1 is the first assignment, and Round rises by
  one only when you return a rejected candidate for rework. Do not use Round to number steps.
- The delivery plugin adds `warning: round <n> exceeds rework limit 3; REOPEN or context-reset
  required` to a receipt above Round 3, and `warning: task reused across peers` when a Peer first
  reports a Task ID at a round above one that another Peer reported. A warning does not change
  `kind`. Treat either as the trigger for the table below, or split the work into new Task IDs
  when the rounds were steps.

## Decide by the findings

| Situation | Action |
|---|---|
| The same finding failed three times | `REOPEN`: re-frame your own premise (brief, scope, decided points), or ask the Human when the premise is theirs. No Peer swap: the brief is the likely fault. |
| Different findings each round | Propose **one** replacement Peer, preferably from another Human-authorized backend, through a confirmed reset (`context-reset` skill). Same baseline, last frozen candidate, same authority. One final round. |
| Replacement round fails, or the cap is exhausted a second time | `BLOCKED` to the Human with every candidate identity and the unresolved findings. |

A REOPEN re-frame resets the count once. A second exhaustion after a re-frame → `BLOCKED`.

## Rules that always hold

- Preserve both artifacts: rejected candidates and baseline stay frozen and retrievable.
- Forward prior findings to the replacement Peer as third-party input ("Another engineer's review
  found X — assess with evidence"), never as your verdict or the Human's.
- Rework still goes to the same Peer by one explicit next-round `send_agent_prompt` after a
  validated handback; the cap does not shorten that procedure.
- Count rounds in events, not time. Do not create a new Peer to "try again" outside this table.
