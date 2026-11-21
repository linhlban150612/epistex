# Epistex delivery plugin (Paseo >=0.17.0 <0.18)

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
- **Typed handoff.** `server/submit.ts` defines the agent tool `epistex_submit_handoff`;
  `index.server.ts` adds it in `agent.open.before` to interactive sessions whose provider is a Peer
  seat. The zod schema holds the six cells: Task ID, round, outcome (enum), done, not done, candidate,
  read paths, proof class (enum), verification, unknown/risk, ownership. The candidate is a union:
  `commit` (base SHA, candidate SHA, branch), `snapshot` (files, each with its sha256) or `none`
  (reason), so a read-only or browser task has a valid candidate. The tool refuses with a code and
  stores nothing when a SHA is not a commit of the worktree (`CANDIDATE_UNRESOLVED`), the candidate
  is the baseline (`CANDIDATE_SAME_AS_BASE`), a snapshot file is gone or has another checksum
  (`SNAPSHOT_FILE_MISSING`, `SNAPSHOT_MISMATCH`), a text field has a line that reads as another cell
  (`CELL_TEXT_AMBIGUOUS`), no Lead created the session (`NO_LEAD`) or the store fails
  (`STORE_FAILED`). The changed paths of a commit come from `git diff --name-only`, not from the
  Peer. The tool renders the six-cell text, stores it in `submissions.json` (temp file + rename)
  and answers `HANDOFF_STORED`; at the Peer's turn end the delivery sends that text as
  `HANDBACK_VALID` in place of the Peer's last message, also when the turn was cut after the call
  (a warning says so). The receipt has `submitted: true`. A Peer session without the tool still
  hands over as text, through the parser.
- **Typed assignment.** `server/assign.ts` defines the agent tool `epistex_assign`; `index.server.ts`
  adds it in `agent.open.before` to sessions whose provider is a Lead seat and whose purpose is
  `interactive`. The zod schema holds the brief fields that were missed in real briefs: Task ID,
  round 1 to 3, Peer profile id, absolute worktree, owned scope, commit required or forbidden, and a
  baseline (commit SHA, or snapshot path with sha256). Paseo rejects input that fails the schema
  before the tool code runs. The tool then refuses with a code and creates nothing when the profile
  is unknown (`PROFILE_UNKNOWN`) or not a Peer seat (`PROFILE_NOT_PEER`), the worktree is not a
  directory (`WORKTREE_MISSING`), the worktree has no HEAD (`BASELINE_UNREADABLE`), `base_sha` is
  not HEAD (`BASELINE_STALE`), the Lead's free text fails `server/brief.ts` (the port of
  `setup/check-brief`, for example `CELLS_REDEFINED`), or Paseo cannot create the agent
  (`CREATE_FAILED`). Otherwise it calls `paseo.agents.create` with the profile's provider/model,
  mode and thinking option, the worktree as `cwd`, the Lead as `parent`, and the composed brief.
  That API has no finish notification, so the receipt is the only report. The tool hook is
  registered apart from the delivery hooks: when it cannot be registered, delivery stays on, but a
  Lead has no tool to create a Peer and reports `BLOCKED`. Rework rounds go to the same Peer with `send_agent_prompt`; the tool
  does not cover them.
- **Parser.** `server/handoff.ts` ports `parse_handoff`/`classify_handoff` from
  `setup/check-handoff`. `check-handoff --parse-only <file> --json` is the parity oracle:
  `tests/fixtures/handoffs/` runs through both (`node --test` in the plugin, driven by
  `tests/test_kit_tools.py`, which also runs `tsc --noEmit`; so `setup/verify` covers the plugin); `expected.json` there holds the reason codes of each accepted
  markup form (`ok-*`) and each rejection (`bad-*`). Both parsers accept Unicode spaces (em space,
  no-break space) between a cell name and its text, because Codex writes them. Real receipts stay outside Git:
  `eval/extract-receipts --out .amp/in/receipts` writes them and the parity test reads
  `$EPISTEX_RECEIPTS` (default `.amp/in/receipts`), skipped when the folder is absent. An invalid
  receipt carries `codes` (`HEADER_MISSING`, `CELL_MISSING:<name>`, `CANDIDATE_IDENTITY`,
  `PROOF_CLASS`, `TURN_FAILED`, `TURN_CANCELED`, `NO_MESSAGE`) in the record and as a `codes:` line before `reasons:`.
