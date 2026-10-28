import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "setup" / "fail-on-base"
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@x", "GIT_CONFIG_GLOBAL": os.devnull}
TEST = "import sys; sys.path.insert(0, 'src'); import calc\nassert calc.add(2, 2) == 4, 'expected 4'\n"


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True,
                          check=True, env=ENV).stdout.strip()


class FailOnBaseTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self.folder.name) / "repo"
        (self.repo / "src").mkdir(parents=True)
        (self.repo / "tests").mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "src/calc.py").write_text("def add(a, b):\n    return a - b\n")
        git(self.repo, "add", "."), git(self.repo, "commit", "-q", "-m", "base")
        self.base = git(self.repo, "rev-parse", "HEAD")

    def tearDown(self):
        self.folder.cleanup()

    def commit_candidate(self, fix=True, test=TEST):
        if fix:
            (self.repo / "src/calc.py").write_text("def add(a, b):\n    return a + b\n")
        (self.repo / "tests/test_calc.py").write_text(test)
        git(self.repo, "add", "."), git(self.repo, "commit", "-q", "-m", "fix")

    def run_script(self, **brief_extra):
        brief = {"task_id": "T", "round": 1, "repo_root": str(self.repo), "worktree": str(self.repo),
                 "base_sha": self.base, "bug_reproducible": True,
                 "regression_check": f"{sys.executable} -I tests/test_calc.py", **brief_extra}
        path = pathlib.Path(self.folder.name) / "brief.json"
        path.write_text(json.dumps(brief))
        return subprocess.run([sys.executable, str(SCRIPT), str(path)], text=True, capture_output=True, env=ENV)

    def test_valid_assertion_failure(self):
        self.commit_candidate()
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("cause ASSERTION", result.stdout)
        self.assertIn("FAIL_ON_BASE_OK", result.stdout)
        self.assertEqual(git(self.repo, "worktree", "list").count("\n"), 0)

    def test_rejects_anything_but_assertion_failure_on_base_and_pass_on_candidate(self):
        helper_test = "import sys; sys.path.insert(0, 'src'); import helper, calc\nassert calc.add(2, 2) == 4\n"
        cases = (
            ("missing dep on base", {"test": helper_test}, {}, 1, "baseline failed for MISSING_DEP"),
            ("candidate still failing", {"fix": False}, {}, 1, "did not pass"),
            ("passes on base", {"test": "assert True\n"}, {}, 1, "does not reproduce the bug"),
            ("not marked reproducible", {}, {"bug_reproducible": False}, 2, "SKIPPED"),
        )
        for name, candidate, brief, code, message in cases:
            with self.subTest(name):
                git(self.repo, "reset", "-q", "--hard", self.base)
                (self.repo / "tests").mkdir(exist_ok=True)
                if name == "missing dep on base":
                    (self.repo / "src/helper.py").write_text("X = 1\n")
                self.commit_candidate(**candidate)
                result = self.run_script(**brief)
                self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                self.assertIn(message, result.stdout)


if __name__ == "__main__":
    unittest.main()


class ClassifyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_loader("fail_on_base", loader=None)
        cls.module = importlib.util.module_from_spec(spec)
        exec(compile(SCRIPT.read_text(), str(SCRIPT), "exec"), cls.module.__dict__)

    def classify(self, stdout, stderr=""):
        return self.module.classify(subprocess.CompletedProcess([], 1, stdout, stderr))

    def test_classify_failure_causes(self):
        cases = {
            "ASSERTION": [
                "AssertionError [ERR_ASSERTION]: Expected values to be strictly equal",
                "expect(received).toBe(expected)\n\nExpected: 4\nReceived: 0",
                "Tests:       1 failed, 3 passed, 4 total",
                " Test Files  1 failed (1)",
                "  3 passing (20ms)\n  1 failing",
                "not ok 1 - add\n# fail 1",
                "Expected 0 to equal 4",
                "Tests run: 3, Failures: 1, Errors: 0",
                ("", "AssertionError: expected 4"),
                "org.opentest4j.AssertionFailedError: expected: <4> but was: <0>",
            ],
            "COMPILE": [
                "src/calc.ts(3,5): error TS2322: Type 'string' is not assignable to type 'number'.",
                "SyntaxError: Unexpected token '}'",
                "✘ [ERROR] Transform failed with 1 error:",
                "ReferenceError: add is not defined",
                "[ERROR] COMPILATION ERROR :",
            ],
            "MISSING_DEP": [
                "Error: Cannot find module 'lodash'",
                "code: 'ERR_MODULE_NOT_FOUND'",
                "npm ERR! 404 Not Found - GET https://registry.npmjs.org/x",
                ("", "ModuleNotFoundError: No module named 'x'"),
            ],
            "MISSING_FILE": [
                "Error: ENOENT: no such file or directory, open 'tests/calc.test.js'",
                "No tests found, exiting with code 1",
                "No test files found, exiting with code 1",
                "Error: No test files found: \"tests/**/*.spec.js\"",
                "No tests were executed!",
            ],
            "UNKNOWN": [
                ("", "something else"),
                # the word "expected" alone is not an assertion failure
                "the non-numeric case logged the expected NumberFormatException",
            ],
        }
        for expected, outputs in cases.items():
            for output in outputs:
                with self.subTest(output=output):
                    stdout, stderr = output if isinstance(output, tuple) else (output, "")
                    self.assertEqual(self.classify(stdout, stderr), expected)
        self.assertEqual(self.module.classify(None), "TIMEOUT")
