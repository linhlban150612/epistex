import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
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

    def test_report_receipts_per_seat(self):
        def receipt(delivery, peer, kind, task, created, body="", reasons=(), outcome=None, **extra):
            record = {"deliveryId": delivery, "peerAgentId": peer, "leadAgentId": "lead-1", "kind": kind, "taskId": task,
                      "round": "1", "reasons": list(reasons), "body": body, "state": "pending", "createdAt": created}
            if outcome:
                record["outcome"] = outcome
            return json.dumps({**record, **extra})
        handoff = ("Task ID: TASK-C | Round: 1\n**Outcome:** complete\n**Candidate:** base 1111111, candidate 2222222\n"
                   "**Scope:** a.py\n**Verification:** ran; Proof class: observed\n**Unknown / risk:** none\n**Ownership:** released")
        agents = [{"id": "peer-a", "provider": "p", "model": "m1", "cwd": "/repo"},
                  {"id": "peer-t", "provider": "p", "model": "m1", "cwd": "/tmp/epistex-live-x1"},
                  {"id": "peer-c", "provider": "p", "model": "m2", "cwd": "/repo"}]
        lines = [
            receipt("d1", "peer-a", "TURN_ENDED_INVALID_HANDOFF", None, "2026-11-01T01", "x" * 300, ["turn canceled: Interrupted"],
                    briefCodes=["ROUND_MISSING"], toolCalls=40),
            json.dumps({"deliveryId": "d1", "state": "sent", "sentAt": "t", "sendReceipt": "accepted"}),
            receipt("d2", "peer-a", "HANDBACK_VALID", "`TASK-A`", "2026-11-01T02", "é" * 50, outcome="completed", toolCalls=7),
            receipt("d3", "peer-b", "TURN_ENDED_NO_MESSAGE", None, "2026-11-01T03", reasons=["x"], outcome="failed"),
            receipt("d4", "peer-b", "PERMISSION_REQUESTED", None, "2026-11-01T04", "{}"),
            receipt("d5", "peer-s", "HANDBACK_VALID", "T-1", "2026-11-01T05", "smoke", outcome="completed"),
            receipt("d6", "peer-t", "HANDBACK_VALID", "TASK-T", "2026-11-01T06", "live", outcome="completed"),
            receipt("d7", "peer-c", "TURN_ENDED_INVALID_HANDOFF", "TASK-C", "2026-11-01T07", handoff,
                    ["turn completed", "Candidate cell needs base SHA and candidate SHA (found 0)"], briefCodes=[], toolCalls=3),
            receipt("d8", "peer-a", "BRIEF_INVALID", None, "2026-11-01T00", codes=["ROUND_MISSING", "AUTHORITY_MISSING"]),
            receipt("d9", "peer-x", "BRIEF_INVALID", None, "2026-11-01T08", codes=["ROUND_MISSING"]),
            receipt("d10", "peer-c", "PEER_REMINDED", None, "2026-11-01T06", "still running", ["turn completed"], recipientAgentId="peer-c"),
            receipt("d11", "peer-c", "TURN_ENDED_FAILED", None, "2026-11-01T09", "Error", ["turn failed: quota"], outcome="failed", codes=["TURN_FAILED"]),
            '{"deliveryId": "torn',
        ]
        with tempfile.TemporaryDirectory() as directory:
            pathlib.Path(directory, "lead-1.jsonl").write_text("\n".join(lines))
            pathlib.Path(directory, "agents.txt").write_text(json.dumps(agents))
            command = [str(ROOT / "eval" / "report"), "--receipts", directory, "--agents", str(pathlib.Path(directory, "agents.txt"))]
            result = subprocess.run(command, text=True, capture_output=True)
            everything = subprocess.run(command + ["--include-test-seats"], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("| lead-1 | peer-a | p / m1 | TASK-A | 2 | 1 | 1 | 0 | yes | 300 |", result.stdout)
        self.assertIn("| lead-1 | peer-b | ? / ? | ? | 1 | 0 | 0 | 1 | no | 0 |", result.stdout)
        self.assertNotIn("peer-s", result.stdout)  # test seat by task ID
        self.assertNotIn("peer-t", result.stdout)  # test seat by cwd
        self.assertIn("| lead-1 | peer-s |", everything.stdout)
        self.assertIn("| lead-1 | peer-t |", everything.stdout)
        self.assertIn("| p / m1 | 2 | 1 | 0 |", result.stdout)
        self.assertIn("| lead-1 | peer-c | p / m2 | TASK-C | 2 | 0 | 1 | 1 | no | 205 |", result.stdout)  # the reminder is not a receipt for the Lead
        self.assertIn("| Turns bounced to the Peer (PEER_REMINDED) | 1 |", result.stdout)
        self.assertIn("| TURN_FAILED | 1 |", result.stdout)
        self.assertIn("| p / m2 | 2 | 0 | 1 |", result.stdout)  # the current parser accepts the old invalid body
        self.assertIn("| all | 5 | 1 | 1 |", result.stdout)
        self.assertIn("| TURN_CANCELED | 1 |", result.stdout)
        self.assertIn("| CANDIDATE_IDENTITY | 1 |", result.stdout)
        self.assertIn("| NO_MESSAGE | 1 |", result.stdout)
        self.assertIn("| Valid rate | 1/5 |", result.stdout)
        self.assertIn("| Seats whose first receipt is valid | 0/3 |", result.stdout)
        self.assertIn("| Briefs that pass check-brief | 1/2 checked |", result.stdout)
        self.assertIn("| Early brief warnings (BRIEF_INVALID) | 1 of 3 seats; 1 more for Peers not in this report |", result.stdout)
        self.assertIn("| Early brief warning codes | AUTHORITY_MISSING 1, ROUND_MISSING 1 |", result.stdout)
        self.assertIn("| all | 5 | 1 | 1 |", result.stdout)  # a BRIEF_INVALID record is not a handback receipt
        self.assertIn("| Tool calls per seat median / max | 25 / 47 (2 seats counted) |", result.stdout)
        self.assertIn("| Body size median / max (B) | 152 / 300 |", result.stdout)
        self.assertIn("| Turn outcome | canceled 1, completed 2, failed 2 |", result.stdout)


NO_GIT_CONFIG = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull}


