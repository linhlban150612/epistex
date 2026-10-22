import json
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "target-repo"


class TargetRepoExamplesTest(unittest.TestCase):
    def test_paseo_json_shape(self):
        config = json.loads((EXAMPLE / "paseo.json").read_text(encoding="utf-8"))
        self.assertTrue(config["worktree"]["setup"])
        self.assertEqual(config["scripts"]["app"]["type"], "service")
        for name in ("quick", "it", "full"):
            self.assertIn("./verify " + name, config["scripts"][name]["command"])

    def test_verify_syntax_and_groups(self):
        subprocess.run(["bash", "-n", str(EXAMPLE / "verify")], check=True)
        with tempfile.TemporaryDirectory() as folder:
            repo = pathlib.Path(folder)
            mvnw = repo / "mvnw"
            mvnw.write_text("#!/bin/sh\necho mvnw \"$@\"\nexit 0\n")
            mvnw.chmod(0o755)
            env = {**os.environ, "PASEO_BRANCH_NAME": "feat/x", "PASEO_WORKTREE_PORT": "18123"}
            env.pop("VERIFY_ALLOW_IT", None)

            def verify(*args, **extra):
                return subprocess.run([str(EXAMPLE / "verify"), *args], cwd=repo, text=True,
                                      capture_output=True, env={**env, **extra})

            quick = verify("quick")
            self.assertEqual(quick.returncode, 0, quick.stderr)
            self.assertIn("SERVER_PORT=18123 DB_NAME=app_feat_x", quick.stdout)
            self.assertIn("+ ./mvnw -B -q -DskipITs test", quick.stdout)
            self.assertIn("exit 0", quick.stdout)

            blocked = verify("it")
            self.assertEqual(blocked.returncode, 3)
            self.assertIn("BLOCKED", blocked.stderr)

            dry = verify("full", "--dry-run", VERIFY_ALLOW_IT="1")
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertIn("-Pit -DskipUnitTests verify", dry.stdout)
            self.assertIn("(dry-run)", dry.stdout)

            self.assertEqual(verify("nope").returncode, 2)
            mvnw.write_text("#!/bin/sh\nexit 5\n")
            failed = verify("quick")
            self.assertEqual(failed.returncode, 1)
            self.assertIn("exit 5", failed.stdout)


if __name__ == "__main__":
    unittest.main()
