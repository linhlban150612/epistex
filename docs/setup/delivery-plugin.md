# Epistex delivery plugin (Paseo >=0.15.0 <0.16)

`plugins/epistex-delivery/` is a required Paseo **server plugin** and the only report channel
from a Peer to the Lead that created it. [OVERVIEW.md](../../plugins/epistex-delivery/OVERVIEW.md)
is the short summary shipped with the plugin; this document owns its design, install, decisions
and verification status.

The plugin only adds delivery. It does not create, cancel, archive, reload or re-mode agents, does
not answer permissions, does not accept work, and runs no timers, schedules, heartbeats or periodic
scans. Its outbox is a delivery receipt store outside Git; it holds no authority or decisions.

## Design

- **Entry and guard.** `index.server.ts` wires `server/plugin.ts`, which registers
  `agent.turn.after` and `agent.permission.before` through `server.addHook`. Without `addHook`, or
  when either hook cannot be registered, it logs the reason and registers nothing.
- **Parser.** `server/handoff.ts` ports `parse_handoff`/`classify_handoff` from
  `setup/check-handoff`. `check-handoff --parse-only <file> --json` is the parity oracle:
  `tests/fixtures/handoffs/` runs through both (`node --test` in the plugin, driven by
  `tests/test_delivery_plugin.py`); `expected.json` there holds the reason codes of each accepted
  markup form (`ok-*`) and each rejection (`bad-*`). Real receipts stay outside Git:
  `eval/extract-receipts --out .amp/in/receipts` writes them and the parity test reads
  `$EPISTEX_RECEIPTS` (default `.amp/in/receipts`), skipped when the folder is absent. An invalid
  receipt carries `codes` (`HEADER_MISSING`, `CELL_MISSING:<name>`, `CANDIDATE_IDENTITY`,
  `TURN_CANCELED`, `NO_MESSAGE`) in the record and as a `codes:` line before `reasons:`.
- **Round warnings** (`roundWarnings` in `server/delivery.ts`). A receipt whose round is a plain
  number above 3 carries `warning: round <n> exceeds rework limit 3; REOPEN or context-reset
  required`. A Peer's first receipt for a task, at a round above one that another Peer of the same
  Lead reported, carries `warning: task reused across peers`; the receipt store supplies the earlier
  receipts. Warnings are stored in `warnings` and never change `kind`.
- **Brief check** (`server/brief.ts`, a port of `setup/check-brief`; `brief.test.ts` holds the
  parity cases). On a Peer's first receipt the plugin reads the Peer's first user message, takes
  the body of the Lead's `agent-message` envelope (role instructions an ACP launcher put before it
  are left out) and stores its codes in `briefCodes`; an empty list is a pass. A failed brief adds
  `warning: brief failed check-brief: <codes>`. The warning arrives with the first handback, not
  before the Peer starts. A first prompt that is not this Lead's agent message is not checked.
- **Tool-call count**. Each receipt stores `toolCalls`, the `tool_call` entries read for it. When
  the sum for one Peer reaches 150 (`TOOL_CALL_LIMIT`), the receipt carries `warning: peer session
  at <n> tool calls (limit 150); context-reset or a new Peer advised`. A first turn longer than
  the 200-entry tail is counted from the tail only, so the count is a lower bound.
- **Receipt store** (`server/outbox.ts`, under `${PASEO_HOME:-~/.paseo}/epistex-delivery/`):
  `<leadAgentId>.jsonl` is append-only with `fsync`; a `sent` update is a second line for the same
  `deliveryId`, folded on load; a torn last line is skipped with a warning. `cursors.json` is
  written as temp file + rename. `deliveryId()` = sha256 over
  `peerAgentId, taskId|"?", round|"?", candidate|"?", lastMessageId`. A Peer-turn receipt records
  `outcome` (`completed`/`failed`/`canceled`, `unknown` for a restart catch-up) for
  `eval/report --receipts`; permission receipts have none.
- **Peer turn end** (`server/delivery.ts`). For a child whose parent (`refresh()`) is a Lead seat
  (provider `^[a-z]+-lead(--.*)?$`), the handler reads the Peer's timeline `after` the stored
  cursor (`tail` when the cursor is stale, the timeline was reset or the `epoch` changed;
  `hasNewer` is followed). It delivers the last `assistant_message` that is a valid handoff,
  preferring the ended `turnId`; assistant text after it travels as `trailing` with
  `warning: trailing_text_after_handoff`. Without a valid handoff the last message is classified.
  A `completed` turn with no new assistant message is logged and not delivered (a replayed hook
  lands here); `failed`/`canceled` turns without a message become `TURN_ENDED_NO_MESSAGE`. Root
  agents and children of non-Lead parents are ignored.
