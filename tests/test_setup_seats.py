import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "setup" / "setup-seats.sh"
CATALOG = set("""archive_agent archive_workspace browser_back browser_click browser_close_tab browser_drag browser_evaluate browser_fill browser_forward browser_hover browser_keypress browser_list_tabs browser_logs browser_navigate browser_new_tab browser_reload browser_resize browser_screenshot browser_scroll browser_select browser_snapshot browser_type browser_upload browser_wait cancel_agent capture_terminal create_agent create_heartbeat create_schedule create_terminal create_workspace delete_heartbeat delete_schedule get_agent_activity get_agent_status inspect_provider inspect_schedule kill_agent kill_terminal list_agents list_models list_pending_permissions list_profiles list_providers list_schedules list_terminals list_workspace_scripts list_workspaces pause_schedule rename_workspace respond_to_permission resume_schedule run_schedule_once schedule_logs send_agent_prompt send_terminal_keys set_agent_mode start_workspace_script stop_workspace_script update_agent update_schedule""".split())
KEEP = set("""list_agents list_workspaces list_providers list_models create_agent send_agent_prompt get_agent_activity get_agent_status cancel_agent archive_agent list_pending_permissions respond_to_permission set_agent_mode""".split())
DENY = CATALOG - KEEP


class SetupSeatsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.config = pathlib.Path(self.temporary.name) / "config.json"
        self.bin = pathlib.Path(self.temporary.name) / "bin"
        self.bin.mkdir()
        for name in ("bash", "jq", "dirname", "wc", "chmod"):
            target = shutil.which(name)
            if target is None:
                raise RuntimeError(f"test prerequisite missing: {name}")
            (self.bin / name).symlink_to(target)
        (self.bin / "python3").symlink_to(sys.executable)
        self.codex = self.bin / "fake-codex"
        self.codex.write_text("#!/usr/bin/env bash\nexit 99\n")
        self.codex.chmod(0o755)
        self.env = {"PATH": str(self.bin), "HOME": self.temporary.name,
                    "CODEX_BIN": str(self.codex), "PASEO_CONFIG": str(self.config)}
        providers = json.loads((ROOT / "examples" / "paseo-providers.json").read_text())
        providers.pop("_doc")
        for role in ("lead", "peer"):
            providers[f"codex-{role}"]["command"] = [str(ROOT / "setup" / "codex-room"), role]
        providers["devin-supervisor"]["command"] = [str(ROOT / "setup" / "role-agent"), "supervisor", "devin"]
        self.data = {"daemon": {"mcp": {"injectIntoAgents": True}}, "agents": {"providers": providers}}

    def tearDown(self):
        self.temporary.cleanup()

    def run_check(self, *args):
        return subprocess.run([str(self.bin / "bash"), str(SCRIPT), *args], text=True,
                              capture_output=True, env=self.env)

    def save(self):
        self.config.write_text(json.dumps(self.data))

    def test_check_accepts_installed_policy_without_changing_files(self):
        self.save()
        before = self.config.read_bytes()
        result = self.run_check("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertIn("auth, daemon and launch not checked", result.stdout)

    def test_catalog_partition_and_example_policy(self):
        self.assertEqual((len(CATALOG), len(KEEP), len(DENY)), (61, 13, 48))
        self.assertFalse(KEEP & DENY)
        self.assertEqual(KEEP | DENY, CATALOG)
        example = json.loads((ROOT / "examples" / "paseo-providers.json").read_text())
        enabled = [p for p in example.values() if isinstance(p, dict) and p.get("paseoTools", {}).get("enabled") is True]
        self.assertTrue(enabled)
        self.assertTrue(all(set(p["paseoTools"]["disabledTools"]) == DENY for p in enabled))
        script = SCRIPT.read_text()
        match = re.search(r"expected_deny='(\[.*?\])'", script)
        self.assertIsNotNone(match, "checker deny-list constant not found")
        self.assertEqual(set(json.loads(match.group(1))), DENY)

    def test_enabled_provider_requires_exact_denylist(self):
        self.save()
        result = self.run_check("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        for edit, name in (
            ("remove", "missing member"),
            ("add", "keep member"),
        ):
            with self.subTest(name=name):
                tools = self.data["agents"]["providers"]["codex-lead"]["paseoTools"]["disabledTools"]
                if edit == "remove":
                    tools.remove("create_heartbeat")
                else:
                    tools.append("list_agents")
                self.save()
                result = self.run_check("--check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("codex-lead", result.stderr)
                # Restore from the canonical fixture before the next case.
                self.data["agents"]["providers"]["codex-lead"]["paseoTools"]["disabledTools"] = sorted(DENY)
        del self.data["agents"]["providers"]["codex-lead"]["paseoTools"]["disabledTools"]
        self.save()
        result = self.run_check("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("codex-lead", result.stderr)

    def test_default_codex_on_isolated_path(self):
        self.save()
        del self.env["CODEX_BIN"]
        (self.bin / "codex").symlink_to(self.codex)
        self.assertEqual(self.run_check("--check").returncode, 0)

    def test_missing_or_nonexecutable_codex_override_fails(self):
        self.save()
        self.env["CODEX_BIN"] = str(self.bin / "missing")
        self.assertNotEqual(self.run_check("--check").returncode, 0)
        self.env["CODEX_BIN"] = str(self.codex)
        self.codex.chmod(0o644)
        self.assertNotEqual(self.run_check("--check").returncode, 0)

    def test_missing_config_fails(self):
        self.assertNotEqual(self.run_check("--check").returncode, 0)
        self.assertFalse(self.config.exists())

    def test_wrong_model_or_tools_fails(self):
        peer = self.data["agents"]["providers"]["codex-peer"]
        for key, value in (("models", []), ("paseoTools", {"enabled": True})):
            with self.subTest(key=key):
                old = peer[key]
                peer[key] = value
                self.save()
                self.assertNotEqual(self.run_check("--check").returncode, 0)
                peer[key] = old

    def test_models_match_requested_roles_and_reject_wrong_role_model(self):
        for role, expected, wrong_role in (("lead", "gpt-6.1-sol", "gpt-6-luna"),
                                           ("peer", "gpt-6-luna", "gpt-6.1-sol")):
            with self.subTest(role=role):
                model = self.data["agents"]["providers"][f"codex-{role}"]["models"][0]
                self.assertEqual(model["id"], expected)
                model["id"] = wrong_role
                self.save()
                result = self.run_check("--check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"codex-{role}:", result.stderr)
                model["id"] = expected

    def test_disabled_injection_fails(self):
        self.data["daemon"]["mcp"]["enabled"] = False
        self.save()
        self.assertNotEqual(self.run_check("--check").returncode, 0)

    def test_missing_or_wrong_supervisor_seat_fails(self):
        supervisor = self.data["agents"]["providers"].pop("devin-supervisor")
        self.save()
        result = self.run_check("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("devin-supervisor", result.stderr)
        self.data["agents"]["providers"]["devin-supervisor"] = supervisor
        supervisor["paseoTools"]["enabled"] = False
        self.save()
        self.assertNotEqual(self.run_check("--check").returncode, 0)

    def test_unknown_argument_fails(self):
        self.assertEqual(self.run_check("--unknown").returncode, 2)
