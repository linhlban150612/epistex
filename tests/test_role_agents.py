import importlib.machinery
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import queue
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
proxy = importlib.machinery.SourceFileLoader("role_agent", str(ROOT / "setup" / "role-agent")).load_module()
claude_sdk = importlib.machinery.SourceFileLoader("claude_sdk", str(ROOT / "setup" / "claude-sdk")).load_module()


class ProfilesTest(unittest.TestCase):
    def test_devin_copilot_acp_launchers_forward_args_and_inject_role(self):
        with tempfile.TemporaryDirectory() as folder:
            for backend, binary, acp_arg, role in (
                ("devin", "devin", "acp", "peer"),
                ("copilot", "copilot", "--acp", "peer"),
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
                    for launcher in (["role-agent", role, backend], [f"{backend}-acp", role]):
                        result = subprocess.run(
                            [sys.executable, str(ROOT / "setup" / launcher[0]), *launcher[1:], "--extra"],
                            input=raw * 2, text=True, capture_output=True,
                            env={**os.environ, "PATH": folder}, timeout=10)
                        self.assertEqual(result.returncode, 7, result.stderr)
                        args, first, second = map(json.loads, result.stdout.splitlines())
                        self.assertEqual(args, [acp_arg, "--extra"])
                        expected = json.loads(raw)
                        instructions = ((ROOT / "agents/contract/COMMON.md").read_text().rstrip() + "\n\n"
                                        + (ROOT / "agents" / f"{role.upper()}.md").read_text())
                        expected["params"]["prompt"].insert(0, {
                            "type": "text", "text": "Role instructions for this session:\n" + instructions})
                        self.assertEqual(first, expected)
                        self.assertEqual(second, prompt)

    def test_cursor_confirms_effort_and_fast_off_before_prompt_without_changing_user_config(self):
        with tempfile.TemporaryDirectory() as folder:
            home = pathlib.Path(folder)
            config = home / ".cursor"
            config.mkdir()
            original = '{"model":"user selection"}'
            (config / "cli-config.json").write_text(original)
            executable = home / "cursor-agent"
            executable.write_text(f"#!{sys.executable}\n" + '''
import json, os, pathlib, sys
state = {"model":"grok-4.7", "fast":"true", "reasoning_effort":"high", "context":"500k"}
negotiated = False
for line in sys.stdin:
    r = json.loads(line); p = r.get("params", {}); method = r.get("method")
    if method == "initialize":
        negotiated = p["clientCapabilities"].get("_meta", {}).get("parameterizedModelPicker") is True
        result = {"protocolVersion":1}
    elif method in ("session/new", "session/load"):
        result = {"sessionId":"seat", "models":{"currentModelId":"unsafe-default"}}
    elif method == "session/set_config_option":
        if not negotiated:
            print(json.dumps({"jsonrpc":"2.0", "id":r["id"], "error":{"code":-32602,"message":"not negotiated"}}), flush=True)
            continue
        state[p["configId"]] = p["value"]
        if os.environ.get("FAULT"):
            state[os.environ["FAULT"]] = "true" if os.environ["FAULT"] == "fast" else "high"
        pathlib.Path(os.environ["CURSOR_CONFIG_DIR"], "cli-config.json").write_text(json.dumps(state))
        result = {"configOptions":[{"id":k,"currentValue":v} for k,v in state.items()]}
    elif method == "session/prompt":
        result = {"state":dict(state), "prompt":p["prompt"]}
    else:
        result = {}
    print(json.dumps({"jsonrpc":"2.0", "id":r["id"], "result":result}), flush=True)
''')
            executable.chmod(0o755)
            for fault in ("", "fast", "reasoning_effort"):
                with self.subTest(fault=fault):
                    requests = [
                        ("initialize", {"protocolVersion": 1, "clientCapabilities": {}}),
                        ("session/new", {"cwd": folder, "mcpServers": []}),
                        ("session/prompt", {"sessionId": "seat", "prompt": [{"type": "text", "text": "low task"}]}),
                        ("session/set_model", {"sessionId": "seat", "modelId": "grok-4.7-medium"}),
                        ("session/prompt", {"sessionId": "seat", "prompt": [{"type": "text", "text": "task"}]}),
                        ("session/set_model", {"sessionId": "seat", "modelId": "composer-2.5[fast=true]"}),
                        ("session/prompt", {"sessionId": "seat", "prompt": []}),
                    ]
                    result = subprocess.run(
                        [sys.executable, str(ROOT / "setup/role-agent"), "peer", "cursor"],
                        input="".join(json.dumps({"jsonrpc": "2.0", "id": i, "method": m, "params": p}) + "\n"
                                      for i, (m, p) in enumerate(requests)),
                        text=True, capture_output=True, timeout=15,
                        env={**os.environ, "PATH": folder, "HOME": folder,
                             "CURSOR_CONFIG_DIR": str(config), "FAULT": fault})
                    self.assertEqual(result.returncode, 0, result.stderr)
                    replies = {r["id"]: r for r in map(json.loads, result.stdout.splitlines()) if "id" in r}
                    self.assertEqual((config / "cli-config.json").read_text(), original)
                    if fault:
                        for i in (1, 2, 3, 4):
                            self.assertIn("error", replies[i])
                    else:
                        self.assertEqual(replies[1]["result"]["models"]["currentModelId"], "grok-4.7-low")
                        self.assertEqual(replies[2]["result"]["state"], {
                            "model": "grok-4.7", "reasoning_effort": "low", "fast": "false", "context": "256k"})
                        self.assertEqual(replies[4]["result"]["state"], {
                            "model": "grok-4.7", "reasoning_effort": "medium", "fast": "false", "context": "256k"})
                        self.assertIn("# Peer", replies[2]["result"]["prompt"][0]["text"])
                        self.assertEqual(replies[4]["result"]["prompt"], [{"type": "text", "text": "task"}])
                    for i in (5, 6):
                        self.assertIn("error", replies[i])

    def test_cursor_native_drift_invalidates_until_explicit_reselection(self):
        for drift in ("model", "fast", "reasoning_effort", "context"):
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as folder:
                home = pathlib.Path(folder)
                config = home / ".cursor"
                config.mkdir()
                executable = home / "cursor-agent"
                executable.write_text(f"#!{sys.executable}\n" + '''
import json, os, sys
state = {"model":"grok-4.7", "fast":"false", "context":"256k", "reasoning_effort":"low"}
drift = os.environ["DRIFT"]
for line in sys.stdin:
    r = json.loads(line); p = r.get("params", {}); method = r.get("method")
    after_reply = None
    if method in ("session/new", "session/load"):
        result = {"sessionId":"seat"}
    elif method == "session/set_config_option":
        state[p["configId"]] = p["value"]
        result = {"configOptions":[{"id":k,"currentValue":v} for k,v in state.items()]}
        if p["configId"] == "context":
            # A selection-time update must not defeat the complete later confirmation.
            print(json.dumps({"jsonrpc":"2.0", "method":"session/update", "params":{"sessionId":"seat",
                "update":{"sessionUpdate":"config_option_update", "configOptions":[{"id":"fast","currentValue":"true"}]}}}), flush=True)
    elif method == "session/prompt":
        result = {"accepted":True}
        if any(item.get("text") == "first" for item in p["prompt"]):
            if drift == "model":
                after_reply = {"sessionUpdate":"current_model_update", "currentModelId":"composer-2.5"}
            else:
                value = {"fast":"true", "reasoning_effort":"high", "context":"500k"}[drift]
                after_reply = {"sessionUpdate":"config_option_update", "configOptions":[{"id":drift,"currentValue":value}]}
    else:
        result = {}
    if "id" in r:
        print(json.dumps({"jsonrpc":"2.0", "id":r["id"], "result":result}), flush=True)
    if after_reply:
        print(json.dumps({"jsonrpc":"2.0", "method":"session/update", "params":{"sessionId":"seat", "update":after_reply}}), flush=True)
        print(json.dumps({"jsonrpc":"2.0", "method":"session/update", "params":{"sessionId":"seat",
            "update":{"sessionUpdate":"agent_message_chunk", "content":"drift processed"}}}), flush=True)
''')
                executable.chmod(0o755)
                proc = subprocess.Popen(
                    [sys.executable, str(ROOT / "setup/role-agent"), "peer", "cursor"],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, env={**os.environ, "PATH": folder + os.pathsep + os.defpath, "HOME": folder,
                                    "CURSOR_CONFIG_DIR": str(config), "DRIFT": drift})
                output = queue.Queue()
                threading.Thread(target=lambda: [output.put(line) for line in proc.stdout], daemon=True).start()
                def send(ident, method, params):
                    proc.stdin.write(json.dumps({"jsonrpc":"2.0", "id":ident,
                                                 "method":method, "params":params}) + "\n")
                    proc.stdin.flush()
                def read():
                    try:
                        return json.loads(output.get(timeout=5))
                    except queue.Empty:
                        self.fail("Cursor proxy timed out")
                def response(ident):
                    while True:
                        message = read()
                        if message.get("id") == ident:
                            return message
                send(1, "initialize", {})
                self.assertEqual(read()["id"], 1)
                send(2, "session/new", {})
                self.assertIn("result", response(2))
                # Selection-time event is reconciled by the later complete confirmation.
                send(3, "session/prompt", {"sessionId":"seat", "prompt":[{"type":"text", "text":"first"}]})
                self.assertEqual(read()["id"], 3)
                event = read()
                self.assertEqual(event["method"], "session/update")
                self.assertEqual(event["params"]["update"]["content"], "drift processed")
                send(4, "session/prompt", {"sessionId":"seat", "prompt":[{"type":"text", "text":"blocked"}]})
                self.assertIn("error", read())
                send(5, "session/set_model", {"sessionId":"seat", "modelId":"grok-4.7-medium"})
                self.assertIn("result", response(5))
                # Reselection emits the same harmless in-flight update, then confirms all parameters.
                send(6, "session/prompt", {"sessionId":"seat", "prompt":[{"type":"text", "text":"after reselection"}]})
                self.assertEqual(read()["id"], 6)
                proc.stdin.close()
                proc.wait(timeout=10)
                self.assertEqual(proc.returncode, 0, proc.stderr.read())
                proc.stdout.close()
                proc.stderr.close()

    def test_cursor_final_confirmation_then_native_drift_blocks_first_prompt(self):
        with tempfile.TemporaryDirectory() as folder:
            home = pathlib.Path(folder)
            config = home / ".cursor"
            config.mkdir()
            executable = home / "cursor-agent"
            executable.write_text(f"#!{sys.executable}\n" + '''
import json, sys
state = {"model":"grok-4.7", "fast":"false", "context":"256k", "reasoning_effort":"low"}
drift_sent = False
for line in sys.stdin:
    r = json.loads(line); p = r.get("params", {}); method = r.get("method")
    if method in ("session/new", "session/load"):
        result = {"sessionId":"seat"}
    elif method == "session/set_config_option":
        state[p["configId"]] = p["value"]
        result = {"configOptions":[{"id":k,"currentValue":v} for k,v in state.items()]}
    else:
        result = {"accepted":True}
    if "id" in r:
        print(json.dumps({"jsonrpc":"2.0", "id":r["id"], "result":result}), flush=True)
    if method == "session/set_config_option" and p["configId"] == "reasoning_effort" and not drift_sent:
        drift_sent = True
        # Adjacent stdout lines: contradiction follows the complete final confirmation.
        print(json.dumps({"jsonrpc":"2.0", "method":"session/update", "params":{"sessionId":"seat",
            "update":{"sessionUpdate":"config_option_update", "configOptions":[
                {"id":"fast", "currentValue":"true"}]}}}), flush=True)
        print(json.dumps({"jsonrpc":"2.0", "method":"session/update", "params":{"sessionId":"seat",
            "update":{"sessionUpdate":"agent_message_chunk", "content":"drift processed"}}}), flush=True)
''')
            executable.chmod(0o755)
            proc = subprocess.Popen(
                [sys.executable, str(ROOT / "setup/role-agent"), "peer", "cursor"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                env={**os.environ, "PATH": folder + os.pathsep + os.defpath, "HOME": folder,
                     "CURSOR_CONFIG_DIR": str(config)})
            output = queue.Queue()
            threading.Thread(target=lambda: [output.put(line) for line in proc.stdout], daemon=True).start()
            def send(ident, method, params):
                proc.stdin.write(json.dumps({"jsonrpc":"2.0", "id":ident, "method":method, "params":params}) + "\n")
                proc.stdin.flush()
            def read():
                try:
                    return json.loads(output.get(timeout=5))
                except queue.Empty:
                    self.fail("Cursor proxy timed out")
            def response(ident):
                while True:
                    message = read()
                    if message.get("id") == ident:
                        return message
            send(1, "initialize", {})
            self.assertEqual(read()["id"], 1)
            send(2, "session/new", {})
            created = None
            barrier_seen = False
            while created is None or not barrier_seen:
                message = read()
                if message.get("id") == 2:
                    created = message
                elif message.get("params", {}).get("update", {}).get("content") == "drift processed":
                    barrier_seen = True
            self.assertIn("result", created)
            send(3, "session/prompt", {"sessionId":"seat", "prompt":[{"type":"text", "text":"first"}]})
            blocked = response(3)
            self.assertIn("error", blocked)
            send(4, "session/set_model", {"sessionId":"seat", "modelId":"grok-4.7-medium"})
            self.assertIn("result", response(4))
            send(5, "session/prompt", {"sessionId":"seat", "prompt":[{"type":"text", "text":"reselected"}]})
            self.assertEqual(response(5)["result"]["accepted"], True)
            proc.stdin.close()
            proc.wait(timeout=10)
            self.assertEqual(proc.returncode, 0, proc.stderr.read())
            proc.stdout.close()
            proc.stderr.close()

    def test_devin_and_copilot_launchers_reject_non_peer_roles(self):
        with tempfile.TemporaryDirectory() as folder:
            for backend in ("devin", "copilot"):
                for role in ("lead", "supervisor"):
                    for launcher in (["role-agent", role, backend], [f"{backend}-acp", role]):
                        with self.subTest(launcher=launcher):
                            result = subprocess.run(
                                [sys.executable, str(ROOT / "setup" / launcher[0]), *launcher[1:]],
                                input="", text=True, capture_output=True,
                                env={**os.environ, "PATH": folder}, timeout=10)
                            self.assertNotEqual(result.returncode, 0)
                            self.assertIn(f"usage: {backend}-acp peer", result.stderr)

    def test_droid_acp_launcher_uses_installed_binary_and_injects_peer_role(self):
        with tempfile.TemporaryDirectory() as folder:
            executable = pathlib.Path(folder) / "droid"
            executable.write_text(f"#!{sys.executable}\nimport json, sys\n"
                                  "print(json.dumps(sys.argv[1:]), flush=True)\n"
                                  "for line in sys.stdin:\n"
                                  "    print(line, end='', flush=True)\n")
            executable.chmod(0o755)
            prompt = {"jsonrpc": "2.0", "id": 3, "method": "session/prompt",
                      "params": {"sessionId": "droid", "prompt": [{"type": "text", "text": "task"}]}}
            result = subprocess.run(
                [sys.executable, str(ROOT / "setup" / "role-agent"), "peer", "droid"],
                input=json.dumps(prompt) + "\n", text=True, capture_output=True,
                env={**os.environ, "PATH": folder}, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            args, first = map(json.loads, result.stdout.splitlines())
            self.assertEqual(args, ["exec", "--output-format", "acp"])
            self.assertTrue(first["params"]["prompt"][0]["text"].startswith("Role instructions for this session:\n"))
            self.assertEqual(first["params"]["prompt"][1:], prompt["params"]["prompt"])

    def test_kiro_launcher_accepts_only_scoped_lead_and_peer_without_flags(self):
        with tempfile.TemporaryDirectory() as folder:
            for args in (("lead", "kiro", "--extra"), ("peer", "kiro", "--extra")):
                with self.subTest(args=args):
                    result = subprocess.run(
                        [sys.executable, str(ROOT / "setup" / "role-agent"), *args],
                        input="", text=True, capture_output=True,
                        env={**os.environ, "PATH": folder, "HOME": folder}, timeout=10)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("Kiro supports only the scoped Supervisor, Lead and Peer seats", result.stderr)

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
                    parsed_args = json.loads(args)
                    self.assertEqual(parsed_args[0], "--append-system-prompt")
                    self.assertIn("# Common contract", parsed_args[1])
                    self.assertIn("# Peer — independent co-worker", parsed_args[1])
                    self.assertEqual(parsed_args[2:], ["--mode", "rpc", "--model", "provider/model"])
                    self.assertEqual(message, '{"type":"prompt","message":"unchanged"}')

    def test_omp_combines_last_wins_append_text_and_file_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            home = pathlib.Path(folder)
            append_file = home / "caller-system.md"
            append_file.write_text("CALLER FILE CONTENT")
            executable = home / "omp"
            executable.write_text(f"#!{sys.executable}\n" + '''
import json, pathlib, sys
args = sys.argv[1:]
append = None
i = 0
while i < len(args):
    if args[i] == "--append-system-prompt" and i + 1 < len(args):
        append = args[i + 1]; i += 2
    elif args[i].startswith("--append-system-prompt="):
        append = args[i].split("=", 1)[1]; i += 1
    else:
        i += 1
if append and "\\n" not in append:
    try: append = pathlib.Path(append).read_text()
    except (OSError, UnicodeError): pass
print(json.dumps({"effective":append, "args":args}))
''')
            executable.chmod(0o755)
            result = subprocess.run(
                [sys.executable, str(ROOT / "setup/role-agent"), "peer", "omp",
                 "--append-system-prompt", "CALLER INLINE TEXT",
                 "--append-system-prompt=" + str(append_file), "--mode", "rpc"],
                text=True, capture_output=True, env={**os.environ, "PATH": folder}, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            effective = json.loads(result.stdout)["effective"]
            self.assertIn("# Peer — independent co-worker", effective)
            self.assertIn("CALLER INLINE TEXT", effective)
            self.assertIn("CALLER FILE CONTENT", effective)

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
                result = claude_sdk.prime_claude((json.dumps(message) + "\n").encode(), "# Peer — test role")
                self.assertEqual(json.loads(result), expected)
        for raw in (b'not json\n', b'[]\n', b'{"type":"user","message":{"content":"task"}}\n',
                    b'{"type":"control_request","request":{"subtype":"interrupt"}}\n'):
            self.assertEqual(claude_sdk.prime_claude(raw, "role"), raw)

    def test_claude_stream_launcher_injects_both_roles_and_forwards_messages(self):
        with tempfile.TemporaryDirectory() as folder:
            executable = pathlib.Path(folder) / "claude"
            executable.write_text(f"#!{sys.executable}\nimport json, sys\n"
                                  "print(json.dumps(sys.argv[1:]), flush=True)\n"
                                  "for line in sys.stdin.buffer:\n"
                                  "    sys.stdout.buffer.write(line)\n"
                                  "    sys.stdout.buffer.flush()\n")
            executable.chmod(0o755)
            env = {**os.environ, "PATH": folder}
            initialize = {"type": "control_request", "request_id": "init",
                          "request": {"subtype": "initialize", "appendSystemPrompt": "keep me"}}
            user = {"type": "user", "message": {"role": "user", "content": "unchanged task"}}
            for role in ("supervisor", "lead", "peer"):
                with self.subTest(role=role):
                    result = subprocess.run(
                        [sys.executable, str(ROOT / "setup" / "role-agent"), role, "claude",
                         "--input-format", "stream-json", "--output-format", "stream-json"],
                        input=json.dumps(initialize) + "\n" + json.dumps(user) + "\n",
                        text=True, capture_output=True, env=env, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    args, first, second = map(json.loads, result.stdout.splitlines())
                    self.assertEqual(args, ["--disallowed-tools", ",".join(claude_sdk.DISALLOWED),
                                            "--input-format", "stream-json", "--output-format", "stream-json"])
                    instructions = ((ROOT / "agents/contract/COMMON.md").read_text().rstrip() + "\n\n"
                                    + (ROOT / "agents" / f"{role.upper()}.md").read_text())
                    self.assertEqual(first["request"]["appendSystemPrompt"], "keep me\n\n" + instructions)
                    self.assertEqual(first["request_id"], "init")
                    self.assertEqual(second, user)

    def test_launchers_load_common_from_kit_and_reject_missing_or_oversized_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            kit = root / "kit"
            shutil.copytree(ROOT / "setup", kit / "setup")
            (kit / "agents/contract").mkdir(parents=True)
            common = kit / "agents/contract/COMMON.md"
            common.write_text("COMMON SENTINEL\n", encoding="utf-8")
            for role in ("supervisor", "lead", "peer"):
                (kit / f"agents/{role.upper()}.md").write_text(f"ROLE {role}\n", encoding="utf-8")
            (root / "agents/contract").mkdir(parents=True)
            (root / "agents/contract/COMMON.md").write_text("WRONG CWD CONTRACT")
            binary = root / "pi"
            binary.write_text(f"#!{sys.executable}\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n")
            binary.chmod(0o755)
            env = {**os.environ, "PATH": str(root), "PYTHONDONTWRITEBYTECODE": "1"}
            for role in ("supervisor", "lead", "peer"):
                result = subprocess.run([sys.executable, str(kit / "setup/role-agent"), role, "pi"],
                                        cwd=root, env=env, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout),
                                 ["--append-system-prompt", f"COMMON SENTINEL\n\nROLE {role}\n"])
            # Byte boundary: multi-byte text must not be counted as characters.
            common.write_text("é" * 8186, encoding="utf-8")
            command = [sys.executable, str(kit / "setup/role-agent"), "peer", "pi"]
            result = subprocess.run(command, cwd=root, env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)  # 16372 + 2 + 10 = 16384
            common.write_text("é" * 8187, encoding="utf-8")
            result = subprocess.run(command, cwd=root, env=env, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exceeds 16 KiB", result.stderr)
            self.assertEqual(result.stdout, "")
            common.unlink()
            for launcher in (["role-agent", "peer", "pi"], ["amp-acp", "peer"],
                             ["claude-sdk", "lead"], ["kiro-acp", "supervisor"],
                             ["cursor-acp", "peer"], ["codex-room", "peer"]):
                result = subprocess.run([sys.executable, str(kit / "setup" / launcher[0]), *launcher[1:]],
                                        cwd=root, env=env, text=True, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("COMMON.md", result.stderr)
                self.assertEqual(result.stdout, "")

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

    def test_acp_pins_session_cwd_when_requested(self):
        new = {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": "/work/project", "mcpServers": []}}
        self.assertEqual(proxy.session_cwd((json.dumps(new) + "\n").encode()), "/work/project")
        self.assertIsNone(proxy.session_cwd(b'{"method":"session/prompt","params":{"cwd":"/x"}}\n'))
        self.assertIsNone(proxy.session_cwd(b"not json\n"))
        prompt = {"method": "session/prompt", "params": {"sessionId": "a", "prompt": [{"type": "text", "text": "task"}]}}
        raw = (json.dumps(prompt) + "\n").encode()
        text = json.loads(proxy.prime(raw, "lead", set(), "/work/project"))["params"]["prompt"][0]["text"]
        self.assertTrue(text.startswith("Session working directory: /work/project."))
        self.assertIn("# Lead", text)
        self.assertNotIn("Session working directory", json.loads(proxy.prime(raw, "lead", set()))["params"]["prompt"][0]["text"])

if __name__ == "__main__":
    unittest.main()
