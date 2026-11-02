import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { classifyHandoff, parseHandoff, splitLines } from "./handoff.ts";

const ROOT = path.resolve(import.meta.dirname, "../../..");
const FIXTURES = path.join(ROOT, "tests/fixtures/handoffs");
const CHECK_HANDOFF = path.join(ROOT, "setup/check-handoff");

function fixture(name: string): string {
  return readFileSync(path.join(FIXTURES, name), "utf8");
}

test("parity: every fixture classifies identically in TypeScript and setup/check-handoff", () => {
  const names = readdirSync(FIXTURES).filter((name) => name.endsWith(".txt")).sort();
  assert.ok(names.length >= 5, `fixtures: ${names.join(", ")}`);
  for (const name of names) {
    const python = JSON.parse(
      execFileSync("python3", [CHECK_HANDOFF, "--parse-only", path.join(FIXTURES, name), "--json"], {
        encoding: "utf8",
        stdio: ["ignore", "pipe", "pipe"],
      }),
    );
    assert.deepEqual(classifyHandoff(fixture(name)), python, name);
  }
});

test("valid.txt: header, six cells, two SHAs", () => {
  const result = classifyHandoff(fixture("valid.txt"));
  assert.equal(result.valid, true);
  assert.deepEqual(result.header, { task: "T-1", round: "1" });
  assert.deepEqual(Object.keys(result.cells), ["Outcome", "Candidate", "Scope", "Verification", "Unknown / risk", "Ownership"]);
  assert.equal(result.cells.Verification, "`true` exit 0\noutput: (none)");
  assert.deepEqual(result.shas, [
    "3f2a9c1d4e5b6a7f8091a2b3c4d5e6f708192a3b",
    "9c3b6e5f4a2d1c0b8e7f6a5d4c3b2a1908f7e6d5",
  ]);
});

test("emphasis.txt: Markdown emphasis, colons, header note, bullets and snapshot wording", () => {
  const result = classifyHandoff(fixture("emphasis.txt"));
  assert.equal(result.valid, true);
  assert.deepEqual(result.header, { task: "eval/task--20261022-161431", round: "3" });
  assert.equal(result.cells.Outcome, "partial; Done: a; Not done: b");
  assert.equal(result.cells.Scope, "Changed:\n- `src/a.py` (file mới)\n- `src/b.py`.\nRead: README.md");
  assert.equal(result.cells["Unknown / risk"], "không có");
  assert.equal(result.snapshot, true);
  // Unresolved hex tokens: the short SHA and the timestamp both count here; check-handoff resolves them.
  assert.deepEqual(result.shas, ["3f2a9c1", "20261022"]);
});

test("missing-cell, no-round, truncated and empty fixtures fail with the expected reasons", () => {
  assert.deepEqual(classifyHandoff(fixture("missing-cell.txt")).reasons, ["missing cells: Ownership"]);
  assert.equal(classifyHandoff(fixture("no-round.txt")).header, null);
  const truncated = classifyHandoff(fixture("truncated.txt"));
  assert.deepEqual(truncated.header, { task: "T-1", round: "2" });
  assert.deepEqual(truncated.missing, ["Scope", "Verification", "Unknown / risk", "Ownership"]);
  const empty = classifyHandoff(fixture("empty.txt"));
  assert.equal(empty.valid, false);
  assert.equal(empty.reasons.length, 2);
});

test("candidate without two hex tokens or snapshot wording is rejected", () => {
  const text = fixture("valid.txt").replace(/^Candidate .*$/m, "Candidate          branch main worktree /tmp/repo");
  const result = classifyHandoff(text);
  assert.deepEqual(result.reasons, ["Candidate cell needs base SHA and candidate SHA (found 0)"]);
});

test("hex glued to letters is not a SHA; mixed line endings split like Python", () => {
  const glued = parseHandoff("Task ID: T | Round: 1\nCandidate  xabcdef12 abcdef12x abcdef12\n");
  assert.deepEqual([...(glued.cells.Candidate ?? "").matchAll(/(?<![\p{L}\p{N}_])[0-9a-f]{7,40}(?![\p{L}\p{N}_])/gu)].map((m) => m[0]), ["abcdef12"]);
  assert.deepEqual(splitLines("a\r\nb\rc\u2028d\n"), ["a", "b", "c", "d"]);
  assert.deepEqual(splitLines(""), []);
  assert.deepEqual(splitLines("a\n\n"), ["a", ""]);
});
