# Epistex desk and Jev-style handoff

Date: 2026-09-26, Asia/Ho_Chi_Minh.

This is a local checkpoint with known defects, not feature acceptance or a release.
The Human requested a full review, a handoff of completed/outstanding work, and local
commits. Do not infer permission to push, merge, deploy, accept a task, or close a lane.

Source conversation: https://ampcode.com/threads/T-01a0db96-fddb-734a-860d-06eea9d2d4c6

Previous investigation: https://ampcode.com/threads/T-01a0d3a5-1ae7-73a8-a11f-c8ef6b2fbbde

## Repositories and delivery state

| Repository | Local checkout / branch | Reviewed scope |
| --- | --- | --- |
| Epistex | `/home/linh/work/paseo/epistex`, local `main` | All 18 changed/new files relative to initial commit `ae69a00`, plus this handoff |
| chrome-cdp | `/home/linh/.paseo/worktrees/0rrjafnn/epistex-p2`, `epistex-p2` | Full seven-file Jev feature diff from `b9ba9f8789d343aba28aced637152921b43c02f9` to `2572509cf99e5a41c67b7193cde4ccb7a212db8c` |
| chrome-cdp root | `/home/linh/work/chrome-cdp`, local `main` | Unchanged at the original feature base; feature remains in its worktree |

The commit containing this file checkpoints all reviewed Epistex changes, including
the previously uncommitted standalone-role rollout. No history was rewritten.
Jev changes are already committed locally; the three repair commits are:

- `8c82f9d777b323673fece01439e8aa4ffe2826c4`: initial role-guard correction.
- `aa27e55c3055057c325a918ba1f00ec59353da5d`: shared serialized observation/action guards.
- `2572509cf99e5a41c67b7193cde4ccb7a212db8c`: restore unlabeled-checkbox regression coverage.

The repair base is `e2b3efc7047437331a343fc8457c8db292aa2b43`. Older feature and
review-era commits are preserved. Nothing was pushed, merged, deployed, or released.

## Completed: Epistex

The earlier rollout, now included in the checkpoint, adds five roles across seven
providers (35 profiles), native/ACP role launchers, project/role Codex runtimes,
durable desk state/outbox, a patrol installer, prompts, setup documentation and tests.
It does not provide an OS sandbox or the Seatworks plugin's full governance engine.

This repair completed:

- Explicit `--workspace` routing for lane Peers, Reviewers and Watchers. A missing
  or ambiguous workspace match fails before launch; CWD validation remains enforced.
- Handbacks bound to a working round and declared candidate identifier. Only the
  currently assigned Reviewer can complete the current review. Historical handbacks
  remain available; candidate existence/immutability is still verified procedurally.
- Pending rework/handback mail carries a scope. Patrol marks obsolete scoped mail
  superseded rather than starting an obsolete turn.
- No automatic duplicate Watcher/Reviewer launch after a response-loss outcome.
- Explicit Supervisor `upgrade`: preserves deep legacy task snapshots, assigns
  rounds and quarantines pending unscoped legacy mail without resuming work.
  Patrol refuses unmigrated state rather than delivering old control mail.
- Explicit opener `retire-watcher --lane ...`: archives an idle misplaced Watcher;
  a later patrol creates its replacement. Retry inspects actual archived state.
- Prompts require stopping writes after handback, retaining assigned round/candidate,
  and using desk rework instead of a second manual continuation channel.

Relevant owners: `setup/desk.py`, `tests/test_desk.py`, and role prompts in `agents/`.
Installers and `setup/codex-room*` remain separate ownership areas with issues below.

## Completed: narrow Jev false-stale repair

`src/observed-elements.js` now uses one self-contained, serialized page function
for shared role/label/guard derivation during observation and action. The opaque-ID
public API still does not accept model-supplied selectors or executable code.

Real-Chrome regressions cover unchanged unlabeled search, number and checkbox
controls, assert actual values/checked state and events, and use fresh observations.
Type-only and label-only mutations preserve unrelated values; role-only mutation
uses a labeled checkbox so fallback-label changes cannot mask the role guard.
Rejected actions preserve the checked/value state and event counts.

Independent review loaded both exact revisions with `git show` into memory:
the repair base falsely rejects all three unlabeled controls; the final candidate
operates them correctly and rejects real label/type/role changes without side effects.

The first repair copied role logic into both paths and was rejected in self-review.
It was replaced by shared helpers. A subsequent fixture accidentally labeled the
positive checkbox case; it was corrected before independent candidate review.

## Full review findings: unresolved

All paths/line numbers refer to the checkpoint or exact Jev candidate above.
These findings were reported, not silently fixed during the Human's review/commit request.

### Epistex rollout