- **Round warnings** (`roundWarnings` in `server/delivery.ts`). A receipt whose round is a plain
  number above 3 carries `warning: round <n> exceeds rework limit 3; REOPEN or context-reset
  required`. A Peer's first receipt for a task, at a round above one that another Peer of the same
  Lead reported, carries `warning: task reused across peers`; the receipt store supplies the earlier
  receipts. Warnings are stored in `warnings` and never change `kind`.
- **Brief check** (`server/brief.ts`, a port of `setup/check-brief`; `brief.test.ts` holds the
  parity cases; `tests/fixtures/briefs/` holds shapes of real briefs, with `expected.json` as for
  the handoffs). On a Peer's first receipt the plugin reads the Peer's first prompt: a `tool_call`
  row with `agentMessage` from this Lead (how Paseo 0.15.4 and 0.16.0 show a prompt that is only an agent
  message), or the Lead's `agent-message` envelope inside a `user_message` (role instructions before
  it are left out). It stores the codes in `briefCodes`; an empty list is a pass. A failed brief adds
  `warning: brief failed check-brief: <codes>`. A first prompt that is not this Lead's agent
  message is not checked.
- **Early brief warning** (`warnBriefs`). The same check also runs when the Lead's own turn ends,
  which is the turn that briefed the Peer: the plugin lists the Lead's children
  (`agents.list`, label `paseo.parent-agent-id`, first 200) and reads the first prompt of each
  child that has no receipt yet. A failed brief becomes one `BRIEF_INVALID` delivery to the Lead
  (`codes:` and `reasons:` lines, no body; id from the Peer id; `task:` and `round:` from the
  brief, `?` when the brief does not state them), so the Lead learns it while the
  Peer still works. The Peer is not stopped. The first handback then stores `briefCodes` but does
  not repeat the warning. Each Peer is read once per plugin process; a daemon without
  `agents.list`, or a list that fails, skips this check and the first-handback warning remains.
- **Scope warning** (`ownedScope`, `outsideScope` in `server/brief.ts`). The plugin takes the path
  globs of the brief's `Owned scope` field (the newest Lead message that names one, stored as
  `ownedScope` and reused by later receipts of the Peer). A path under `Changed:` in the handoff's
  `Scope` cell that no glob covers adds `warning: declared change outside the brief's Owned scope:
  <paths>`. A directory name ending in `/` owns the files below it; a scope in prose, without a
  path, is not compared. This compares text with text only: the plugin does not read Git, so
  `setup/check-handoff` stays the gate for the files that really changed.
- **Tool-call count**. Each receipt stores `toolCalls`, the `tool_call` entries read for it,
  without delivered agent messages. When
  the sum for one Peer reaches 150 (`TOOL_CALL_LIMIT`), the receipt carries `warning: peer session
  at <n> tool calls (limit 150); context-reset or a new Peer advised`. A first turn longer than
  the 200-entry tail is counted from the tail only, so the count is a lower bound. The reason for
  150: in 179 Peer sessions over seven days the 95th percentile was 168 calls, and the sessions
  above it lost the brief's rules.
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
  `warning: trailing_text_after_handoff`. Without a valid handoff the kind follows the turn outcome:
  a `failed` or `canceled` turn becomes `TURN_ENDED_FAILED` or `TURN_ENDED_CANCELED` with the
  outcome as its only reason and the last message as body (a quota stop or an interrupt is not a
  broken handoff); a `completed` turn is classified as `TURN_ENDED_INVALID_HANDOFF`.
- **Peer reminder.** A `completed` turn whose last message has no handoff header (a progress line,
  a question, a turn ended while a job runs) is recorded as `PEER_REMINDED` with the Peer as
  recipient: the plugin sends the fixed text `PEER_REMINDER` to the Peer, without a sender, and
  nothing to the Lead. One reminder only: when the Peer's next turn again has no valid handoff, the
  Lead gets `TURN_ENDED_INVALID_HANDOFF` with `warning: peer was reminded once and again ended its
  turn without a handoff`, plus the warnings of the reminded turn. A handoff with a header and wrong
  cells goes to the Lead at once, and a restart catch-up never reminds.
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
  recipient's own turn end flushes it. This includes a `closed` recipient: its deliveries wait for
  the end of the turn that its next prompt starts. `send()` resolves on acceptance only, so delivery is at
  least once and the recipient processes each `delivery-id` once.
