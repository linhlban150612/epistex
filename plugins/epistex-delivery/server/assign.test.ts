import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { test } from "node:test";
import { assign, assignInput, assignTool, renderBrief, type AssignDeps, type AssignInput, type PeerProfile } from "./assign.ts";
import { briefIdentity, ownedScope } from "./brief.ts";

const ROOT = path.resolve(import.meta.dirname, "../../..");
const HEAD = "3f2a9c1d4e5b6a7f8091a2b3c4d5e6f708192a3b";
const SHA256 = "0a184d9dc3b8fa90d6a48f5cc8ce41074537be65a5e848a714844125a55aeb01";
const PROFILES: PeerProfile[] = [
  { id: "droid-peer--gpt-6-luna--low", provider: "droid-peer", model: "gpt-6-luna", modeId: "auto-high", thinkingOptionId: "low" },
  { id: "pi-peer--glm", provider: "pi-peer", model: "openrouter/z-ai/glm-5.3" },
  { id: "droid-lead--opus--low", provider: "droid-lead", model: "claude-opus-5-5", modeId: "auto-high", thinkingOptionId: "low" },
  { id: "claude-supervisor--sonnet", provider: "claude-supervisor", model: "claude-sonnet-5-5" },
];
const INPUT: AssignInput = {
  task_id: "T-15",
  round: 1,
  profile: "droid-peer--gpt-6-luna--low",
  worktree: "/tmp/repo",
  owned_scope: ["src/**", "docs/a.md"],
  commit_allowed: true,
  baseline: { kind: "commit", base_sha: HEAD.slice(0, 12) },
  title: "T-15 detail fields",
  brief: "Disposition: Engineer\nObjective: I need the detail response to carry the approver per level.\nVerification: required: `true`",
};

function setup(overrides: Partial<AssignDeps> = {}) {
  const created: unknown[] = [];
  const lines: string[] = [];
  let heads = 0;
  const deps: AssignDeps = {
    head: async () => ((heads += 1), HEAD),
    isDirectory: async () => true,
    profiles: async () => PROFILES,
    log: { info: (m) => lines.push(`info ${m}`), error: (m) => lines.push(`error ${m}`) },
    ...overrides,
  };
  const paseo = { agents: { create: async (options: unknown) => (created.push(options), { id: "peer-9" }) } };
  return { created, lines, deps, paseo, heads: () => heads };
}

test("schema: a brief without its fields, a round above the rework limit or a baseline without an identity cannot be written", () => {
  assert.equal(assignInput.safeParse(INPUT).success, true);
  const issue = (patch: Record<string, unknown>) => {
    const result = assignInput.safeParse({ ...INPUT, ...patch });
    return result.success ? null : result.error.issues[0].path.join(".");
  };
  assert.equal(issue({ round: 4 }), "round", "Round 39, 67 and 91 reached Peers as plain text");
  assert.equal(issue({ round: 0 }), "round");
  assert.equal(issue({ round: "1" }), "round");
  assert.equal(issue({ owned_scope: [] }), "owned_scope");
  assert.equal(issue({ owned_scope: ["only the files needed"] }), "owned_scope.0", "prose is not a scope");
  assert.equal(issue({ commit_allowed: "allowed" }), "commit_allowed");
  assert.equal(issue({ baseline: { kind: "commit", base_sha: "HEAD" } }), "baseline.base_sha");
  assert.equal(issue({ baseline: { kind: "snapshot", path: "in/a.xlsx", sha256: "b122b975" } }), "baseline.sha256", "a cut checksum is no identity");
  assert.equal(issue({ baseline: { kind: "none" } }), "baseline.kind");
  assert.equal(issue({ worktree: "repo" }), "worktree");
  assert.equal(issue({ task_id: "T-1 | Round: 9" }), "task_id");
  for (const field of ["task_id", "round", "profile", "worktree", "owned_scope", "commit_allowed", "baseline", "title", "brief"]) {
    const { [field as keyof AssignInput]: _, ...rest } = INPUT;
    assert.equal(assignInput.safeParse(rest).success, false, `${field} is required`);
  }
});

test("the rendered brief passes setup/check-brief and gives the delivery its task, round and scope", () => {
  for (const input of [INPUT, { ...INPUT, commit_allowed: false, baseline: { kind: "snapshot" as const, path: "/tmp/in/a.xlsx", sha256: SHA256 } }]) {
    const text = renderBrief(input);
    const python = JSON.parse(execFileSync("python3", [path.join(ROOT, "setup/check-brief"), "-", "--json"], { input: text, encoding: "utf8" }));
    assert.deepEqual(python.codes, [], text);
    assert.deepEqual(briefIdentity(text), { taskId: "T-15", round: "1" });
    assert.deepEqual(ownedScope(text), ["src/**", "docs/a.md"]);
    assert.match(text, input.commit_allowed ? /^Authority: .*commit required$/m : /^Authority: .*commit forbidden$/m);
    assert.ok(text.includes(input.brief));
  }
});

