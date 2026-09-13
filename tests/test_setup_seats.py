import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "setup" / "setup-seats.sh"


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
        self.assertIn("chưa kiểm auth, daemon hoặc launch", result.stdout)

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

    def test_disabled_injection_fails(self):
        self.data["daemon"]["mcp"]["enabled"] = False
        self.save()
        self.assertNotEqual(self.run_check("--check").returncode, 0)

    def test_unknown_argument_fails(self):
        self.assertEqual(self.run_check("--unknown").returncode, 2)
