Epistex delivery forwards a Peer's last message of a finished turn to the Lead that created the
Peer. It exists because Paseo's one-shot `notifyOnFinish` notification can be missed
(getpaseo/paseo#6346), which leaves a Lead waiting for a handback that already happened.

How it works: on every `agent.turn_ended` event for an agent whose `paseo.parent-agent-id` label
points at a Lead seat, the plugin reads the Peer's timeline, classifies the last assistant message
with the same handoff parser as `setup/check-handoff`, writes a receipt to
`${PASEO_HOME:-~/.paseo}/epistex-delivery/`, and sends a `[epistex-delivery]` message to the Lead.
Delivery is at least once; the Lead processes each `delivery-id` once.

Requirements: Paseo 0.14.0 exactly. The plugin refuses to register anything when the daemon does
not expose the lifecycle API it was built against.

Limits: the plugin only delivers. It never creates, cancels, archives, reloads or re-modes agents,
never answers permissions, and runs no timers, schedules or periodic scans. It runs unsandboxed as
the same Unix user as the daemon and every seat; the receipt store is not a trust boundary.
