import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@x", "GIT_CONFIG_GLOBAL": os.devnull}


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True,
                          check=True, env=ENV).stdout.strip()


CHECK_BRIEF = ROOT / "setup" / "check-brief"
BASE = "3f2a9c1d4e5b6a7f8091a2b3c4d5e6f708192a3b"
SHA256 = "0a184d9dc3b8fa90d6a48f5cc8ce41074537be65a5e848a714844125a55aeb01"
# The assignment template of agents/LEAD.md, filled in.
BRIEF = f"""Project / Task ID: demo / T-1
Round (assigned by Lead): 1
Repository root + workspace: /tmp/repo, branch main, base {BASE}
Disposition: Engineer
Objective: I need requests to survive a daemon restart.
Owned scope        src/**
Excluded scope     db.sql
Authority          edit files in owned scope; commit required
Verification       required: `true`
Effort             medium
Handoff contract   candidate per § Ownership; six cells per § Handoff in the Peer prompt
"""


def run(text, *extra):
    return subprocess.run([sys.executable, str(CHECK_BRIEF), "-", *extra], input=text, text=True, capture_output=True)


def codes(text):
    return json.loads(run(text, "--json").stdout)["codes"]


class CheckBriefTest(unittest.TestCase):
    def test_template_brief_passes_in_plain_and_marked_up_form(self):
        result = run(BRIEF)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "OK"), result.stdout + result.stderr)
        fields = json.loads(run(BRIEF, "--json").stdout)["fields"]
        self.assertEqual(fields, {"Task ID": "demo / T-1", "Round": "1", "Owned scope": "src/**",
                                  "Authority": "edit files in owned scope; commit required"})
        inline = (f"Project: demo / Task ID: T-1, round 2. Baseline snapshot sha256 {SHA256} path /tmp/base.tar\n"
                  "- **Owned scope:** read-only\n- **Authority:** read-only, commit forbidden\n"
                  "Handoff: Outcome, Candidate, Scope, Verification, Unknown/risk, Ownership. Add to Verification: the log.\n")
        self.assertEqual(codes(inline), [])
        self.assertEqual(json.loads(run(inline, "--json").stdout)["fields"]["Round"], "2")

    def test_each_missing_field_fails_with_its_code(self):
        cases = {
            "Project / Task ID: demo / T-1\n": "TASK_ID_MISSING",
            "Round (assigned by Lead): 1\n": "ROUND_MISSING",
            "Owned scope        src/**\n": "OWNED_SCOPE_MISSING",
            "Authority          edit files in owned scope; commit required\n": "AUTHORITY_MISSING",
            f", base {BASE}": "BASELINE_MISSING",
        }
        for line, code in cases.items():
            with self.subTest(code):
                self.assertIn(line, BRIEF)
                result = run(BRIEF.replace(line, ""))
                self.assertEqual(result.returncode, 1)
                self.assertTrue(result.stdout.startswith("FAIL\n- "), result.stdout)
                self.assertEqual(codes(BRIEF.replace(line, "")), [code])
        self.assertEqual(codes(BRIEF.replace("Owned scope        src/**", "Owned scope")), ["OWNED_SCOPE_MISSING"])
        self.assertEqual(codes(BRIEF.replace("by Lead): 1", "by Lead): R2-V1")), ["ROUND_NOT_NUMBER"])
        # A base word without an identity, a checksum without a path, and prose that only mentions the words.
        self.assertEqual(codes(BRIEF.replace(f"base {BASE}", "base is the current main")), ["BASELINE_MISSING"])
        root = f"Repository root + workspace: /tmp/repo, branch main, base {BASE}"
        self.assertEqual(codes(BRIEF.replace(root, f"Baseline: sha256 {SHA256}")), ["BASELINE_MISSING"])
        self.assertEqual(codes(BRIEF.replace(root, f"Baseline:\n  sha256 {SHA256} at /tmp/base.tar")), [])
        prose = "Before writing, confirm owned scope, write authority and the task id for this round.\n"
        self.assertEqual(codes(prose), ["TASK_ID_MISSING", "ROUND_MISSING", "OWNED_SCOPE_MISSING",
                                        "AUTHORITY_MISSING", "BASELINE_MISSING"])

    def test_handoff_paragraph_that_redefines_cells_fails(self):
        contract = "Handoff contract   candidate per § Ownership; six cells per § Handoff in the Peer prompt"
        self.assertIn(contract, BRIEF)
        for own_format in (
            "Handoff contract: six cells: Outcome; Changed files; Verification; Not verified; Risks; Next step.",
            "Handoff: Task/Round, DONE/NOT DONE; base SHA, candidate SHA; files; check outputs; risks.",
            "Handoff contract — reply with these six cells:\n1. Candidate identity\n2. Scope / coverage\n3. Risks",
        ):
            with self.subTest(own_format):
                self.assertEqual(codes(BRIEF.replace(contract, own_format)), ["CELLS_REDEFINED"])
        self.assertEqual(codes(BRIEF.replace(contract, "")), [], "a brief without a handoff paragraph leaves the Peer prompt in force")

    def test_brief_json_uses_the_check_handoff_schema(self):
        brief = {"task_id": "T-1", "round": 1, "repo_root": "/tmp/repo", "base_sha": BASE, "owned_scope": ["src/**"],
                 "commit_allowed": True}
        self.assertEqual(codes(json.dumps(brief)), [])
        for key, code in {"task_id": "TASK_ID_MISSING", "round": "ROUND_MISSING", "owned_scope": "OWNED_SCOPE_MISSING",
                          "commit_allowed": "AUTHORITY_MISSING", "base_sha": "BASELINE_MISSING"}.items():
            with self.subTest(key):
                self.assertEqual(codes(json.dumps({k: v for k, v in brief.items() if k != key})), [code])
        self.assertEqual(codes(json.dumps({**brief, "round": "1", "owned_scope": []})),
                         ["ROUND_MISSING", "OWNED_SCOPE_MISSING"])

    def test_brief_fixtures_report_the_expected_codes(self):
        # Shapes of real Lead briefs, project text replaced: accepted label forms (ok-*) and rejections (bad-*).
        fixtures = ROOT / "tests/fixtures/briefs"
        expected = json.loads((fixtures / "expected.json").read_text())
        self.assertEqual(sorted(expected), sorted(path.name for path in fixtures.glob("*.txt")))
        for name, expected_codes in expected.items():
            with self.subTest(name):
                result = subprocess.run([sys.executable, str(CHECK_BRIEF), str(fixtures / name), "--json"], text=True, capture_output=True)
                self.assertEqual(json.loads(result.stdout)["codes"], expected_codes)
                self.assertEqual(result.returncode, 1 if expected_codes else 0)
        fields = json.loads(run((fixtures / "ok-upper-snake-labels.txt").read_text(), "--json").stdout)["fields"]
        self.assertEqual((fields["Task ID"], fields["Round"]), ("T-15", "2"))
        self.assertTrue(fields["Owned scope"].startswith("/tmp/repo/src/main/java/demo/"))

    def test_file_argument_and_read_error(self):
        missing = subprocess.run([sys.executable, str(CHECK_BRIEF), "/nonexistent/brief.txt"], text=True, capture_output=True)
        self.assertEqual(missing.returncode, 1)
        self.assertTrue(missing.stdout.startswith("FAIL"))


