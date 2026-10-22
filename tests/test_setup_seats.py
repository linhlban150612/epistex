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
KEEP_LEAD = set("""list_workspaces list_providers list_models list_profiles create_agent send_agent_prompt cancel_agent archive_agent list_pending_permissions respond_to_permission set_agent_mode""".split())
KEEP_SUPERVISOR = KEEP_LEAD | {"create_workspace", "get_agent_activity", "get_agent_status", "list_agents"}
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
        providers["amp-supervisor"]["command"] = [str(self.kit / "setup" / "role-agent"), "supervisor", "amp"]
        providers["agy-peer"]["command"] = [str(self.kit / "setup" / "role-agent"), "peer", "agy"]
        providers["agy-lead"]["command"] = [str(self.kit / "setup" / "role-agent"), "lead", "agy"]
        providers["kiro-peer"]["command"] = [str(self.kit / "setup" / "role-agent"), "peer", "kiro"]
        providers["kiro-lead"]["command"] = [str(self.kit / "setup" / "role-agent"), "lead", "kiro"]
        providers["droid-peer"]["command"] = [str(self.kit / "setup" / "role-agent"), "peer", "droid"]
        providers["droid-lead"]["command"] = [str(self.kit / "setup" / "role-agent"), "lead", "droid"]
        providers["amp-lead"]["command"] = [str(self.kit / "setup" / "role-agent"), "lead", "amp"]
        providers["amp-peer"]["command"] = [str(self.kit / "setup" / "role-agent"), "peer", "amp"]
        providers["devin-peer"]["command"] = [str(self.kit / "setup" / "role-agent"), "peer", "devin"]
        providers["claude-lead"]["command"] = [str(self.kit / "setup" / "role-agent"), "lead", "claude"]
        providers["cursor-peer"]["command"] = [str(self.kit / "setup" / "role-agent"), "peer", "cursor"]
        providers["kiro-supervisor"]["command"] = [str(self.kit / "setup" / "role-agent"), "supervisor", "kiro"]
        runtime = pathlib.Path(self.temporary.name) / ".kiro/agents"
        runtime.mkdir(parents=True)
        shutil.copyfile(self.kit / "setup/kiro-peer.json", runtime / "epistex_peer.json")
        shutil.copyfile(self.kit / "setup/kiro-lead.json", runtime / "epistex_lead.json")
        shutil.copyfile(self.kit / "setup/kiro-supervisor.json", runtime / "epistex_supervisor.json")
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

    def test_check_requires_common_and_enforces_combined_prompt_limit(self):
        self.save()
        common = self.kit / "agents/contract/COMMON.md"
        common.write_text("x" * 16000)
        result = self.run_check("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("combined lead prompt exceeds 16 KiB", result.stderr)
        common.unlink()
        result = self.run_check("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("COMMON.md", result.stderr)

    def test_claude_compaction_env_checks_each_enabled_seat_and_peer(self):
        providers = self.data["agents"]["providers"]
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
        self.assertEqual((len(CATALOG), len(KEEP_LEAD), len(DENY_LEAD)), (61, 11, 50))
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
        self.assertEqual(len(example["daemon"]["agentProfiles"]), 109)
        counts = Counter(p["provider"] for p in example["daemon"]["agentProfiles"])
        self.assertEqual(counts, Counter({"amp-peer": 1, "amp-lead": 1, "amp-supervisor": 2,
            "claude-peer": 6, "claude-supervisor": 5, "codex-lead": 2, "codex-peer": 4,
            "codex-supervisor": 4, "copilot-peer": 10, "omp-peer": 11,
            "pi-peer": 11, "agy-peer": 4, "agy-lead": 2, "kiro-peer": 4, "kiro-lead": 4,
            "kiro-supervisor": 4, "droid-peer": 22, "droid-lead": 8, "devin-peer": 1, "claude-lead": 1, "cursor-peer": 2}))
        script = SCRIPT.read_text()
        match = re.search(r"expected_deny_lead='(\[.*?\])'", script)
        self.assertIsNotNone(match, "checker deny-list constant not found")
        self.assertEqual(set(json.loads(match.group(1))), DENY_LEAD)
        self.assertEqual(set(json.loads(match.group(1))) - {"create_workspace", "get_agent_activity", "get_agent_status", "list_agents"}, DENY_SUPERVISOR)

    def test_omp_luna_cell_and_profiles(self):
        providers = self.data["agents"]["providers"]
        model = "openai-codex/gpt-6-luna"
        cell = next(m for m in providers["omp-peer"]["models"] if m["id"] == model)
        pi_cell = next(m for m in providers["pi-peer"]["models"] if m["id"] == model)
        self.assertTrue(pi_cell["isDefault"])
        self.assertEqual(pi_cell["thinkingOptions"], [
            {"id": "low", "label": "Low", "isDefault": True},
            {"id": "medium", "label": "Medium", "isDefault": False}])
        self.assertEqual(len([m for m in providers["pi-peer"]["models"] if m["isDefault"]]), 1)
        self.assertTrue(cell["isDefault"])
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

    def test_cost_defaults_are_pinned(self):
        providers = self.data["agents"]["providers"]
        expected = {"claude-supervisor": ("claude-sonnet-5-5", "low"),
                    "kiro-supervisor": ("claude-sonnet-5.5", "low"),
                    "kiro-peer": ("claude-sonnet-5.5", "low"),
                    "kiro-lead": ("claude-opus-5.5", "low"),
                    "omp-peer": ("openai-codex/gpt-6-luna", "low"),
                    "pi-peer": ("openai-codex/gpt-6-luna", "low")}
        for seat, (model, effort) in expected.items():
            defaults = [m for m in providers[seat]["models"] if m["isDefault"]]
            self.assertEqual([m["id"] for m in defaults], [model], seat)
            self.assertEqual([o["id"] for o in defaults[0]["thinkingOptions"] if o["isDefault"]], [effort], seat)
        for seat, model, message in (
                ("kiro-peer", "claude-opus-5.5", "kiro-peer: wrong launcher, tools or model/effort"),
                ("kiro-supervisor", "claude-opus-5.5", "kiro-supervisor: wrong launcher, tools or model/effort"),
                ("claude-supervisor", "claude-fable-5-1", "claude-supervisor: wrong launcher, tools or model/effort")):
            with self.subTest(seat=seat):
                models = providers[seat]["models"]
                before = [m["isDefault"] for m in models]
                for m in models:
                    m["isDefault"] = m["id"] == model
                self.save()
                result = self.run_check("--check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                for m, flag in zip(models, before):
                    m["isDefault"] = flag
        luna = next(m for m in providers["omp-peer"]["models"] if m["id"] == "openai-codex/gpt-6-luna")
        for option in luna["thinkingOptions"]:
            option["isDefault"] = option["id"] == "medium"
        self.save()
        result = self.run_check("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("omp-peer/pi-peer: default must be openai-codex GPT-6 Luna, low effort", result.stderr)

    def test_omp_luna_profiles_required(self):
        for effort in ("low", "medium"):
            with self.subTest(effort=effort):
                profile = next(p for p in self.data["daemon"]["agentProfiles"]
                               if p["id"] == f"omp-peer--openai-codex-gpt-6-luna--{effort}")
                self.assertEqual(profile["provider"], "omp-peer")
                self.assertEqual(profile["model"], "openai-codex/gpt-6-luna")
                self.assertEqual(profile["thinkingOptionId"], effort)
                self.data["daemon"]["agentProfiles"].remove(profile)
                self.save()
                result = self.run_check("--check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"omp-peer: missing or wrong GPT-6 Luna {effort} profile", result.stderr)
                self.data["daemon"]["agentProfiles"].append(profile)

    def test_agy_peer_requires_models_permissions_and_profiles(self):
        provider = self.data["agents"]["providers"]["agy-peer"]
        models = ("gemini-3.8-flash-low", "gemini-3.8-flash-medium",
                  "gemini-4-argon-low", "gemini-4-argon-medium")
        self.assertEqual([m["id"] for m in provider["models"]], list(models))
        self.assertEqual([m["id"] for m in provider["models"] if m["isDefault"]],
                         ["gemini-3.8-flash-low"])
        self.save()
        result = self.run_check("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        provider["env"]["AGY_EXTRA_ARGS"] = "--dangerously-skip-permissions"
        self.save()
        result = self.run_check("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("agy-peer: wrong launcher, permissions or model pins", result.stderr)
        provider["env"] = {}
        provider["paseoTools"]["enabled"] = True
        self.save()
        result = self.run_check("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("agy-peer: wrong launcher, permissions or model pins", result.stderr)
        provider["paseoTools"]["enabled"] = False
        for model in models:
            with self.subTest(model=model):
                profile = next(p for p in self.data["daemon"]["agentProfiles"]
                               if p["id"] == f"agy-peer--{model.replace('.', '-')}")
                self.assertEqual(profile["provider"], "agy-peer")
                self.assertEqual(profile["model"], model)
                self.assertEqual(profile["modeId"], "auto_edit")
                self.assertNotIn("thinkingOptionId", profile)
                self.data["daemon"]["agentProfiles"].remove(profile)
                self.save()
                result = self.run_check("--check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"agy-peer: missing or wrong {model} profile", result.stderr)
                self.data["daemon"]["agentProfiles"].append(profile)
        for model in ("gemini-4-argon-low", "gemini-4-argon-medium"):
            cell = next(m for m in provider["models"] if m["id"] == model)
            for mutation in ("missing", "default"):
                with self.subTest(model=model, mutation=mutation):
                    if mutation == "missing":
                        provider["models"].remove(cell)
                    else:
                        cell["isDefault"] = True
                    self.save()
                    result = self.run_check("--check")
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("agy-peer: wrong launcher, permissions or model pins", result.stderr)
                    if mutation == "missing":
                        provider["models"].append(cell)
                    else:
                        cell["isDefault"] = False
            profile = next(p for p in self.data["daemon"]["agentProfiles"]
                           if p["id"] == f"agy-peer--{model.replace('.', '-')}")
            for key, value in (("provider", "agy-lead"), ("model", "gemini-3.8-flash-low"),
                               ("modeId", "yolo"), ("modeId", "default"),
                               ("thinkingOptionId", "low")):
                with self.subTest(model=model, key=key):
                    original = dict(profile)
                    profile[key] = value
                    self.save()
                    result = self.run_check("--check")
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(f"agy-peer: missing or wrong {model} profile", result.stderr)
                    profile.clear()
                    profile.update(original)

    def test_agy_lead_requires_lead_policy_default_mode_and_argon_profiles(self):
        provider = self.data["agents"]["providers"]["agy-lead"]
        self.assertTrue(provider["enabled"])
        self.assertEqual(set(provider["paseoTools"]["disabledTools"]), DENY_LEAD)
        self.save()
        result = self.run_check("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        for key, value in (("AGY_EXTRA_ARGS", "--dangerously-skip-permissions"),
                           ("AGY_EXTRA_ARGS", "--mode accept-edits")):
            with self.subTest(value=value):
                provider["env"][key] = value
                self.save()
                result = self.run_check("--check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("agy-lead: wrong launcher, permissions or model pins", result.stderr)
        provider["env"] = {}
        provider["command"][1] = "peer"
        self.save()
        result = self.run_check("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("agy-lead: wrong launcher, permissions or model pins", result.stderr)
        provider["command"][1] = "lead"
        provider["paseoTools"]["disabledTools"].remove("kill_agent")
        self.save()
        result = self.run_check("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("agy-lead", result.stderr)
        provider["paseoTools"]["disabledTools"].append("kill_agent")
        for model in ("gemini-4-argon-low", "gemini-4-argon-medium"):
            with self.subTest(model=model):
                profile = next(p for p in self.data["daemon"]["agentProfiles"] if p["id"] == f"agy-lead--{model}")
                self.assertEqual(profile["modeId"], "yolo")
                for bad_mode in ("default", "auto_edit"):
                    with self.subTest(model=model, modeId=bad_mode):
                        original = profile["modeId"]
                        profile["modeId"] = bad_mode
                        self.save()
                        result = self.run_check("--check")
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn(f"agy-lead: missing or wrong {model} profile", result.stderr)
                        profile["modeId"] = original
                self.data["daemon"]["agentProfiles"].remove(profile)
                self.save()
                result = self.run_check("--check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"agy-lead: missing or wrong {model} profile", result.stderr)
                self.data["daemon"]["agentProfiles"].append(profile)
        del self.data["agents"]["providers"]["agy-lead"]
        self.data["daemon"]["agentProfiles"] = [p for p in self.data["daemon"]["agentProfiles"]
                                                if p["provider"] != "agy-lead"]
        self.save()
        result = self.run_check("--check")
        self.assertEqual(result.returncode, 0, result.stderr)

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
                    tools.append("cancel_agent")
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

    def test_devin_peer_swe_2_high_only(self):
        models = self.data["agents"]["providers"]["devin-peer"]["models"]
        self.assertEqual([m["id"] for m in models], ["swe-2-high"])
        self.assertNotIn("devin-supervisor", self.data["agents"]["providers"])

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
        supervisor = self.data["agents"]["providers"].pop("codex-supervisor")
        self.save()
        result = self.run_check("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("codex-supervisor", result.stderr)
        self.data["agents"]["providers"]["codex-supervisor"] = supervisor
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
                           if p["id"] == "amp-peer--low")
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

    def test_disabled_optional_seats_require_profile_removal_and_validate_when_reenabled(self):
        for seat in ("amp-supervisor", "claude-supervisor", "codex-supervisor",
                     "copilot-peer", "devin-peer", "agy-lead"):
            self.data["agents"]["providers"][seat]["enabled"] = False
        self.save()
        result = self.run_check("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("daemon.agentProfiles", result.stderr)
        self.data["daemon"]["agentProfiles"] = [
            p for p in self.data["daemon"]["agentProfiles"]
            if self.data["agents"]["providers"][p["provider"]]["enabled"]]
        self.save()
        before = self.config.read_bytes()
        result = self.run_check("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.config.read_bytes(), before)
        for seat in ("amp-supervisor", "devin-peer", "agy-lead"):
            with self.subTest(seat=seat):
                provider = self.data["agents"]["providers"][seat]
                provider["enabled"] = True
                command = provider.pop("command")
                self.save()
                result = self.run_check("--check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(seat + ": wrong launcher", result.stderr)
                provider["command"] = command
                provider["enabled"] = False

    def test_profile_optional_settings_types(self):
        profile = self.data["daemon"]["agentProfiles"][0]
        for key, value in (("modeId", 12), ("modeId", ""), ("featureValues", [])):
            with self.subTest(key=key, value=value):
                profile[key] = value
                self.save()
                result = self.run_check("--check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("daemon.agentProfiles", result.stderr)
                profile.pop(key)

    def test_profile_normalization_preserves_catalog_launch_settings_and_foreign_profiles(self):
        profiles = self.data["daemon"]["agentProfiles"]
        profiles[0]["featureValues"] = {"example_feature": False}
        foreign = {"id": "personal", "provider": "personal-peer", "notes": "Keep mine"}
        profiles.append(foreign)
        for seat in ("copilot-peer", "amp-supervisor", "devin-peer"):
            self.data["agents"]["providers"][seat]["enabled"] = False
        self.save()
        for catalog in (True, False):
            with self.subTest(catalog=catalog):
                command = [str(self.bin / "jq"), "--argjson", "catalog", json.dumps(catalog),
                           "-f", str(ROOT / "setup/normalize-profiles.jq")]
                result = subprocess.run(command + [str(self.config)], text=True,
                                        capture_output=True, check=True)
                data = json.loads(result.stdout)
                actual = data["daemon"]["agentProfiles"]
                self.assertEqual(len(actual), len(profiles) - (0 if catalog else 13))
                self.assertEqual(actual[-1], foreign)
                self.assertEqual(data["agents"], self.data["agents"])
                expected = [p for p in profiles if catalog or p == foreign or
                            self.data["agents"]["providers"][p["provider"]]["enabled"]]
                for old, new in zip(expected, actual):
                    self.assertEqual({k: v for k, v in old.items() if k != "notes"},
                                     {k: v for k, v in new.items() if k != "notes"})
                    if new != foreign:
                        self.assertNotIn("cheap/fast", new["notes"])
                        self.assertIn("featureValues to settings.features", new["notes"])
                        self.assertIn("modeId to settings.modeId", new["notes"])
                        self.assertIn("thinkingOptionId to settings.thinkingOptionId", new["notes"])
                again = subprocess.run(command, input=result.stdout, text=True,
                                       capture_output=True, check=True)
                self.assertEqual(json.loads(again.stdout), data)

    def test_codex_lead_requires_full_access_profiles(self):
        self.save()
        result = self.run_check("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        profiles = self.data["daemon"]["agentProfiles"]
        for effort in ("low", "medium"):
            profile = next(p for p in profiles if p["id"] == f"codex-lead--gpt-6-1-sol--{effort}")
            for mode in ("auto", "auto-review", None):
                with self.subTest(effort=effort, mode=mode):
                    original = profile.pop("modeId")
                    if mode:
                        profile["modeId"] = mode
                    self.save()
                    result = self.run_check("--check")
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(f"codex-lead: missing or wrong gpt-6.1-sol {effort} profile", result.stderr)
                    profile["modeId"] = original

    def test_codex_peer_requires_auto_review_profiles(self):
        # Default mode "auto" leaves a non-interactive Peer in a read-only sandbox (observed 2026-10-22).
        self.save()
        result = self.run_check("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        profiles = self.data["daemon"]["agentProfiles"]
        for effort in ("low", "medium"):
            profile = next(p for p in profiles if p["id"] == f"codex-peer--gpt-6-luna--{effort}")
            self.assertEqual(profile["modeId"], "auto-review")
            for mode in ("auto", "full-access", None):
                with self.subTest(effort=effort, mode=mode):
                    original = profile.pop("modeId")
                    if mode:
                        profile["modeId"] = mode
                    self.save()
                    result = self.run_check("--check")
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(f"codex-peer: missing or wrong gpt-6-luna {effort} profile", result.stderr)
                    profile["modeId"] = original

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

    def test_kiro_peer_requires_all_four_profiles_and_scoped_runtime(self):
        self.save()
        self.assertEqual(self.run_check("--check").returncode, 0)
        profiles = self.data["daemon"]["agentProfiles"]
        for profile in [p for p in profiles if p["provider"] == "kiro-peer"]:
            profiles.remove(profile)
            self.save()
            result = self.run_check("--check")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("kiro-peer: missing or wrong", result.stderr)
            profiles.append(profile)
        self.save()
        runtime = pathlib.Path(self.temporary.name) / ".kiro/agents/epistex_peer.json"
        runtime.write_text('{"tools":["subagent"]}')
        result = self.run_check("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("install exact seat-owned runtime config", result.stderr)

    def test_kiro_lead_requires_lead_policy_profiles_and_scoped_runtime(self):
        self.save()
        self.assertEqual(self.run_check("--check").returncode, 0)
        provider = self.data["agents"]["providers"]["kiro-lead"]
        for key, value in (("command", [str(self.kit / "setup" / "role-agent"), "peer", "kiro"]),
                           ("paseoTools", {"enabled": False}), ("env", {"KIRO_EXTRA": "1"})):
            with self.subTest(key=key):
                original = provider[key]
                provider[key] = value
                self.save()
                result = self.run_check("--check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("kiro-lead: wrong launcher, tools or model/effort", result.stderr)
                provider[key] = original
        provider["paseoTools"]["disabledTools"] = provider["paseoTools"]["disabledTools"][1:]
        self.save()
        result = self.run_check("--check")
        self.assertIn("kiro-lead: paseoTools.disabledTools must exactly match the deny-list", result.stderr)
        provider["paseoTools"]["disabledTools"] = sorted(DENY_LEAD)
        profiles = self.data["daemon"]["agentProfiles"]
        for profile in [p for p in profiles if p["provider"] == "kiro-lead"]:
            profiles.remove(profile)
            self.save()
            result = self.run_check("--check")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("kiro-lead: missing or wrong", result.stderr)
            profiles.append(profile)
        self.save()
        runtime = pathlib.Path(self.temporary.name) / ".kiro/agents/epistex_lead.json"
        runtime.write_text('{"tools":["@paseo"]}')
        result = self.run_check("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("kiro-lead: install exact seat-owned runtime config", result.stderr)
        self.assertNotIn("kiro-peer", result.stderr)
        runtime.unlink()
        runtime.symlink_to(self.kit / "setup/kiro-lead.json")
        self.assertIn("kiro-lead: install exact", self.run_check("--check").stderr)
        runtime.unlink()
        del self.data["agents"]["providers"]["kiro-lead"]
        self.data["daemon"]["agentProfiles"] = [p for p in profiles if p["provider"] != "kiro-lead"]
        self.save()
        self.assertEqual(self.run_check("--check").returncode, 0)

    def test_droid_peer_requires_role_wrapper_and_luna_default(self):
        self.save()
        self.assertEqual(self.run_check("--check").returncode, 0)
        provider = self.data["agents"]["providers"]["droid-peer"]
        self.assertEqual([m["id"] for m in provider["models"] if m["isDefault"]], ["gpt-6-luna"])
        self.assertNotIn("auto", {p["model"] for p in self.data["daemon"]["agentProfiles"]
                                  if p["provider"] == "droid-peer"})
        for key, value in (("command", ["droid", "exec", "--output-format", "acp"]),
                           ("command", [str(self.kit / "setup" / "role-agent"), "lead", "droid"]),
                           ("paseoTools", {"enabled": True})):
            with self.subTest(key=key):
                old = provider[key]
                provider[key] = value
                self.save()
                result = self.run_check("--check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("droid-peer", result.stderr)
                provider[key] = old
        profile = next(p for p in self.data["daemon"]["agentProfiles"] if p["id"] == "droid-peer--gpt-6-luna--low")
        profile.pop("thinkingOptionId")
        self.save()
        result = self.run_check("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("agentProfiles", result.stderr)
        profile["thinkingOptionId"] = "low"
        profile["provider"] = "factory-droid"
        self.save()
        result = self.run_check("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("agentProfiles", result.stderr)

    def test_droid_peer_luna_cell_and_profiles_required(self):
        provider = self.data["agents"]["providers"]["droid-peer"]
        cell = next(m for m in provider["models"] if m["id"] == "gpt-6-luna")
        self.assertTrue(cell["isDefault"])
        self.assertEqual([o["id"] for o in cell["thinkingOptions"]], ["off", "low", "medium", "high", "xhigh", "max"])
        self.assertEqual([o["id"] for o in cell["thinkingOptions"] if o["isDefault"]], ["low"])
        for flag in ("isDefault", "effort"):
            with self.subTest(default=flag):
                target = cell if flag == "isDefault" else next(o for o in cell["thinkingOptions"] if o["id"] == "low")
                target["isDefault"] = False
                self.save()
                result = self.run_check("--check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("droid-peer: wrong launcher, tools or model/effort", result.stderr)
                target["isDefault"] = True
        for effort in ("low", "medium"):
            with self.subTest(effort=effort):
                profile = next(p for p in self.data["daemon"]["agentProfiles"]
                               if p["id"] == f"droid-peer--gpt-6-luna--{effort}")
                self.assertEqual((profile["provider"], profile["model"], profile["thinkingOptionId"]),
                                 ("droid-peer", "gpt-6-luna", effort))
                self.data["daemon"]["agentProfiles"].remove(profile)
                self.save()
                result = self.run_check("--check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"droid-peer: missing or wrong GPT-6 Luna {effort} profile", result.stderr)
                self.data["daemon"]["agentProfiles"].append(profile)

    def test_droid_peer_supported_model_inventory_and_required_choices(self):
        expected = {
            "gemini-4-argon": ["low", "medium"], "gemini-3.8-flash": ["low", "medium"],
            "claude-opus-5-5": ["low", "medium"], "claude-sonnet-5-5": ["low", "medium"],
            "claude-haiku-5-5": ["low", "medium"], "gpt-6.1-sol": ["low", "medium"],
            "glm-5.3-flash": ["low", "high"], "glm-5.3": ["low", "high"],
            "kimi-k3": ["low", "high"], "deepseek-v4.1-flash": ["low", "high"],
        }
        models = self.data["agents"]["providers"]["droid-peer"]["models"]
        added = [m for m in models if m["id"] != "gpt-6-luna"]
        self.assertEqual({m["id"]: [o["id"] for o in m["thinkingOptions"]] for m in added}, expected)
        for model in added:
            self.assertFalse(model["isDefault"])
            self.assertEqual([o["id"] for o in model["thinkingOptions"] if o["isDefault"]], ["low"])
        profiles = [p for p in self.data["daemon"]["agentProfiles"]
                    if p["provider"] == "droid-peer" and p["model"] != "gpt-6-luna"]
        self.assertEqual(sorted((p["id"], p["model"], p["thinkingOptionId"]) for p in profiles),
                         sorted((f"droid-peer--{model.replace('.', '-')}--{effort}", model, effort)
                                for model, efforts in expected.items() for effort in efforts))
        for model_id, effort in (("gemini-4-argon", None), ("claude-opus-5-5", "medium"),
                                 ("gpt-6.1-sol", "low"), ("glm-5.3-flash", "high")):
            with self.subTest(model=model_id, missing=effort):
                model = next(m for m in models if m["id"] == model_id)
                if effort is None:
                    models.remove(model)
                else:
                    options = model["thinkingOptions"]
                    model["thinkingOptions"] = [o for o in options if o["id"] != effort]
                self.save()
                result = self.run_check("--check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("droid-peer: wrong launcher, tools or model/effort", result.stderr)
                if effort is None:
                    models.append(model)
                else:
                    model["thinkingOptions"] = options

    def test_droid_peer_new_profiles_required_and_bound_to_exact_choices(self):
        profiles = self.data["daemon"]["agentProfiles"]
        for profile_id in ("droid-peer--gemini-3-8-flash--low", "droid-peer--gpt-6-1-sol--medium",
                           "droid-peer--glm-5-3--low", "droid-peer--kimi-k3--high"):
            with self.subTest(missing=profile_id):
                profile = next(p for p in profiles if p["id"] == profile_id)
                profiles.remove(profile)
                self.save()
                result = self.run_check("--check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("droid-peer: missing or wrong supported model/effort profile", result.stderr)
                profiles.append(profile)
        profile = next(p for p in profiles if p["id"] == "droid-peer--claude-sonnet-5-5--medium")
        for key, value in (("provider", "claude-peer"), ("model", "claude-haiku-5-5"),
                           ("thinkingOptionId", "low")):
            with self.subTest(mismatch=key):
                original = profile[key]
                profile[key] = value
                self.save()
                result = self.run_check("--check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("droid-peer: missing or wrong supported model/effort profile", result.stderr)
                profile[key] = original

        profile = next(p for p in profiles if p["id"] == "droid-peer--deepseek-v4-1-flash--high")
        profile["thinkingOptionId"] = "low"
        self.save()
        result = self.run_check("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("droid-peer: missing or wrong supported model/effort profile", result.stderr)

    def test_droid_peer_low_high_models_reject_fabricated_medium(self):
        models = self.data["agents"]["providers"]["droid-peer"]["models"]
        profiles = self.data["daemon"]["agentProfiles"]
        for model_id in ("glm-5.3-flash", "glm-5.3", "kimi-k3", "deepseek-v4.1-flash"):
            with self.subTest(model=model_id):
                model = next(m for m in models if m["id"] == model_id)
                medium = {"id": "medium", "label": "Medium", "isDefault": False}
                profile = {"id": f"droid-peer--{model_id.replace('.', '-')}--medium",
                           "provider": "droid-peer", "model": model_id, "thinkingOptionId": "medium"}
                model["thinkingOptions"].append(medium)
                profiles.append(profile)
                self.save()
                result = self.run_check("--check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("droid-peer: wrong launcher, tools or model/effort", result.stderr)
                model["thinkingOptions"].remove(medium)
                self.save()
                result = self.run_check("--check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("agentProfiles: invalid seat, model or thinking option", result.stderr)
                profiles.remove(profile)

    def test_droid_peer_absent_or_disabled_is_not_required(self):
        providers = self.data["agents"]["providers"]
        providers.pop("droid-peer")
        self.data["daemon"]["agentProfiles"] = [p for p in self.data["daemon"]["agentProfiles"]
                                                if p["provider"] != "droid-peer"]
        self.save()
        result = self.run_check("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
