import hashlib
import os
import pathlib
import subprocess
import tempfile
import tomllib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SYNC = ROOT / "setup" / "codex-room-sync"


class CodexRoomSyncTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.temporary.name) / "home"
        self.canonical = self.home / ".codex"
        self.project = pathlib.Path(self.temporary.name) / "project"
        self.canonical.mkdir(parents=True)
        self.project.mkdir()
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
        env.update(HOME=str(self.home), EPISTEX_CODEX_HOME=str(self.canonical))
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [str(SYNC), role, str(project or self.project), session_id],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def runtime(self, role: str) -> pathlib.Path:
        project_id = hashlib.sha256(str(self.project).encode()).hexdigest()[:12]
        return self.home / ".codex-runtime" / "epistex" / project_id / role

    def test_roles_are_isolated_and_native_agents_are_disabled(self) -> None:
        lead = self.sync("lead")
        peer = self.sync("peer")

        self.assertEqual(lead.returncode, 0, lead.stderr)
        self.assertEqual(peer.returncode, 0, peer.stderr)
        lead_config = (self.runtime("lead") / "config.toml").read_text(encoding="utf-8")
        peer_config = (self.runtime("peer") / "config.toml").read_text(encoding="utf-8")

        for config in (lead_config, peer_config):
            parsed = tomllib.loads(config)
            self.assertFalse(parsed["agents"]["enabled"])
            self.assertFalse(parsed["features"]["multi_agent"])
            self.assertFalse(parsed["features"]["multi_agent_v2"])
            self.assertEqual(parsed["mcp_servers"]["other"], {"command": "other"})
        self.assertIn("paseo", tomllib.loads(lead_config)["mcp_servers"])
        self.assertNotIn("paseo", tomllib.loads(peer_config)["mcp_servers"])
        self.assertTrue((self.runtime("lead") / "auth.json").is_symlink())
        self.assertEqual(tomllib.loads(lead_config)["model_instructions_file"], str(ROOT / "agents" / "LEAD.md"))
        self.assertEqual(tomllib.loads(peer_config)["model_instructions_file"], str(ROOT / "agents" / "PEER.md"))
        self.assertNotEqual(self.runtime("lead"), self.runtime("peer"))

        private_state = self.runtime("lead") / "session.jsonl"
        private_state.write_text("keep\n", encoding="utf-8")
        repeated = self.sync("lead")
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(private_state.read_text(encoding="utf-8"), "keep\n")

    def test_legacy_credentials_and_runtime_are_reused_repeatably(self) -> None:
        legacy = self.home / "legacy-codex"
        legacy.mkdir()
        (legacy / "config.toml").write_text('model = "legacy"\n')
        (legacy / "auth.json").write_text('{"legacy": true}\n')
        project_id = hashlib.sha256(str(self.project).encode()).hexdigest()[:12]
        runtime = self.home / ".codex-runtime" / "seatworks" / project_id / "lead"
        (runtime / "sessions").mkdir(parents=True)
        private = runtime / "sessions" / "keep.jsonl"
        private.write_text("keep\n")
        env = {"EPISTEX_CODEX_HOME": "", "SEATWORKS_CODEX_HOME": str(legacy)}

        first = self.sync("lead", extra_env=env)
        second = self.sync("lead", extra_env=env)

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first.stdout.strip(), str(runtime))
        self.assertEqual(second.stdout.strip(), str(runtime))
        self.assertEqual((runtime / "auth.json").resolve(), legacy / "auth.json")
        self.assertEqual(private.read_text(), "keep\n")

    def test_explicit_new_credential_setting_precedes_legacy(self) -> None:
        legacy = self.home / "legacy-codex"
        legacy.mkdir()
        (legacy / "config.toml").write_text('model = "legacy"\n')
        result = self.sync("lead", extra_env={"SEATWORKS_CODEX_HOME": str(legacy)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.runtime("lead") / "auth.json").resolve(), self.canonical / "auth.json")

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

    def test_conflicting_namespaces_require_explicit_session(self):
        current = self.runtime("lead")
        legacy = self.home / ".codex-runtime" / "seatworks" / current.parent.name / "lead"
        for runtime in (current, legacy):
            runtime.mkdir(parents=True)
        result = self.sync("lead")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ambiguous", result.stderr)
        self.assertEqual(list(current.iterdir()), [])
        self.assertEqual(list(legacy.iterdir()), [])

    def test_resume_requires_unique_exact_role_session_and_preserves_data(self):
        session_id = "12345678-1234-1234-1234-123456789abc"
        filename = f"rollout-2026-09-26T10-00-00-{session_id}.jsonl"
        legacy = self.home / ".codex-runtime" / "seatworks" / "old-project" / "lead"
        sessions = legacy / "sessions" / "2026" / "09"
        sessions.mkdir(parents=True)
        # A backup filename and another role must not count as a session match.
        (sessions / (filename + ".bak")).write_text("backup")
        result = self.sync("lead", session_id)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not found", result.stderr)
        (sessions / filename).write_text("session data")
        for _ in range(2):
            result = self.sync("lead", session_id)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), str(legacy))
            self.assertEqual((sessions / filename).read_text(), "session data")
        wrong_role = self.sync("peer", session_id)
        self.assertIn("not found", wrong_role.stderr)
        duplicate = self.runtime("lead") / "sessions"
        duplicate.mkdir(parents=True)
        (duplicate / filename).write_text("duplicate")
        result = self.sync("lead", session_id)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ambiguous", result.stderr)
        self.assertFalse((self.runtime("lead") / "config.toml").exists())

    def test_other_roles_have_distinct_instructions_and_read_only_roles_omit_paseo_mcp(self) -> None:
        for role in ("supervisor", "peer"):
            with self.subTest(role=role):
                result = self.sync(role)
                self.assertEqual(result.returncode, 0, result.stderr)
                config = tomllib.loads((self.runtime(role) / "config.toml").read_text())
                self.assertEqual(config["model_instructions_file"], str(ROOT / "agents" / f"{role.upper()}.md"))
                self.assertEqual("paseo" in config["mcp_servers"], role == "supervisor")

    def test_refuses_symlinked_role_runtime(self) -> None:
        runtime = self.runtime("peer")
        redirected = pathlib.Path(self.temporary.name) / "redirected"
        redirected.mkdir()
        runtime.parent.mkdir(parents=True)
        runtime.symlink_to(redirected, target_is_directory=True)

        result = self.sync("peer")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing symlinked role runtime", result.stderr)
        self.assertFalse((redirected / "config.toml").exists())

    def test_refuses_symlinked_runtime_ancestor(self) -> None:
        redirected = pathlib.Path(self.temporary.name) / "redirected"
        redirected.mkdir()
        (self.home / ".codex-runtime").symlink_to(redirected, target_is_directory=True)
        result = self.sync("lead")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlinked runtime ancestor", result.stderr)
        self.assertEqual(list(redirected.iterdir()), [])

    def test_invalid_policy_table_fails_without_replacing_config(self) -> None:
        self.assertEqual(self.sync("peer").returncode, 0)
        config = self.runtime("peer") / "config.toml"
        previous = config.read_bytes()
        (self.canonical / "config.toml").write_text(
            'features = "not a table"\n', encoding="utf-8")
        result = self.sync("peer")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid canonical TOML", result.stderr)
        self.assertEqual(config.read_bytes(), previous)

    def test_indented_prompt_setting_is_replaced(self) -> None:
        config = self.canonical / "config.toml"
        config.write_text('  model_instructions_file = "old.md"\n' + config.read_text(), encoding="utf-8")
        result = self.sync("lead")
        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = tomllib.loads((self.runtime("lead") / "config.toml").read_text())
        self.assertEqual(parsed["model_instructions_file"], str(ROOT / "agents" / "LEAD.md"))

    def test_inline_and_quoted_policy_tables_are_supported(self) -> None:
        (self.canonical / "config.toml").write_text(
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

    def test_multiline_strings_and_unrelated_values_survive(self) -> None:
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
        canonical = self.canonical / "config.toml"
        canonical.write_text(original, encoding="utf-8")
        expected = tomllib.loads(original)
        expected["features"].update(multi_agent=False, multi_agent_v2=False)
        expected["agents"] = {"enabled": False}
        expected["model_instructions_file"] = str(ROOT / "agents" / "PEER.md")
        del expected["mcp_servers"]["paseo"]
        result = self.sync("peer")
        self.assertEqual(result.returncode, 0, result.stderr)
        actual = tomllib.loads((self.runtime("peer") / "config.toml").read_text())
        self.assertEqual(actual, expected)
        self.assertEqual(actual["numbers"][2].hex(), (-0.0).hex())
        self.assertEqual(canonical.read_text(), original)

    def test_nan_round_trip(self) -> None:
        (self.canonical / "config.toml").write_text('values = [nan, +nan, -nan]\n')
        result = self.sync("lead")
        self.assertEqual(result.returncode, 0, result.stderr)
        values = tomllib.loads((self.runtime("lead") / "config.toml").read_text())["values"]
        self.assertEqual(len(values), 3)
        self.assertTrue(all(value != value for value in values))

    def test_late_link_conflict_leaves_config_and_earlier_links_unchanged(self) -> None:
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

    def test_restart_preserves_private_plugins_when_canonical_plugins_are_absent(self) -> None:
        (self.canonical / "plugins").rmdir()
        self.assertEqual(self.sync("supervisor").returncode, 0)
        plugins = self.runtime("supervisor") / "plugins"
        plugins.mkdir()
        (plugins / "private-state").write_text("keep")
        result = self.sync("supervisor")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(plugins.is_symlink())
        self.assertEqual((plugins / "private-state").read_text(), "keep")

        (self.canonical / "plugins").mkdir()
        result = self.sync("supervisor")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to replace non-symlink", result.stderr)
        self.assertEqual((plugins / "private-state").read_text(), "keep")

    def test_invalid_toml_does_not_create_runtime(self) -> None:
        (self.canonical / "config.toml").write_text('broken = [\n')
        result = self.sync("peer")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid canonical TOML", result.stderr)
        self.assertFalse(self.runtime("peer").exists())

    def test_config_directory_conflict_does_not_create_links(self) -> None:
        runtime = self.runtime("lead")
        (runtime / "config.toml").mkdir(parents=True)
        result = self.sync("lead")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing non-regular runtime config", result.stderr)
        self.assertEqual([path.name for path in runtime.iterdir()], ["config.toml"])


if __name__ == "__main__":
    unittest.main()
