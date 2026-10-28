import importlib.util
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_runner():
    spec = importlib.util.spec_from_loader("eval_runner", loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(ROOT / "eval" / "run-scenario")
    exec(compile((ROOT / "eval" / "run-scenario").read_text(), "eval/run-scenario", "exec"), module.__dict__)
    return module


class EvalHarnessTest(unittest.TestCase):
    def test_runner_detects_status_and_scope(self):
        runner = load_runner()
        for text, status in (("Outcome            complete; Done: x", "complete"),
                             ("**Outcome**: blocked. Brief lacks round", "BLOCKED"),
                             ("Outcome  reopen; REOPEN_REQUEST layer: foundation", "REOPEN_REQUEST"),
                             ("Outcome partial; DEPENDENCY_REQUEST: utils", "DEPENDENCY_REQUEST"),
                             ("no cells here", "NONE")):
            with self.subTest(text=text):
                self.assertEqual(runner.detect_status(text), status)
        owned = [runner.glob_to_regex("src/test/java/com/smac/utils/**")]
        excluded = [runner.glob_to_regex("src/main/**")]
        self.assertTrue(runner.in_scope("src/test/java/com/smac/utils/DataUtilTest.java", owned, excluded))
        self.assertFalse(runner.in_scope("src/main/java/com/smac/utils/DataUtil.java", owned, excluded))
        self.assertFalse(runner.in_scope("pom.xml", owned, excluded))

    def test_report_without_results(self):
        result = subprocess.run([str(ROOT / "eval" / "report"), str(ROOT / "eval" / "nonexistent")],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("no results", result.stderr)


if __name__ == "__main__":
    unittest.main()
