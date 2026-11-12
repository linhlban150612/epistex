import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { briefOf, checkBrief, outsideScope } from "./brief.ts";

const ROOT = path.resolve(import.meta.dirname, "../../..");
// Real seat logs hold project text, so they stay outside Git.
const LOGS = process.env.EPISTEX_SEAT_LOGS ?? path.join(ROOT, ".amp/in/paseo7d/logs");
const BASE = "3f2a9c1d4e5b6a7f8091a2b3c4d5e6f708192a3b";
const SHA256 = "0a184d9dc3b8fa90d6a48f5cc8ce41074537be65a5e848a714844125a55aeb01";
const BRIEF = `Project / Task ID: demo / T-1
Round (assigned by Lead): 1
Repository root + workspace: /tmp/repo, branch main, base ${BASE}
Owned scope        src/**
Authority          edit files in owned scope; commit required
Handoff contract   candidate per § Ownership; six cells per § Handoff in the Peer prompt
`;

function python(text: string): string[] {
  try {
    return JSON.parse(execFileSync("python3", [path.join(ROOT, "setup/check-brief"), "-", "--json"], { input: text, encoding: "utf8" })).codes;
  } catch (error) {
    return JSON.parse((error as { stdout: string }).stdout).codes; // exit 1 on FAIL
  }
}

test("parity: checkBrief reports the codes of setup/check-brief", () => {
  const cases: Array<[string, string[]]> = [
    [BRIEF, []],
    [BRIEF.replaceAll("\n", "\r\n"), []],
    [
      `Project: demo / Task ID: T-1, round 2. Baseline snapshot sha256 ${SHA256} path /tmp/base.tar\n- **Owned scope:** read-only\n` +
        "- **Authority:** read-only\nHandoff: Outcome, Candidate, Scope, Verification, Unknown/risk, Ownership.\n",
      [],
    ],
    [BRIEF.replace("Project / Task ID: demo / T-1\n", ""), ["TASK_ID_MISSING"]],
    [BRIEF.replace("Round (assigned by Lead): 1\n", ""), ["ROUND_MISSING"]],
    [BRIEF.replace("by Lead): 1", "by Lead): R2-V1"), ["ROUND_NOT_NUMBER"]],
    [BRIEF.replace("Owned scope        src/**", "Owned scope"), ["OWNED_SCOPE_MISSING"]],
    [BRIEF.replace("Owned scope        src/**", "Owned scope\n  - src/**"), []],
    [BRIEF.replace(/Authority.*\n/, ""), ["AUTHORITY_MISSING"]],
    [BRIEF.replace(`base ${BASE}`, "base is the current main"), ["BASELINE_MISSING"]],
    [BRIEF.replace(/Repository.*/, `Baseline: sha256 ${SHA256}`), ["BASELINE_MISSING"]],
    [BRIEF.replace(/Repository.*/, `Baseline:\n  sha256 ${SHA256} at /tmp/base.tar`), []],
    [BRIEF.replace(/Handoff.*/, "Handoff contract: six cells: Outcome; Changed files; Verification; Risks."), ["CELLS_REDEFINED"]],
    ["Before writing, confirm owned scope and the task id for this round.\n", ["TASK_ID_MISSING", "ROUND_MISSING", "OWNED_SCOPE_MISSING", "AUTHORITY_MISSING", "BASELINE_MISSING"]],
  ];
  for (const [text, expected] of cases) {
    assert.deepEqual(checkBrief(text), expected, text);
    assert.deepEqual(python(text), expected, text);
  }
});

test("briefOf takes the Lead's agent-message body and leaves role instructions out", () => {
  const envelope = (id: string, body: string) => `<paseo-system version="1" kind="agent-message" source-agent-id="${id}" message-id="m1" source-agent-title="Lead">\n${body}\n</paseo-system>`;
  const escaped = BRIEF.replace("src/**", "src/** &amp; &quot;docs&quot;");
  const first = `Role instructions for this session:\nTask ID: … | Round: …\nOwned scope in the brief is your write authority.\n${envelope("lead-1", escaped)}`;
  assert.equal(briefOf(first, "lead-1"), BRIEF.replace("src/**", 'src/** & "docs"'));
  assert.equal(briefOf(first, "lead-2"), null, "a message from another agent is not this Lead's brief");
  assert.equal(briefOf(BRIEF, "lead-1"), null, "text without an envelope is not checked");
  assert.equal(briefOf(`<paseo-system>\nnote\n</paseo-system>\n${envelope("lead-1", "x")}`, "lead-1"), "x");
});

test("real briefs: both checkers agree on every Lead brief in the seat logs", { skip: !existsSync(LOGS) }, () => {
  let briefs = 0;
  for (const name of readdirSync(LOGS)) {
    const log = readFileSync(path.join(LOGS, name), "utf8");
    for (const [, lead] of log.matchAll(/kind="agent-message" source-agent-id="([^"]+)"/g)) {
      const brief = briefOf(log, lead);
      if (brief === null || briefs >= 60) continue;
      briefs += 1;
      assert.deepEqual(checkBrief(brief), python(brief), `${name}: ${brief.slice(0, 80)}`);
      break;
    }
  }
  assert.ok(briefs > 0);
});

test("outsideScope: `**/` also matches no directory, as glob_to_regex of setup/check-handoff", () => {
  const scope = "Changed: README.md docs/a/b.md src/a.py src/a/b.py other.txt\nRead: none";
  assert.deepEqual(outsideScope(scope, ["**/*.md", "src/**/*.py"]), ["other.txt"]);
  assert.deepEqual(outsideScope("Changed: srcx/a.py lib/a.py", ["src/**/*.py", "lib/"]), ["srcx/a.py"]);
});
