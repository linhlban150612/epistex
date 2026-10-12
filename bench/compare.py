#!/usr/bin/env python3
"""Paired comparison of two bench runs (baseline vs candidate).

Reads the two JSONL result files, aligns trials by (task_id, trial), and
prints per-task paired outcomes plus aggregate deltas. Flags regressions.
"""
from __future__ import annotations

import json
import pathlib
import sys
from collections import defaultdict


def load(path: pathlib.Path):
    trials = {}
    summary = None
    for line in path.read_text().splitlines():
        rec = json.loads(line)
        if "_summary" in rec:
            summary = rec["_summary"]
        elif "_run" not in rec:
            trials[(rec["task_id"], rec["trial"])] = rec
    return trials, summary


def main(a_path: str, b_path: str):
    a, a_sum = load(pathlib.Path(a_path))
    b, b_sum = load(pathlib.Path(b_path))
    keys = sorted(set(a) & set(b))
    paired = defaultdict(lambda: [0, 0, 0, 0])  # task: [both_pass, a_only, b_only, none]
    for k in keys:
        t = k[0]
        pa, pb = a[k]["passed_eventual"], b[k]["passed_eventual"]
        if pa and pb:
            paired[t][0] += 1
        elif pa and not pb:
            paired[t][1] += 1
        elif pb and not pa:
            paired[t][2] += 1
        else:
            paired[t][3] += 1
    print(f"A = {a_sum['label']}: first_pass {a_sum['first_pass_rate']:.2%}, "
          f"eventual {a_sum['eventual_success_rate']:.2%}, "
          f"cost ${a_sum.get('cost_usd')}, turns/trial {a_sum.get('avg_turns_per_trial')}")
    print(f"B = {b_sum['label']}: first_pass {b_sum['first_pass_rate']:.2%}, "
          f"eventual {b_sum['eventual_success_rate']:.2%}, "
          f"cost ${b_sum.get('cost_usd')}, turns/trial {b_sum.get('avg_turns_per_trial')}")
    print(f"\nPaired per-task (eventual pass), {len(keys)} trials:")
    regressions = []
    for t in sorted(paired):
        bp, ao, bo, nn = paired[t]
        marker = "="
        if ao:
            marker = "REGRESSION (A-only pass)"
            regressions.append(t)
        elif bo:
            marker = "IMPROVED (B-only pass)"
        print(f"  {t:24s} both={bp} a_only={ao} b_only={bo} none={nn}  {marker}")
    n = len(keys)
    d_fp = b_sum["first_pass_rate"] - a_sum["first_pass_rate"]
    d_ev = b_sum["eventual_success_rate"] - a_sum["eventual_success_rate"]
    print(f"\nDelta first-pass: {d_fp:+.2%} | Delta eventual: {d_ev:+.2%} | "
          f"Cost delta: ${(b_sum.get('cost_usd') or 0) - (a_sum.get('cost_usd') or 0):+.4f}")
    if regressions:
        print(f"⚠ REGRESSIONS: {regressions}")
    else:
        print("No regressions on paired trials.")
    return 0 if not regressions else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
