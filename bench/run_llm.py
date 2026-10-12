#!/usr/bin/env python3
"""Epistex protocol-compliance benchmark runner (Layer B).

Runs the frozen task suite against a pinned OpenRouter model with the repo's
LEAD.md / PEER.md as the system prompt, grades deterministically, simulates
the rework loop (max 2 rework rounds, mirroring LEAD.md's rework cap), and
records per-trial traces + aggregate metrics as JSONL.

Usage:
  python3 bench/run_llm.py --label baseline --trials 3 \
      [--model deepseek/deepseek-chat-v3.1] [--agents-dir agents] [--out bench/results]

Reads OPENROUTER_API_KEY from the environment, falling back to the shared
workspace .env of the telegram-hackathon-bot project (per user convention).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys
import time
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent

DEFAULT_MODEL = os.environ.get("EPX_BENCH_MODEL", "deepseek/deepseek-chat-v3.1")
FALLBACK_ENV = [
    pathlib.Path("/root/.hermes/workspace/packs/tgbot/telegram-hackathon-bot-main/.env"),
]

PRICES = {  # USD per 1M tokens (input, output) — OpenRouter listed prices, Oct 2026
    "deepseek/deepseek-chat-v3.1": (0.28, 0.42),
    "z-ai/glm-4.6": (0.60, 2.20),
    "openai/gpt-4.1-mini": (0.40, 1.60),
}


def load_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    for f in FALLBACK_ENV:
        if f.exists():
            m = re.search(r"^OPENROUTER_API_KEY=(\S+)", f.read_text(), re.M)
            if m:
                return m.group(1)
    sys.exit("OPENROUTER_API_KEY not found in env or fallback .env files")


def chat(model: str, system: str, user: str, temperature: float, seed: int, key: str):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "seed": seed,
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.load(r)
    latency = time.monotonic() - t0
    msg = data["choices"][0]["message"]
    usage = data.get("usage", {})
    return {
        "output": msg.get("content") or "",
        "latency_s": round(latency, 3),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "model_reported": data.get("model"),
        "finish_reason": data["choices"][0].get("finish_reason"),
    }


def system_prompt(role: str, agents_dir: pathlib.Path) -> str:
    fname = {"lead": "LEAD.md", "peer": "PEER.md"}[role]
    return (agents_dir / fname).read_text()


def user_prompt(task: dict) -> str:
    return f"Scenario:\n{task['scenario']}\n\n{task['instruction']}"


def run_suite(args):
    import graders  # noqa: sys.path trick below

    sys.path.insert(0, str(HERE))
    import graders  # noqa: F811

    tasks = json.loads((HERE / "tasks" / "tasks.json").read_text())["tasks"]
    key = load_key()
    agents_dir = pathlib.Path(args.agents_dir)
    results_dir = pathlib.Path(args.out)
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_file = results_dir / f"{args.label}_{stamp}.jsonl"
    price_in, price_out = PRICES.get(args.model, (None, None))

    env_note = {
        "runner": "bench/run_llm.py",
        "suite_version": "epistex-bench-1.0",
        "label": args.label,
        "model_requested": args.model,
        "temperature": args.temperature,
        "trials_per_task": args.trials,
        "rework_cap": 2,
        "agents_dir": str(agents_dir),
        "repo_head": os.popen("git rev-parse HEAD").read().strip(),
        "recorded_at": stamp,
    }
    print(json.dumps(env_note))
    with open(run_file, "w") as fh:
        fh.write(json.dumps({"_run": env_note}) + "\n")

    agg = {
        "attempts": 0, "first_pass": 0, "eventual_pass": 0, "rework_turns": 0,
        "tokens_in": 0, "tokens_out": 0, "latency_s": 0.0, "cost_usd": 0.0,
        "per_task": {},
    }
    for task in tasks:
        per_task = {"first_pass": 0, "eventual_pass": 0, "attempts_list": [], "tokens": 0}
        for trial in range(1, args.trials + 1):
            system = system_prompt(task["role"], agents_dir)
            user = user_prompt(task)
            seed = 1000 + trial
            turns = []
            passed, failed_checks = False, []
            for attempt in range(1, 4):  # initial + 2 rework rounds
                resp = chat(args.model, system, user, args.temperature, seed + attempt, key)
                turns.append(resp)
                agg["attempts"] += 1
                agg["tokens_in"] += resp["prompt_tokens"] or 0
                agg["tokens_out"] += resp["completion_tokens"] or 0
                agg["latency_s"] += resp["latency_s"]
                if price_in:
                    agg["cost_usd"] += (
                        (resp["prompt_tokens"] or 0) * price_in
                        + (resp["completion_tokens"] or 0) * price_out
                    ) / 1e6
                passed, failed_checks = graders.grade(task, resp["output"])
                if passed:
                    if attempt == 1:
                        per_task["first_pass"] += 1
                        agg["first_pass"] += 1
                    per_task["eventual_pass"] += 1
                    agg["eventual_pass"] += 1
                    break
                if attempt < 3:
                    agg["rework_turns"] += 1
                    user = graders.feedback_from(failed_checks, task)
            per_task["attempts_list"].append(len(turns))
            per_task["tokens"] += sum(t["completion_tokens"] or 0 for t in turns)
            rec = {
                "task_id": task["id"], "capability": task["capability"],
                "role": task["role"], "trial": trial, "passed_first": len(turns) == 1 and passed,
                "passed_eventual": passed, "turns_used": len(turns),
                "failed_checks": failed_checks,
                "outputs": [t["output"] for t in turns],
                "usage": [
                    {k: t[k] for k in ("latency_s", "prompt_tokens", "completion_tokens",
                                       "model_reported", "finish_reason")}
                    for t in turns
                ],
            }
            with open(run_file, "a") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        agg["per_task"][task["id"]] = per_task
        print(f"  {task['id']}: first-pass {per_task['first_pass']}/{args.trials}, "
              f"eventual {per_task['eventual_pass']}/{args.trials}")

    n_total = args.trials * len(tasks)
    summary = {
        "label": args.label, "model": args.model,
        "task_trials": n_total,
        "first_pass_rate": round(agg["first_pass"] / n_total, 4),
        "eventual_success_rate": round(agg["eventual_pass"] / n_total, 4),
        "rework_rate": round(agg["rework_turns"] / max(agg["attempts"], 1), 4),
        "avg_turns_per_trial": round(agg["attempts"] / n_total, 3),
        "total_latency_s": round(agg["latency_s"], 1),
        "tokens_in": agg["tokens_in"], "tokens_out": agg["tokens_out"],
        "cost_usd": round(agg["cost_usd"], 4) if price_in else None,
        "cost_per_successful_trial": round(agg["cost_usd"] / max(agg["eventual_pass"], 1), 4)
        if price_in else None,
        "per_task": agg["per_task"],
        "results_file": str(run_file),
    }
    with open(run_file, "a") as fh:
        fh.write(json.dumps({"_summary": summary}) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "per_task"}, indent=1))
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--label", required=True)
    p.add_argument("--trials", type=int, default=3)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--agents-dir", default=str(REPO / "agents"))
    p.add_argument("--out", default=str(HERE / "results"))
    run_suite(p.parse_args())


if __name__ == "__main__":
    main()