CHECK_HANDOFF = ROOT / "setup" / "check-handoff"


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

    def handoff(self, round_="1", changed="src/a.py src/b.py", verification="`true` exit 0\noutput: (none)\nProof class: tests-only",
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
        return subprocess.run([sys.executable, str(CHECK_HANDOFF), str(folder / "brief.json"),
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
                               verification="baseline run: `true` exit 1\ncandidate: `true` exit 0\nProof class: observed")
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

    def snapshot(self, diff_untracked=True):
        """An uncommitted candidate on top of the work commit, frozen as a diff file outside the repo."""
        (self.repo / "src/a.py").write_text("a3\n")
        (self.repo / "src/new.py").write_text("n\n")
        if diff_untracked:
            git(self.repo, "add", "-N", "src/new.py")
        diff = subprocess.run(["git", "-C", str(self.repo), "diff", self.candidate], capture_output=True, check=True, env=ENV).stdout
        path = pathlib.Path(self.folder.name) / "candidate.diff"
        path.write_bytes(diff)
        brief = {**self.brief, "base_sha": self.candidate, "commit_allowed": False}
        cell = (f"base {self.candidate}; no commit; branch main worktree {self.repo}; "
                f"candidate diff sha256 {hashlib.sha256(diff).hexdigest()} path {path}")
        return brief, cell, path

    def test_snapshot_mode_checks_checksum_scope_and_worktree(self):
        brief, cell, path = self.snapshot()
        result = self.run_check(self.handoff(candidate=cell, changed="src/a.py src/new.py"), brief, "--rerun")
        self.assertEqual(result.stdout.strip(), "READY_FOR_REVIEW", result.stdout + result.stderr)
        result = self.run_check(self.handoff(candidate=cell, changed="src/a.py"), brief)
        self.assertIn("changed but not declared in Scope/Changed: src/new.py", result.stdout)
        (self.repo / "other.txt").write_text("x\n")
        result = self.run_check(self.handoff(candidate=cell, changed="src/a.py src/new.py other.txt"), brief)
        self.assertEqual(result.returncode, 1)
        self.assertIn("changed file outside owned_scope: other.txt", result.stdout)
        self.assertIn("worktree change not in the candidate diff file (not frozen): other.txt", result.stdout)
        (self.repo / "other.txt").unlink()
        # A sandboxed Peer keeps its diff file inside the worktree: evidence, not a change.
        inside = self.repo / "candidate.diff"
        inside.write_bytes(path.read_bytes())
        result = self.run_check(self.handoff(candidate=cell.replace(str(path), "candidate.diff"), changed="src/a.py src/new.py"), brief)
        self.assertEqual(result.stdout.strip(), "READY_FOR_REVIEW", result.stdout + result.stderr)
        # Live Codex form: the path in backticks with a comma after it.
        result = self.run_check(self.handoff(candidate=cell.replace(f"path {path}", "snapshot: `candidate.diff`, no commit"),
                                             changed="src/a.py src/new.py candidate.diff"), brief)
        self.assertEqual(result.stdout.strip(), "READY_FOR_REVIEW", result.stdout + result.stderr)
        inside.unlink()
        path.write_text("tampered\n")
        result = self.run_check(self.handoff(candidate=cell, changed="src/a.py src/new.py"), brief)
        self.assertIn("matches no readable file named in the Candidate cell", result.stdout)

    def test_snapshot_mode_failures(self):
        brief, cell, _ = self.snapshot()
        cases = {
            "no checksum": (self.handoff(candidate=f"base {self.candidate}; uncommitted; branch main worktree {self.repo}",
                                         changed="src/a.py src/new.py"), brief, "needs a sha256 checksum"),
            "commit required": (self.handoff(candidate=cell, changed="src/a.py src/new.py"),
                                {**brief, "commit_allowed": True}, "the brief requires a commit"),
            "committed although forbidden": (self.handoff(candidate=cell, changed="src/a.py src/new.py"),
                                             {**brief, "base_sha": self.base}, "commit_allowed=false but worktree HEAD"),
        }
        for name, (handoff, case_brief, message) in cases.items():
            with self.subTest(name):
                result = self.run_check(handoff, case_brief)
                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stdout)
        # Without Git the file list comes from the diff file; without both it is UNSUPPORTED.
        plain = pathlib.Path(self.folder.name) / "plain"
        plain.mkdir()
        outside = {**brief, "repo_root": str(plain), "worktree": str(plain), "base_sha": None, "branch": None}
        cell = cell.replace(str(self.repo), str(plain))
        result = self.run_check(self.handoff(candidate=cell, changed="src/a.py src/new.py"), outside)
        self.assertEqual(result.stdout.strip(), "READY_FOR_REVIEW", result.stdout + result.stderr)
        note = plain / "snapshot.txt"
        note.write_text("not a diff\n")
        cell = f"no Git; worktree {plain}; snapshot sha256 {hashlib.sha256(note.read_bytes()).hexdigest()} path {note}"
        result = self.run_check(self.handoff(candidate=cell), outside)
        self.assertIn("UNSUPPORTED", result.stdout)

    def test_commit_mode_rejects_uncommitted_work(self):
        (self.repo / "src/a.py").write_text("later\n")
        (self.repo / "stray.txt").write_text("x\n")
        result = self.run_check(self.handoff())
        self.assertEqual(result.returncode, 1)
        self.assertIn("uncommitted change in the worktree, not in the candidate: src/a.py", result.stdout)
        self.assertIn("uncommitted change in the worktree, not in the candidate: stray.txt", result.stdout)
        git(self.repo, "add", "."), git(self.repo, "commit", "-q", "-m", "after handback")
        result = self.run_check(self.handoff(), None, "--rerun")
        self.assertIn("uncommitted work not checked", result.stdout)
        self.assertIn("rerun skipped", result.stdout)

    def test_parse_only_reports_shape_without_brief_or_repo(self):
        fixtures = ROOT / "tests/fixtures/handoffs"

        def parse_only(name, *extra):
            return subprocess.run([sys.executable, str(CHECK_HANDOFF), "--parse-only", str(fixtures / name), *extra],
                                  text=True, capture_output=True, env=ENV)

        valid = json.loads(parse_only("valid.txt", "--json").stdout)
        self.assertTrue(valid["valid"])
        self.assertEqual(valid["header"], {"task": "T-1", "round": "1"})
        self.assertEqual(len(valid["shas"]), 2)
        emphasis = json.loads(parse_only("emphasis.txt", "--json").stdout)
        self.assertEqual(emphasis["header"]["round"], "3")
        self.assertEqual(emphasis["cells"]["Unknown / risk"], "không có")
        self.assertTrue(emphasis["snapshot"])
        for name, reason in {"missing-cell.txt": "missing cells: Ownership",
                             "no-round.txt": "header 'Task ID: … | Round: …' not found",
                             "truncated.txt": "missing cells: Scope, Verification, Unknown / risk, Ownership",
                             "empty.txt": "missing cells: Outcome"}.items():
            with self.subTest(name):
                as_json = parse_only(name, "--json")
                self.assertEqual(as_json.returncode, 0, "JSON mode reports, it does not judge")
                self.assertFalse(json.loads(as_json.stdout)["valid"])
                as_text = parse_only(name)
                self.assertEqual(as_text.returncode, 1)
                self.assertIn(reason, as_text.stdout)
        self.assertEqual(parse_only("valid.txt").stdout.strip(), "VALID")
        # One fixture per accepted markup form (ok-*) and per rejection (bad-*), with its reason codes.
        expected = json.loads((fixtures / "expected.json").read_text())
        self.assertEqual(sorted(expected), sorted(path.name for path in fixtures.glob("*.txt")))
        for name, codes in expected.items():
            with self.subTest(name):
                result = json.loads(parse_only(name, "--json").stdout)
                self.assertEqual(result["codes"], codes)
                self.assertEqual(result["valid"], not codes)
        missing_args = subprocess.run([sys.executable, str(CHECK_HANDOFF), "brief.json"], text=True, capture_output=True, env=ENV)
        self.assertEqual(missing_args.returncode, 2)
        self.assertIn("brief and handoff are required", missing_args.stderr)


FAIL_ON_BASE = ROOT / "setup" / "fail-on-base"
CALC_TEST = "import sys; sys.path.insert(0, 'src'); import calc\nassert calc.add(2, 2) == 4, 'expected 4'\n"


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

    def commit_candidate(self, fix=True, test=CALC_TEST):
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
        return subprocess.run([sys.executable, str(FAIL_ON_BASE), str(path)], text=True, capture_output=True, env=ENV)

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


class ClassifyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_loader("fail_on_base", loader=None)
        cls.module = importlib.util.module_from_spec(spec)
        exec(compile(FAIL_ON_BASE.read_text(), str(FAIL_ON_BASE), "exec"), cls.module.__dict__)

    def classify(self, stdout, stderr=""):
        return self.module.classify(subprocess.CompletedProcess([], 1, stdout, stderr))

    def test_scope_globs_agree_between_the_gates(self):
        handoff = {"__name__": "check_handoff"}
        exec(compile(CHECK_HANDOFF.read_text(), str(CHECK_HANDOFF), "exec"), handoff)
        cases = [("src/**", "src/a/b.py", True), ("src/**", "other.py", False), ("**/*.md", "README.md", True),
                 ("**/*.md", "docs/a/b.md", True), ("src/**/*.py", "src/a.py", True), ("src/**/*.py", "src/a/b.py", True),
                 ("src/**/*.py", "srcx/a.py", False), ("*.py", "src/a.py", False), ("**/secrets/*", "secrets/key", True)]
        for pattern, path, expected in cases:
            with self.subTest(pattern=pattern, path=path):
                self.assertEqual(bool(handoff["glob_to_regex"](pattern).match(path)), expected)
                self.assertEqual(bool(self.module.glob_to_regex(pattern).match(path)), expected)

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


if __name__ == "__main__":
    unittest.main()
