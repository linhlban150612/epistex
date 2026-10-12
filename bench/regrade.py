#!/usr/bin/env python3
"""Re-grade a saved run against the current graders (no API calls).

Turn semantics preserved: a trial passes at the first turn whose output passes
the (possibly updated) grader; turns_used is taken from the recorded trace.
Usage: python3 bench/regrade.py <results.jsonl> <new_label>
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import graders  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent


def main(path: str, new_label: str):
    tasks = {t["id"]: t for t in json.loads((HERE / "tasks" / "tasks.json").read_text())["tasks"]}
    recs = [json.loads(l) for l in open(path)]
    run = next(r for r in recs if "_run" in r)["_run"]
    out_path = pathlib.Path(path).with_name(
        pathlib.Path(path).name.replace(pathlib.Path(path).name.split("_")[0], new_label, 1)
    )
    n_first = n_event = n_total = 0
    with open(out_path, "w") as fh:
        fh.write(json.dumps({"_run": {**run, "regraded_from": str(path), "label": new_label}}) + "\n")
        for r in recs:
            if "_run" in r or "_summary" in r:
                continue
            passed_at = None
            failed_checks = []
            for i, out in enumerate(r["outputs"]):
                ok, fc = graders.grade(tasks[r["task_id"]], out)
                if ok:
                    passed_at = i + 1
                    failed_checks = []
                    break
                failed_checks = fc
            n_total += 1
            if passed_at == 1:
                n_first += 1
            if passed_at:
                n_event += 1
            rec = dict(r)
            rec["passed_first"] = passed_at == 1
            rec["passed_eventual"] = passed_at is not None
            rec["failed_checks"] = failed_checks
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        summary = {
            "label": new_label,
            "regraded_from": str(path),
            "task_trials": n_total,
            "first_pass_rate": round(n_first / n_total, 4),
            "eventual_success_rate": round(n_event / n_total, 4),
        }
        fh.write(json.dumps({"_summary": summary}) + "\n")
    print(json.dumps(summary, indent=1), "->", out_path)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
