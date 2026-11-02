# Epistex delivery plugin (Paseo 0.14.0)

Status: **Step 8 (installed on this host and verified live, 2026-11-02; five fault-injection
scenarios passed, see [Live fault-injection results](#live-fault-injection-results-2026-11-02),
and one run with the real role prompts, see
[Live run with real seats](#live-run-with-real-seats-2026-11-02)).** The facts below were read from the installed Paseo
0.14.0 build (`$(npm root -g)/@getpaseo/cli/node_modules/@getpaseo/{plugin,server,client,protocol}`)
and from the live daemon on this host. `plugins/epistex-delivery/` holds the manifest (pin
`0.14.0`), the entry and a fail-closed version guard: without `server.on` or when
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
timeline read `after` the stored cursor (tail when stale, `hasNewer` followed), the last
`assistant_message` (preferring the ended `turnId`) is classified, the record is appended and
fsynced, the cursor advanced, then sent with `{sourceAgentId: peer, activeTurnBehavior: "steer",
messageId: delivery-id}` only while the Lead is `idle`/`error`. Root agents and children of
non-Lead parents are ignored. A `completed` turn with no new assistant message after the cursor
is logged and not delivered (its message, if any, was delivered already; a replayed hook lands
here); `failed`/`canceled` turns without a message become `TURN_ENDED_NO_MESSAGE`. Reconcile
(difference 6) runs once per plugin process on the first `agent.turn_ended` event: every Peer
with a stored cursor that is not `running` is read `after` its cursor and recorded, then every
Lead with `pending` records is flushed. Installed in `~/.paseo/config.json` on this host as a
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
paseo plugin logs epistex-delivery                 # expect: registered agent.turn_ended (Paseo 0.14.0)
bash <KIT>/setup/setup-seats.sh --check            # pin, path, pluginsEnabled and daemon version
```

Observed on install: the running daemon had read `pluginsEnabled: false` at start, so right after
`--install-plugin` the entry existed but `paseo plugin ls` showed STATUS `disabled`. `paseo reload`
re-read the global switch and the plugin went `running` with no daemon restart. `paseo reload` prints
a hint to run `paseo daemon restart` for plugin sources; it was not needed.

`setup-seats.sh` shares the `0.14.0` pin with `paseo-plugin.json` and `server/plugin.ts` and fails when
they drift. It refuses to install under `--check`, when `paseo --version` is not the pin, or when
`pluginsEnabled` is not `true`; it never edits `config.json` itself (the daemon does, through the
CLI). With the plugin installed, `--check` fails when the entry is not a `directory` source at the kit
path, points through a symlink, is disabled, `pluginsEnabled` is off, or the daemon version differs from
the pin; without `paseo` on PATH the version check is reported as pending. `--remove-plugin` removes the
config entry and keeps the receipts under `${PASEO_HOME:-~/.paseo}/epistex-delivery/`.

## Live fault-injection results (2026-11-02)

Paseo 0.14.0, daemon on `127.0.0.1:6767`, plugin installed as above. Harness: one Lead
(`droid-lead`, id `71feea91…`, prompt: reply only `ACK <delivery-id> <kind>`) and two Peers
(`droid-peer`, A `69625e7a…`, B `d2c01db3…`) created with `paseo run --label
paseo.parent-agent-id=<lead>`; each Peer echoed `tests/fixtures/handoffs/valid.txt` with its own
Task/Round. Receipts: `~/.paseo/epistex-delivery/71feea91-….jsonl` and `cursors.json`. The eval
workspace was archived afterwards; the receipts were kept (open question 3).

| Scenario | Injected fault | Observed | Result |
| --- | --- | --- | --- |
| A. Smoke | none | Peer A turn end → `recorded HANDBACK_VALID 10e86e3f…`, `sent`; Lead received the §4.4 message and ACKed the id. Outbox and cursor file created. | pass |
| B. Lead busy | Lead in a long turn when Peer A ended | Record `bc145291…` stayed `pending` ("lead is running; 1 delivery(ies) stay pending"); no steer into the running turn. When the Lead went idle (its turn was stopped), the record was `sent` and ACKed. | pass |
| C. Missed turns + reconcile | `paseo plugin disable`, round 2 for A and B (plugin silent), `paseo plugin enable`, ping Lead | First event after enable reconciled 2 watched Peers in order (`5ee2305a…`, `3c3a456e…`): `recorded` + `sent`; Lead ACKed both ids. | pass |
| D. Crash between fsync and send | Record `c0ffee…` injected as `pending` in the jsonl, Peer A mid-turn, `paseo daemon restart`, ping Lead | Cursor stale → tail read; A and B deduped ("already recorded; replay"); `c0ffee…` `sent` exactly once; Lead ACKed. Peer A came back `idle`, its cut turn produced no message. | pass |
| E. Peer cut mid-turn | `paseo agent stop` on Peer B during a long turn | `TURN_ENDED_NO_MESSAGE 42b417d0…` with reasons "turn canceled: Interrupted; no assistant message after cursor"; Lead ACKed; agent count unchanged (no writer created). | pass |

Side observations, not plugin faults: `paseo ls`/`inspect` show `labels: null` for Peers created
with `--label paseo.parent-agent-id=…` although the plugin receives the parent correctly; after
the restart the Lead timeline shows a Paseo-generated `[Message received] <title>` line for Peer B.
Scope of the evidence: one host, one Lead, two Peers, five scenarios; it proves the delivery path
on 0.14.0. The run below adds the real role prompts to that evidence; on both, the Human decided
the prompt workaround's removal (decision 5 below).

## Live run with real seats (2026-11-02)

Same host and plugin. Lead `droid-lead/gpt-6.1-sol` (thinking `low`, mode `auto-high`, id
`9788612c…`) started with the `examples/LEAD_INITIAL_PROMPT.md` template on a scratch clone of a
Java repository (`./verify quick` exit 0 at the baseline). Peers were created by the Lead itself:
`droid-peer/deepseek-v4.1-flash-1017`, effort `low`. Task: unit tests for `DataUtil.parseToLong`,
owned scope `src/test/java/com/smac/utils/**`, commit required. Receipts:
`~/.paseo/epistex-delivery/9788612c-….jsonl` (five records, all `sent`), `cursors.json`.

| Step | Peer | Observed | Result |
| --- | --- | --- | --- |
| Task 1, round 1 | `2b19cfaf…` | Peer committed `83f14f2` (7 tests pass). The Lead received both the native `[Agent finished]` and `[epistex-delivery] TURN_ENDED_INVALID_HANDOFF bb3d762b…` (reason: missing cell `Ownership`; the Peer wrote "Cessation and ownership"). The Lead handled them as one turn (§4.6): asked for a handoff-only resend, received `HANDBACK_VALID 3c4e5586…`, accepted `83f14f2`, archived the Peer. No duplicate round was assigned. | pass |
| Task 2, round 1 | `7a9a3402…` | Peer committed `744d975` (9 tests pass). Same sequence: `TURN_ENDED_INVALID_HANDOFF 332e4375…` (task/round header missing) → resend → `HANDBACK_VALID a7050d02…` → accepted; Peer left idle on request. | pass |
| Duplicate handback | `7a9a3402…` | The Peer was told directly to repeat its last handoff verbatim. The plugin recorded a new delivery `529368e3…` (new `lastMessageId`, so a new delivery-id, as designed). The Lead received it and took no action: no new round, no second acceptance, no reply. | pass |

Observations, not plugin faults:

- The Lead's first turn stalled for about 8 minutes after a `Glob` call (Droid session log
  without new messages, status `running`). `paseo agent stop` followed by an `interrupt` prompt
  made it continue and create the Peer. Backend (Droid / `gpt-6.1-sol`) behaviour; cause not
  identified.
- Both Peers produced the handoff cells with wrong labels or without the `Task ID | Round`
  header on the first try, so the plugin classified the real turn end as
  `TURN_ENDED_INVALID_HANDOFF` and the Lead had to request a resend. That is the §4.3 contract,
  not a parser fault; the resend was valid both times.
- The #6346 case itself (a background completion whose `notifyOnFinish` never arrives) did not
  occur in this run: every turn end produced the native notification and the plugin delivery.
  The run therefore proves the duplicate path (native plus plugin, same turn, handled once), not
  the missing-notification path, which the fault-injection scenarios C and D cover.

## Live run 2 after the cleanup (2026-11-02)

Same setup on a fresh clone (`eval/live-delivery-20261102-225410`, baseline `736f30c`, kit
installed with `setup-seats.sh --project`, plugin installed as `--install-plugin` default). Lead
`droid-lead/gpt-6.1-sol` (`485b657b…`), Peer created by the Lead:
`droid-peer/deepseek-v4.1-flash-1017`, effort `low` (`0b5b2224…`). Task `INT-TESTS`: unit tests for
`DataUtil.safeToInt`/`parseToInt`, commit required. Receipts: `~/.paseo/epistex-delivery/485b657b-….jsonl`.

| Step | Observed | Result |
| --- | --- | --- |
| Reconcile with stale cursors | The first event after the plugin reload read the four watched Peers of the earlier runs; each timeline read failed with `Working directory does not exist` (their clones were deleted). Each Peer was skipped with a logged error, `reconciled 4 watched peer(s)`, and the live event was still processed. | pass (after the fix below) |
| Round 1 | Peer committed `f4c7066` (15 tests pass), wrote a valid handoff, then ended the turn with a `TodoWrite` call and the text "the handoff above stands". Plugin: `TURN_ENDED_INVALID_HANDOFF b7f09c47…` (header and all cells missing in the last message). Lead asked for a handoff-only resend; plugin: `HANDBACK_VALID 54fca5c4…` (`INT-TESTS`, round 1, candidate `736f30c..f4c7066`). Lead reran `./verify quick` (exit 0), accepted the commit, archived the Peer. One round, no duplicate assignment. | pass |

Plugin fault found and fixed in this run: `reconcile()` let a failed timeline read of one watched
Peer throw out of the `agent.turn_ended` handler, so two Lead turn ends were dropped and, because the
rejected promise was cached, every later event failed too. `server/delivery.ts` now skips that Peer
(`reconcile: peer <id> skipped: <error>`) and, if reconcile still fails, clears the cached promise,
logs and handles the live event anyway. Regression test: "reconcile skips a watched peer whose
timeline read fails and still delivers the live event".

Observation, not a plugin fault: the Peer's Paseo record carries `config.modeId: auto-high`, yet
its Droid session stopped on an `edit` permission request until the Human ran
`paseo agent mode <peer> auto-high` and `paseo permit allow`. The Lead correctly refused to approve
it. Cause not identified (Droid ACP mode application at session start); watch for it on
`droid-peer` seats.

## Decisions and open questions

Decided by the Human (2026-11-02):

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

No open questions remain.
