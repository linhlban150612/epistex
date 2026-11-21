import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { test } from "node:test";
import { classifyHandoff } from "./handoff.ts";
import type { Submission } from "./outbox.ts";
import { PEER_SEAT, submit, submitInput, type SubmitDeps, type SubmitInput } from "./submit.ts";

const ROOT = path.resolve(import.meta.dirname, "../../..");
const BASE = "3f2a9c1d4e5b6a7f8091a2b3c4d5e6f708192a3b";
const HEAD = "9c3b6e5f4a2d1c0b8e7f6a5d4c3b2a1908f7e6d5";
const SHA256 = "0a184d9dc3b8fa90d6a48f5cc8ce41074537be65a5e848a714844125a55aeb01";
const PEER = { id: "peer-1", cwd: "/tmp/repo", parentAgentId: "lead-1" };
const INPUT: SubmitInput = {
  task_id: "T-15",
  round: 2,
  outcome: "complete",
  done: "the detail response carries the approver per level",
  not_done: "nothing in scope",
  candidate: { kind: "commit", base_sha: BASE.slice(0, 12), candidate_sha: HEAD.slice(0, 12), branch: "main" },
  read: "README.md, src/api/detail.ts",
  proof_class: "observed",
  verification: "`npm test` exit 0\n12 tests passed",
  unknown_risk: "none",
  ownership: "Stopped writing and returned scope to the Lead",
};

function setup(overrides: Partial<SubmitDeps> = {}) {
  const stored: Array<[string, Submission]> = [];
  const lines: string[] = [];
  const deps: SubmitDeps = {
    head: async () => HEAD,
    commit: async (_worktree, sha) => [BASE, HEAD].find((full) => full.startsWith(sha)) ?? null,
    diffPaths: async () => ["src/api/detail.ts", "docs/a.md"],
    sha256: async () => SHA256,
    store: async (peerAgentId, submission) => void stored.push([peerAgentId, submission]),
    now: () => "2026-11-15T00:00:00.000Z",
    id: () => "s-1",
    log: { info: (m) => lines.push(`info ${m}`), error: (m) => lines.push(`error ${m}`) },
    ...overrides,
  };
  return { stored, lines, deps };
}

