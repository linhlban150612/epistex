Epistex delivery is the only channel from a Peer to the Lead that created it. The Lead calls
`create_agent`/`send_agent_prompt` with `notifyOnFinish: false`: Paseo's one-shot notification can
be missed (getpaseo/paseo#6346), cuts the message at 4000 characters, and would put every handback
into the Lead's context a second time.

How it works:

- On every `agent.turn.after` hook for an agent whose `paseo.parent-agent-id` label points at a Lead
  seat, the plugin reads the Peer's timeline, delivers the turn's last valid handoff in full (the
  same parser as `setup/check-handoff`; text after it is attached as a warning, and without a valid
  handoff the last message is classified), writes a receipt to
  `${PASEO_HOME:-~/.paseo}/epistex-delivery/`, and sends a `[epistex-delivery]` message to the Lead.
  A completed turn whose last message has no handoff header gets one fixed reminder, sent to the
  Peer instead of the Lead; the Lead hears of the Peer's next turn end.
- On every `agent.permission.before` hook for such a Peer, the plugin sends a
  `PERMISSION_REQUESTED` message with the Peer's `agentId` and `requestId` to the Lead's Supervisor
  (the Lead's `paseo.parent-agent-id`, when it is a live Supervisor seat), otherwise to the Lead.

- On every `agent.open.before` hook for an interactive Lead seat, the plugin adds the agent tool
  `epistex_assign`. The Lead calls it to give a task to a new Peer: task, round (1 to 3), Peer
  profile, worktree, owned scope, commit authority and baseline are schema fields, the baseline is
  compared with the worktree's HEAD, and the composed brief passes the `setup/check-brief` rules
  before the Peer is created. A refusal names its code and creates nothing.

A message waits in the receipt store while its recipient is mid-turn and is sent when that
recipient's turn ends. Delivery is at least once; the recipient processes each `delivery-id` once.

Requirements: Paseo `>=0.15.0 <0.16`. The plugin registers both delivery hooks or none when the daemon does
not expose the lifecycle API it was built against; the tool hook is registered apart, so a failure there leaves delivery on.

Limits: the plugin delivers, reminds, and creates a Peer only inside a Lead's `epistex_assign` call. It never
cancels, archives, reloads or re-modes agents, never answers permissions, and runs no timers, schedules or periodic scans. It runs unsandboxed as
the same Unix user as the daemon and every seat; the receipt store is not a trust boundary.
