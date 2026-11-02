---
name: seat-recovery
description: Lead procedure for a Peer whose turn is stuck or whose handback did not arrive whole. Use on `A foreground turn is already active`, on a truncated `<agent-response>`, or when a `[epistex-delivery]` message reports `TURN_ENDED_*` and the handoff must be retrieved or the seat reloaded without polling or a blind resend.
---

# Seat recovery

Recovery changes no task, round, baseline, frozen candidate or authority. It is bounded, event-driven
and Human-run where it touches the seat.

## Truncated handback

If `<agent-response>` ends with `[truncated N chars; ...]`, ignore its activity hint and retrieve
the handoff once:

```bash
paseo agent logs <agentId> --filter assistant_message --tail 1
```

No activity means no handoff. An incomplete handoff → ask the Peer for a handoff-only resend of
the same task/round; never reconstruct cells from the timeline or ask the Peer to read the Lead
prompt. A stale-turn error on that resend goes to the stuck-turn procedure below.

## Stuck turn

`A foreground turn is already active` means the seat has a stale ACP turn
([#3256](https://github.com/getpaseo/paseo/issues/3256)).

1. Stop resends at once. Never cancel and re-prompt: the new prompt queues behind the stuck turn.
2. Escalate to the Supervisor (Human if none) with task/round, the frozen candidate identity and
   the exact error. Recovery is a Human-run `paseo agent reload <agentId>` for that seat only.
3. After the reload, the Peer's instructions are the ones it had on load; assign a fresh round
   that names task, round, baseline and candidate. Do not assume the stuck round finished.

## Delivered `TURN_ENDED_*`

A `[epistex-delivery]` message with `kind: TURN_ENDED_NO_MESSAGE` or
`TURN_ENDED_INVALID_HANDOFF` is a delivery from the kit's plugin, not a handoff and not acceptance.
Treat it as `errored` / missing handoff: handle the `delivery-id` once, apply the truncated
handback retrieval if a body is present, otherwise follow the Monitoring rules for `errored`.
The [cessation gate](../../../agents/contract/COMMON.md#ownership-and-candidate-identity) applies
before any replacement.

## Limits

- At the common three-event limit with one agent, REOPEN with the layer (re-frame your own
  premise, or ask the Human when it is theirs) and move to the `context-reset` skill.
- Unresolved writer or children → `BLOCKED`. Idle status or a cancel receipt is not cessation.
- No patrol, timer, schedule or heartbeat to watch the seat.