class VerifyTest(unittest.TestCase):
    """setup/verify in a small copy of the kit; the real test suite is never started from a test."""

    def kit(self, folder, codex_room="x = 1\n", test="import unittest\n\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        pass\n"):
        kit = pathlib.Path(folder) / "kit"
        (kit / "setup").mkdir(parents=True)
        (kit / "tests").mkdir()
        shutil.copy2(ROOT / "setup/verify", kit / "setup/verify")
        (kit / "setup/codex-room").write_text(codex_room)
        (kit / "setup/setup-seats.sh").write_text("#!/usr/bin/env bash\ntrue\n")
        (kit / "tests/test_small.py").write_text(test)
        subprocess.run(["git", "-C", str(kit), "init", "-q"], check=True, env=NO_GIT_CONFIG)
        return kit

    def run_verify(self, kit, *args):
        return subprocess.run([str(kit / "setup/verify"), *args], text=True, capture_output=True, cwd="/", env=NO_GIT_CONFIG, timeout=60)

    def test_all_checks_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            kit = self.kit(folder)
            result = self.run_verify(kit)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout.splitlines()[-1], "VERIFY OK")
            for name in ("unit tests", "codex-room compile", "setup-seats.sh syntax", "git diff --check"):
                self.assertIn(f"ok: {name}", result.stdout)
            partial = self.run_verify(kit, "--skip-tests")
            self.assertEqual(partial.returncode, 0, partial.stdout + partial.stderr)
            self.assertEqual(partial.stdout.splitlines()[-1], "VERIFY PARTIAL: unit tests skipped")
            self.assertNotIn("VERIFY OK", partial.stdout)
            self.assertEqual(self.run_verify(kit, "--unknown").returncode, 2)

    def test_failures_are_named_and_later_checks_still_run(self):
        with tempfile.TemporaryDirectory() as folder:
            kit = self.kit(folder, codex_room="def broken(:\n",
                           test="import unittest\n\n\nclass T(unittest.TestCase):\n    def test_bad(self):\n        self.fail('x')\n")
            result = self.run_verify(kit)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(result.stdout.splitlines()[-1], "VERIFY FAILED: unit tests, codex-room compile")
            self.assertIn("ok: setup-seats.sh syntax", result.stdout)
            self.assertNotIn("VERIFY OK", result.stdout)


PLUGIN = ROOT / "plugins/epistex-delivery"


class DeliveryPluginTest(unittest.TestCase):
    # The manifest/guard pin is enforced by setup-seats.sh --check (covered in test_setup_seats.py).
    def test_node_test_suite_passes(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        result = subprocess.run([node, "--test", "--test-reporter=tap", "server/**/*.test.ts"], cwd=PLUGIN,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("# fail 0", result.stdout)

    def test_typecheck_passes(self):
        # node --test strips the types and runs: a type error fails only here.
        tsc = PLUGIN / "node_modules/.bin/tsc"
        if shutil.which("node") is None or not tsc.exists():
            self.skipTest("node or the plugin's dev dependencies (npm install) are not installed")
        result = subprocess.run([str(tsc), "--noEmit"], cwd=PLUGIN, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


EXAMPLE = ROOT / "examples" / "target-repo"


class TargetRepoExamplesTest(unittest.TestCase):
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


class LeadSkillsTest(unittest.TestCase):
    def test_lead_prompt_references_only_existing_skills_and_keeps_headroom(self):
        lead = (ROOT / "agents/LEAD.md").read_text()
        protocol = (ROOT / "examples/WORKSPACE_PROTOCOL.md").read_text()
        entry_points = lead + "\n" + protocol
        paths = set(re.findall(r"`(\.agents/skills/[\w-]+/SKILL\.md)`", entry_points))
        on_disk = {p.relative_to(ROOT).as_posix() for p in ROOT.glob(".agents/skills/*/SKILL.md")}
        self.assertEqual(paths, on_disk, "every kit skill is reachable from the Lead prompt or protocol template")
        for path in paths:
            self.assertTrue((ROOT / path).is_file(), path)
            name = path.split("/")[2]
            text = (ROOT / path).read_text()
            self.assertRegex(text, rf"(?m)^name: {name}$", path)
            self.assertIn(f"`{name}` skill", entry_points, path)
        prompt = subprocess.run([sys.executable, str(ROOT / "setup/role_prompt.py"), "lead"],
                                text=True, capture_output=True, check=True).stdout
        self.assertLessEqual(len(prompt.encode()), 16384 - 1024, "Lead prompt must keep 1 KiB of headroom")


if __name__ == "__main__":
    unittest.main()
