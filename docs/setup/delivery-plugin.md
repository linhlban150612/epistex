# Epistex delivery plugin (Paseo 0.14.0)

Status: **Step 0 only.** The facts below were read from the installed Paseo 0.14.0 build
(`$(npm root -g)/@getpaseo/cli/node_modules/@getpaseo/{plugin,server,client,protocol}`) and from
the live daemon on this host. The plugin under `plugins/epistex-delivery/` does not exist yet.

## Purpose

A Paseo **server plugin** that delivers a Peer's end-of-turn handback to its Lead when the one-shot
`notifyOnFinish` notification is missed
([getpaseo/paseo#6346](https://github.com/getpaseo/paseo/issues/6346)). The plugin only adds
delivery. It does not create, cancel, archive, reload or re-mode agents, does not answer
permissions, does not accept work, and runs no timers, schedules, heartbeats or periodic scans.
Its outbox is a delivery receipt store outside Git; it holds no authority or decisions.

## Verified facts

| Topic | Verified result (0.14.0) | Source |
|---|---|---|
| Plugin entry | `index.server.ts`/`.tsx` (legacy `index.ts`), default export `contribute(server) => cleanup`. `cleanup` must be a function. | `server/dist/server/server/plugins/plugin-process.js` |
| Server context | `server.on(name, handler)`, `server.before(...)`, `server.handle`, `server.registerSettings`, `registerProvider`, `registerUsageSource`. **No `addHook`.** | `plugin/dist/server/contracts.d.ts` |
| Hook name | `"agent.turn_ended"`; also `agent.created/closed/archived`, `agent.turn_started`, `agent.permission_*`, `workspace.*`. | `plugin/dist/server/lifecycle.d.ts` |
| Hook payload | `{agent: {id, workspaceId, parentAgentId, provider, cwd, title}, turnId: string\|null, outcome: {kind:"completed"} \| {kind:"failed", error:{message, code?}} \| {kind:"canceled", reason}, timeline: []}`. `timeline` is deprecated and **always empty**. | `plugins/lifecycle/index.js`, `plugin-process-protocol.js` |
| Hook emission | Emitted for every `turn_completed`/`turn_failed`/`turn_canceled` stream event, including background completions. `internal` agents emit nothing. | `plugins/lifecycle/index.js` (`publishAgentStream`) |
| Hook durability | Notifications only. A throwing handler is logged (`console.error`), never replayed. `drainEvents()` waits for pending handlers only at shutdown. | `plugins/lifecycle/index.js` |
| Handler context | `(payload, {paseo, signal})`; `paseo` is a `PaseoApi` created inside the plugin worker. | `plugin-process.js` |
| Process model | Each plugin is a **forked child process** (`serialization: "advanced"`) talking to the daemon over the Paseo session socket (`ipc://plugin/<id>`), reconnect enabled. A daemon restart restarts the plugin. | `plugin-process.js`, `runtime.js` |
| Parent link | `agent.parentAgentId` = label `paseo.parent-agent-id` (`PARENT_AGENT_ID_LABEL`). **Verified live**: stored agent records under `~/.paseo/agents/*/<id>.json` carry `labels["paseo.parent-agent-id"]` for MCP-created children. | `protocol/dist/agent-labels.js`, `~/.paseo/agents` |
| Lead detection | `agent.provider` is the agent-profile id, e.g. `codex-lead`, `claude-lead`, `amp-lead`, `droid-lead--gpt-6-1-sol--medium`. A Lead seat matches `^[a-z]+-lead(--.*)?$`. | live `~/.paseo/config.json`, `paseo agent ls --json` |
| Agent list / status | `paseo.agents.list()` returns snapshots with `labels`, `parentAgentId`, `provider`, `status ∈ {initializing, idle, running, error, closed}`. | `client/dist/index.d.ts`, `protocol/dist/agent-lifecycle.js` |
| Timeline read | `paseo.agents.ref(id).timeline.refetch({direction: "tail"\|"before"\|"after", cursor?, limit, projection?})` → `{entries, startCursor, endCursor, hasOlder, hasNewer, epoch, reset, staleCursor, gap, window, error}`. Cursor = `{epoch, seq}`; a timeline `replacement` changes `epoch`. Entries carry `item`, `turnId?`, `timestamp`, `seqStart/seqEnd`. `item.type === "assistant_message"` has `text` and `messageId?`. `timeline.subscribe` streams live events only. | `protocol/dist/messages.js` (`AgentTimelineCursorSchema`, `AgentTimelineEntryPayloadSchema`) |
| Send | `paseo.agents.ref(id).send(text, {sourceAgentId?, sourceAgentServerId?, messageId?, activeTurnBehavior?, sessionMode?})`. Resolves when the daemon **accepts** the message, not when the Lead reads it. | `client/dist/daemon-client.d.ts`, `session.js` |
| `ActiveTurnBehavior` | `z.enum(["interrupt", "steer"])`. **There is no queue-until-idle value.** | `protocol/dist/messages.js:995` |
| Send without `sourceAgentId` | `sendPromptToAgent(..., activeTurnBehavior ?? "interrupt")` → `startAgentRun(replaceRunning: true)`. A busy recipient's turn is **replaced**. | `session.js`, `agent/agent-prompt.js` |
| Send with `sourceAgentId` | `agentMessages.enqueue(...)` with `activeTurnBehavior ?? "steer"`: messages for one recipient coalesce for 2 quiet seconds, then dispatch through `sendPreparedPromptToAgent`. Response carries `deliveryStatus: "queued"`. | `session.js`, `agent/agent-messages/delivery.js`, `websocket-server.js` |
| `steer` semantics | If the provider session implements `steerActiveTurn` and accepts, the text joins the running turn (`steered`). Otherwise the running turn is **replaced**. ACP providers steer only when the bridge negotiated `prompt.steer`. | `agent-manager.js` (`steerOrReplaceActiveTurn`), `providers/acp-agent.js` |
| Native `notifyOnFinish` path | `finish-subscriptions` uses the same `enqueue` with `activeTurnBehavior: "steer"`, `unarchive: false`, source kind `agent-notification`. | `agent/finish-subscriptions/index.js` |
| Manifest | `paseo-plugin.json`: `{id, name?, description?, icon?, media?, requirements?: {paseo: <semver range>}, build?: string[][]}`. Missing `requirements.paseo` is treated as `<0.8.0` and fails compatibility. | `plugins/manifest.js`, `plugin-compatibility` |
| Build | esbuild, cjs, `platform: node20`; `@getpaseo/plugin*` and `zod` are host-provided externals; imports outside the plugin directory are rejected. `paseo plugin init <dir>` scaffolds `package.json` (devDeps `@getpaseo/plugin` 0.14.0, `zod ^4.4.3`) and `tsconfig.json` (`moduleResolution: Bundler`). | `plugins/compiler-build.js`, `cli/dist/commands/plugin/scaffold.js` |
| Install / config | `paseo plugin install <dir>` resolves the directory to an absolute path and writes a `directory` source into `plugins` in `~/.paseo/config.json`; loading requires top-level `pluginsEnabled: true`. Also `paseo plugin ls/logs/reload/enable/disable/remove`. On this host: `pluginsEnabled: false`, `plugins` unset (nothing installed). | `cli/dist/commands/plugin/index.js`, `server/dist/server/server/config.js:427` |
| Daemon | `paseo daemon status --json` → `daemonVersion: "0.14.0"`, home `~/.paseo`, listen `127.0.0.1:6767`. | live |

## Differences from the handoff, and the design adjustment

1. **`payload.timeline` is empty.** The handler must `timeline.refetch` for the Peer. Keep the
   stored cursor per Peer and read `after` it; fall back to `tail` when `staleCursor`/`reset` is
   set or the `epoch` changed. Take the last `assistant_message` whose `turnId` matches the
   ended turn when present, otherwise the last one after the cursor.
2. **"If the Lead is busy the prompt queues" is false.** The only queue is the 2-second
   coalescing window; after it the message either steers into or replaces the Lead's running
   turn. `interrupt` always replaces. There is no send option that never disturbs a running
   Lead. Adjustment (event-gated, no timers):
   - Send only when the Lead snapshot reports `status: "idle"` (or `error`).
   - If the Lead is `running`, keep the outbox record `pending`; the plugin also subscribes to
     `agent.turn_ended` for Lead seats and flushes that Lead's `pending` records when its turn
     ends. Plugin start/reconnect replays `pending` records the same way.
   - For the residual race (Lead starts a turn between the status read and dispatch) use the
     same path as native `notifyOnFinish`: `sourceAgentId: <peerId>`, `activeTurnBehavior:
     "steer"`, `messageId: <delivery-id>`. This is **not worse** than today; it is a change from
     the handoff's "do not use steer" and is listed as an open question below.
3. **`send()` confirms acceptance only** (`accepted: true`, `deliveryStatus: "queued"` on the
   agent-message path). The outbox record moves to `sent` on acceptance; delivery remains
   at-least-once and the Lead dedupes by `delivery-id`.
4. **Hooks are not replayed and the plugin is a child process.** Every daemon restart or plugin
   reload loses in-flight handlers, so reconcile on start (timeline `after` cursor for every
   watched Peer) is required, not optional.
5. **Agent records are stored per cwd under `~/.paseo/agents/<cwd-slug>/<id>.json`.** The plugin
   reads agents through `paseo.agents.list()`, never from these files.

## Security and operational caveats

- Role tool visibility is not an OS sandbox: the plugin, the daemon and every seat run as the
  **same Unix user**. The outbox at `${PASEO_HOME:-~/.paseo}/epistex-delivery/` is readable and
  writable by any seat. It is a receipt store, not a trust boundary.
- `paseo plugin install` prints that plugin server code runs **unsandboxed on the daemon host**.
- Enabling plugins (`pluginsEnabled: true`) and installing the plugin change the user's live
  `~/.paseo/config.json`; both need the Human's approval.

## Planned install path (not executed yet)

```bash
# Human-approved: set "pluginsEnabled": true in ~/.paseo/config.json, then
paseo plugin install /abs/path/to/epistex/plugins/epistex-delivery
paseo plugin ls --json
paseo plugin logs epistex-delivery
```

## Open questions for the Human

1. Parser: shell out to `setup/check-handoff --parse-only --json` or port to TypeScript with the
   shared fixture suite?
2. Root (UI-opened) Peers: in scope or not?
3. Outbox retention after the Lead is archived: compact, or keep for audit?
4. Send policy when the Lead is busy (see difference 2): event-gated send plus `steer` for the
   residual race, or event-gated send plus `interrupt`? `interrupt` always replaces a running
   Lead turn; `steer` replaces only when the provider cannot steer.
