---
name: context-reset
description: Lead procedure to replace a stuck or context-lost agent through a Human-confirmed reset. Use when the Lead has reached the common three-event limit with one agent, or a Peer lost its context, and a replacement writer is needed on the same task, round, baseline and frozen candidate.
---

# Context reset

A reset archives one agent and opens a replacement that resumes the same task. It never changes
task, round, baseline, frozen candidate or authority.

## Rules that always hold

- Reset needs explicit Human confirmation. Silence, idle status or a notification is not confirmation.
- No replacement writer before the old writer's cessation is verified
  (see [common cessation gate](../../../agents/contract/COMMON.md#ownership-and-candidate-identity)).
- Preserve baseline, frozen candidate and rejected candidates. No candidate → resume from baseline.
- No patrol, timer or heartbeat to watch the stuck agent; use a bounded check triggered by
  cancellation or a lifecycle event.

## Steps

1. **Propose.** Send the Supervisor (`send_agent_prompt`, agent ID from your initial prompt) the
   agent ID, task, round, baseline and last frozen candidate identities (or explicitly "no
   candidate"), plus symptom evidence: the repeated command/error/finding and the event count.
   No Supervisor → ask the Human directly.
2. **Wait.** End the turn. Act only on an explicit Human confirmation relayed by the Supervisor
   or given directly. No confirmation → no reset; keep the agent, report `BLOCKED` if work cannot
   continue.
3. **Stop the writer.** `cancel_agent` if a turn is running, then `archive_agent`.
4. **Verify cessation.** Use lifecycle/tool execution evidence that the agent and its
   write-capable commands or children stopped or lost scope access: archived status plus no new
   commits, files or processes in the worktree after the cancel timestamp. Messages, cancel
   acknowledgements, idle status, silence or an unchanged diff are insufficient. Unresolved →
   `BLOCKED` to the Human, no replacement.
5. **Replace.** Create one new Peer with the same provider configuration unless the Human chose
   another. The brief keeps task ID and round, names the baseline and the last frozen candidate
   as the starting point, restates authority and scope, and lists unresolved findings as
   third-party input. It does not mention the previous agent's failure as blame.

## Without a reset

Cancellation or reassignment of a writer without archiving still requires steps 3 and 4 before
any other agent may write in that scope.
