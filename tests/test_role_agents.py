import importlib.machinery
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
proxy = importlib.machinery.SourceFileLoader("role_agent", str(ROOT / "setup" / "role-agent")).load_module()


class ProfilesTest(unittest.TestCase):
    def test_devin_copilot_cursor_acp_launchers_forward_args_and_inject_role(self):
        with tempfile.TemporaryDirectory() as folder:
            for backend, binary, acp_arg, role in (
                ("devin", "devin", "acp", "lead"),
                ("devin", "devin", "acp", "peer"),
                ("copilot", "copilot", "--acp", "peer"),
                ("cursor", "cursor-agent", "acp", "peer"),
            ):
                executable = pathlib.Path(folder) / binary
                executable.write_text(f"#!{sys.executable}\nimport json, sys\n"
                                      "print(json.dumps(sys.argv[1:]), flush=True)\n"
                                      "for line in sys.stdin:\n"
                                      "    print(line, end='', flush=True)\n"
                                      "sys.exit(7)\n")
                executable.chmod(0o755)
                with self.subTest(backend=backend, role=role):
                    prompt = {"jsonrpc": "2.0", "id": 9, "method": "session/prompt",
                              "params": {"sessionId": "seat", "prompt": [{"type": "text", "text": "task"}]}}
                    raw = json.dumps(prompt) + "\n"
                    result = subprocess.run(
                        [sys.executable, str(ROOT / "setup" / "role-agent"), role, backend, "--extra"],
                        input=raw * 2, text=True, capture_output=True,
                        env={**os.environ, "PATH": folder}, timeout=10)
                    self.assertEqual(result.returncode, 7, result.stderr)
                    args, first, second = map(json.loads, result.stdout.splitlines())
                    self.assertEqual(args, [acp_arg, "--extra"])
                    expected = json.loads(raw)
                    instructions = (ROOT / "agents" / f"{role.upper()}.md").read_text()
                    expected["params"]["prompt"].insert(0, {
                        "type": "text", "text": "Role instructions for this session:\n" + instructions})
                    self.assertEqual(first, expected)
                    self.assertEqual(second, prompt)

    def test_pi_and_omp_native_launchers_append_peer_prompt_and_preserve_rpc(self):
        with tempfile.TemporaryDirectory() as folder:
            for agent in ("pi", "omp"):
                executable = pathlib.Path(folder) / agent
                executable.write_text(f"#!{sys.executable}\nimport json, sys\n"
                                      "print(json.dumps(sys.argv[1:]))\n"
                                      "sys.stdout.write(sys.stdin.read())\n"
                                      "sys.exit(7)\n")
                executable.chmod(0o755)
                with self.subTest(agent=agent):
                    result = subprocess.run(
                        [sys.executable, str(ROOT / "setup" / "role-agent"), "peer", agent,
                         "--mode", "rpc", "--model", "provider/model"],
                        input='{"type":"prompt","message":"unchanged"}\n',
                        text=True, capture_output=True, env={**os.environ, "PATH": folder}, timeout=10)
                    self.assertEqual(result.returncode, 7, result.stderr)
                    args, message = result.stdout.splitlines()
                    self.assertEqual(json.loads(args), ["--append-system-prompt", str(ROOT / "agents" / "PEER.md"),
                                                       "--mode", "rpc", "--model", "provider/model"])
                    self.assertEqual(message, '{"type":"prompt","message":"unchanged"}')

    def test_claude_initialize_appends_role_without_replacing_sdk_context(self):
        for existing in (None, "", "Paseo session guidance"):
            with self.subTest(existing=existing):
                message = {"type": "control_request", "request_id": "initialize-7",
                           "request": {"subtype": "initialize", "systemPrompt": ["custom base"],
                                       "appendSystemPrompt": existing, "sdkMcpServers": ["paseo"]}}
                expected = json.loads(json.dumps(message))
                expected["request"]["appendSystemPrompt"] = (
                    "Paseo session guidance\n\n# Peer — test role" if existing
                    else "# Peer — test role")
                result = proxy.prime_claude((json.dumps(message) + "\n").encode(), "# Peer — test role")
                self.assertEqual(json.loads(result), expected)
        for raw in (b'not json\n', b'[]\n', b'{"type":"user","message":{"content":"task"}}\n',
                    b'{"type":"control_request","request":{"subtype":"interrupt"}}\n'):
            self.assertEqual(proxy.prime_claude(raw, "role"), raw)

    def test_claude_stream_launcher_injects_both_roles_and_forwards_messages(self):
        with tempfile.TemporaryDirectory() as folder:
            executable = pathlib.Path(folder) / "claude"
            executable.write_text(f"#!{sys.executable}\nimport sys\n"
                                  "for line in sys.stdin.buffer:\n"
                                  "    sys.stdout.buffer.write(line)\n"
                                  "    sys.stdout.buffer.flush()\n")
            executable.chmod(0o755)
            env = {**os.environ, "PATH": folder}
            initialize = {"type": "control_request", "request_id": "init",
                          "request": {"subtype": "initialize", "appendSystemPrompt": "keep me"}}
            user = {"type": "user", "message": {"role": "user", "content": "unchanged task"}}
            for role in ("lead", "peer"):
                with self.subTest(role=role):
                    result = subprocess.run(
                        [sys.executable, str(ROOT / "setup" / "role-agent"), role, "claude",
                         "--input-format", "stream-json", "--output-format", "stream-json"],
                        input=json.dumps(initialize) + "\n" + json.dumps(user) + "\n",
                        text=True, capture_output=True, env=env, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    first, second = map(json.loads, result.stdout.splitlines())
                    instructions = (ROOT / "agents" / f"{role.upper()}.md").read_text()
                    self.assertEqual(first["request"]["appendSystemPrompt"], "keep me\n\n" + instructions)
                    self.assertEqual(first["request_id"], "init")
                    self.assertEqual(second, user)

    def test_acp_primes_each_session_once_and_preserves_other_messages(self):
        seen = set()
        prompt = {"jsonrpc": "2.0", "id": 7, "method": "session/prompt",
                  "params": {"sessionId": "a", "prompt": [{"type": "image", "data": "opaque"},
                                                          {"type": "text", "text": "actual task"}]}}
        raw = (json.dumps(prompt) + "\n").encode()
        primed = json.loads(proxy.prime(raw, "peer", seen))
        self.assertIn("# Peer", primed["params"]["prompt"][0]["text"])
        self.assertEqual(primed["params"]["prompt"][1:], prompt["params"]["prompt"])
        self.assertEqual(proxy.prime(raw, "peer", seen), raw)
        prompt["params"]["sessionId"] = "b"
        self.assertIn("# Peer", json.loads(proxy.prime((json.dumps(prompt) + "\n").encode(), "peer", seen))["params"]["prompt"][0]["text"])
        self.assertEqual(proxy.prime(b'{"method":"session/update"}\n', "peer", seen), b'{"method":"session/update"}\n')

if __name__ == "__main__":
    unittest.main()
