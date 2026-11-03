# Epistex delivery plugin (Paseo >=0.14.0 <0.16)

Status: **installed on this host and verified live on 0.14.0 (2026-11-02) and 0.15.0 (2026-11-03);
see [Live evidence](#live-evidence).** The facts below were read from the installed Paseo
0.14.0 build (`$(npm root -g)/@getpaseo/cli/node_modules/@getpaseo/{plugin,server,client,protocol}`)
and from the live daemon on this host. 0.15.0 was rechecked from its SDK: `server.on("agent.turn_ended")` is kept (deprecated in favour
of `addHook("agent.turn.after")`, removal after 2027-04-30) and the `refresh`, `timeline.refetch` and
`send` shapes are unchanged. `plugins/epistex-delivery/` holds the manifest (range
`>=0.14.0 <0.16`), the entry and a fail-closed version guard: without `server.on` or when
`agent.turn_ended` cannot be registered, the plugin logs the reason and registers nothing. Paseo's
own `compileDirectoryPlugin` + `evaluateBundle` (0.14.0) load the bundle. `server/handoff.ts`
ports `parse_handoff`/`classify_handoff` from `setup/check-handoff`; `check-handoff --parse-only
<file> --json` exposes the Python result and `tests/fixtures/handoffs/` is run through both
(`node --test` in the plugin, driven by `tests/test_delivery_plugin.py`). `server/outbox.ts`
is the receipt store: `<leadAgentId>.jsonl` append-only with `fsync` (a `sent` update is a second
line for the same `deliveryId`, folded on load), `cursors.json` written temp file + rename, and
`deliveryId()` = sha256 over `peerAgentId, taskId|"?", round|"?", candidate|"?", lastMessageId`.
A torn last line is skipped with a warning. `server/delivery.ts` is the `agent.turn_ended`
handler wired in `index.server.ts`: a Lead seat's own turn end (provider `^[a-z]+-lead(--.*)?$`)
flushes that Lead's `pending` records; a child whose parent (`refresh()`) is a Lead seat has its
timeline read `after` the stored cursor (tail when stale, `hasNewer` followed), and the last
`assistant_message` (preferring the ended `turnId`) that is a valid handoff is delivered; assistant
text after it in the turn travels as `trailing` with `warning: trailing_text_after_handoff`, and
without a valid handoff the last message is classified as before. The record is appended and
fsynced, the cursor advanced, then sent with `{sourceAgentId: peer, activeTurnBehavior: "steer",
messageId: delivery-id}` only while the Lead is `idle`/`error`. Root agents and children of
non-Lead parents are ignored. A `completed` turn with no new assistant message after the cursor
is logged and not delivered (its message, if any, was delivered already; a replayed hook lands
here); `failed`/`canceled` turns without a message become `TURN_ENDED_NO_MESSAGE`. Reconcile
(difference 6) runs once per plugin process on the first `agent.turn_ended` event: every Peer
with a stored cursor that is not `running` is read `after` its cursor and recorded, then every
Lead with `pending` records is flushed. A Peer that is gone, archived or `closed` gets that one
attempt and is then unwatched (its cursor removed, receipts kept), so a dead Peer is not read on
every later start. Installed in `~/.paseo/config.json` on this host as a
`directory` source at the kit path (`pluginsEnabled: true`, Human-approved 2026-11-02).

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
   reads agents through `paseo.agents.ref(id).refresh()`, never from these files.
6. **`contribute(server)` receives no `PaseoApi`.** `plugin-process.js` passes only `handle`,
   `registerProvider`, `registerUsageSource`, `registerSettings`, `on`, `before`; `paseo` arrives in
   the hook context. "Reconcile on start" therefore runs on the **first lifecycle event** after the
   plugin process starts (memoised, no timer). Watched Peers are those with a stored cursor: a Peer
   the plugin never saw is not read, so a fresh install does not replay old handbacks the Lead
   already handled through `notifyOnFinish`. A Peer whose turn ended while the plugin was down and
   that the plugin had never seen is not replayed: only the native notification covers that turn,
   and the Lead treats a Peer without a handoff as a missing handoff (Monitoring rules).

## Security and operational caveats

- Role tool visibility is not an OS sandbox: the plugin, the daemon and every seat run as the
  **same Unix user**. The outbox at `${PASEO_HOME:-~/.paseo}/epistex-delivery/` is readable and
  writable by any seat. It is a receipt store, not a trust boundary.
- `paseo plugin install` prints that plugin server code runs **unsandboxed on the daemon host**.
- Enabling plugins (`pluginsEnabled: true`) and installing the plugin change the user's live
  `~/.paseo/config.json`; both need the Human's approval.

## Install path (executed on this host 2026-11-02)

```bash
# Human-approved: set "pluginsEnabled": true in ~/.paseo/config.json, then
bash <KIT>/setup/setup-seats.sh --install-plugin   # runs: paseo plugin install <KIT>/plugins/epistex-delivery
paseo reload                                       # the daemon keeps pluginsEnabled in memory; see below
paseo plugin ls --json                             # STATUS must be "running", not "disabled"
paseo plugin logs epistex-delivery                 # expect: registered agent.turn_ended (Paseo >=0.14.0 <0.16)
bash <KIT>/setup/setup-seats.sh --check            # range, path, pluginsEnabled and daemon version
```

Observed on install: the running daemon had read `pluginsEnabled: false` at start, so right after
`--install-plugin` the entry existed but `paseo plugin ls` showed STATUS `disabled`. `paseo reload`
re-read the global switch and the plugin went `running` with no daemon restart. `paseo reload` prints
a hint to run `paseo daemon restart` for plugin sources; it was not needed.

`setup-seats.sh` shares the `>=0.14.0 <0.16` range with `paseo-plugin.json` and `server/plugin.ts` and
fails when they drift. A prerelease counts as its stable core, as in Paseo's own check. It refuses to
install under `--check`, when `paseo --version` is outside the range, or when
`pluginsEnabled` is not `true`; it never edits `config.json` itself (the daemon does, through the
CLI). With the plugin installed, `--check` fails when the entry is not a `directory` source at the kit
path, points through a symlink, is disabled, `pluginsEnabled` is off, or the daemon version is outside
the range; without `paseo` on PATH the version check is reported as pending. `--check` also fails
when `agents.resumeOnStartup` (Paseo 0.15+, default off) is on (decision 7); it never changes it. `--remove-plugin` removes the
config entry and keeps the receipts under `${PASEO_HOME:-~/.paseo}/epistex-delivery/`.

## Live evidence

The run logs are kept outside the tracked docs, in the local `eval/results/delivery-plugin-live-runs.md`.
The conclusions:

- **Paseo 0.14.0 (2026-11-02):** five fault-injection scenarios passed (smoke, busy Lead, missed turns
  plus reconcile, crash between fsync and send, Peer cut mid-turn). Two runs with real role prompts
  passed: native `finished` plus plugin delivery for the same turn were handled once. Run 2 found the
  reconcile fault (fixed: a failing Peer is skipped, and the cached catch-up is retried).
- **Paseo 0.15.0 (2026-11-03):** the plugin loads with the range, the hook fires, the five dead Peers of
  the earlier runs are unwatched after one attempt, and a handoff followed by a tool call and filler
  text is delivered as `HANDBACK_VALID` with `trailing_text_after_handoff`.
- **Not covered live:** a real missed `notifyOnFinish` (#6346) on a background completion; one host only.

## Decisions and open questions

Decided by the Human (2026-11-02; items 6 and 7 on 2026-11-03):

1. Parser: **ported to TypeScript** (`server/handoff.ts`) with the shared fixture suite; the Python
   `--parse-only --json` output is the parity oracle.
2. Root (UI-opened) Peers: **out of scope**; the plugin keeps ignoring agents without a parent
   (no Lead to deliver to).
3. Outbox retention after the Lead is archived: **keep for audit**; no compaction. The receipts
   stay under `${PASEO_HOME:-~/.paseo}/epistex-delivery/` until the Human deletes them.
4. Send policy when the Lead is busy (see difference 2): **event-gated send plus `steer`** for the
   residual race (`sourceAgentId: <peerId>`, `activeTurnBehavior: "steer"`, `messageId:
   <delivery-id>`), the same path as native `notifyOnFinish`.
5. Prompt workaround for #6346 (bounded rounds, `BLOCKED`/`WAITING_CI` handoffs on a CI route,
   Lead escalation of interim messages): **removed from `agents/LEAD.md` and `agents/PEER.md`**
   after the fault-injection pass and the real-seat run above. The #3256 handling (stale
   foreground turn, Human-run reload) stays. The plugin is therefore **required**: a host without
   it has no mitigation for #6346, and `setup/setup-seats.sh --check` fails until it is installed.
   Running seats keep their old injected instructions until a separate authorized transition.

6. Paseo requirement (2026-11-03): **`>=0.14.0 <0.16`** instead of `0.14.0` exactly, after the 0.15.0
   SDK check and live run. 0.16 needs a new check (the deprecated `server.on` is removed after
   2027-04-30; `addHook("agent.turn.after")` replaces it).
7. `agents.resumeOnStartup` (2026-11-03): **keep off**. When on, a Peer cut by a daemon restart gets
   "Resume working." and keeps writing its round, while the Lead treats it as `was closed` and
   reassigns the round. `setup-seats.sh --check` fails when it is on.

Resolved (2026-11-03): the `droid-peer` stop on an `edit` permission request in live run 2 came from the
kit, not Paseo. The 23 `droid-peer` profiles had no `modeId`, and the profile notes tell the Lead to omit
absent settings, so the Peer started in Droid's `normal` mode. The profiles now carry `modeId: "auto-high"`
and `--check` requires it ([Droid seats](droid.md)). Verified with a real Lead launch on 0.15.0 (see the
live-run log).

No open questions remain.