1. **P1: runtime selection/resume.** `setup/codex-room:12-18` and
   `setup/codex-room-sync:121-127` select a runtime from `EPISTEX_PROJECT_ROOT` or
   launcher `$PWD`, not a durable session identity. Profiles do not establish a
   stable per-project binding. Disposable wrapper tests reproduce different homes
   for the same role launched from different directories. Actual old Supervisor
   resume fails although its rollout still exists. This is consistent with, but
   does not fully prove, the runtime-selection diagnosis. `SETUP.md` overstates
   that launcher cwd necessarily equals the Paseo workspace cwd.
2. **P1 for existing installations: namespace/variable migration.** Renaming
   `SEATWORKS_*` variables to `EPISTEX_*` and `.codex-runtime/seatworks/` to
   `.codex-runtime/epistex/` has no migration. A disposable old-variable fixture
   fails to find credentials despite the configured directory existing. This is
   separate from the observed same-namespace runtime mismatch.
3. **P2: ACP child exit can hang the proxy.** `setup/role-agent:60-81` blocks on
   caller stdin after the child exits. A fake backend exiting 7 left the proxy
   alive until caller stdin closed. Message-transformation tests do not cover this.
4. **P2: systemd path quoting.** `setup/install-patrol.py:28-30` interpolates paths
   without systemd-specific quoting. Kit/interpreter paths containing spaces break
   the generated directives. Source-verified, not executed against live systemd.

No remaining blocker was found in the recent desk fixes themselves. General
uncertain-launch and `accept_uncertain` reconciliation still lack supported recovery
commands. Desk state is trusted-user coordination, not protection against direct
Git writes or arbitrary commands outside the desk.

### Full Jev feature: not ready for acceptance

1. **P1: wrong native option selected.** `src/observed-elements.js:128-129` checks
   the observed index/value but mutates via `element.value`. With an earlier disabled
   option and a later enabled option sharing a value, the later option's ID selects
   the disabled earlier option and reports success. Reproduced in real Chrome.
2. **P1: inherited disabled state ignored.** Lines 104, 112 and 148 use
   `element.disabled`, which misses fieldset-inherited native disabled state.
   Disabling a fieldset after observation still permits fill and emits events,
   although the target matches `:disabled`. Reproduced in real Chrome.
3. **P1: context guarantee overstates implementation.** Lines 98-100 protect layout
   markers and only the first 1,000 characters of immediate-parent text. Changing
   an invoice heading outside that parent still allows an old-ID click on the new
   invoice. Reproduced; `references/api.md:277` needs an explicit bounded contract.
4. **P2: controller-local IDs collide.** Lines 12, 20 and 36-40 start each
   controller at `oe1`. Mixing a page A ID into page B's controller can act on B's
   different target. Reproduced; settle/enforce the intended ownership contract.
5. **P2: focus-handler invalidation.** Lines 119-125 validate before focus. A
   synchronous focus handler that disables the input does not prevent the subsequent
   write/events. Reproduced; post-focus semantics need a regression and fix.
6. **P2: Linux-only default E2E.** `test/observed-e2e.js:13` unconditionally reads
   `/proc` in a test discovered by `npm test`. Cross-platform failure is inferred
   from source; macOS/Windows were not run.
7. **P2: cleanup fault paths remain.** E2E lines 8-9 lack asynchronous spawn-error
   handling and have an unbounded post-SIGKILL wait. These unsafe fault paths were
   not rerun. `test/observed-e2e-cleanup.test.js:13-18` tests a separate imitation
   that emits its own exit event, not the actual cleanup implementation.
8. **Coverage gap:** E2E line 17 uses an option ID invalidated by later observations.
   Its rejection does not prove fresh-ID option binding; independent fresh-ID
   rejection passed, while duplicate-value selection above failed.
9. **Provenance unresolved:** the clean-room/no-copy assertion in
   `references/api.md:279` is a historical claim, not established by diff review.
   Do not claim license/provenance verification complete.

These are broader-feature findings, not regressions introduced by the false-stale repair.

## Verification performed