- **Re-anchor.** A replaced timeline (archive, reload) returns old messages under new
  `messageId`s, so the tail is re-anchored after the last `assistant_message` whose text equals
  the Peer's newest recorded text (its last `trailing`, else its body); the cursor still advances
  to the end of the tail. Residual: an identical handoff the Peer writes again after a replacement,
  and that was not yet recorded, is taken as already delivered.
- **Permission request.** For such a Peer, `agent.permission.before` (observe-only in Paseo)
  records and sends `PERMISSION_REQUESTED` with the Peer's `agentId`/`requestId` to the Lead's
  `paseo.parent-agent-id` when that is a live `*-supervisor` seat, otherwise to the Lead.
- **Send.** The record is appended and fsynced and the cursor advanced before sending. A message
  is sent only while its recipient is `idle`/`error`, with `{sourceAgentId: <peer>,
  activeTurnBehavior: "steer", messageId: <delivery-id>}`; otherwise it stays `pending` and the
  recipient's own turn end flushes it. `send()` resolves on acceptance only, so delivery is at
  least once and the recipient processes each `delivery-id` once.
- **Reconcile.** Hooks are not replayed and the plugin is a child process, so the first
  `agent.turn.after` hook of each plugin process (memoised, no timer) reads every watched Peer that
  is not `running` `after` its cursor, then flushes every Lead with `pending` records. Watched
  Peers are those with a stored cursor, so a fresh install does not replay old handbacks. A Peer
  that is gone, archived or `closed` gets that one attempt and is then unwatched (cursor removed,
  receipts kept). A Peer whose timeline read fails is skipped so the others still catch up; a
  reconcile that fails as a whole runs again on the next hook. A Peer turn
  that ended while the plugin was down and that the plugin never saw is a missing handoff for the
  Lead ([Lead monitoring](../../agents/LEAD.md#monitoring)).

## Paseo API the plugin relies on

Read from the installed `@getpaseo/{plugin,server,client,protocol}` packages and the live daemon.

| Topic | Fact | Source |
|---|---|---|
| Plugin entry | `index.server.ts`/`.tsx` (legacy `index.ts`), default export `contribute(server) => cleanup`; `cleanup` must be a function. `contribute` receives no `PaseoApi`: `paseo` arrives in the hook context `(payload, {paseo, signal})`. | `plugin-process.js` |
| Hooks | `server.addHook(name, handler)` (0.15+); `server.on`/`before` are deprecated and removed after 2027-04-30. `agent.turn.after` (legacy alias `agent.turn_ended`) and `agent.permission.before`. | `plugin/dist/server/lifecycle.d.ts` |
| Hook payload | `{agent: {id, workspaceId, parentAgentId, provider, cwd, title}, turnId, outcome: {kind: completed\|failed\|canceled, ...}, timeline: []}`. `timeline` is deprecated and always empty, so the handler must `timeline.refetch`. | `plugins/lifecycle/index.js` |
| Hook emission | Emitted for every `turn_completed`/`turn_failed`/`turn_canceled` stream event, including background completions; `internal` agents emit nothing. A throwing handler is logged, never replayed. | `plugins/lifecycle/index.js` |
| Process model | Each plugin is a forked child process on the Paseo session socket (`ipc://plugin/<id>`); a daemon restart restarts the plugin. | `plugin-process.js`, `runtime.js` |
| Parent link | `agent.parentAgentId` = label `paseo.parent-agent-id`, set on agents created through MCP `create_agent`. | `protocol/dist/agent-labels.js` |
| Lead detection | `agent.provider` is the agent-profile id, e.g. `claude-lead`, `droid-lead--gpt-6-1-sol--medium`. | `paseo agent ls --json` |
| Agent status | `paseo.agents.ref(id).refresh()` / `agents.list()` give `labels`, `parentAgentId`, `provider`, `status ∈ {initializing, idle, running, error, closed}`. | `client/dist/index.d.ts` |
| Timeline read | `timeline.refetch({direction: tail\|before\|after, cursor?, limit})` → `{entries, endCursor, hasNewer, epoch, reset, staleCursor, ...}`; cursor `{epoch, seq}`; a timeline replacement changes `epoch`. `assistant_message` items carry `text` and `messageId?`. | `protocol/dist/messages.js` |
| Send | `ref(id).send(text, {sourceAgentId?, messageId?, activeTurnBehavior?})` resolves when the daemon accepts. `ActiveTurnBehavior` is `interrupt`\|`steer`; there is no queue-until-idle value. With `sourceAgentId`, messages coalesce for 2 quiet seconds, then steer into or replace a running turn. Native `notifyOnFinish` uses the same path. | `session.js`, `agent/agent-messages/delivery.js`, `agent-manager.js` |
| Manifest / build | `paseo-plugin.json` with `requirements.paseo`; esbuild cjs `node20`, `@getpaseo/plugin*` and `zod` host-provided, imports outside the plugin directory rejected. | `plugins/manifest.js`, `plugins/compiler-build.js` |
| Install | `paseo plugin install <dir>` writes a `directory` source into `plugins` in `~/.paseo/config.json`; loading requires top-level `pluginsEnabled: true`. | `cli/dist/commands/plugin/index.js` |

## Security and operational caveats

- Not an OS sandbox: the plugin, the daemon and every seat run as the **same Unix user**. The
  receipt store is readable and writable by any seat; it is not a trust boundary.
- `paseo plugin install` prints that plugin server code runs **unsandboxed on the daemon host**.
- Enabling plugins and installing the plugin change the user's live `~/.paseo/config.json`; both
  need the Human's approval.

## Install and check

```bash
# Human-approved: set "pluginsEnabled": true in ~/.paseo/config.json, then
bash <KIT>/setup/setup-seats.sh --install-plugin   # runs: paseo plugin install <KIT>/plugins/epistex-delivery
paseo reload                                       # re-reads pluginsEnabled; no daemon restart needed
paseo plugin ls --json                             # STATUS must be "running", not "disabled"
paseo plugin logs epistex-delivery                 # expect: registered agent.turn.after, agent.permission.before
bash <KIT>/setup/setup-seats.sh --check            # range, path, pluginsEnabled and daemon version
```

A daemon started with `pluginsEnabled: false` shows the new entry as `disabled` until
`paseo reload`.

`setup-seats.sh` shares the `>=0.15.0 <0.16` range with `paseo-plugin.json` and `server/plugin.ts`
and fails when they drift; a prerelease counts as its stable core. It refuses to install under
`--check`, when `paseo --version` is outside the range, or when `pluginsEnabled` is not `true`; it
never edits `config.json` itself. With the plugin installed, `--check` fails when the entry is not
a `directory` source at the kit path, points through a symlink, is disabled, `pluginsEnabled` is
off, or the daemon version is outside the range; without `paseo` on PATH the version check is
reported as pending. `--check` also fails when `agents.resumeOnStartup` is on; it never changes it.
`--remove-plugin` removes the config entry and keeps the receipts.

## Decisions

Human decisions; Git history holds their dates and earlier variants.

1. The handoff parser is ported to TypeScript; the Python `--parse-only --json` output is the
   parity oracle.
2. Root (UI-opened) Peers are out of scope: there is no Lead to deliver to.
3. Receipts are kept for audit after the Lead is archived, with no compaction, until the Human
   deletes them.
4. Busy recipient: event-gated send plus `steer` for the residual race (see [Design](#design)).
5. The plugin is **required**. The earlier prompt workaround for
   [#6346](https://github.com/getpaseo/paseo/issues/6346) is gone from the role prompts, so a host
   without the plugin has no mitigation and `setup-seats.sh --check` fails until it is installed.
   Running seats keep their old injected instructions until a separate authorized transition.
6. Paseo requirement `>=0.15.0 <0.16` (0.14 has no `addHook`); the dev dependency is
   `@getpaseo/plugin` 0.15.3. Paseo 0.16 needs a new SDK check.
7. `agents.resumeOnStartup` stays off: when on, a Peer cut by a daemon restart gets "Resume
   working." and keeps writing its round while the Lead treats it as `was closed` and reassigns it.
8. One report channel: the Lead calls `create_agent`/`send_agent_prompt` for a Peer with
   `notifyOnFinish: false`. Native notifications put every handback into the Lead's context twice,
   cut it at 4000 characters, and can be missed (#6346). Both hooks register or neither.

## Verification status

Verified live with real role seats on Paseo 0.15.x: hook registration, handback delivery as
`HANDBACK_VALID` (including trailing text after the handoff), receipt `outcome` for completed and
canceled turns, `PERMISSION_REQUESTED` routed to the Supervisor and answered there, a single
handoff in the Lead timeline with `notifyOnFinish: false`, re-anchoring after a Peer timeline
replacement, and unwatching dead Peers on reconcile. Earlier fault-injection runs on 0.14.0 covered
a busy Lead, missed turns plus reconcile, a crash between fsync and send, and a Peer cut mid-turn.
Run logs stay outside Git in the local `eval/results/delivery-plugin-live-runs.md`.

Not covered live: a real missed `notifyOnFinish` (#6346) on a background completion; native
`host unreachable`/`host removed` (one host only). A Peer that ends without a turn end the plugin
observes is a missing handoff.