test("assign creates the Peer as the Lead's child from the profile, in the worktree, with the rendered brief", async () => {
  const { created, deps, paseo, lines } = setup();
  const result = await assign(INPUT, { id: "lead-1" }, paseo, deps);
  assert.equal(result.isError, undefined);
  assert.match(result.text, /^ASSIGNED T-15 round 1 to peer peer-9 \(droid-peer--gpt-6-luna--low\)\./);
  assert.deepEqual(created, [
    {
      config: { provider: "droid-peer/gpt-6-luna", modeId: "auto-high", thinkingOptionId: "low" },
      cwd: "/tmp/repo",
      parent: "lead-1",
      title: "T-15 detail fields",
      prompt: renderBrief(INPUT),
    },
  ]);
  assert.ok(lines.some((line) => /^info epistex_assign: lead lead-1 assigned T-15 round 1 to peer peer-9/.test(line)));

  const plain = setup();
  await assign({ ...INPUT, profile: "pi-peer--glm" }, { id: "lead-1" }, plain.paseo, plain.deps);
  assert.deepEqual((plain.created[0] as { config: unknown }).config, { provider: "pi-peer/openrouter/z-ai/glm-5.3" }, "a profile without a mode or effort passes none");
});

test("assign refuses, with a code and no Peer, when the machine state or the profile does not match", async () => {
  const cases: Array<[string, Partial<AssignInput>, Partial<AssignDeps>, RegExp]> = [
    ["stale base", { baseline: { kind: "commit", base_sha: "cad813934c09" } }, {}, /^BASELINE_STALE: base_sha cad813934c09 is not HEAD 3f2a9c1d.* of \/tmp\/repo; .*no Peer was created$/],
    ["base that is a suffix of HEAD", { baseline: { kind: "commit", base_sha: HEAD.slice(-12) } }, {}, /^BASELINE_STALE/],
    ["not a checkout", {}, { head: async () => null }, /^BASELINE_UNREADABLE: .*use a snapshot baseline/],
    ["missing worktree", {}, { isDirectory: async () => false }, /^WORKTREE_MISSING: \/tmp\/repo is not a directory/],
    ["unknown profile", { profile: "droid-peer--gpt-9" }, {}, /^PROFILE_UNKNOWN: .*list_profiles/],
    ["a Lead profile", { profile: "droid-lead--opus--low" }, {}, /^PROFILE_NOT_PEER: .*droid-lead seat/],
    ["a Supervisor profile", { profile: "claude-supervisor--sonnet" }, {}, /^PROFILE_NOT_PEER/],
    ["own handoff format", { brief: "Objective: x\nHandoff contract: six cells: Outcome; Changed files; Verification; Risks." }, {}, /^CELLS_REDEFINED: /],
  ];
  for (const [name, patch, depsPatch, message] of cases) {
    const { created, deps, paseo } = setup(depsPatch);
    const result = await assign({ ...INPUT, ...patch }, { id: "lead-1" }, paseo, deps);
    assert.equal(result.isError, true, name);
    assert.match(result.text, message, name);
    assert.deepEqual(created, [], name);
  }
});

test("a snapshot baseline does not read Git; a failed create is reported, not thrown", async () => {
  const snapshot = setup({ head: async () => null });
  const result = await assign({ ...INPUT, commit_allowed: false, baseline: { kind: "snapshot", path: "/tmp/in/a.xlsx", sha256: SHA256 } }, { id: "lead-1" }, snapshot.paseo, snapshot.deps);
  assert.equal(result.isError, undefined, result.text);
  assert.equal(snapshot.created.length, 1);

  const failing = setup();
  const refused = await assign(INPUT, { id: "lead-1" }, { agents: { create: async () => Promise.reject(new Error("cannot inherit mode")) } }, failing.deps);
  assert.deepEqual([refused.isError, refused.text], [true, "CREATE_FAILED: cannot inherit mode; no Peer was created"]);
  assert.ok(failing.lines.some((line) => line.startsWith("error epistex_assign: create failed for lead lead-1")));
});

test("the tool definition carries the schema and a name Paseo accepts", () => {
  const tool = assignTool(setup().deps);
  assert.match(tool.name, /^[a-z][a-z0-9_]*$/);
  assert.equal(tool.input, assignInput);
});
