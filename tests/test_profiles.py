import importlib.machinery
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "setup" / "install-profiles.py"
proxy = importlib.machinery.SourceFileLoader("role_agent", str(ROOT / "setup" / "role-agent")).load_module()


class ProfilesTest(unittest.TestCase):
    def test_acp_primes_each_session_once_and_preserves_other_messages(self):
        seen = set()
        prompt = {"jsonrpc": "2.0", "id": 7, "method": "session/prompt",
                  "params": {"sessionId": "a", "prompt": [{"type": "image", "data": "opaque"},
                                                          {"type": "text", "text": "actual task"}]}}
        raw = (json.dumps(prompt) + "\n").encode()
        primed = json.loads(proxy.prime(raw, "watcher", seen))
        self.assertIn("# Watcher", primed["params"]["prompt"][0]["text"])
        self.assertEqual(primed["params"]["prompt"][1:], prompt["params"]["prompt"])
        self.assertEqual(proxy.prime(raw, "watcher", seen), raw)
        prompt["params"]["sessionId"] = "b"
        self.assertIn("# Watcher", json.loads(proxy.prime((json.dumps(prompt) + "\n").encode(), "watcher", seen))["params"]["prompt"][0]["text"])
        self.assertEqual(proxy.prime(b'{"method":"session/update"}\n', "watcher", seen), b'{"method":"session/update"}\n')

    def test_install_preserves_other_config_and_checks_each_role_agent(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "config.json"
            original = {"plugins": {}, "features": {"keep": True}, "agents": {"providers": {"mine": {"extends": "acp"}}},
                        "daemon": {"mcp": {"injectIntoAgents": True}, "agentProfiles": [{"id": "mine", "provider": "mine"}]}}
            path.write_text(json.dumps(original))
            env = {**os.environ, "PASEO_CONFIG": str(path)}
            def run(*args):
                return subprocess.run([sys.executable, str(SCRIPT), *args], env=env, text=True, capture_output=True)
            self.assertNotEqual(run("--check").returncode, 0)
            self.assertEqual(run().returncode, 0)
            installed = json.loads(path.read_text())
            self.assertEqual(installed["features"], original["features"])
            self.assertEqual(installed["agents"]["providers"]["mine"], original["agents"]["providers"]["mine"])
            self.assertEqual(installed["daemon"]["agentProfiles"][0], original["daemon"]["agentProfiles"][0])
            providers = {k: v for k, v in installed["agents"]["providers"].items() if k.startswith("epx-")}
            profiles = [p for p in installed["daemon"]["agentProfiles"] if p["id"].startswith("epx-")]
            self.assertEqual(len(providers), 35)
            self.assertEqual(len(profiles), 35)
            self.assertEqual({p["provider"] for p in profiles}, providers.keys())
            self.assertEqual(providers["epx-reviewer-codex"]["command"][-1], "reviewer")
            self.assertFalse(providers["epx-watcher-amp"]["paseoTools"]["enabled"])
            self.assertTrue(providers["epx-supervisor-amp"]["paseoTools"]["enabled"])
            self.assertEqual(run("--check").returncode, 0)
            before = path.read_bytes()
            self.assertEqual(run().returncode, 0)
            self.assertEqual(path.read_bytes(), before)
            installed["agents"]["providers"]["epx-watcher-amp"]["command"][-1] = "lead"
            path.write_text(json.dumps(installed))
            self.assertNotEqual(run("--check").returncode, 0)


if __name__ == "__main__":
    unittest.main()
