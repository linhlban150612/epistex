import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "setup" / "setup-seats.sh"
CATALOG = set("""archive_agent archive_workspace browser_back browser_click browser_close_tab browser_drag browser_evaluate browser_fill browser_forward browser_hover browser_keypress browser_list_tabs browser_logs browser_navigate browser_new_tab browser_reload browser_resize browser_screenshot browser_scroll browser_select browser_snapshot browser_type browser_upload browser_wait cancel_agent capture_terminal create_agent create_heartbeat create_schedule create_terminal create_workspace delete_heartbeat delete_schedule get_agent_activity get_agent_status inspect_provider inspect_schedule kill_agent kill_terminal list_agents list_models list_pending_permissions list_profiles list_providers list_schedules list_terminals list_workspace_scripts list_workspaces pause_schedule rename_workspace respond_to_permission resume_schedule run_schedule_once schedule_logs send_agent_prompt send_terminal_keys set_agent_mode start_workspace_script stop_workspace_script update_agent update_schedule""".split())
KEEP_LEAD = set("""list_agents list_workspaces list_providers list_models list_profiles create_agent send_agent_prompt get_agent_activity get_agent_status cancel_agent archive_agent list_pending_permissions respond_to_permission set_agent_mode""".split())
KEEP_SUPERVISOR = KEEP_LEAD | {"create_workspace"}
DENY_LEAD = CATALOG - KEEP_LEAD
DENY_SUPERVISOR = CATALOG - KEEP_SUPERVISOR


class SetupSeatsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.config = pathlib.Path(self.temporary.name) / "config.json"
        self.bin = pathlib.Path(self.temporary.name) / "bin"
        self.bin.mkdir()
        self.kit = pathlib.Path(self.temporary.name) / "kit"
        for directory in ("setup", "agents", ".pi", ".omp"):
            shutil.copytree(ROOT / directory, self.kit / directory)
        self.script = self.kit / "setup" / "setup-seats.sh"
        for name in ("bash", "jq", "dirname", "wc", "chmod", "grep"):
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
        example = json.loads((ROOT / "examples" / "paseo-providers.json").read_text())
        providers = example["agents"]["providers"]
        for role in ("lead", "peer"):
            providers[f"codex-{role}"]["command"] = [str(self.kit / "setup" / "codex-room"), role]
        providers["devin-supervisor"]["command"] = [str(self.kit / "setup" / "role-agent"), "supervisor", "devin"]
        providers["amp-supervisor"]["command"] = [str(self.kit / "setup" / "role-agent"), "supervisor", "amp"]
        providers["agy-peer"]["command"] = [str(self.kit / "setup" / "role-agent"), "peer", "agy"]
        providers["claude-supervisor"]["command"] = [str(self.kit / "setup" / "role-agent"), "supervisor", "claude"]
        providers["codex-supervisor"]["command"] = [str(self.kit / "setup" / "codex-room"), "supervisor"]
        profiles = example["daemon"]["agentProfiles"]
        self.data = {"daemon": {"mcp": {"enabled": True, "injectIntoAgents": True}, "agentProfiles": profiles}, "agents": {"providers": providers}}

    def tearDown(self):
        self.temporary.cleanup()

    def run_check(self, *args):
        return subprocess.run([str(self.bin / "bash"), str(self.script), *args], text=True,
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

    def test_claude_compaction_env_checks_each_enabled_seat_and_peer(self):
        providers = self.data["agents"]["providers"]
        providers["claude-lead"] = {
            "enabled": True, "env": {"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "100000"}}
        self.save()
        self.assertEqual(self.run_check("--check").returncode, 0)
        for seat in ("claude-peer", "claude-lead", "claude-supervisor"):
            with self.subTest(seat=seat):
                providers[seat]["env"]["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] = "200000"
                self.save()
                result = self.run_check("--check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(seat + ": need env CLAUDE_CODE_AUTO_COMPACT_WINDOW=100000", result.stderr)
                providers[seat]["env"]["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] = "100000"
        providers["claude-lead"]["enabled"] = False
        providers["claude-lead"]["env"] = {}
        providers["claude-peer"]["enabled"] = False
        providers["claude-peer"]["env"] = {}
        self.save()
        result = self.run_check("--check")
        self.assertIn("claude-peer: need env", result.stderr)
        self.assertNotIn("claude-lead: need env", result.stderr)

    def test_pi_compaction_settings_check(self):
        self.save()
        self.assertEqual(self.run_check("--check").returncode, 0)
        settings = self.kit / ".pi" / "settings.json"
        for invalid in ('{', '{}', '{"compaction":{"modelOverrides":{}}}',
                        '{"compaction":{"modelOverrides":[]}}'):
            with self.subTest(invalid=invalid):
                settings.write_text(invalid)
                result = self.run_check("--check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(".pi/settings.json: need valid JSON", result.stderr)
        settings.unlink()
        self.assertNotEqual(self.run_check("--check").returncode, 0)

    def test_omp_compaction_settings_check(self):
        self.save()
        self.assertEqual(self.run_check("--check").returncode, 0)
        config = self.kit / ".omp" / "config.yml"
        for invalid in ("compaction: {}\n", "compaction:\n  thresholdTokens: 200000\n"):
            config.write_text(invalid)
            result = self.run_check("--check")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(".omp/config.yml: need thresholdTokens: 100000", result.stderr)
        config.unlink()
        self.assertNotEqual(self.run_check("--check").returncode, 0)

    def test_devin_compaction_observation_is_informational_only(self):
        self.save()
        absent = self.run_check("--check")
        self.assertEqual(absent.returncode, 0, absent.stderr)
        self.assertIn("Devin user-wide agent.compaction_threshold_tokens is absent", absent.stdout)
        config = pathlib.Path(self.temporary.name) / ".config" / "devin" / "config.json"
        config.parent.mkdir(parents=True)
        for value in (100000, 200000):
            config.write_text(json.dumps({"agent": {"compaction_threshold_tokens": value}}))
            before = config.read_bytes()
            result = self.run_check("--check")
            self.assertEqual(result.returncode, absent.returncode, result.stderr)
            self.assertEqual(config.read_bytes(), before)
            self.assertEqual("Devin user-wide" in result.stdout, value != 100000)

    def test_catalog_partition_and_example_policy(self):
        self.assertEqual((len(CATALOG), len(KEEP_LEAD), len(DENY_LEAD)), (61, 14, 47))
        self.assertEqual((len(KEEP_SUPERVISOR), len(DENY_SUPERVISOR)), (15, 46))
        self.assertEqual(KEEP_LEAD | DENY_LEAD, CATALOG)
        self.assertEqual(KEEP_SUPERVISOR | DENY_SUPERVISOR, CATALOG)
        example = json.loads((ROOT / "examples" / "paseo-providers.json").read_text())
        enabled = [p for p in example["agents"]["providers"].values() if p.get("paseoTools", {}).get("enabled") is True]
        self.assertTrue(enabled)
        for key, provider in example["agents"]["providers"].items():
            if provider.get("paseoTools", {}).get("enabled") is True:
                expected = DENY_SUPERVISOR if key.endswith("-supervisor") else DENY_LEAD
                self.assertEqual(set(provider["paseoTools"]["disabledTools"]), expected, key)
        self.assertEqual(len(example["daemon"]["agentProfiles"]), 45)
        counts = Counter(p["provider"] for p in example["daemon"]["agentProfiles"])
        self.assertEqual(counts, Counter({"amp-peer": 1, "amp-supervisor": 2,
            "claude-peer": 6, "claude-supervisor": 1, "codex-peer": 2,
            "codex-supervisor": 2, "copilot-peer": 10, "omp-peer": 9,
            "pi-peer": 9, "agy-peer": 3}))
        script = SCRIPT.read_text()
        match = re.search(r"expected_deny_lead='(\[.*?\])'", script)
        self.assertIsNotNone(match, "checker deny-list constant not found")
        self.assertEqual(set(json.loads(match.group(1))), DENY_LEAD)
        self.assertEqual(set(json.loads(match.group(1))) - {"create_workspace"}, DENY_SUPERVISOR)

    def test_omp_luna_cell_and_profiles(self):
        providers = self.data["agents"]["providers"]
        model = "github-copilot/gpt-6-luna"
        cell = next(m for m in providers["omp-peer"]["models"] if m["id"] == model)
        pi_cell = next(m for m in providers["pi-peer"]["models"] if m["id"] == model)
        self.assertTrue(pi_cell["isDefault"])
        self.assertEqual(pi_cell["thinkingOptions"], [
            {"id": "low", "label": "Low", "isDefault": False},
            {"id": "medium", "label": "Medium", "isDefault": True}])
        self.assertEqual(len([m for m in providers["pi-peer"]["models"] if m["isDefault"]]), 1)
        self.assertFalse(cell["isDefault"])
        self.assertEqual(cell["thinkingOptions"], [
            {"id": "low", "label": "Low", "isDefault": True},
            {"id": "medium", "label": "Medium", "isDefault": False}])
        self.save()
        result = self.run_check("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        cell["thinkingOptions"][0]["isDefault"] = False
        self.save()
        result = self.run_check("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("omp-peer: wrong GPT-6 Luna", result.stderr)

    def test_omp_luna_profiles_required(self):
        for effort in ("low", "medium"):
            with self.subTest(effort=effort):
                profile = next(p for p in self.data["daemon"]["agentProfiles"]
                               if p["id"] == f"omp-peer--github-copilot-gpt-6-luna--{effort}")
                self.assertEqual(profile["provider"], "omp-peer")
                self.assertEqual(profile["model"], "github-copilot/gpt-6-luna")
                self.assertEqual(profile["thinkingOptionId"], effort)
                self.data["daemon"]["agentProfiles"].remove(profile)
                self.save()
                result = self.run_check("--check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"omp-peer: missing or wrong GPT-6 Luna {effort} profile", result.stderr)
                self.data["daemon"]["agentProfiles"].append(profile)

    def test_agy_peer_requires_models_permissions_and_profiles(self):
        provider = self.data["agents"]["providers"]["agy-peer"]
        self.save()
        result = self.run_check("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        provider["env"]["AGY_EXTRA_ARGS"] = "--dangerously-skip-permissions"
        self.save()
        result = self.run_check("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("agy-peer: wrong launcher, permissions or model pins", result.stderr)
        provider["env"]["AGY_EXTRA_ARGS"] = "--mode accept-edits"
        profile = next(p for p in self.data["daemon"]["agentProfiles"] if p["id"] == "agy-peer--gemini-3.8-flash-high")
        self.data["daemon"]["agentProfiles"].remove(profile)
        self.save()
        result = self.run_check("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("agy-peer: missing or wrong gemini-3.8-flash-high profile", result.stderr)

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
                self.data["agents"]["providers"]["codex-lead"]["paseoTools"]["disabledTools"] = sorted(DENY_LEAD)
        del self.data["agents"]["providers"]["codex-lead"]["paseoTools"]["disabledTools"]
        self.save()
        result = self.run_check("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("codex-lead", result.stderr)

    def test_wrong_role_denylist_is_rejected(self):
        for seat, wrong in (("amp-supervisor", DENY_LEAD), ("codex-lead", DENY_SUPERVISOR)):
            with self.subTest(seat=seat):
                self.data["agents"]["providers"][seat]["paseoTools"]["disabledTools"] = sorted(wrong)
                self.save()
                result = self.run_check("--check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(seat, result.stderr)
                self.data["agents"]["providers"][seat]["paseoTools"]["disabledTools"] = sorted(DENY_SUPERVISOR if seat.endswith("-supervisor") else DENY_LEAD)

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


    def test_profile_validation_accepts_and_rejects_invalid_references(self):
        self.save()
        self.assertEqual(self.run_check("--check").returncode, 0)
        profile = self.data["daemon"]["agentProfiles"][0]
        original = profile["model"]
        profile["model"] = "not-on-seat"
        self.save()
        result = self.run_check("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("agentProfiles", result.stderr)
        profile["model"] = original
        profile["thinkingOptionId"] = "missing"
        self.save()
        result = self.run_check("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("agentProfiles", result.stderr)
        profile.pop("thinkingOptionId")
        amp_profile = next(p for p in self.data["daemon"]["agentProfiles"]
                           if p["id"] == "amp-peer--medium")
        amp_profile["thinkingOptionId"] = "low"
        self.save()
        result = self.run_check("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("agentProfiles", result.stderr)
        amp_profile.pop("thinkingOptionId")
        profile["provider"] = "not-an-epistex-seat"
        self.save()
        result = self.run_check("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("agentProfiles", result.stderr)

    def test_amp_claude_codex_supervisor_seat_checks(self):
        self.save()
        self.assertEqual(self.run_check("--check").returncode, 0)
        for seat in ("amp-supervisor", "claude-supervisor", "codex-supervisor"):
            old = self.data["agents"]["providers"][seat]["command"][0]
            self.data["agents"]["providers"][seat]["command"][0] = "/wrong/path"
            self.save()
            result = self.run_check("--check")
            self.assertNotEqual(result.returncode, 0, seat)
            self.assertIn(seat, result.stderr)
            self.data["agents"]["providers"][seat]["command"][0] = old

    def test_unknown_argument_fails(self):
        self.assertEqual(self.run_check("--unknown").returncode, 2)
