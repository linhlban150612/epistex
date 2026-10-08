# Epistex repository contract

## Product and contract boundaries

- `agents/` owns role prompts; `setup/` owns launchers and runtime sync.
- Paseo owns agent lifecycle and topology. Codex runtime must disable native multi-agent features.
- Keep canonical Codex configuration unchanged. Preserve private runtime sessions and state;
  reject ambiguous runtime selection and symlink runtime paths rather than guessing.
- Role tool visibility is not an OS sandbox: all roles run as the same Unix user.

## Canonical documentation

- `README.md`: product boundaries, supported workflows and known limitations; inspect live state
  before relying on history.
- `SETUP.md`: role-seat installation entry point and live verification.
- `docs/setup/claude.md`, `docs/setup/amp.md`, `docs/setup/pi-omp.md`,
  `docs/setup/devin-copilot-cursor.md`: backend-specific role-seat setup.
- `docs/setup/codex-runtime.md`: Codex runtime/resume, environment compatibility,
  project prerequisites, and key files.

## Authority and repository hygiene

- Preserve unrelated local changes. Keep runtime state, credentials, logs and review
  evidence outside tracked product files. Keep `WORKSPACE_PROTOCOL.md` local and ignored.
- Ask Human before pushing, deploying, publishing, deleting retained state, or changing shared
  infrastructure. Do not create patrol, timers, schedules or heartbeats.
- Do not add project-specific policy to global Paseo providers or role prompts.

## Verification

- Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests` for implementation changes.
- Run `bash -n setup/codex-room`, `bash -n setup/setup-seats.sh` and `git diff --check`.
- Do not run the installed-provider check against live config in isolated tests; report it pending
  when the configured Supervisor provider is not installed.
- For launch/auth/model/tool-policy changes, verify actual Paseo launches for the affected roles;
  static checks and fixture tests alone are insufficient.
