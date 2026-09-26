import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("epistex_desk", ROOT / "setup/desk.py")
desk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desk)


class DeskTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name) / "project"
        self.root.mkdir()
        self.state = patch.object(desk, "HOME", pathlib.Path(self.tmp.name) / "state")
        self.state.start()
        self.addCleanup(self.state.stop)
        self.agents = {"sup": {"Provider": "epx-supervisor-codex", "Status": "idle", "Cwd": str(self.root)}}
        self.sent = []
        self.runs = []
        self.mock = patch.object(desk, "paseo", side_effect=self.paseo)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def paseo(self, command, *args):
        if command == "inspect":
            return self.agents[args[0]]
        if command == "run":
            role = args[args.index("--provider") + 1]
            agent_id = f"agent-{len(self.runs)}"
            self.runs.append((command, *args))
            cwd = self.root / "lane" if "--new-workspace" in args or "--workspace" in args else self.root
            self.agents[agent_id] = {"Provider": role, "Status": "running", "Cwd": str(cwd)}
            return {"agentId": agent_id, "status": "running"}
        if command == "workspace":
            self.assertEqual(args, ("ls", "--json"))
            return [{"workspaceId": "lane-workspace", "cwd": str(self.root / "lane")},
                    {"workspaceId": "root-workspace", "cwd": str(self.root)}]
        if command == "send":
            self.sent.append(args)
            return {"ok": True}
        if command == "archive":
            self.agents[args[0]]["Status"] = "archived"
            return {"ok": True}
        raise AssertionError(command)

    def action(self, who, *argv):
        if argv[0] == "done":
            if "--round" not in argv:
                argv += ("--round", "1")
            if "--candidate" not in argv:
                argv += ("--candidate", "candidate-a")
        args = desk.parser().parse_args([argv[0], "--project", str(self.root), *argv[1:]])
        with patch.dict(os.environ, {"PASEO_AGENT_ID": who}):
            with desk.ledger_for(self.root) as data:
                return desk.patrol(self.root, data) if args.action == "patrol" else desk.act(args, self.root, data)

    def test_role_routing_handback_review_and_acceptance(self):
        self.action("sup", "join")
        lane = self.action("sup", "open-lane", "--title", "Feature", "--goal", "Deliver feature")
        lead = lane["lead"]
        self.assertIn("--new-workspace", self.runs[0]); self.assertEqual(lane["status"], "open")
        self.assertRaises(PermissionError, self.action, "sup", "start-task", "--lane", lane["id"], "--title", "Do", "--goal", "Implement")
        task = self.action(lead, "start-task", "--lane", lane["id"], "--title", "Do", "--goal", "Implement", "--owned", "src/")
        peer = task["peer"]
        self.assertRaises(ValueError, self.action, lead, "start-task", "--lane", lane["id"], "--title", "Again", "--goal", "Overlap")
        self.assertRaises(ValueError, self.action, lead, "accept", "--task", task["id"])
        self.action(peer, "done", "--task", task["id"], "--summary", "Implemented", "--checks", "test passed")
        review = self.action(lead, "start-review", "--task", task["id"], "--focus", "Check regression")
        self.assertRaises(ValueError, self.action, lead, "accept", "--task", task["id"])
        self.action(review["reviewer"], "done", "--task", task["id"], "--summary", "No findings", "--checks", "diff read")
        self.assertRaises(ValueError, self.action, lead, "accept", "--task", task["id"])
        self.agents[peer]["Status"] = "idle"
        self.action(lead, "accept", "--task", task["id"])
        self.action("sup", "close-lane", "--lane", lane["id"])
        with desk.ledger_for(self.root) as saved:
            self.assertEqual(saved["tasks"][task["id"]]["status"], "accepted")
            self.assertEqual(saved["lanes"][lane["id"]]["status"], "closed")
            self.assertEqual(self.agents[peer]["Status"], "archived")

    def test_patrol_starts_one_watcher_and_delivers_once_when_idle(self):
        self.action("sup", "join")
        lane = self.action("sup", "open-lane", "--title", "Feature", "--goal", "Deliver feature")
        lead = lane["lead"]
        self.action("sup", "patrol")
        self.action("sup", "patrol")
        with desk.ledger_for(self.root) as saved:
            watcher = saved["lanes"][lane["id"]]["watcher"]
            self.assertEqual(len([a for a in saved["agents"].values() if a["role"] == "watcher"]), 1)
        self.action(lead, "start-task", "--lane", lane["id"], "--title", "Do", "--goal", "Implement")
        self.action("sup", "patrol")
        self.assertFalse(self.sent, "running agents must not receive a new turn")
        self.agents[watcher]["Status"] = "idle"
        self.action("sup", "patrol")
        self.action("sup", "patrol")
        self.assertEqual(len(self.sent), 1, "sent mail must not be replayed")

    def test_uncertain_launch_is_not_retried_by_patrol(self):
        self.action("sup", "join")
        def fail_run(command, *args):
            if command == "run":
                raise RuntimeError("unknown launch outcome")
            return self.paseo(command, *args)
        with patch.object(desk, "paseo", side_effect=fail_run):
            with self.assertRaises(RuntimeError):
                self.action("sup", "open-lane", "--title", "Feature", "--goal", "Deliver feature")
        with desk.ledger_for(self.root) as saved:
            self.assertEqual(next(iter(saved["lanes"].values()))["status"], "launching")
            self.assertEqual(next(a for a in saved["agents"].values() if a["role"] == "lead")["status"], "uncertain")
        self.action("sup", "patrol")
        self.assertEqual(len(self.runs), 0)

    def test_caller_cannot_operate_on_a_different_project(self):
        self.agents["sup"]["Cwd"] = self.tmp.name
        self.assertRaises(PermissionError, self.action, "sup", "join")
        with desk.ledger_for(self.root) as saved:
            self.assertEqual(saved["agents"], {})

    def test_uncertain_watcher_and_reviewer_are_not_launched_twice(self):
        self.action("sup", "join")
        lane = self.action("sup", "open-lane", "--title", "Feature", "--goal", "Deliver")
        task = self.action(lane["lead"], "start-task", "--lane", lane["id"], "--title", "Do", "--goal", "Implement")
        self.action(task["peer"], "done", "--task", task["id"], "--summary", "First", "--checks", "pass")
        def lost_response(command, *args):
            result = self.paseo(command, *args)
            if command == "run":
                raise RuntimeError("created externally, response lost")
            return result
        with patch.object(desk, "paseo", side_effect=lost_response):
            self.action("sup", "patrol")
            self.action("sup", "patrol")
            self.assertEqual(len(self.runs), 3)
            with self.assertRaises(RuntimeError):
                self.action(lane["lead"], "start-review", "--task", task["id"], "--focus", "Inspect")
            with self.assertRaises(ValueError):
                self.action(lane["lead"], "start-review", "--task", task["id"], "--focus", "Inspect")
            self.assertEqual(len(self.runs), 4)

    def test_upgrade_preserves_legacy_state_and_quarantines_mail(self):
        self.action("sup", "join")
        lane = self.action("sup", "open-lane", "--title", "Feature", "--goal", "Deliver")
        task = self.action(lane["lead"], "start-task", "--lane", lane["id"], "--title", "Do", "--goal", "Implement")
        with desk.ledger_for(self.root) as saved:
            del saved["tasks"][task["id"]]["round"]
            saved["outbox"].append({"id": "legacy", "to": task["peer"], "text": "Rework old", "status": "pending", "at": 1})
        with self.assertRaisesRegex(RuntimeError, "upgrade"):
            self.action("sup", "patrol")
        self.action("sup", "upgrade")
        self.action("sup", "upgrade")
        with desk.ledger_for(self.root) as saved:
            current = saved["tasks"][task["id"]]
            self.assertEqual(current["round"], 1)
            self.assertEqual(current["legacy"]["status"], "running")
            self.assertEqual(next(m for m in saved["outbox"] if m["id"] == "legacy")["status"], "quarantined")
        self.action(task["peer"], "done", "--task", task["id"], "--summary", "First", "--checks", "pass")
        self.assertFalse(self.sent)

    def test_retire_misplaced_watcher_then_patrol_replaces_it(self):
        self.action("sup", "join")
        lane = self.action("sup", "open-lane", "--title", "Feature", "--goal", "Deliver")
        self.action("sup", "patrol")
        with desk.ledger_for(self.root) as saved:
            old = saved["lanes"][lane["id"]]["watcher"]
        self.agents[old]["Cwd"] = str(self.root)
        with self.assertRaises(ValueError):
            self.action("sup", "retire-watcher", "--lane", lane["id"])
        self.agents[old]["Status"] = "idle"
        self.action("sup", "retire-watcher", "--lane", lane["id"])
        self.assertEqual(self.agents[old]["Status"], "archived")
        self.action("sup", "patrol")
        with desk.ledger_for(self.root) as saved:
            new = saved["lanes"][lane["id"]]["watcher"]
        self.assertNotEqual(old, new)
        self.action(new, "raise", "--text", "Workspace verified")

    def test_watcher_alert_routes_to_supervisor_and_lead_without_veto(self):
        self.action("sup", "join")
        lane = self.action("sup", "open-lane", "--title", "Feature", "--goal", "Deliver feature")
        self.action("sup", "patrol")
        self.assertIn("--workspace", self.runs[-1])
        self.assertEqual(self.runs[-1][self.runs[-1].index("--workspace") + 1], "lane-workspace")
        with desk.ledger_for(self.root) as saved:
            watcher = saved["lanes"][lane["id"]]["watcher"]
        raised = self.action(watcher, "raise", "--text", "Peer appears blocked; observed idle")
        self.assertEqual(raised["lane"], lane["id"])
        with desk.ledger_for(self.root) as saved:
            self.assertEqual(saved["lanes"][lane["id"]]["status"], "open")
            self.assertEqual({letter["to"] for letter in saved["outbox"]}, {"sup", lane["lead"]})

    def test_delayed_rework_is_discarded_after_new_handback(self):
        self.action("sup", "join")
        lane = self.action("sup", "open-lane", "--title", "Feature", "--goal", "Deliver")
        task = self.action(lane["lead"], "start-task", "--lane", lane["id"], "--title", "Do", "--goal", "Implement")
        self.action(task["peer"], "done", "--task", task["id"], "--summary", "First", "--checks", "pass")
        self.action(lane["lead"], "rework", "--task", task["id"], "--feedback", "Fix")
        self.action(task["peer"], "done", "--task", task["id"], "--round", "2", "--candidate", "candidate-b", "--summary", "Second", "--checks", "pass")
        self.action(lane["lead"], "start-review", "--task", task["id"], "--focus", "Inspect")
        self.agents[task["peer"]]["Status"] = "idle"
        self.agents[lane["lead"]]["Status"] = "idle"
        self.action("sup", "patrol")
        self.assertFalse(any(task["peer"] in args for args in self.sent))
        with desk.ledger_for(self.root) as saved:
            mail = next(m for m in saved["outbox"] if m["to"] == task["peer"])
            self.assertEqual(mail["status"], "superseded")
            self.assertEqual(saved["tasks"][task["id"]]["candidate"], "candidate-b")
        self.assertFalse(any("First" in args[-1] for args in self.sent))

    def test_current_rework_is_delivered_once_and_old_round_cannot_finish(self):
        self.action("sup", "join")
        lane = self.action("sup", "open-lane", "--title", "Feature", "--goal", "Deliver")
        task = self.action(lane["lead"], "start-task", "--lane", lane["id"], "--title", "Do", "--goal", "Implement")
        self.action(task["peer"], "done", "--task", task["id"], "--summary", "First", "--checks", "pass")
        self.action(lane["lead"], "rework", "--task", task["id"], "--feedback", "Fix")
        self.agents[task["peer"]]["Status"] = "idle"
        self.action("sup", "patrol")
        self.action("sup", "patrol")
        self.assertEqual(sum(task["peer"] in args for args in self.sent), 1)
        self.assertIn("--round 2", next(args[-1] for args in self.sent if task["peer"] in args))
        with self.assertRaisesRegex(PermissionError, "round"):
            self.action(task["peer"], "done", "--task", task["id"], "--summary", "Late", "--checks", "pass")

    def test_old_reviewer_and_wrong_candidate_cannot_finish_current_review(self):
        self.action("sup", "join")
        lane = self.action("sup", "open-lane", "--title", "Feature", "--goal", "Deliver")
        task = self.action(lane["lead"], "start-task", "--lane", lane["id"], "--title", "Do", "--goal", "Implement")
        self.action(task["peer"], "done", "--task", task["id"], "--summary", "First", "--checks", "pass")
        first = self.action(lane["lead"], "start-review", "--task", task["id"], "--focus", "Inspect")
        self.action(first["reviewer"], "done", "--task", task["id"], "--summary", "Findings", "--checks", "pass")
        second = self.action(lane["lead"], "start-review", "--task", task["id"], "--focus", "Inspect again")
        with self.assertRaises(PermissionError):
            self.action(first["reviewer"], "done", "--task", task["id"], "--summary", "Late", "--checks", "pass")
        with self.assertRaisesRegex(PermissionError, "candidate"):
            self.action(second["reviewer"], "done", "--task", task["id"], "--candidate", "candidate-b", "--summary", "Wrong", "--checks", "pass")
        result = self.action(second["reviewer"], "done", "--task", task["id"], "--summary", "Current", "--checks", "pass")
        self.assertEqual(result["verdict"], "Current")
        self.assertIn("candidate-a", self.runs[-1][-1])

    def test_rework_supersedes_running_review_without_reusing_its_evidence(self):
        self.action("sup", "join")
        lane = self.action("sup", "open-lane", "--title", "Feature", "--goal", "Deliver")
        task = self.action(lane["lead"], "start-task", "--lane", lane["id"], "--title", "Do", "--goal", "Implement")
        self.action(task["peer"], "done", "--task", task["id"], "--summary", "First", "--checks", "pass")
        first = self.action(lane["lead"], "start-review", "--task", task["id"], "--focus", "Inspect")
        self.action(lane["lead"], "rework", "--task", task["id"], "--feedback", "Fix")
        self.action(task["peer"], "done", "--task", task["id"], "--round", "2", "--candidate", "candidate-b", "--summary", "Second", "--checks", "pass")
        self.action(lane["lead"], "start-review", "--task", task["id"], "--focus", "Inspect second")
        with self.assertRaisesRegex(PermissionError, "round"):
            self.action(first["reviewer"], "done", "--task", task["id"], "--summary", "Late", "--checks", "pass")
        with desk.ledger_for(self.root) as saved:
            current = saved["tasks"][task["id"]]
            self.assertEqual(current["review_status"], "running")
            self.assertEqual([h["candidate"] for h in current["handbacks"]], ["candidate-a", "candidate-b"])

    def test_ambiguous_workspace_does_not_launch_a_watcher(self):
        self.action("sup", "join")
        lane = self.action("sup", "open-lane", "--title", "Feature", "--goal", "Deliver")
        def ambiguous(command, *args):
            if command == "workspace":
                return [{"workspaceId": "one", "cwd": lane["cwd"]}, {"workspaceId": "two", "cwd": lane["cwd"]}]
            return self.paseo(command, *args)
        with patch.object(desk, "paseo", side_effect=ambiguous):
            self.action("sup", "patrol")
        self.assertEqual(len(self.runs), 1)
        with desk.ledger_for(self.root) as saved:
            self.assertIsNone(saved["lanes"][lane["id"]]["watcher"])
            self.assertIn("ambiguous", saved["events"][-1]["reason"])

    def test_uncertain_mail_is_not_delivered_twice(self):
        self.action("sup", "join")
        lane = self.action("sup", "open-lane", "--title", "Feature", "--goal", "Deliver feature")
        lead = lane["lead"]
        with desk.ledger_for(self.root) as saved:
            desk.queue(saved, lead, "Important hand-back")
        self.agents[lead]["Status"] = "idle"
        def fail_send(command, *args):
            if command == "send":
                raise TimeoutError("outcome unknown")
            return self.paseo(command, *args)
        with patch.object(desk, "paseo", side_effect=fail_send):
            self.action("sup", "patrol")
        self.action("sup", "patrol")
        with desk.ledger_for(self.root) as saved:
            self.assertEqual(saved["outbox"][0]["status"], "uncertain")
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
