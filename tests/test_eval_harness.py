import importlib.util
import json
import pathlib
import subprocess
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
        def receipt(delivery, peer, kind, task, created, body="", reasons=(), outcome=None):
            record = {"deliveryId": delivery, "peerAgentId": peer, "leadAgentId": "lead-1", "kind": kind, "taskId": task,
                      "round": "1", "reasons": list(reasons), "body": body, "state": "pending", "createdAt": created}
            if outcome:
                record["outcome"] = outcome
            return json.dumps(record)
        lines = [
            receipt("d1", "peer-a", "TURN_ENDED_INVALID_HANDOFF", None, "2026-11-01T01", "x" * 300, ["turn canceled: Interrupted"]),
            json.dumps({"deliveryId": "d1", "state": "sent", "sentAt": "t", "sendReceipt": "accepted"}),
            receipt("d2", "peer-a", "HANDBACK_VALID", "`TASK-A`", "2026-11-01T02", "é" * 50, outcome="completed"),
            receipt("d3", "peer-b", "TURN_ENDED_NO_MESSAGE", None, "2026-11-01T03", reasons=["x"], outcome="failed"),
            receipt("d4", "peer-b", "PERMISSION_REQUESTED", None, "2026-11-01T04", "{}"),
            receipt("d5", "peer-s", "HANDBACK_VALID", "T-1", "2026-11-01T05", "smoke", outcome="completed"),
            '{"deliveryId": "torn',
        ]
        with tempfile.TemporaryDirectory() as directory:
            pathlib.Path(directory, "lead-1.jsonl").write_text("\n".join(lines))
            result = subprocess.run([str(ROOT / "eval" / "report"), "--receipts", directory, "--exclude-task", r"^T-\d+$"],
                                    text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("| lead-1 | peer-a | TASK-A | 2 | 1 | 1 | 0 | yes | 300 |", result.stdout)
        self.assertIn("| lead-1 | peer-b | ? | 1 | 0 | 0 | 1 | no | 0 |", result.stdout)
        self.assertNotIn("peer-s", result.stdout)
        self.assertIn("| Valid rate | 1/3 |", result.stdout)
        self.assertIn("| Body size median / max (B) | 200 / 300 |", result.stdout)
        self.assertIn("| Turn outcome | canceled 1, completed 1, failed 1 |", result.stdout)


if __name__ == "__main__":
    unittest.main()