- Epistex: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests`:
  **40/40 pass**, rerun by the coordinating agent during full review. Installer tests
  use disposable configuration; no live installer was run in this repair/review.
- Python compile checks, example JSON parsing, `bash -n setup/codex-room`, and
  `git diff --check`: pass.
- In-memory mutation checks detect removal of workspace routing, round validation,
  candidate binding, current-reviewer checks, obsolete-mail suppression, uncertain
  launch guards and legacy-mail quarantine. Scratch harness errors were corrected;
  no source was changed to manufacture passing results.
- Desk Reviewer: 14/14 desk tests plus recovery reproductions passed. Full-rollout
  review ran 32 selected tests and additional disposable reproductions; it skipped
  eight installer/checker tests, separately run by the coordinating agent.
- Live disposable desk check used the actual `launch` implementation, adding only
  test-state environment and mode to the CLI invocation. Actual Watcher CWD matched
  the lane worktree; `raise` created both recipient messages in temporary state.
  No patrol sent those messages. Live ledger checksum was unchanged. Test agent
  `0fc332a5-600b-4a79-b343-99c8e94d9795` was archived and temporary state removed.
- Jev final candidate: `npm test`: **36/36 pass**, run by Peer, coordinator and
  Reviewer. Focused owned-Chrome tests and exact base/candidate comparisons also ran.
- Full-feature Reviewer independently reproduced the runtime Jev findings above.
  Browser checks used local fixtures and owned temporary profiles; observed child
  exit preceded profile removal. Follow-up checks confirmed owned PIDs/profiles absent.
- Green suites do not cover all reported failure cases and do not establish readiness.

## Live operational state: preserve until recovery is authorized

- Local Paseo daemon 0.9.1 was started with explicit Human permission at
  `/home/linh/.paseo`, listening on `127.0.0.1:6767`; it remains running.
- `epistex-patrol.timer` and service are **inactive**, but the timer is still
  **enabled** and may start at a future user-systemd session/boot. They were stopped
  locally for safe work, not permanently disabled. Do not blindly start the timer.
- Original live ledger is under
  `~/.local/share/epistex/desk/32b7413e63c432f4/ledger.json` and remains unchanged.
  L1 is open; T4 is `done`, `review_status=done`, has no round, and retains its old
  REWORK evidence. It is not accepted. Original wrong-CWD Watcher remains assigned.
- `upgrade` and `retire-watcher` are implemented/tested but **not executed on L1**.
  No live migration, manual JSON editing, replacement of L1 agents or lane closure occurred.
- Old Supervisor and an old test Reviewer reported “no rollout found” on resume.
  Original rollouts exist under `.codex-runtime/epistex/32b7413e63c4/`; newly observed
  app-servers used `.codex-runtime/epistex/aaac9a1ece47/` from daemon cwd Epistex.
  Do not delete/copy session data or claim it was lost based on the resume error.
- To avoid corrupting the stopped desk task, Jev repair used standalone Paseo role
  agents in the same worktree, not legacy T4 handbacks. One Peer wrote; it stopped
  before immutable-candidate review. No concurrent candidate changes occurred.

Useful Paseo agent records (all review/repair work completed):

- Desk/full-rollout Reviewer: `d425435f-89bb-49f5-97a9-3f455c1ad07b`.
- Jev writing Peer: `c0005c8f-3170-4f21-b779-4fd9863f7bac`.
- Jev independent Reviewer: `02dea185-b485-4c4a-a4cf-a0cef22a2cbb`.
- Old L1 Supervisor: `69652050-fe3b-4b8a-bd3c-49aa0ca61064`.
- Old L1 Lead: `f243db77-fefd-4875-99e0-be4bc8b37ae2`.
- Old L1 Peer: `aeffd221-25e0-409a-8b48-952d5bd86ed0`.
- Old misplaced Watcher: `5942514f-9fda-497c-ad2e-502b0e37c269`.

## Evidence behind the original workflow failure

Live ledger events on 2026-09-25 (UTC+07): Peer handback **22:09:30**, review start
**22:09:57**, delayed rework mail M21 sent **22:10:22**. A new Peer commit appeared
during that review. Obsolete-mail delivery is proven; a manual continuation plus
delayed mail explains the sequence plausibly but is not a fully established causal trace.
The desk refusal was task lifecycle/assignment-based, not a candidate-SHA comparison.

## Work not done and safe continuation

1. Resolve stable Codex runtime selection and migration without losing existing
   session data. Do not confuse launcher cwd, ledger root and per-thread worktree cwd.
2. With explicit operational authorization and working role sessions, inspect the
   old lane; use supported desk upgrade/retirement commands rather than editing JSON.
   Have the Lead issue a fresh bound rework/review assignment; do not relabel old
   evidence as review of the new candidate or directly resume a Peer twice.
3. Fix the full-feature P1 defects with asymmetric real-browser regressions, then
   address remaining action, test-harness, documentation and provenance findings.
4. Fix ACP exit handling and systemd quoting with focused disposable tests. Validate
   actual backend/runtime compatibility before claiming all 35 profiles work.
5. Re-run full suites, review an immutable candidate independently, and let the Lead
   make acceptance decisions. Human approval is still required for push/merge/deploy.

No new fixes for the full-review findings, live runtime recovery, broad feature
acceptance, all-backend certification, or cross-platform E2E verification were completed.
