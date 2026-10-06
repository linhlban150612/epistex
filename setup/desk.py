#!/usr/bin/env python3
"""Standalone Paseo desk: durable role routing, handbacks, mail and patrol."""

import argparse
import contextlib
import copy
import fcntl
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOME = pathlib.Path(os.environ.get("EPISTEX_STATE_HOME") or os.environ.get("SEATWORKS_STATE_HOME")
                    or pathlib.Path.home() / ".local/share/epistex/desk")
AGENTS = ("claude", "codex", "devin", "pi", "amp", "glm", "droid")


def paseo(*args):
    result = subprocess.run([os.environ.get("PASEO_BIN", "paseo"), *args], capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError(f"Paseo {args[0]} failed: {result.stderr.strip() or result.stdout.strip()}")
    return json.loads(result.stdout)


def save(path, value):
    fd, name = tempfile.mkstemp(prefix="ledger-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def project_path(args):
    root = pathlib.Path(args.project or os.environ.get("EPISTEX_PROJECT_ROOT")
                        or os.environ.get("SEATWORKS_PROJECT_ROOT") or os.getcwd()).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("project must be a directory")
    return root


@contextlib.contextmanager
def ledger_for(root):
    state = HOME / hashlib.sha256(str(root).encode()).hexdigest()[:16]
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / "lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = state / "ledger.json"
        data = json.loads(path.read_text()) if path.exists() else {
            "project": str(root), "seq": 0, "agents": {}, "lanes": {}, "tasks": {},
            "asks": {}, "outbox": [], "events": [],
        }
        if data["project"] != str(root):
            raise RuntimeError("project identity mismatch")
        try:
            yield data
        finally:
            save(path, data)


def event(data, kind, **fields):
    data["events"].append({"at": time.time(), "kind": kind, **fields})


def caller(data, required=None):
    agent_id = os.environ.get("PASEO_AGENT_ID")
    if not agent_id:
        raise PermissionError("PASEO_AGENT_ID is required; run from a Paseo agent")
    agent = paseo("inspect", agent_id, "--json")
    provider = agent["Provider"].split("/")[0]
    if provider not in {f"epx-{role}-{backend}" for role in ("supervisor", "lead", "peer") for backend in AGENTS}:
        raise PermissionError("caller does not have an Epistex role provider")
    role = provider.split("-")[1]
    if required and role != required:
        raise PermissionError(f"only {required} can run this command")
    registered = data["agents"].get(agent_id)
    if registered and (registered["role"] != role or registered["provider"] != provider):
        raise PermissionError("agent role does not match ledger")
    if not registered and role != "supervisor":
        raise PermissionError("agent is not registered; a Supervisor must open its lane")
    expected = data["lanes"].get(registered.get("lane"), {}).get("cwd") if registered else data["project"]
    if pathlib.Path(agent["Cwd"]).resolve() != pathlib.Path(expected or data["project"]).resolve():
        raise PermissionError("agent is not in its recorded project or lane working copy")
    return agent_id, role, provider


def next_id(data, prefix):
    data["seq"] += 1
    return f"{prefix}{data['seq']}"


def queue(data, to, message, scope=None):
    data["outbox"].append({"id": next_id(data, "M"), "to": to, "text": message, "status": "pending", "at": time.time(), "scope": scope})


def launch(data, root, role, backend, title, prompt, cwd, lane=None, task=None, worktree=False):
    if backend not in AGENTS:
        raise ValueError("unknown agent backend")
    workspace = None
    if lane and not worktree:
        record = data["lanes"][lane]
        workspace = record.get("workspace")
        if not workspace:
            matches = [w["workspaceId"] for w in paseo("workspace", "ls", "--json")
                       if pathlib.Path(w["cwd"]).resolve() == pathlib.Path(cwd).resolve()]
            if len(matches) != 1:
                raise RuntimeError("lane workspace is absent or ambiguous; inspect Paseo before launching")
            workspace = record["workspace"] = matches[0]
    launch_id = next_id(data, "P")
    pending = {"id": launch_id, "role": role, "provider": f"epx-{role}-{backend}", "lane": lane,
               "task": task, "status": "launching"}
    data["agents"][launch_id] = pending
    # Persist before an external side effect: an interrupted launch must never be retried blindly.
    state = HOME / hashlib.sha256(str(root).encode()).hexdigest()[:16]
    save(state / "ledger.json", data)
    command = ["run", "--json", "--background", "--provider", pending["provider"], "--cwd", str(cwd),
               "--title", title, "--env", f"EPISTEX_PROJECT_ROOT={root}", "--label", f"epistex-launch={launch_id}"]
    if worktree:
        command += ["--new-workspace", "worktree", "--worktree-mode", "branch-off", "--worktree-slug", f"epistex-{launch_id.lower()}"]
    elif workspace:
        command += ["--workspace", workspace]
    try:
        created = paseo(*command, prompt)
    except Exception as error:
        pending["status"] = "uncertain"
        event(data, "launch.uncertain", launch=launch_id, reason=str(error))
        raise RuntimeError(f"launch {launch_id} may have succeeded; inspect Paseo before retrying: {error}") from error
    agent_id = created["agentId"]
    pending["status"] = "ready"
    pending["id"] = agent_id
    data["agents"][agent_id] = pending
    del data["agents"][launch_id]
    return agent_id


def need(data, agent_id, role):
    if data["agents"].get(agent_id, {}).get("role") != role:
        raise PermissionError(f"caller is not the assigned {role}")


def act(args, root, data):
    if args.action == "status":
        return {key: data[key] for key in ("project", "lanes", "tasks", "asks", "outbox", "agents")}
    agent_id, role, provider = caller(data, {"join": "supervisor", "open-lane": "supervisor",
                                       "start-task": "lead", "accept": "lead",
                                       "rework": "lead", "close-lane": "supervisor", "upgrade": "supervisor"}.get(args.action))
    if args.action == "join":
        data["agents"].setdefault(agent_id, {"id": agent_id, "role": role, "provider": provider, "status": "ready"})
        event(data, "supervisor.joined", agent=agent_id)
        return {"supervisor": agent_id, "project": str(root)}
    if args.action == "upgrade":
        if agent_id not in data["agents"]:
            raise PermissionError("join as Supervisor first")
        upgraded = []
        for task in data["tasks"].values():
            if "round" not in task:
                task["legacy"] = copy.deepcopy(task)
                task.update(round=1)
                upgraded.append(task["id"])
        quarantined = []
        for letter in data["outbox"]:
            if "scope" not in letter and letter["status"] == "pending":
                letter["status"] = "quarantined"
                quarantined.append(letter["id"])
        if upgraded or quarantined:
            event(data, "ledger.upgraded", by=agent_id, tasks=upgraded, letters=quarantined)
        return {"upgraded": upgraded, "quarantined": quarantined,
                "note": "No work was resumed. Brief active Peers with their round; handed-back legacy tasks need rework before candidate-bound review."}
    if args.action == "open-lane":
        if agent_id not in data["agents"]:
            raise PermissionError("join as Supervisor first")
        lane_id = next_id(data, "L")
        lane = {"id": lane_id, "title": args.title, "goal": args.goal, "status": "launching",
                "opener": agent_id, "cwd": str(root), "lead": None}
        data["lanes"][lane_id] = lane
        prompt = f"You are Lead for {lane_id}: {args.goal}\nRun $EPISTEX_DESK status --project {root} and use its desk commands."
        lead = launch(data, root, "lead", args.agent, args.title, prompt, root, lane=lane_id, worktree=True)
        lane["lead"] = lead
        lane["cwd"] = paseo("inspect", lead, "--json")["Cwd"]
        lane["status"] = "open"
        event(data, "lane.opened", lane=lane_id, lead=lead)
        return lane
    if args.action == "start-task":
        lane = data["lanes"][args.lane]
        need(data, agent_id, "lead")
        if lane["lead"] != agent_id or lane["status"] != "open":
            raise PermissionError("not the active Lead for this lane")
        if any(task["lane"] == args.lane and task["status"] not in ("accepted", "cut")
               for task in data["tasks"].values()):
            raise ValueError("one writer per lane: accept or cut the current task first")
        task_id = next_id(data, "T")
        task = {"id": task_id, "lane": args.lane, "title": args.title, "goal": args.goal,
                "owned": args.owned, "status": "launching", "peer": None, "summary": None, "round": 1, "handbacks": []}
        data["tasks"][task_id] = task
        brief = f"Task {task_id} in lane {args.lane}, round 1. Goal: {args.goal}\nOwned paths: {', '.join(args.owned) or 'as explicitly agreed with Lead'}.\nWhen finished call $EPISTEX_DESK done --task {task_id} --round 1 --candidate <full-commit-SHA-or-snapshot-checksum> --summary ... --checks ... . Then stop writing; resume only for a current desk rework round."
        peer = launch(data, root, "peer", args.agent, args.title, brief, lane["cwd"], lane=args.lane, task=task_id)
        task.update(peer=peer, status="running")
        event(data, "task.started", task=task_id, peer=peer)
        return task
    if args.action == "done":
        task = data["tasks"][args.task]
        if args.round is None or args.round != task.get("round"):
            raise PermissionError("handback round is missing or no longer current; inspect desk status")
        if not args.candidate or not args.candidate.strip():
            raise ValueError("handback requires an immutable candidate identifier")
        if role == "peer" and task["peer"] == agent_id and task["status"] in ("running", "rework"):
            task.update(status="done", summary=args.summary, checks=args.checks, candidate=args.candidate)
        else:
            raise PermissionError("no active task assigned to this agent")
        task.setdefault("handbacks", []).append({"round": args.round, "candidate": args.candidate, "by": agent_id,
                                                 "role": role, "summary": args.summary, "checks": args.checks})
        scope = {"task": task["id"], "round": args.round, "status": "done", "candidate": args.candidate}
        queue(data, data["lanes"][task["lane"]]["lead"], f"{role.title()} hand-back on {task['id']} round {args.round}, candidate {args.candidate}: {args.summary}; checks: {args.checks}. Review evidence before acceptance.", scope)
        event(data, f"{role}.done", task=task["id"], by=agent_id, round=args.round, candidate=args.candidate)
        return task
    if args.action in ("accept", "rework"):
        task = data["tasks"][args.task]
        lane = data["lanes"][task["lane"]]
        if lane["lead"] != agent_id or lane["status"] != "open":
            raise PermissionError("not the active Lead for this task")
        if args.action == "accept":
            if task["status"] != "done":
                raise ValueError("task is not handed back")
            if paseo("inspect", task["peer"], "--json")["Status"] != "idle":
                raise ValueError("Peer must finish its turn before acceptance can release the writer slot")
            # A completed Peer may be prompted again unless it is archived before another writer starts.
            try:
                paseo("archive", task["peer"], "--json")
            except Exception as error:
                task["status"] = "accept_uncertain"
                raise RuntimeError(f"Peer archive may have succeeded; inspect {task['peer']} before accepting again: {error}") from error
            task["status"] = "accepted"
            event(data, "task.accepted", task=task["id"], by=agent_id)
            return task
        if task["status"] != "done":
            raise ValueError("rework requires a handed-back task")
        task["status"] = "rework"
        task["round"] = task.get("round", 0) + 1
        task["idle_notified"] = False
        queue(data, task["peer"], f"Rework {task['id']} round {task['round']}: {args.feedback}. Before writing, check desk status: only this current rework round authorizes work. Hand back with desk done --task {task['id']} --round {task['round']} --candidate <full-commit-SHA-or-snapshot-checksum> --summary ... --checks ...; then stop writing.",
              {"task": task["id"], "round": task["round"], "status": "rework"})
        event(data, "task.rework", task=task["id"], by=agent_id, round=task["round"])
        return task
    if args.action == "close-lane":
        lane = data["lanes"][args.lane]
        if lane["opener"] != agent_id or lane["status"] != "open":
            raise PermissionError("not the opener of this open lane")
        if any(t["lane"] == args.lane and t["status"] not in ("accepted", "cut") for t in data["tasks"].values()):
            raise ValueError("unfinished task: close refused")
        lane["status"] = "closed"
        event(data, "lane.closed", lane=args.lane, by=agent_id)
        return {"lane": args.lane, "status": "closed", "note": "No merge or land was performed; Human owns that decision."}
    if args.action == "ask":
        assigned = data["agents"].get(agent_id, {})
        lane = data["lanes"].get(assigned.get("lane"))
        to = lane["lead"] if role == "peer" and lane else lane["opener"] if role == "lead" and lane else None
        if not to:
            raise ValueError("no recipient in the ledger")
        ask_id = next_id(data, "Q")
        data["asks"][ask_id] = {"id": ask_id, "from": agent_id, "to": to, "question": args.question, "status": "open"}
        queue(data, to, f"Question {ask_id} from {role}: {args.question}. Answer via $EPISTEX_DESK answer --ask {ask_id} --text ...")
        return data["asks"][ask_id]
    if args.action == "answer":
        ask = data["asks"][args.ask]
        if ask["to"] != agent_id or ask["status"] != "open":
            raise PermissionError("not the recipient of an open question")
        ask.update(status="answered", answer=args.text)
        queue(data, ask["from"], f"Answer {args.ask}: {args.text}")
        return ask
    raise ValueError("unknown action")


def patrol(root, data):
    if any("round" not in task for task in data["tasks"].values()) or any(
            "scope" not in letter and letter["status"] == "pending" for letter in data["outbox"]):
        raise RuntimeError("legacy state requires Supervisor desk upgrade before patrol; no mail sent")
    for agent in data["agents"].values():
        if agent["status"] == "launching":
            agent["status"] = "uncertain"
    for letter in data["outbox"]:
        if letter["status"] == "sending":
            letter["status"] = "uncertain"
    for lane in data["lanes"].values():
        if lane["status"] == "open" and lane.get("lead") and not lane.get("lead_failed_notified"):
            try:
                state = paseo("inspect", lane["lead"], "--json")["Status"]
                if state in ("error", "archived"):
                    lane["lead_failed_notified"] = True
                    queue(data, lane["opener"], f"Lead {lane['lead']} is {state} on {lane['id']}. Inspect before taking action; the desk will not silently replace it.")
            except Exception:
                pass
    for task in data["tasks"].values():
        if task["status"] != "running" or task.get("idle_notified") or not task.get("peer"):
            continue
        try:
            state = paseo("inspect", task["peer"], "--json")["Status"]
            if state in ("idle", "error"):
                task["idle_notified"] = True
                queue(data, data["lanes"][task["lane"]]["lead"], f"Peer {task['peer']} is {state} without desk done on {task['id']}. Inspect its work; do not infer acceptance.")
        except Exception:
            pass
    for letter in data["outbox"]:
        if letter["status"] != "pending":
            continue
        scope = letter.get("scope")
        if scope:
            task = data["tasks"].get(scope["task"], {})
            if any(task.get(key) != value for key, value in scope.items() if key != "task"):
                letter["status"] = "superseded"
                event(data, "mail.superseded", letter=letter["id"])
                continue
        try:
            state = paseo("inspect", letter["to"], "--json")["Status"]
            if state != "idle":
                continue
            # A timeout after sending is uncertain: mark it, never send a duplicate automatically.
            letter["status"] = "sending"
            save(HOME / hashlib.sha256(str(root).encode()).hexdigest()[:16] / "ledger.json", data)
            paseo("send", "--json", "--no-wait", letter["to"], f"[Epistex desk {letter['id']}] {letter['text']}")
            letter["status"] = "sent"
            event(data, "mail.sent", letter=letter["id"])
        except Exception as error:
            letter["status"] = "uncertain" if letter["status"] == "sending" else "pending"
            letter["error"] = str(error)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("join", "upgrade", "open-lane", "start-task", "done", "accept", "rework", "close-lane", "ask", "answer", "status", "patrol"))
    p.add_argument("--project")
    p.add_argument("--lane")
    p.add_argument("--task")
    p.add_argument("--title")
    p.add_argument("--goal")
    p.add_argument("--agent", choices=AGENTS, default="codex")
    p.add_argument("--owned", action="append", default=[])
    p.add_argument("--summary")
    p.add_argument("--checks")
    p.add_argument("--round", type=int)
    p.add_argument("--candidate")
    p.add_argument("--feedback")
    p.add_argument("--question")
    p.add_argument("--ask")
    p.add_argument("--text")
    return p


def main():
    args = parser().parse_args()
    needed = {"open-lane": ("title", "goal"), "start-task": ("lane", "title", "goal"),
              "done": ("task", "round", "candidate", "summary", "checks"),
              "accept": ("task",), "rework": ("task", "feedback"), "close-lane": ("lane",),
              "ask": ("question",), "answer": ("ask", "text")}
    for key in needed.get(args.action, ()):
        if not getattr(args, key):
            raise ValueError(f"{args.action} requires --{key}")
    if args.action == "patrol" and not args.project:
        results = []
        for path in HOME.glob("*/ledger.json"):
            root = pathlib.Path(json.loads(path.read_text())["project"])
            if root.is_dir():
                with ledger_for(root) as data:
                    patrol(root, data)
                results.append(str(root))
        result = {"patrolled": results}
    else:
        root = project_path(args)
        with ledger_for(root) as data:
            result = patrol(root, data) if args.action == "patrol" else act(args, root, data)
    print(json.dumps(result if result is not None else {"ok": True}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, PermissionError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"desk: {error}", file=sys.stderr)
        sys.exit(1)
