# Epistex repository contract

## Product and contract boundaries

- `agents/` owns role prompts; `setup/` owns launchers and runtime sync.
- Paseo owns agent lifecycle and topology. Codex runtime must disable native multi-agent features.
- Keep canonical Codex configuration unchanged. Preserve private runtime sessions and state;
  reject ambiguous runtime selection and symlink runtime paths rather than guessing.
- Role tool visibility is not an OS sandbox: all roles run as the same Unix user.

## Canonical documentation

- `README.md`: product boundaries, supported workflows, key files and known limitations; inspect
  live state before relying on history.
- `SETUP.md`: role-seat installation entry point and live verification.
- `docs/setup/claude.md`, `docs/setup/amp.md`, `docs/setup/pi-omp.md`, `docs/setup/devin.md`,
  `docs/setup/copilot.md`, `docs/setup/cursor.md`, `docs/setup/antigravity.md`,
  `docs/setup/droid.md`, `docs/setup/kiro.md`: backend-specific role-seat setup.
- `docs/setup/context-compaction.md`: per-backend compaction thresholds and limits.
- `docs/setup/codex-runtime.md`: Codex runtime/resume, environment compatibility, Peer sandbox
  and Supervisor pin.
- `docs/setup/delivery-plugin.md`: the required Paseo delivery plugin (pin, install path, live
  evidence, decisions); `SETUP.md` and `README.md` only link to it.

## Authority and repository hygiene

- Preserve unrelated local changes. Keep runtime state, credentials, logs and review
  evidence outside tracked product files. Keep `WORKSPACE_PROTOCOL.md` local and ignored.
- Ask Human before pushing, deploying, publishing, deleting retained state, or changing shared
  infrastructure. Do not create patrol, timers, schedules or heartbeats.
- Do not add project-specific policy to global Paseo providers or role prompts.

## Verification

- Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests` for implementation changes.
- Run `python3 -c 'compile(open("setup/codex-room").read(), "setup/codex-room", "exec")'`, `bash -n setup/setup-seats.sh` and `git diff --check`.
- Run `setup/lint-comments`. Code has no comments: a known weakness goes to an issue.
  `setup/comment-baseline.json` is a ratchet; a limit only goes down.
- `setup/verify` runs these five checks in one command; its last line is `VERIFY OK` only when all pass.
- Do not run the installed-provider check against live config in isolated tests; report it pending
  when the configured Supervisor provider is not installed.
- For launch/auth/model/tool-policy changes, verify actual Paseo launches for the affected roles;
  static checks and fixture tests alone are insufficient.

## Measures (Goodhart rule)

- A number that the kit can raise by itself is not a measure of the kit. Test results, `VERIFY OK`,
  gate verdicts, valid receipts and the comment count are guards: they show that a known defect
  did not return. They do not show that the kit works.
- A test or a gate expects a fact (exit status, file, Git object, sent message) or a status that
  an agent declared. It does not expect words in a prompt or a handoff.
- Do not change a prompt, gate, parser, fixture or expected value to make a check pass. Change it
  when a real task shows a defect; then the check is a regression probe.
- Do not label a fixture with the parser under test. Do not score old records again with the
  current parser.
- Tools print rows and counts. They do not print a score for a seat, a provider or a model.
- The measures that decide are live Paseo launches and the real-task records that a person
  writes (`eval/README.md`).
