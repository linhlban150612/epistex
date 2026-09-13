import hashlib
import json
import pathlib
import shutil
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
        for name in ("bash", "dirname"):
            target = shutil.which(name)
            if target is None:
                raise RuntimeError(f"test prerequisite missing: {name}")
            (self.bin / name).symlink_to(target)
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
                    "SEATWORKS_CODEX_HOME": str(self.canonical),
                    "CODEX_BIN": str(self.codex), "PYTHONDONTWRITEBYTECODE": "1"}

    def run_room(self, *args):
        return subprocess.run([str(self.bin / "bash"), str(WRAPPER), *args],
                              cwd=self.project, env=self.env, text=True, capture_output=True)

    def assert_launch(self, result, role, project, args):
        self.assertEqual(result.returncode, 23, result.stderr)
        payload = json.loads(result.stdout)
        project_id = hashlib.sha256(str(project).encode()).hexdigest()[:12]
        runtime = self.root / ".codex-runtime" / "seatworks" / project_id / role
        self.assertEqual(payload, {"cwd": str(project), "home": str(runtime), "args": args})
        self.assertTrue((runtime / "config.toml").is_file())

    def test_roles_forward_arguments_and_exit_status(self):
        args = ["--message", "two words", "", "literal $value"]
        for role in ("lead", "peer"):
            with self.subTest(role=role):
                self.assert_launch(self.run_room(role, *args), role, self.project, args)

    def test_project_override_and_default_codex_lookup(self):
        project = self.root / "other project"
        project.mkdir()
        self.env["SEATWORKS_PROJECT_ROOT"] = str(project)
        del self.env["CODEX_BIN"]
        (self.bin / "codex").symlink_to(self.codex)
        self.assert_launch(self.run_room("peer"), "peer", project, [])

    def test_invalid_or_missing_role_does_not_create_runtime(self):
        for args in ((), ("root",)):
            with self.subTest(args=args):
                result = self.run_room(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertFalse((self.root / ".codex-runtime").exists())

    def test_sync_failure_does_not_launch_codex(self):
        (self.canonical / "config.toml").write_text("invalid = [")
        result = self.run_room("lead")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotEqual(result.returncode, 23)
        self.assertEqual(result.stdout, "")
        self.assertFalse((self.root / ".codex-runtime").exists())
