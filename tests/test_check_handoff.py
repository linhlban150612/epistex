import json
import re
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "setup" / "check-handoff"
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@x", "GIT_CONFIG_GLOBAL": os.devnull}


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True,
                          check=True, env=ENV).stdout.strip()


class CheckHandoffTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self.folder.name) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "src").mkdir()
        (self.repo / "src/a.py").write_text("a\n")
        (self.repo / "db.sql").write_text("db\n")
        git(self.repo, "add", "."), git(self.repo, "commit", "-q", "-m", "base")
        self.base = git(self.repo, "rev-parse", "HEAD")
        (self.repo / "src/a.py").write_text("a2\n")
        (self.repo / "src/b.py").write_text("b\n")
        git(self.repo, "add", "."), git(self.repo, "commit", "-q", "-m", "work")
        self.candidate = git(self.repo, "rev-parse", "HEAD")
        self.brief = {"task_id": "T-1", "round": 1, "repo_root": str(self.repo), "worktree": str(self.repo),
                      "branch": "main", "base_sha": self.base, "owned_scope": ["src/**"],
                      "excluded_scope": ["db.sql"], "required_checks": ["true"], "commit_allowed": True}

    def tearDown(self):
        self.folder.cleanup()

    def handoff(self, round_="1", changed="src/a.py src/b.py", verification="`true` exit 0\noutput: (none)",
                candidate=None, drop=()):
        candidate = candidate or f"base {self.base} candidate {self.candidate} branch main worktree {self.repo}"
        cells = [("Outcome", "complete; Done: x; Not done: none"), ("Candidate", candidate),
                 ("Scope", f"Changed: {changed}; Read: README.md"), ("Verification", verification),
                 ("Unknown / risk", "none"), ("Ownership", "stopped writing, scope returned")]
        body = "\n".join(f"{name:<19}{text}" for name, text in cells if name not in drop)
        return f"Task ID: T-1 | Round: {round_}\n\n{body}\n"

    def run_check(self, handoff, brief=None, *extra):
        folder = pathlib.Path(self.folder.name)
        (folder / "brief.json").write_text(json.dumps(brief or self.brief))
        (folder / "handoff.txt").write_text(handoff)
        return subprocess.run([sys.executable, str(SCRIPT), str(folder / "brief.json"),
                               str(folder / "handoff.txt"), *extra], text=True, capture_output=True, env=ENV)

    def test_ready_for_review_tolerates_handoff_formatting(self):
        result = self.run_check(self.handoff(), None, "--rerun")
        self.assertEqual(result.stdout.strip(), "READY_FOR_REVIEW", result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("ACCEPTED", result.stdout)
        bold = self.handoff().replace("Outcome ", "**Outcome** ", 1).replace("Candidate ", "**Candidate**: ", 1)
        bold = bold.replace("Verification ", "*Verification* ", 1)
        bold = "\n".join(re.sub(r"^(\*\*Outcome\*\*)\s+", r"\1 ", line) for line in bold.splitlines())
        bullets = self.handoff(changed="\n- `src/a.py` (new file)\n- `src/b.py` (file mới).",
                               verification="baseline run: `true` exit 1\ncandidate: `true` exit 0")
        cases = {
            "hex-like tokens": self.handoff(candidate=(
                f"base `{self.base}` candidate `{self.candidate}` branch main (task eval/task--20261022-161431) "
                f"worktree {self.repo} diff sha256 0a184d9dc3b8fa90d6a48f5cc8ce41074537be65a5e848a714844125a55aeb01")),
            "backticks and commas": self.handoff(changed="`src/a.py`, `src/b.py`."),
            "parentheses and semicolons": self.handoff(changed="(src/a.py), src/b.py;"),
            "bold cell names": bold,
            "bullets, notes and header tail": bullets.replace("| Round: 1", "| Round: 1 (assigned by the brief)", 1),
            "baseline run after candidate": self.handoff(
                verification="`true` on the candidate: exit 0\nRegression check on base: `true` exit 1"),
        }
        for name, handoff in cases.items():
            with self.subTest(name):
                result = self.run_check(handoff)
                self.assertEqual(result.returncode, 0, result.stdout)

    def test_header_and_candidate_failures(self):
        result = self.run_check(self.handoff(round_="2", drop=("Ownership",)))
        self.assertEqual(result.returncode, 1)
        self.assertIn("round '2' != brief 1", result.stdout)
        self.assertIn("missing cells: Ownership", result.stdout)
        result = self.run_check(self.handoff(candidate="base 20261022 candidate 161431 branch main"))
        self.assertIn("resolve to commits", result.stdout)
        git(self.repo, "checkout", "-q", "-b", "other", self.base)
        (self.repo / "src/c.py").write_text("c\n")
        git(self.repo, "add", "."), git(self.repo, "commit", "-q", "-m", "other")
        other = git(self.repo, "rev-parse", "HEAD")
        result = self.run_check(self.handoff(
            candidate=f"base {other} candidate {self.candidate} branch main worktree {self.repo}"))
        self.assertIn("not an ancestor", result.stdout)
        self.assertIn("!= brief base_sha", result.stdout)

    def test_changed_files_must_match_declaration_and_scope(self):
        result = self.run_check(self.handoff(changed="src/a.py src/zzz.py"))
        self.assertIn("changed but not declared in Scope/Changed: src/b.py", result.stdout)
        self.assertIn("declared in Scope/Changed but not in diff: src/zzz.py", result.stdout)
        git(self.repo, "mv", "src/b.py", "src/renamed.py")
        git(self.repo, "rm", "-q", "db.sql")
        (self.repo / "other.txt").write_text("x\n")
        git(self.repo, "add", "."), git(self.repo, "commit", "-q", "-m", "more")
        self.candidate = git(self.repo, "rev-parse", "HEAD")
        result = self.run_check(self.handoff(changed="src/a.py src/b.py src/renamed.py db.sql other.txt"))
        self.assertIn("changed file in excluded_scope: db.sql", result.stdout)
        self.assertIn("changed file outside owned_scope: other.txt", result.stdout)
        self.assertNotIn("not declared", result.stdout)

    def test_required_check_missing_or_failing(self):
        cases = {
            "ran nothing": "required check not reported: true",
            "`true` ran fine": "required check without exit status: true",
            "`true` exit 1": "required check reported non-zero exit: true",
            "`true` exit 0\nrerun: `true` exit 1": "required check reported non-zero exit: true",
            "regression check: `true` exit 1": "required check reported non-zero exit: true",
        }
        for verification, message in cases.items():
            with self.subTest(verification=verification):
                self.assertIn(message, self.run_check(self.handoff(verification=verification)).stdout)
        brief = {**self.brief, "required_checks": ["false"]}
        result = self.run_check(self.handoff(verification="`false` exit 0"), brief, "--rerun")
        self.assertIn("rerun exit 1: false", result.stdout)

    def test_snapshot_mode_unsupported(self):
        cases = {
            "commit not allowed": (self.handoff(), {**self.brief, "commit_allowed": False}),
            "snapshot candidate": (self.handoff(
                candidate="baseline snapshot sha256 … path /tmp/x; candidate snapshot …"), None),
            "uncommitted candidate": (self.handoff(
                candidate=f"base {self.base}; uncommitted candidate on branch eval/task--20261022-161431; "
                          f"worktree {self.repo}"), None),
        }
        for name, (handoff, brief) in cases.items():
            with self.subTest(name):
                result = self.run_check(handoff, brief)
                self.assertEqual(result.returncode, 1)
                self.assertIn("UNSUPPORTED", result.stdout)

if __name__ == "__main__":
    unittest.main()
