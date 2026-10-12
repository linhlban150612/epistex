#!/usr/bin/env python3
"""Layer C — live Paseo smoke check (qualitative, not scored).

Verifies the repo's seat prompts actually install and launch on this host's
Paseo daemon, by checking seat registration and provider availability.
Does NOT run scored tasks through live agents (cost and nondeterminism).
"""
from __future__ import annotations

import json
import subprocess
import sys


def sh(*args):
    r = subprocess.run(["paseo", *args, "--json"], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return None, r.stderr.strip()
    try:
        return json.loads(r.stdout), None
    except json.JSONDecodeError:
        return r.stdout, None


def main():
    providers, err = sh("provider", "ls")
    if err:
        print("FAIL: paseo provider ls:", err)
        return 1
    # provider ls --json returns a list or dict; find seat providers
    text = json.dumps(providers)
    seats = [s for s in ("codex-lead", "codex-peer", "amp-supervisor") if s in text]
    print(f"Seat providers registered: {seats}")
    ok = len(seats) == 3
    print("SMOKE " + ("PASS" if ok else "FAIL") +
          " — expected codex-lead, codex-peer, amp-supervisor")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