- **Reconcile.** Hooks are not replayed and the plugin is a child process, so the first
  lifecycle hook of each plugin process (`agent.turn.after` or `agent.permission.before`; memoised,
  no timer) reads every watched Peer that
  is not `running` `after` its cursor, then flushes every Lead with `pending` records. Watched
  Peers are those with a stored cursor, so a fresh install does not replay old handbacks. A Peer
  that is gone, archived or `closed` gets that one attempt and is then unwatched (cursor removed,
  receipts kept). A Peer whose timeline read fails (Paseo rejects the read when the Peer's cwd
  was deleted; seen live on 0.14.0) is skipped so the others still catch up; a
  reconcile that fails as a whole runs again on the next hook. A Peer turn
  that ended while the plugin was down and that the plugin never saw is a missing handoff for the
  Lead ([Lead monitoring](../../agents/LEAD.md#monitoring)).

## Paseo API the plugin relies on

Read from the installed `@getpaseo/{plugin,server,client,protocol}` packages and the live daemon.
A source path starts with its package directory (`plugin/`, `protocol/`, `client/`, `cli/`); a path
without that prefix is below `server/dist/server/server/` of `@getpaseo/server`, not in this kit.

| Topic | Fact | Source |
|---|---|---|
| Plugin entry | `index.server.ts`/`.tsx` (a legacy `index.ts`/`.tsx` entry is rejected with a migration error), default export `contribute(server) => cleanup`; `cleanup` must be a function. `contribute` receives no `PaseoApi`: `paseo` arrives in the hook context `(payload, {paseo, signal})`. | `plugins/compiler-build.js`, `plugins/bundle-evaluator.js`, `plugins/plugin-process.js` |
| Hooks | `server.addHook(name, handler)` (hook names added in v0.14); `server.on`/`before` are deprecated and removed after 2027-04-30. `agent.turn.after` (legacy alias `agent.turn_ended`) and `agent.permission.before`. | `plugin/dist/server/lifecycle.d.ts`, `plugin/dist/server/lifecycle.js` |
| Hook payload | `{agent: {id, workspaceId, parentAgentId, provider, cwd, title, background, metadata}, turnId, outcome: {kind: completed\|failed\|canceled, ...}}`. The payload carries no history (0.16 removed the always-empty `timeline` field), so the handler must `timeline.refetch`. | `plugin/dist/server/lifecycle.d.ts`, `plugins/lifecycle/index.js` |
| Hook emission | Emitted for every live `turn_completed`/`turn_failed`/`turn_canceled` stream event, including background completions (a repeat for an already finalized turn and history replay emit nothing); `internal` agents emit nothing. A throwing handler is logged, never replayed. | `plugins/lifecycle/index.js`, `agent/agent-manager.js` |
| Agent tools | `agent.open.before` receives `{request: {agentId, provider, purpose, tools, ...}}` and may return a changed request; a tool is `{name, title, description, input: zod schema, execute(input, {agent, paseo})}` and returns `{text, isError?}`. Paseo validates `input` before `execute`. A seat sees a plugin tool only when its `paseoTools.enabled` is true. | `plugin/dist/server/index.d.ts`, live probe |
| Agent creation | `paseo.agents.create({config: {provider: "<seat>/<model>", modeId?, thinkingOptionId?}, cwd, parent, title, prompt})` returns a handle with `id` and sets the label `paseo.parent-agent-id`; it sends no finish notification to the parent. | live probe |
| Process model | Each plugin is a forked child process on the Paseo session socket (`ipc://plugin/<id>`); a daemon restart restarts the plugin. | `plugins/plugin-process.js`, `plugins/runtime.js` |
| Parent link | `agent.parentAgentId` = label `paseo.parent-agent-id`, set on agents created through MCP `create_agent`. | `protocol/dist/agent-labels.js` |
| Lead detection | `agent.provider` is the agent-profile id, e.g. `claude-lead`, `droid-lead`. `paseo agent ls --json` prints it as `<id>/<model>`, e.g. `claude-lead/claude-opus-5-5`. | `plugins/lifecycle/index.js`, `paseo agent ls --json` |
| Agent status | `paseo.agents.ref(id).refresh()` / `agents.list()` give `labels`, `provider`, `status ∈ {initializing, idle, running, error, closed}`. A snapshot has no `parentAgentId` field; read `labels["paseo.parent-agent-id"]`. | `client/dist/index.d.ts`, `protocol/dist/messages.js`, `protocol/dist/agent-lifecycle.js` |
| Timeline read | `timeline.refetch({direction: tail\|before\|after, cursor?, limit})` → `{entries, endCursor, hasNewer, epoch, reset, staleCursor, ...}`; cursor `{epoch, seq}`; a timeline replacement changes `epoch`. `assistant_message` items carry `text` and `messageId?`. | `protocol/dist/messages.js` |
| Send | `ref(id).send(text, {sourceAgentId?, messageId?, activeTurnBehavior?})` resolves when the daemon accepts. `ActiveTurnBehavior` is `interrupt`\|`steer`; there is no queue-until-idle value. With `sourceAgentId`, messages coalesce for 2 quiet seconds, then steer into or replace a running turn. Native `notifyOnFinish` uses the same path. | `session.js`, `agent/agent-messages/delivery.js`, `agent/agent-manager.js`, `agent/finish-subscriptions/index.js` |
| Manifest / build | `paseo-plugin.json` with `requirements.paseo`; esbuild cjs `node20`, `@getpaseo/plugin*` and `zod` host-provided, imports outside the plugin directory rejected. | `plugins/manifest.js`, `plugins/compiler-build.js`, `plugins/compiler-esbuild.js` |
| Install | `paseo plugin install <dir>` writes a `directory` source into `plugins` in `~/.paseo/config.json`; loading requires top-level `pluginsEnabled: true`. | `plugins/index.js`, `cli/dist/commands/plugin/index.js` |

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

`setup-seats.sh` shares the `>=0.17.0 <0.18` range with `paseo-plugin.json` and `server/plugin.ts`
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
5. The plugin is **required**: the role prompts carry no workaround for
   [#6346](https://github.com/getpaseo/paseo/issues/6346), so a host without the plugin has no
   mitigation and `setup-seats.sh --check` fails until it is installed.
6. Paseo requirement `>=0.17.0 <0.18`; the dev dependency is `@getpaseo/plugin` 0.17.0. A daemon
   outside the range refuses to load the plugin, so each new Paseo minor needs a new SDK check
   (typecheck, tests, one live Lead and Peer run) before the range moves. The plugin types follow
   the 0.16 SDK (no `timeline` in the `agent.turn.after` payload; `background` and `metadata` on
   the hook agent); the 0.17 SDK only adds to it (`appendSystemPrompt` on the `agent.open.before`
   request, `registerWorktreeManager`), and the plugin uses neither. 0.16 is no longer in the
   range: the deny-lists name the three tools that 0.17 adds to the catalog.
7. `agents.resumeOnStartup` stays off: when on, a Peer cut by a daemon restart gets "Resume
   working." and keeps writing its round while the Lead treats it as `was closed` and reassigns it.
8. One report channel: the Lead calls `send_agent_prompt` for a Peer with
   `notifyOnFinish: false`, and `epistex_assign` creates a Peer with no finish notification. Native notifications put every handback into the Lead's context twice,
   cut it at 4000 characters, and can be missed (#6346). Both hooks register or neither.
9. A Lead creates a new Peer only with `epistex_assign`: `create_agent` is blocked in the Lead tool
   policy, so a brief that fails the schema or the baseline check cannot reach a Peer. A Supervisor
   keeps `create_agent` to open Leads.
10. A Peer hands over with `epistex_submit_handoff`. A plugin tool reaches a session only through
    the Paseo channel, so every Peer seat has `paseoTools.enabled: true` with every catalog tool
    in `disabledTools` ([SETUP.md §3](../../SETUP.md#paseo-tools-policy-for-lead-and-supervisor)): the Peer sees the handoff tool and no Paseo tool. `setup-seats.sh --check`
    enforces the list. The text handoff and its two parsers stay as the fallback and for the
    Lead's `setup/check-handoff`; they are not removed until no Peer session uses them.

## Verification status

Live runs used real role seats; their logs stay outside Git.

- **Paseo 0.17.0** (2026-11-21, Droid 1.17.0, the live daemon): with `@getpaseo/plugin` 0.17.0,
  `tsc --noEmit` and the plugin tests pass. The plugin was `running` with its three hooks. A
  `droid-lead` (Sonnet 5.5) created a `droid-peer` (Haiku 5.5) with `epistex_assign` (T-1, round 1,
  commit baseline); the Peer committed and called `epistex_submit_handoff`; the Lead got one
  `HANDBACK_VALID` delivery (`submitted`), and `setup/check-handoff` on that body printed
  `READY_FOR_REVIEW`. Ten Peer seats (Claude, Codex, Kiro, Cursor, Antigravity, Devin, Amp, Droid,
  Pi, OMP) each started with the role prompt, the requested cwd, and `epistex_submit_handoff` as
  the only Paseo-channel tool. `copilot-peer` is disabled in the live config and was not run.
- **Paseo 0.16.0** (2026-11-16, Droid 1.12.1, a separate daemon with a copy of the live seat
  config): the plugin loaded as `running` and registered its three hooks. A `droid-lead`
  (Sonnet 5.5) listed seven Paseo tools and `epistex_assign`, had no `create_agent`, and created a
  `droid-peer` (Haiku 5.5) with `epistex_assign`; the Peer committed and called
  `epistex_submit_handoff`; the Lead got one `HANDBACK_VALID` (`submitted: true`, `briefCodes: []`)
  and no `[Agent finished]`. A root `droid-peer` listed `epistex_submit_handoff` and no catalog
  tool. After a plugin reload, reconcile read the watched Peer and sent no second delivery.
- **Delivery core** (Paseo 0.15.x): hook registration, `HANDBACK_VALID` with trailing text,
  receipt `outcome` for completed and canceled turns, `PERMISSION_REQUESTED` routed to the
  Supervisor and answered there, one handoff in the Lead timeline with `notifyOnFinish: false`,
  re-anchoring after a Peer timeline replacement, and unwatching dead Peers on reconcile.
- **`epistex_assign`** (Paseo 0.15.4, 2026-11-14 and 15): on `droid-lead`, `claude-lead`,
  `codex-lead`, `omp-lead`, `kiro-lead`, `cursor-lead`, `amp-lead` and `agy-lead`, each with a
  `droid-peer` profile, round 7 was rejected by the schema, a wrong `base_sha` returned
  `BASELINE_STALE`, a Lead profile returned `PROFILE_NOT_PEER` (no Peer created in either case),
  and valid input returned `ASSIGNED` with a receipt holding the task, round 1 and
  `briefCodes: []`, then one `HANDBACK_VALID` and no native finish notification. With
  `create_agent` blocked, each Lead had no `create_agent` and listed the seven Lead tools and
  `epistex_assign` (the OMP Lead was asked only for names containing `paseo` or `epistex`). Kiro
  and Cursor Leads see the tool only through their allowlists (`setup/kiro-lead.json`, which
  `setup/cursor-acp` also reads); the Cursor Lead still asks permission for `git` shell commands.
- **`epistex_submit_handoff`** (Paseo 0.15.4, 2026-11-15, briefs that did not name the tool):
  `droid-peer`, `claude-peer`, `kiro-peer`, `amp-peer`, `agy-peer`, `omp-peer-1`, `omp-peer-2` and
  `devin-peer` committed and submitted `commit`; `droid-peer-2` submitted `none` for a read-only
  task; `codex-peer` could not write `.git` in its sandbox and submitted `BLOCKED` with a
  `snapshot`; `cursor-peer` submitted after two shell permission requests were allowed by hand (the
  Human's Cursor config allows only `ls` and `pwd`; the tool call needed no request). Every Lead
  got one `HANDBACK_VALID` with `submitted: true` and no `[Agent finished]`. A snapshot file inside
  the worktree is stored relative to it, so the scope warning compares it with the brief.
- **Fault injection** (a busy Lead, missed turns plus reconcile, a crash between fsync and send, a
  Peer cut mid-turn): Paseo 0.14.0 only, below the required range.

Not covered live: on 0.17.0, every behavior except the 0.17.0 item; on 0.16.0, every behavior above except the 0.16.0
item and on backends other than Droid; the snapshot baseline of `epistex_assign`, a round above 1 for a replacement Peer, and
a Lead that chooses the tool without a prompt that names it; `epistex_submit_handoff` on
`pi-peer`, `omp-peer`, `droid-peer-3` and `copilot-peer`, a tool refusal and a rework
round; a real missed `notifyOnFinish` (#6346) on a background completion; native
`host unreachable`/`host removed` (one host only). A Peer that ends without a turn end the plugin
observes is a missing handoff.