function python(text: string) {
  const dir = mkdtempSync(path.join(tmpdir(), "epistex-submit-"));
  try {
    const file = path.join(dir, "handoff.txt");
    writeFileSync(file, text);
    return JSON.parse(execFileSync("python3", [path.join(ROOT, "setup/check-handoff"), "--parse-only", file, "--json"], { encoding: "utf8" }));
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

test("schema: a handoff without a cell, with an unknown outcome or proof class, or with a candidate without an identity cannot be written", () => {
  assert.equal(submitInput.safeParse(INPUT).success, true);
  const issue = (patch: Record<string, unknown>) => {
    const result = submitInput.safeParse({ ...INPUT, ...patch });
    return result.success ? null : result.error.issues[0].path.join(".");
  };
  for (const field of ["task_id", "round", "outcome", "done", "not_done", "candidate", "read", "proof_class", "verification", "unknown_risk", "ownership"]) {
    assert.equal(issue({ [field]: undefined }), field, `${field} is required`);
  }
  assert.equal(issue({ outcome: "done" }), "outcome");
  assert.equal(issue({ outcome: "blocked" }), "outcome", "the stop outcomes are upper case, as in the Peer prompt");
  assert.equal(issue({ proof_class: "manual" }), "proof_class");
  assert.equal(issue({ round: 0 }), "round");
  assert.equal(issue({ ownership: "  " }), "ownership");
  assert.equal(issue({ candidate: { kind: "commit", base_sha: BASE } }), "candidate.candidate_sha", "a commit candidate names both SHAs");
  assert.equal(issue({ candidate: { kind: "commit", base_sha: "no local change", candidate_sha: HEAD, branch: "main" } }), "candidate.base_sha");
  assert.equal(issue({ candidate: { kind: "snapshot", files: [] } }), "candidate.files");
  assert.equal(issue({ candidate: { kind: "snapshot", files: [{ path: "a.md", sha256: "abc" }] } }), "candidate.files.0.sha256");
  assert.equal(issue({ candidate: { kind: "none" } }), "candidate.reason", "no candidate needs its reason");
  assert.equal(issue({ candidate: { kind: "browser" } }), "candidate.kind");
});

test("a commit candidate is stored with full SHAs and the changed paths Git reports; both parsers accept the text", async () => {
  const { stored, deps, lines } = setup();
  const result = await submit(INPUT, PEER, deps);
  assert.equal(result.isError, undefined);
  assert.match(result.text, /^HANDOFF_STORED T-15 round 2\. .*End your turn now/);
  assert.equal(stored.length, 1);
  const [peerAgentId, submission] = stored[0];
  assert.equal(peerAgentId, "peer-1");
  assert.deepEqual({ ...submission, body: "" }, { id: "s-1", taskId: "T-15", round: "2", candidate: `${BASE}..${HEAD}`, body: "", submittedAt: "2026-11-15T00:00:00.000Z" });
  assert.equal(
    submission.body,
    [
      "Task ID: T-15 | Round: 2",
      "",
      "Outcome: complete; Done: the detail response carries the approver per level; Not done: nothing in scope",
      `Candidate: base SHA ${BASE} + candidate SHA ${HEAD} + branch main + worktree /tmp/repo`,
      "Scope: Changed: src/api/detail.ts, docs/a.md. Read: README.md, src/api/detail.ts",
      "Verification: Proof class: observed. `npm test` exit 0\n12 tests passed",
      "Unknown / risk: none",
      "Ownership: Stopped writing and returned scope to the Lead",
    ].join("\n"),
  );
  const parsed = classifyHandoff(submission.body);
  assert.equal(parsed.valid, true);
  assert.deepEqual(parsed.shas, [BASE, HEAD]);
  const gate = python(submission.body);
  assert.equal(gate.valid, true, JSON.stringify(gate.reasons));
  assert.deepEqual(gate.header, { task: "T-15", round: "2" });
  assert.equal(gate.proof, "observed");
  assert.ok(lines.some((line) => /^info epistex_submit_handoff: peer peer-1 submitted T-15 round 2 \(commit\)/.test(line)));
});

test("a snapshot, no candidate and a stopped turn are valid handoffs without two commit SHAs", async () => {
  const cases: Array<[string, Partial<SubmitInput>, Partial<SubmitDeps>, RegExp, string | null]> = [
    ["snapshot", { candidate: { kind: "snapshot", files: [{ path: "docs/a.md", sha256: SHA256 }] } }, {}, new RegExp(`^Candidate: snapshot: docs/a\\.md sha256 ${SHA256}; base SHA ${HEAD}; worktree /tmp/repo$`, "m"), "snapshot"],
    ["snapshot by absolute path", { candidate: { kind: "snapshot", files: [{ path: "/tmp/repo/docs/a.md", sha256: SHA256 }] } }, {}, new RegExp(`^Candidate: snapshot: docs/a\\.md sha256 ${SHA256}; `, "m"), "snapshot"],
    ["snapshot outside the worktree", { candidate: { kind: "snapshot", files: [{ path: "/tmp/evidence/a.diff", sha256: SHA256 }] } }, {}, new RegExp(`^Scope: Changed: /tmp/evidence/a\\.diff\\. `, "m"), "snapshot"],
    ["read-only task", { candidate: { kind: "none", reason: "read-only review" } }, {}, new RegExp(`^Candidate: none, no candidate: read-only review; base SHA ${HEAD}; worktree /tmp/repo$`, "m"), null],
    ["browser task outside Git", { candidate: { kind: "none", reason: "browser task" } }, { head: async () => null }, /^Candidate: none, no candidate: browser task; no Git checkout; worktree \/tmp\/repo$/m, null],
    ["blocked", { outcome: "BLOCKED", proof_class: "none", candidate: { kind: "none", reason: "stopped before writing" } }, {}, /^Outcome: BLOCKED; /m, null],
  ];
  for (const [name, patch, depsPatch, line, identity] of cases) {
    const { stored, deps } = setup(depsPatch);
    const result = await submit({ ...INPUT, ...patch }, PEER, deps);
    assert.equal(result.isError, undefined, `${name}: ${result.text}`);
    const submission = stored[0][1];
    assert.match(submission.body, line, name);
    assert.equal(submission.candidate, identity, name);
    assert.equal(classifyHandoff(submission.body).valid, true, name);
    assert.equal(python(submission.body).valid, true, name);
    if (patch.candidate?.kind !== "snapshot") assert.match(submission.body, /^Scope: Changed: none\. Read: /m, name);
    if (name === "snapshot by absolute path") assert.match(submission.body, /^Scope: Changed: docs\/a\.md\. /m, name);
  }
});

test("submit refuses, with a code and nothing stored, when the worktree does not match or a field reads as another cell", async () => {
  const cases: Array<[string, Partial<SubmitInput>, Partial<SubmitDeps>, RegExp]> = [
    ["candidate SHA that is not a commit", { candidate: { kind: "commit", base_sha: BASE, candidate_sha: "abcdef1234", branch: "main" } }, {}, /^CANDIDATE_UNRESOLVED: candidate_sha abcdef1234 is not a commit in \/tmp\/repo; .*nothing was sent to the Lead$/],
    ["neither SHA resolves", {}, { commit: async () => null }, /^CANDIDATE_UNRESOLVED: base_sha 3f2a9c1d4e5b and candidate_sha 9c3b6e5f4a2d /],
    ["candidate is the baseline", { candidate: { kind: "commit", base_sha: BASE, candidate_sha: BASE.slice(0, 9), branch: "main" } }, {}, /^CANDIDATE_SAME_AS_BASE: /],
    ["snapshot checksum of an older write", { candidate: { kind: "snapshot", files: [{ path: "docs/a.md", sha256: "f".repeat(64) }] } }, {}, new RegExp(`^SNAPSHOT_MISMATCH: docs/a\\.md has sha256 ${SHA256}, not f{64}`)],
    ["snapshot file that is gone", { candidate: { kind: "snapshot", files: [{ path: "docs/a.md", sha256: SHA256 }] } }, { sha256: async () => null }, /^SNAPSHOT_FILE_MISSING: docs\/a\.md /],
    ["a text line that reads as a cell", { done: "wrote the code\nScope: everything" }, {}, /^CELL_TEXT_AMBIGUOUS: .*reads as the cell 'Scope'/],
    ["store failure", {}, { store: async () => Promise.reject(new Error("disk full")) }, /^STORE_FAILED: disk full; give the six-cell handoff as your last message/],
  ];
  for (const [name, patch, depsPatch, message] of cases) {
    const { stored, deps } = setup(depsPatch);
    const result = await submit({ ...INPUT, ...patch }, PEER, deps);
    assert.equal(result.isError, true, name);
    assert.match(result.text, message, name);
    if (name !== "store failure") assert.deepEqual(stored, [], name);
  }
  const rootPeer = setup();
  const result = await submit(INPUT, { ...PEER, parentAgentId: null }, rootPeer.deps);
  assert.match(result.text, /^NO_LEAD: /, "a Peer session no Lead created has nobody to deliver to");
  assert.deepEqual(rootPeer.stored, []);
});

test("the tool is offered to Peer seats only", () => {
  for (const provider of ["droid-peer", "droid-peer-2", "omp-peer-1", "codex-peer", "kiro-peer"]) assert.ok(PEER_SEAT.test(provider), provider);
  for (const provider of ["droid-lead", "claude-supervisor", "peer", "droid", "my-peering"]) assert.ok(!PEER_SEAT.test(provider), provider);
});
