import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "setup" / "codex-room"


class CodexRoomTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.project = self.root / "project with spaces"
        self.project.mkdir()
        self.canonical = self.root / "canonical"
        self.canonical.mkdir()
        (self.canonical / "config.toml").write_text('model = "fixture"\n')
        self.bin = self.root / "bin"
        self.bin.mkdir()
        (self.bin / "python3").symlink_to(sys.executable)
        self.codex = self.bin / "fake codex"
        self.codex.write_text(
            '#!/usr/bin/env python3\n'
            'import json, os, sys\n'
            'print(json.dumps({"cwd": os.getcwd(), "home": os.environ["CODEX_HOME"], '
            '"args": sys.argv[1:]}))\n'
            'sys.exit(23)\n'
        )
        self.codex.chmod(0o755)
        self.env = {"PATH": str(self.bin), "HOME": str(self.root),
                    "EPISTEX_CODEX_HOME": str(self.canonical),
                    "CODEX_BIN": str(self.codex), "PYTHONDONTWRITEBYTECODE": "1"}

    def run_room(self, *args):
        return subprocess.run([str(self.bin / "python3"), str(WRAPPER), *args],
                              cwd=self.project, env=self.env, text=True, capture_output=True)

    def assert_launch(self, result, role, project, args):
        self.assertEqual(result.returncode, 23, result.stderr)
        payload = json.loads(result.stdout)
        project_id = hashlib.sha256(str(project).encode()).hexdigest()[:12]
        runtime = self.root / ".codex-runtime" / "epistex" / project_id / role
        self.assertEqual(payload, {"cwd": str(project), "home": str(runtime), "args": args})
        self.assertTrue((runtime / "config.toml").is_file())

    def test_launch_forwards_arguments_exit_status_and_project(self):
        args = ["--message", "two words", "", "literal $value"]
        for role in ("lead", "peer"):
            with self.subTest(role=role):
                self.assert_launch(self.run_room(role, *args), role, self.project, args)
        legacy = self.root / "legacy project"
        legacy.mkdir()
        with self.subTest("SEATWORKS_PROJECT_ROOT fallback and default codex lookup"):
            self.env["SEATWORKS_PROJECT_ROOT"] = str(legacy)
            del self.env["CODEX_BIN"]
            (self.bin / "codex").symlink_to(self.codex)
            self.assert_launch(self.run_room("peer"), "peer", legacy, [])
        with self.subTest("EPISTEX_PROJECT_ROOT precedence"):
            self.env["EPISTEX_PROJECT_ROOT"] = str(self.project)
            self.assert_launch(self.run_room("lead"), "lead", self.project, [])

    def test_only_direct_uuid_resume_selects_runtime_from_another_cwd(self):
        session_id = "12345678-1234-1234-1234-123456789abc"
        old_project = self.root / "old launcher cwd"
        old_project.mkdir()
        old_id = hashlib.sha256(str(old_project).encode()).hexdigest()[:12]
        runtime = self.root / ".codex-runtime" / "epistex" / old_id / "supervisor"
        sessions = runtime / "sessions" / "2026" / "09"
        sessions.mkdir(parents=True)
        (sessions / f"rollout-2026-09-26T10-00-00-{session_id}.jsonl").write_text("fixture\n")

        for args in (["resume", session_id], ["exec", "resume", session_id, "--json", "prompt"],
                     ["e", "resume", session_id.upper()]):
            with self.subTest(args=args):
                result = self.run_room("supervisor", *args)
                self.assertEqual(result.returncode, 23, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["cwd"], str(self.project))
                self.assertEqual(payload["home"], str(runtime))
                self.assertEqual(payload["args"], args)
        # Prompts and option values are not session IDs.
        for args in (["resume", "--last", session_id], ["resume", "named-session", session_id],
                     ["exec", "--model", "resume", session_id]):
            with self.subTest(args=args):
                self.assert_launch(self.run_room("lead", *args), "lead", self.project, args)

    def test_invalid_role_or_sync_failure_creates_no_runtime_and_does_not_launch(self):
        def assert_refused(result):
            self.assertNotIn(result.returncode, (0, 23))
            self.assertEqual(result.stdout, "")
            self.assertFalse((self.root / ".codex-runtime").exists())

        for args in ((), ("root",)):
            with self.subTest(args=args):
                assert_refused(self.run_room(*args))
        with self.subTest("invalid canonical TOML"):
            (self.canonical / "config.toml").write_text("invalid = [")
            result = self.run_room("lead")
            assert_refused(result)
            self.assertIn("invalid canonical TOML", result.stderr)
