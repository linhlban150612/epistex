import copy
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
CATALOG = set("""archive_agent archive_workspace browser_back browser_click browser_close_tab browser_drag browser_evaluate browser_fill browser_forward browser_hover browser_keypress browser_list_tabs browser_logs browser_navigate browser_new_tab browser_reload browser_resize browser_screenshot browser_scroll browser_select browser_snapshot browser_type browser_upload browser_wait cancel_agent capture_terminal create_agent create_heartbeat create_schedule create_terminal create_workspace delete_heartbeat delete_schedule get_agent_activity get_agent_status inspect_provider inspect_schedule kill_agent kill_terminal list_agents list_hosts list_models list_pending_permissions list_profiles list_providers list_schedules list_terminals list_workspace_scripts list_workspaces pause_schedule rename_workspace respond_to_permission resume_schedule run_schedule_once schedule_logs send_agent_prompt send_terminal_keys set_agent_mode start_workspace_script stop_workspace_script update_agent update_schedule""".split())
KEEP_LEAD = set("""list_workspaces list_providers list_models list_profiles create_agent send_agent_prompt cancel_agent archive_agent list_pending_permissions respond_to_permission set_agent_mode""".split())
KEEP_SUPERVISOR = KEEP_LEAD | {"create_workspace", "get_agent_activity", "get_agent_status", "list_agents", "list_hosts"}
DENY_LEAD = CATALOG - KEEP_LEAD
DENY_SUPERVISOR = CATALOG - KEEP_SUPERVISOR


class SetupSeatsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.config = pathlib.Path(self.temporary.name) / "config.json"
        self.bin = pathlib.Path(self.temporary.name) / "bin"
        self.bin.mkdir()
        self.kit = pathlib.Path(self.temporary.name) / "kit"
        for directory in ("setup", "agents", "examples", ".agents", ".pi", ".omp"):
            shutil.copytree(ROOT / directory, self.kit / directory)
        self.script = self.kit / "setup" / "setup-seats.sh"
        for name in ("bash", "jq", "dirname", "wc", "chmod", "grep", "sort", "diff", "cp", "mkdir", "git"):
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

    def check_config(self, data):
        self.config.write_text(json.dumps(data))
        return self.run_check("--check")

    def test_example_catalog_passes_without_changing_files(self):
        self.assertEqual((len(CATALOG), len(KEEP_LEAD), len(DENY_LEAD)), (62, 11, 51))
        self.assertEqual((len(KEEP_SUPERVISOR), len(DENY_SUPERVISOR)), (16, 46))
        match = re.search(r"expected_deny_lead='(\[.*?\])'", SCRIPT.read_text())
        self.assertIsNotNone(match, "checker deny-list constant not found")
        self.assertEqual(set(json.loads(match.group(1))), DENY_LEAD)
        for key, provider in self.data["agents"]["providers"].items():
            if provider.get("paseoTools", {}).get("enabled") is True:
                expected = DENY_SUPERVISOR if key.endswith("-supervisor") else DENY_LEAD
                self.assertEqual(set(provider["paseoTools"]["disabledTools"]), expected, key)

        self.save()
        before = self.config.read_bytes()
        result = self.run_check("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertIn("auth, daemon and launch not checked", result.stdout)
        self.assertIn("Devin user-wide agent.compaction_threshold_tokens is absent", result.stdout)

        # Devin compaction is a user-wide observation and never gates setup.
        devin = pathlib.Path(self.temporary.name) / ".config/devin/config.json"
        devin.parent.mkdir(parents=True)
        for value in (100000, 200000):
            devin.write_text(json.dumps({"agent": {"compaction_threshold_tokens": value}}))
            result = self.run_check("--check")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual("Devin user-wide" in result.stdout, value != 100000)

        del self.env["CODEX_BIN"]
        (self.bin / "codex").symlink_to(self.codex)
        self.assertEqual(self.run_check("--check").returncode, 0)

    def test_check_rejects_each_provider_and_profile_violation(self):
        def seat(d, name):
            return d["agents"]["providers"][name]

        def profile(d, pid):
            return next(p for p in d["daemon"]["agentProfiles"] if p["id"] == pid)

        def drop(d, pid):
            d["daemon"]["agentProfiles"].remove(profile(d, pid))

        def model(d, name, mid):
            return next(m for m in seat(d, name)["models"] if m["id"] == mid)

        def deny(name, tools):
            return lambda d: seat(d, name)["paseoTools"].__setitem__("disabledTools", tools)

        def fabricated_medium(d):
            model(d, "droid-peer", "glm-5.3")["thinkingOptions"].append(
                {"id": "medium", "label": "Medium", "isDefault": False})
            d["daemon"]["agentProfiles"].append({"id": "droid-peer--glm-5-3--medium", "provider": "droid-peer",
                                                 "model": "glm-5.3", "thinkingOptionId": "medium"})

        def default_model(name, mid):
            def mutate(d):
                for m in seat(d, name)["models"]:
                    m["isDefault"] = m["id"] == mid
            return mutate

        kit = str(self.kit / "setup")
        deny_lead = sorted(DENY_LEAD)
        profiles_error = "daemon.agentProfiles: invalid seat, model or thinking option"
        hf_deepseek = "pi-peer--huggingface-deepseek-ai-deepseek-v4-1-flash-1017--low"
        or_deepseek = "omp-peer--openrouter-deepseek-deepseek-v4-1-flash-1017--low"
        cases = [
            # Paseo tool policy
            ("deny-list missing member", deny("codex-lead", sorted(DENY_LEAD - {"create_heartbeat"})),
             "codex-lead: paseoTools.disabledTools must exactly match"),
            ("deny-list blocks a kept tool", deny("codex-lead", deny_lead + ["cancel_agent"]),
             "codex-lead: paseoTools.disabledTools must exactly match"),
            ("deny-list absent", lambda d: seat(d, "codex-lead")["paseoTools"].pop("disabledTools"),
             "codex-lead: paseoTools.disabledTools must exactly match"),
            ("lead deny-list on supervisor", deny("amp-supervisor", deny_lead),
             "amp-supervisor: paseoTools.disabledTools must exactly match"),
            ("supervisor deny-list on lead", deny("codex-lead", sorted(DENY_SUPERVISOR)),
             "codex-lead: paseoTools.disabledTools must exactly match"),
            ("peer with Paseo tools", lambda d: seat(d, "codex-peer").__setitem__("paseoTools", {"enabled": True}),
             "codex-peer: enabled Paseo seat must be a Lead or Supervisor"),
            ("MCP injection disabled", lambda d: d["daemon"]["mcp"].__setitem__("enabled", False),
             "Paseo MCP injection is not enabled"),
            ("Claude compaction window", lambda d: seat(d, "claude-lead")["env"].__setitem__(
                "CLAUDE_CODE_AUTO_COMPACT_WINDOW", "200000"),
             "claude-lead: need env CLAUDE_CODE_AUTO_COMPACT_WINDOW=100000"),
            # Supervisor seats
            ("supervisor missing", lambda d: d["agents"]["providers"].pop("codex-supervisor"),
             "codex-supervisor: wrong launcher"),
            ("supervisor without tools", lambda d: seat(d, "codex-supervisor")["paseoTools"].__setitem__("enabled", False),
             "codex-supervisor: wrong launcher"),
            ("supervisor wrong launcher", lambda d: seat(d, "amp-supervisor")["command"].__setitem__(0, "/wrong/path"),
             "amp-supervisor: wrong launcher"),
            ("supervisor expensive default", default_model("claude-supervisor", "claude-fable-5-1"),
             "claude-supervisor: wrong launcher, tools or model/effort"),
            # Codex and Claude seats
            ("codex lead with peer model", lambda d: seat(d, "codex-lead")["models"][0].__setitem__("id", "gpt-6-luna"),
             "codex-lead: wrong wrapper"),
            ("codex peer with lead model", lambda d: seat(d, "codex-peer")["models"][0].__setitem__("id", "gpt-6.1-sol"),
             "codex-peer: wrong wrapper"),
            ("codex peer without models", lambda d: seat(d, "codex-peer").__setitem__("models", []),
             "codex-peer: wrong wrapper"),
            ("codex lead sandboxed", lambda d: profile(d, "codex-lead--gpt-6-1-sol--low").__setitem__("modeId", "auto-review"),
             "codex-lead: missing or wrong gpt-6.1-sol low profile"),
            ("codex peer read-only", lambda d: profile(d, "codex-peer--gpt-6-luna--medium").__setitem__("modeId", "auto"),
             "codex-peer: missing or wrong gpt-6-luna medium profile"),
            ("codex peer Terra read-only", lambda d: profile(d, "codex-peer--gpt-6-1-terra--low").__setitem__("modeId", "auto"),
             "codex-peer: missing or wrong gpt-6.1-terra low profile"),
            ("codex peer without Terra", lambda d: seat(d, "codex-peer").__setitem__("models", [m for m in seat(d, "codex-peer")["models"] if m["id"] != "gpt-6.1-terra"]),
             "codex-peer: wrong wrapper"),
            ("claude peer acceptEdits", lambda d: profile(d, "claude-peer--claude-opus-5-5--medium").__setitem__(
                "modeId", "acceptEdits"), "claude-peer: every profile needs modeId bypassPermissions"),
            # Pi and OMP seats
            ("OMP Luna effort default", lambda d: model(d, "omp-peer", "openai-codex/gpt-6-luna")["thinkingOptions"][0]
             .__setitem__("isDefault", False), "omp-peer: wrong GPT-6 Luna"),
            ("OMP default effort", lambda d: next(m for m in seat(d, "omp-peer")["models"] if m["isDefault"])
             ["thinkingOptions"][0].__setitem__("isDefault", False),
             "omp-peer/pi-peer: default must be Hugging Face DeepSeek V4.1 Flash 1017, low effort"),
            ("Pi DeepSeek profile missing", lambda d: drop(d, hf_deepseek), "pi-peer: wrong DeepSeek 1017 models/profiles"),
            ("OMP DeepSeek profile missing", lambda d: drop(d, or_deepseek), "omp-peer: wrong DeepSeek 1017 models/profiles"),
            ("OMP Luna profile missing", lambda d: drop(d, "omp-peer--openai-codex-gpt-6-luna--medium"),
             "omp-peer: missing or wrong GPT-6 Luna medium profile"),
            # Antigravity seats
            ("agy peer skips permissions", lambda d: seat(d, "agy-peer")["env"].__setitem__(
                "AGY_EXTRA_ARGS", "--dangerously-skip-permissions"), "agy-peer: wrong launcher, permissions or model pins"),
            ("agy peer model missing", lambda d: seat(d, "agy-peer")["models"].remove(
                model(d, "agy-peer", "gemini-4-argon-low")), "agy-peer: wrong launcher, permissions or model pins"),
            ("agy peer profile missing", lambda d: drop(d, "agy-peer--gemini-4-argon-low"),
             "agy-peer: missing or wrong gemini-4-argon-low profile"),
            ("agy peer yolo", lambda d: profile(d, "agy-peer--gemini-4-argon-medium").__setitem__("modeId", "yolo"),
             "agy-peer: missing or wrong gemini-4-argon-medium profile"),
            ("agy peer thinking option", lambda d: profile(d, "agy-peer--gemini-4-argon-low").__setitem__(
                "thinkingOptionId", "low"), "agy-peer: missing or wrong gemini-4-argon-low profile"),
            ("agy lead with peer role", lambda d: seat(d, "agy-lead")["command"].__setitem__(1, "peer"),
             "agy-lead: wrong launcher, permissions or model pins"),
            ("agy lead extra args", lambda d: seat(d, "agy-lead")["env"].__setitem__("AGY_EXTRA_ARGS", "--mode accept-edits"),
             "agy-lead: wrong launcher, permissions or model pins"),
            ("agy lead deny-list", deny("agy-lead", sorted(DENY_LEAD - {"kill_agent"})),
             "agy-lead: paseoTools.disabledTools must exactly match"),
            ("agy lead auto_edit", lambda d: profile(d, "agy-lead--gemini-4-argon-low").__setitem__("modeId", "auto_edit"),
             "agy-lead: missing or wrong gemini-4-argon-low profile"),
            # Kiro seats
            ("kiro lead with peer role", lambda d: seat(d, "kiro-lead").__setitem__(
                "command", [kit + "/role-agent", "peer", "kiro"]), "kiro-lead: wrong launcher, tools or model/effort"),
            ("kiro lead extra env", lambda d: seat(d, "kiro-lead").__setitem__("env", {"KIRO_EXTRA": "1"}),
             "kiro-lead: wrong launcher, tools or model/effort"),
            ("kiro lead deny-list", deny("kiro-lead", deny_lead[1:]),
             "kiro-lead: paseoTools.disabledTools must exactly match"),
            ("kiro lead profile missing", lambda d: drop(d, "kiro-lead--claude-sonnet-5-5--medium"),
             "kiro-lead: missing or wrong claude-sonnet-5.5 medium profile"),
            ("kiro peer profile missing", lambda d: drop(d, "kiro-peer--claude-opus-5-5--low"),
             "kiro-peer: missing or wrong claude-opus-5.5 low profile"),
            ("kiro peer expensive default", default_model("kiro-peer", "claude-opus-5.5"),
             "kiro-peer: wrong launcher, tools or model/effort"),
            ("kiro supervisor expensive default", default_model("kiro-supervisor", "claude-opus-5.5"),
             "kiro-supervisor: wrong launcher, tools or model/effort"),
            # Droid seats
            ("droid peer unwrapped", lambda d: seat(d, "droid-peer").__setitem__(
                "command", ["droid", "exec", "--output-format", "acp"]), "droid-peer: wrong launcher, tools or model/effort"),
            ("droid peer with lead role", lambda d: seat(d, "droid-peer").__setitem__(
                "command", [kit + "/role-agent", "lead", "droid"]), "droid-peer: wrong launcher, tools or model/effort"),
            ("droid Luna not default", lambda d: model(d, "droid-peer", "gpt-6-luna").__setitem__("isDefault", False),
             "droid-peer: wrong launcher, tools or model/effort"),
            ("droid model missing", lambda d: seat(d, "droid-peer")["models"].remove(
                model(d, "droid-peer", "gemini-4-argon")), "droid-peer: wrong launcher, tools or model/effort"),
            ("droid effort missing", lambda d: model(d, "droid-peer", "glm-5.3-flash").__setitem__(
                "thinkingOptions", [o for o in model(d, "droid-peer", "glm-5.3-flash")["thinkingOptions"] if o["id"] != "high"]),
             "droid-peer: wrong launcher, tools or model/effort"),
            ("droid fabricated medium", fabricated_medium, "droid-peer: wrong launcher, tools or model/effort"),
            ("droid Luna profile missing", lambda d: drop(d, "droid-peer--gpt-6-luna--low"),
             "droid-peer: missing or wrong GPT-6 Luna low profile"),
            ("droid supported profile missing", lambda d: drop(d, "droid-peer--kimi-k3--high"),
             "droid-peer: missing or wrong supported model/effort profile"),
            ("droid profile wrong effort", lambda d: profile(d, "droid-peer--claude-sonnet-5-5--medium").__setitem__(
                "thinkingOptionId", "low"), "droid-peer: missing or wrong supported model/effort profile"),
            ("droid profile on plain provider", lambda d: profile(d, "droid-peer--gpt-6-luna--low").__setitem__(
                "provider", "factory-droid"), profiles_error),
            # Generic profile validation
            ("profile model not on seat", lambda d: d["daemon"]["agentProfiles"][0].__setitem__("model", "not-on-seat"),
             profiles_error),
            ("profile unknown thinking option", lambda d: d["daemon"]["agentProfiles"][0].__setitem__(
                "thinkingOptionId", "missing"), profiles_error),
            ("profile thinking option without options", lambda d: profile(d, "amp-peer--low").__setitem__(
                "thinkingOptionId", "low"), profiles_error),
            ("profile missing required thinking option", lambda d: profile(d, "droid-peer--gpt-6-luna--medium").pop(
                "thinkingOptionId"), profiles_error),
            ("profile on foreign seat", lambda d: d["daemon"]["agentProfiles"][0].__setitem__(
                "provider", "not-an-epistex-seat"), profiles_error),
            ("profile modeId type", lambda d: d["daemon"]["agentProfiles"][0].__setitem__("modeId", 12), profiles_error),
            ("profile empty modeId", lambda d: d["daemon"]["agentProfiles"][0].__setitem__("modeId", ""), profiles_error),
            ("profile featureValues type", lambda d: d["daemon"]["agentProfiles"][0].__setitem__("featureValues", []),
             profiles_error),
        ]
        for label, mutate, message in cases:
            with self.subTest(label):
                data = copy.deepcopy(self.data)
                mutate(data)
                result = self.check_config(data)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

    def test_check_rejects_kit_runtime_and_environment_violations(self):
        self.save()
        common = self.kit / "agents/contract/COMMON.md"
        lead = self.kit / "agents/LEAD.md"
        pi = self.kit / ".pi/settings.json"
        omp = self.kit / ".omp/config.yml"
        kiro = pathlib.Path(self.temporary.name) / ".kiro/agents"
        cases = [
            (common, "x" * 16000, "combined lead prompt exceeds 16 KiB"),
            (common, None, "COMMON.md"),
            (lead, lead.read_text() + "\nFollow `.agents/skills/ghost/SKILL.md`.\n",
             ".agents/skills/ghost/SKILL.md: referenced by a prompt or template but missing"),
            (pi, "{", ".pi/settings.json: need valid JSON"),
            (pi, '{"compaction":{"modelOverrides":{}}}', ".pi/settings.json: need valid JSON"),
            (pi, None, ".pi/settings.json: need valid JSON"),
            (omp, "compaction:\n  thresholdTokens: 200000\n", ".omp/config.yml: need thresholdTokens: 100000"),
            (omp, None, ".omp/config.yml: need thresholdTokens: 100000"),
            (kiro / "epistex_peer.json", '{"tools":["subagent"]}', "kiro-peer: install exact seat-owned runtime config"),
            (kiro / "epistex_lead.json", self.kit / "setup/kiro-lead.json", "kiro-lead: install exact seat-owned runtime config"),
        ]
        for path, content, message in cases:
            with self.subTest(path=path.name, message=message):
                original = path.read_bytes()
                path.unlink()
                if isinstance(content, pathlib.Path):
                    path.symlink_to(content)
                elif content is not None:
                    path.write_text(content)
                try:
                    result = self.run_check("--check")
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(message, result.stderr)
                    if path.parent == kiro:
                        self.assertEqual(result.stderr.count("install exact"), 1, "only the changed runtime fails")
                finally:
                    path.unlink(missing_ok=True)
                    path.write_bytes(original)

        self.env["CODEX_BIN"] = str(self.bin / "missing")
        self.assertIn("CODEX_BIN executable not found", self.run_check("--check").stderr)
        self.env["CODEX_BIN"] = str(self.codex)
        self.codex.chmod(0o644)
        self.assertIn("CODEX_BIN executable not found", self.run_check("--check").stderr)
        self.codex.chmod(0o755)
        self.assertEqual(self.run_check("--unknown").returncode, 2)
        self.assertEqual(self.run_check("--check", "--project").returncode, 2)
        self.config.unlink()
        self.assertNotEqual(self.run_check("--check").returncode, 0)
        self.assertFalse(self.config.exists())

    def test_disabled_or_absent_optional_seats(self):
        providers = self.data["agents"]["providers"]
        for name in ("amp-supervisor", "claude-supervisor", "codex-supervisor", "copilot-peer", "devin-peer", "agy-lead"):
            providers[name]["enabled"] = False
        result = self.check_config(self.data)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("daemon.agentProfiles", result.stderr, "disabled seats must not keep profiles")
        self.data["daemon"]["agentProfiles"] = [p for p in self.data["daemon"]["agentProfiles"]
                                                if providers[p["provider"]]["enabled"]]
        result = self.check_config(self.data)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("amp-supervisor", "devin-peer", "agy-lead"):
            with self.subTest(reenabled=name):
                data = copy.deepcopy(self.data)
                data["agents"]["providers"][name]["enabled"] = True
                del data["agents"]["providers"][name]["command"]
                result = self.check_config(data)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(name + ": wrong launcher", result.stderr)

        with self.subTest("claude-peer compaction is always required"):
            data = copy.deepcopy(self.data)
            for name in ("claude-lead", "claude-peer"):
                data["agents"]["providers"][name].update(enabled=False, env={})
            result = self.check_config(data)
            self.assertIn("claude-peer: need env", result.stderr)
            self.assertNotIn("claude-lead: need env", result.stderr)

        with self.subTest("absent optional seats"):
            for name in ("agy-lead", "kiro-lead", "droid-peer"):
                providers.pop(name)
            self.data["daemon"]["agentProfiles"] = [p for p in self.data["daemon"]["agentProfiles"]
                                                    if p["provider"] in providers]
            (pathlib.Path(self.temporary.name) / ".kiro/agents/epistex_lead.json").unlink()
            result = self.check_config(self.data)
            self.assertEqual(result.returncode, 0, result.stderr)

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

    def test_project_installs_and_checks_every_kit_skill(self):
        self.save()
        kit_skills = sorted(p.parent.name for p in self.kit.glob(".agents/skills/*/SKILL.md"))
        self.assertIn("handling-reopen", kit_skills)
        project = pathlib.Path(self.temporary.name) / "project"
        project.mkdir()
        subprocess.run(["git", "init", "-q", str(project)], check=True)
        exclude = project / ".git/info/exclude"
        shutil.copyfile(ROOT / "examples/WORKSPACE_PROTOCOL.md", project / "WORKSPACE_PROTOCOL.md")

        result = self.run_check("--check", "--project", str(project))
        self.assertNotEqual(result.returncode, 0)
        for name in kit_skills:
            self.assertIn(f"{project}: missing skill {name}", result.stderr)
        self.assertIn("WORKSPACE_PROTOCOL.md names .agents/skills/handling-reopen/SKILL.md but it is not installed",
                      result.stderr)
        self.assertFalse((project / ".agents").exists(), "--check must not install")
        self.assertNotIn("/.agents/skills/", exclude.read_text() if exclude.exists() else "")

        result = self.run_check("--project", str(project))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"{len(kit_skills)} kit skills present in {project}/.agents/skills (ignored in Git)", result.stdout)
        installed = sorted(p.parent.name for p in project.glob(".agents/skills/*/SKILL.md"))
        self.assertEqual(installed, kit_skills)
        for name in kit_skills:
            self.assertEqual((project / ".agents/skills" / name / "SKILL.md").read_bytes(),
                             (self.kit / ".agents/skills" / name / "SKILL.md").read_bytes())
        self.assertEqual(exclude.read_text().count("/.agents/skills/\n"), 1)
        status = subprocess.run(["git", "-C", str(project), "status", "--porcelain"], text=True,
                                capture_output=True, check=True).stdout
        self.assertNotIn(".agents", status, "installed skills must not show up as untracked files")
        result = self.run_check("--check", "--project", str(project))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.run_check("--project", str(project)).returncode, 0)
        self.assertEqual(exclude.read_text().count("/.agents/skills/\n"), 1, "exclude line is added once")

        exclude.unlink()
        result = self.run_check("--check", "--project", str(project))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".agents/skills is neither tracked nor ignored", result.stderr)
        subprocess.run(["git", "-C", str(project), "add", ".agents/skills"], check=True)
        result = self.run_check("--project", str(project))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("(tracked in Git)", result.stdout)
        self.assertFalse(exclude.exists(), "tracked skills are not added to the exclude file")
        subprocess.run(["git", "-C", str(project), "rm", "-rq", "--cached", ".agents/skills"], check=True)
        self.assertEqual(self.run_check("--project", str(project)).returncode, 0)

        stale = project / ".agents/skills/handling-reopen/SKILL.md"
        stale.write_text(stale.read_text() + "\nlocal edit\n")
        result = self.run_check("--check", "--project", str(project))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"{project}: skill handling-reopen differs from the kit", result.stderr)
        self.assertEqual(self.run_check("--project", str(project)).returncode, 0)
        self.assertNotIn("local edit", stale.read_text())

        (self.kit / ".agents/skills/new-skill").mkdir()
        (self.kit / ".agents/skills/new-skill/SKILL.md").write_text("---\nname: new-skill\n---\n")
        result = self.run_check("--check", "--project", str(project))
        self.assertIn(f"{project}: missing skill new-skill", result.stderr)
        self.assertEqual(self.run_check("--project", str(project)).returncode, 0)
        self.assertTrue((project / ".agents/skills/new-skill/SKILL.md").is_file())

        protocol = project / "WORKSPACE_PROTOCOL.md"
        protocol.write_text(protocol.read_text() + "\n- also `.agents/skills/ghost/SKILL.md`\n")
        result = self.run_check("--check", "--project", str(project))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("WORKSPACE_PROTOCOL.md names .agents/skills/ghost/SKILL.md but it is not installed", result.stderr)

        result = self.run_check("--project", str(project / "missing"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("project directory not found", result.stderr)

        plain = pathlib.Path(self.temporary.name) / "plain"
        plain.mkdir()
        result = self.run_check("--project", str(plain))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("(untracked in Git)", result.stdout)
        self.assertEqual(sorted(p.parent.name for p in plain.glob(".agents/skills/*/SKILL.md")),
                         sorted(p.parent.name for p in self.kit.glob(".agents/skills/*/SKILL.md")))

        linked = pathlib.Path(self.temporary.name) / "linked"
        (linked / ".agents").mkdir(parents=True)
        (linked / ".agents/skills").symlink_to(self.kit / ".agents/skills")
        result = self.run_check("--project", str(linked))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to use symlinked skill path", result.stderr)


if __name__ == "__main__":
    unittest.main()
