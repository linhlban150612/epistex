import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "setup" / "check-brief"
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
    return subprocess.run([sys.executable, str(SCRIPT), "-", *extra], input=text, text=True, capture_output=True)


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

    def test_file_argument_and_read_error(self):
        missing = subprocess.run([sys.executable, str(SCRIPT), "/nonexistent/brief.txt"], text=True, capture_output=True)
        self.assertEqual(missing.returncode, 1)
        self.assertTrue(missing.stdout.startswith("FAIL"))


if __name__ == "__main__":
    unittest.main()
