import hashlib
import os
import pathlib
import subprocess
import sys
import tempfile
import tomllib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ROOM = ROOT / "setup" / "codex-room"
# Prints CODEX_HOME so tests observe the selected runtime.
PRINT_HOME = "import os; print(os.environ['CODEX_HOME'])"


class CodexRoomRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.temporary.name) / "home"
        self.canonical = self.home / ".codex"
        self.project = pathlib.Path(self.temporary.name) / "project"
        self.canonical.mkdir(parents=True)
        self.project.mkdir()
        self.codex = pathlib.Path(self.temporary.name) / "fake-codex"
        self.codex.write_text(f"#!{sys.executable}\n{PRINT_HOME}\n")
        self.codex.chmod(0o755)
        (self.canonical / "config.toml").write_text(
            """model = "test-model"

[features]
multi_agent = true

[agents]
enabled = true

[mcp_servers.paseo]
command = "paseo"

[mcp_servers.other]
command = "other"
""",
            encoding="utf-8",
        )
        (self.canonical / "auth.json").write_text("{}\n", encoding="utf-8")
        (self.canonical / "skills").mkdir()
        (self.canonical / "plugins").mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def sync(self, role: str, session_id: str = "", extra_env=None, project=None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(HOME=str(self.home), EPISTEX_CODEX_HOME=str(self.canonical),
                   EPISTEX_PROJECT_ROOT=str(project or self.project), CODEX_BIN=str(self.codex))
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [str(ROOM), role, *(["resume", session_id] if session_id else [])],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def runtime(self, role: str) -> pathlib.Path:
        project_id = hashlib.sha256(str(self.project).encode()).hexdigest()[:12]
        return self.home / ".codex-runtime" / "epistex" / project_id / role

    def test_generated_config_isolates_roles_and_disables_native_agents(self) -> None:
        canonical = self.canonical / "config.toml"
        canonical.write_text('model_auto_compact_token_limit = 250000\n'
                             '  model_instructions_file = "old.md"\n' + canonical.read_text())
        before = canonical.read_bytes()
        for role in ("lead", "peer", "supervisor"):
            with self.subTest(role=role):
                result = self.sync(role)
                self.assertEqual(result.returncode, 0, result.stderr)
                runtime = self.runtime(role)
                self.assertEqual(result.stdout.strip(), str(runtime))
                parsed = tomllib.loads((runtime / "config.toml").read_text(encoding="utf-8"))
                self.assertFalse(parsed["agents"]["enabled"])
                self.assertFalse(parsed["features"]["multi_agent"])
                self.assertFalse(parsed["features"]["multi_agent_v2"])
                self.assertEqual(parsed["model_auto_compact_token_limit"], 100000)
                self.assertEqual(parsed["mcp_servers"]["other"], {"command": "other"})
                self.assertEqual("paseo" in parsed["mcp_servers"], role != "peer")
                self.assertTrue((runtime / "auth.json").is_symlink())
                prompt = pathlib.Path(parsed["model_instructions_file"])
                self.assertEqual(prompt, runtime / "role-instructions.md")
                expected = ((ROOT / "agents/contract/COMMON.md").read_text().rstrip() + "\n\n"
                            + (ROOT / "agents" / f"{role.upper()}.md").read_text())
                self.assertEqual(prompt.read_text(), expected)
                self.assertEqual(canonical.read_bytes(), before)
        self.assertEqual(len({self.runtime(role) for role in ("lead", "peer", "supervisor")}), 3)

    def test_toml_round_trip_keeps_unrelated_values(self) -> None:
        canonical = self.canonical / "config.toml"
        with self.subTest("multi-line strings and value types"):
            original = '''description = """
[mcp_servers.paseo]
model_instructions_file = "example"
"""
unicode = "Tiếng Việt 😀"
control = "\\u007f\\u0000"
day = 2026-09-13
clock = 12:34:56.123
local = 2026-09-13T12:34:56
offset = 2026-09-13T12:34:56+07:00
numbers = [1, 1.5, -0.0, inf, -inf]
nested = [{ "a.b" = [true, false], empty = {} }]
[features]
multi_agent = true
notes = \'\'\'
multi_agent = true
[agents]
enabled = true
[mcp_servers.paseo]
command = "example only"
\'\'\'
[mcp_servers.paseo]
command = "paseo"
[mcp_servers.other]
command = "other"
'''
            canonical.write_text(original, encoding="utf-8")
            expected = tomllib.loads(original)
            expected["features"].update(multi_agent=False, multi_agent_v2=False)
            expected["agents"] = {"enabled": False}
            expected["model_instructions_file"] = str(self.runtime("peer") / "role-instructions.md")
            expected["model_auto_compact_token_limit"] = 100000
            del expected["mcp_servers"]["paseo"]
            result = self.sync("peer")
            self.assertEqual(result.returncode, 0, result.stderr)
            actual = tomllib.loads((self.runtime("peer") / "config.toml").read_text())
            self.assertEqual(actual, expected)
            self.assertEqual(actual["numbers"][2].hex(), (-0.0).hex())
            self.assertEqual(canonical.read_text(), original)
        with self.subTest("inline and quoted policy tables"):
            canonical.write_text(
                '"features" = { "multi_agent" = true, keep = "yes" }\n'
                'agents.enabled = true\n'
                'mcp_servers = { paseo = { command = "paseo" }, other = { command = "other" } }',
                encoding="utf-8")
            result = self.sync("peer")
            self.assertEqual(result.returncode, 0, result.stderr)
            config = tomllib.loads((self.runtime("peer") / "config.toml").read_text())
            self.assertEqual(config["features"], {"multi_agent": False, "multi_agent_v2": False, "keep": "yes"})
            self.assertEqual(config["agents"], {"enabled": False})
            self.assertEqual(config["mcp_servers"], {"other": {"command": "other"}})
        with self.subTest("nan"):
            canonical.write_text('values = [nan, +nan, -nan]\n')
            result = self.sync("peer")
            self.assertEqual(result.returncode, 0, result.stderr)
            values = tomllib.loads((self.runtime("peer") / "config.toml").read_text())["values"]
            self.assertEqual(len(values), 3)
            self.assertTrue(all(value != value for value in values))

    def test_invalid_canonical_config_fails_without_replacing_config(self) -> None:
        self.assertEqual(self.sync("peer").returncode, 0)
        config = self.runtime("peer") / "config.toml"
        previous = config.read_bytes()
        for text in ('broken = [\n', 'features = "not a table"\n'):
            with self.subTest(canonical=text):
                (self.canonical / "config.toml").write_text(text, encoding="utf-8")
                result = self.sync("peer")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("invalid canonical TOML", result.stderr)
                self.assertEqual(config.read_bytes(), previous)

    def test_seatworks_fallbacks_reuse_runtime_and_epistex_settings_take_precedence(self) -> None:
        legacy = self.home / "legacy-codex"
        legacy.mkdir()
        (legacy / "config.toml").write_text('model = "legacy"\n')
        (legacy / "auth.json").write_text('{"legacy": true}\n')
        project_id = hashlib.sha256(str(self.project).encode()).hexdigest()[:12]
        runtime = self.home / ".codex-runtime" / "seatworks" / project_id / "lead"
        (runtime / "sessions").mkdir(parents=True)
        private = runtime / "sessions" / "keep.jsonl"
        private.write_text("keep\n")
        for name, env, auth in (
                ("SEATWORKS_CODEX_HOME fallback", {"EPISTEX_CODEX_HOME": ""}, legacy),
                ("repeat", {"EPISTEX_CODEX_HOME": ""}, legacy),
                ("EPISTEX_CODEX_HOME precedence", {}, self.canonical)):
            with self.subTest(name):
                result = self.sync("lead", extra_env={"SEATWORKS_CODEX_HOME": str(legacy), **env})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), str(runtime))
                self.assertEqual((runtime / "auth.json").resolve(), auth / "auth.json")
                self.assertEqual(private.read_text(), "keep\n")

    def test_git_root_subdirectory_and_linked_worktree_reuse_legacy_runtime(self):
        subprocess.run(["git", "init", str(self.project)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.project), "-c", "user.name=Test",
                        "-c", "user.email=test@example.com", "commit", "--allow-empty", "-m", "fixture"],
                       check=True, capture_output=True)
        worktree = self.project.parent / "linked"
        subprocess.run(["git", "-C", str(self.project), "worktree", "add", "--detach", str(worktree)],
                       check=True, capture_output=True)
        subdirectory = self.project / "nested"
        subdirectory.mkdir()
        legacy = self.home / ".codex-runtime" / "seatworks" / self.runtime("lead").parent.name / "lead"
        legacy.mkdir(parents=True)
        (legacy / "private-state").write_text("preserved")
        for project in (subdirectory, worktree, self.project, subdirectory):
            result = self.sync("lead", project=project)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), str(legacy))
        self.assertFalse(self.runtime("lead").exists())
        self.assertEqual((legacy / "private-state").read_text(), "preserved")

    def test_ambiguous_runtime_selection_is_rejected_and_resume_needs_unique_role_session(self):
        current = self.runtime("lead")
        with self.subTest("epistex and seatworks runtimes both exist"):
            legacy = self.home / ".codex-runtime" / "seatworks" / current.parent.name / "lead"
            for runtime in (current, legacy):
                runtime.mkdir(parents=True)
            result = self.sync("lead")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ambiguous", result.stderr)
            self.assertEqual(list(current.iterdir()), [])
            self.assertEqual(list(legacy.iterdir()), [])

        session_id = "12345678-1234-1234-1234-123456789abc"
        filename = f"rollout-2026-09-26T10-00-00-{session_id}.jsonl"
        legacy = self.home / ".codex-runtime" / "seatworks" / "old-project" / "lead"
        sessions = legacy / "sessions" / "2026" / "09"
        sessions.mkdir(parents=True)
        with self.subTest("backup filename is not a session"):
            (sessions / (filename + ".bak")).write_text("backup")
            result = self.sync("lead", session_id)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not found", result.stderr)
        (sessions / filename).write_text("session data")
        with self.subTest("unique session resumes repeatably"):
            for _ in range(2):
                result = self.sync("lead", session_id)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), str(legacy))
                self.assertEqual((sessions / filename).read_text(), "session data")
        with self.subTest("another role's session"):
            self.assertIn("not found", self.sync("peer", session_id).stderr)
        with self.subTest("duplicate session"):
            (current / "sessions").mkdir()
            (current / "sessions" / filename).write_text("duplicate")
            result = self.sync("lead", session_id)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ambiguous", result.stderr)
            self.assertFalse((current / "config.toml").exists())

    def test_refuses_symlinked_runtime_or_ancestor(self) -> None:
        redirected = pathlib.Path(self.temporary.name) / "redirected"
        redirected.mkdir()
        runtime_base = self.home / ".codex-runtime"
        with self.subTest("ancestor"):
            runtime_base.symlink_to(redirected, target_is_directory=True)
            result = self.sync("lead")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("symlinked runtime ancestor", result.stderr)
            self.assertEqual(list(redirected.iterdir()), [])
            runtime_base.unlink()
        with self.subTest("role runtime"):
            runtime = self.runtime("peer")
            runtime.parent.mkdir(parents=True)
            runtime.symlink_to(redirected, target_is_directory=True)
            result = self.sync("peer")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("refusing symlinked role runtime", result.stderr)
            self.assertFalse((redirected / "config.toml").exists())

    def test_runtime_entry_conflicts_fail_before_changing_runtime(self) -> None:
        with self.subTest("non-symlink shared directory"):
            runtime = self.runtime("peer")
            runtime.mkdir(parents=True)
            config = runtime / "config.toml"
            config.write_text('old = true\n')
            auth = runtime / "auth.json"
            auth.symlink_to(self.home / "old-auth")
            conflict = runtime / "plugins"
            conflict.mkdir()
            (conflict / "keep").write_text("private")
            before_entries = sorted(path.name for path in runtime.iterdir())
            result = self.sync("peer")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("refusing to replace non-symlink", result.stderr)
            self.assertEqual(config.read_text(), 'old = true\n')
            self.assertEqual(auth.readlink(), self.home / "old-auth")
            self.assertEqual((conflict / "keep").read_text(), "private")
            self.assertEqual(sorted(path.name for path in runtime.iterdir()), before_entries)
        with self.subTest("symlinked role-instructions.md"):
            runtime = self.runtime("lead")
            runtime.mkdir(parents=True)
            target = self.project / "retained.md"
            target.write_text("retain me")
            (runtime / "role-instructions.md").symlink_to(target)
            result = self.sync("lead")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("refusing non-regular runtime role-instructions.md", result.stderr)
            self.assertEqual(target.read_text(), "retain me")
            self.assertEqual([path.name for path in runtime.iterdir()], ["role-instructions.md"])

    def test_repeated_sync_preserves_private_sessions_and_state(self) -> None:
        (self.canonical / "plugins").rmdir()
        self.assertEqual(self.sync("lead").returncode, 0)
        runtime = self.runtime("lead")
        (runtime / "session.jsonl").write_text("keep\n", encoding="utf-8")
        plugins = runtime / "plugins"
        plugins.mkdir()
        (plugins / "private-state").write_text("keep")
        result = self.sync("lead")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((runtime / "session.jsonl").read_text(encoding="utf-8"), "keep\n")
        self.assertFalse(plugins.is_symlink())
        self.assertEqual((plugins / "private-state").read_text(), "keep")

if __name__ == "__main__":
    unittest.main()
