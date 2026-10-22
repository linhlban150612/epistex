import importlib.util
import json
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCENARIOS = sorted((ROOT / "eval" / "scenarios").glob("*.json"))


def load_runner():
    spec = importlib.util.spec_from_loader("eval_runner", loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(ROOT / "eval" / "run-scenario")
    exec(compile((ROOT / "eval" / "run-scenario").read_text(), "eval/run-scenario", "exec"), module.__dict__)
    return module


class EvalHarnessTest(unittest.TestCase):
    def test_scenarios_have_required_fields(self):
        self.assertGreaterEqual(len(SCENARIOS), 5)
        for path in SCENARIOS:
            with self.subTest(scenario=path.name):
                s = json.loads(path.read_text())
                for key in ("id", "title", "objective", "decided", "verification", "brief_json", "expect", "brief_template"):
                    self.assertIn(key, s)
                self.assertEqual(s["id"], path.stem)
                self.assertIn("owned_scope", s["brief_json"])
                self.assertIn("required_checks", s["brief_json"])
                self.assertIn("status", s["expect"])
                if s["brief_json"].get("bug_reproducible"):
                    self.assertIn("regression_check", s["brief_json"])

    def test_brief_template_placeholders_are_known(self):
        known = {"TASK_ID", "ROUND_LINE", "WORKTREE", "BRANCH", "BASE_SHA", "DISPOSITION", "OBJECTIVE",
                 "MUST_HOLD_EXTRA", "DECIDED", "OWNED", "EXCLUDED", "VERIFICATION"}
        import re
        for path in SCENARIOS:
            used = set(re.findall(r"{{(\w+)}}", json.loads(path.read_text())["brief_template"]))
            self.assertTrue(used <= known, f"{path.name}: unknown placeholders {used - known}")

    def test_detect_status(self):
        runner = load_runner()
        self.assertEqual(runner.detect_status("Outcome            complete; Done: x"), "complete")
        self.assertEqual(runner.detect_status("**Outcome**: blocked. Brief lacks round"), "BLOCKED")
        self.assertEqual(runner.detect_status("Outcome  reopen; REOPEN_REQUEST layer: foundation"), "REOPEN_REQUEST")
        self.assertEqual(runner.detect_status("Outcome partial; DEPENDENCY_REQUEST: utils"), "DEPENDENCY_REQUEST")
        self.assertEqual(runner.detect_status("no cells here"), "NONE")

    def test_scope_globs(self):
        runner = load_runner()
        owned = [runner.glob_to_regex("src/test/java/com/smac/utils/**")]
        excluded = [runner.glob_to_regex("src/main/**")]
        self.assertTrue(runner.in_scope("src/test/java/com/smac/utils/DataUtilTest.java", owned, excluded))
        self.assertFalse(runner.in_scope("src/main/java/com/smac/utils/DataUtil.java", owned, excluded))
        self.assertFalse(runner.in_scope("pom.xml", owned, excluded))

    def test_scripts_compile(self):
        for name in ("run-scenario", "report"):
            compile((ROOT / "eval" / name).read_text(), f"eval/{name}", "exec")

    def test_report_without_results(self):
        result = subprocess.run([str(ROOT / "eval" / "report"), str(ROOT / "eval" / "nonexistent")],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("no results", result.stderr)


if __name__ == "__main__":
    unittest.main()
