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

    def sync(self, role: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(HOME=str(self.home), SEATWORKS_CODEX_HOME=str(self.canonical))
        return subprocess.run(
            [str(SYNC), role, str(self.project)],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def runtime(self, role: str) -> pathlib.Path:
        project_id = hashlib.sha256(str(self.project).encode()).hexdigest()[:12]
        return self.home / ".codex-runtime" / "seatworks" / project_id / role

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
