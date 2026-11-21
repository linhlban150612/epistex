import { execFile } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { z } from "zod";
import type { AgentToolDefinition } from "@getpaseo/plugin/server";
import { CELLS, classifyHandoff, type CellName } from "./handoff.ts";
import type { Submission } from "./outbox.ts";
import { describe, type Logger } from "./plugin.ts";

export const SUBMIT_TOOL = "epistex_submit_handoff";
export const PEER_SEAT = /^[a-z]+-peer(-\d+)?(--.*)?$/;
const OUTCOMES = ["complete", "partial", "BLOCKED", "REOPEN_REQUEST", "DEPENDENCY_REQUEST"] as const;
const PROOF_CLASSES = ["e2e", "observed", "tests-only", "none"] as const;
const commitSha = z.string().regex(/^[0-9a-f]{7,40}$/, "a commit SHA: 7 to 40 lower-case hex digits");
const text = (what: string) => z.string().trim().min(1).describe(what);

export const submitInput = z.object({
  task_id: z.string().trim().min(1).regex(/^[^|\n]+$/, "one line without '|'").describe("Task ID of the brief."),
  round: z.number().int().min(1).describe("Round of the brief or of the Lead's rework message. Do not change it."),
  outcome: z.enum(OUTCOMES),
  done: text("What is done."),
  not_done: text("What is not done, or 'nothing in scope'."),
  candidate: z.discriminatedUnion("kind", [
    z.object({ kind: z.literal("commit"), base_sha: commitSha.describe("Baseline commit of the brief."), candidate_sha: commitSha.describe("Your commit."), branch: z.string().trim().min(1) }),
    z.object({
      kind: z.literal("snapshot"),
      files: z.array(z.object({ path: z.string().trim().min(1).regex(/^\S+$/, "one path without spaces"), sha256: z.string().regex(/^[0-9a-f]{64}$/) })).min(1)
        .describe("Each file you changed and did not commit, or one diff file, with its sha256."),
    }),
    z.object({ kind: z.literal("none"), reason: text("Why there is no candidate: read-only task, browser task, stopped before writing.") }),
  ]).describe("commit: the brief requires a commit. snapshot: files changed without a commit. none: nothing was written."),
  read: text("Paths you read that are not in the diff."),
  proof_class: z.enum(PROOF_CLASSES).describe("e2e: ran the changed behaviour through its real entry point. observed: ran the changed code and saw its result. tests-only: only automated tests ran. none: nothing ran."),
  verification: text("Each command, its exit status and real output or labelled excerpts; checks you skipped."),
  unknown_risk: text("Assumptions, decisions that need the Human, transitional code with its removal condition, or 'none'."),
  ownership: text("'Stopped writing and returned scope to the Lead', or the scope you still hold and why."),
});
export type SubmitInput = z.infer<typeof submitInput>;

export interface SubmitDeps {
  head(worktree: string): Promise<string | null>;
  commit(worktree: string, sha: string): Promise<string | null>;
  diffPaths(worktree: string, base: string, candidate: string): Promise<string[]>;
  sha256(file: string): Promise<string | null>;
  store(peerAgentId: string, submission: Submission): Promise<void>;
  now(): string;
  id(): string;
  log: Logger;
}

type Cells = Record<CellName, string>;

export function renderHandoff(taskId: string, round: number, cells: Cells): string {
  return [`Task ID: ${taskId} | Round: ${round}`, "", ...CELLS.map((cell) => `${cell}: ${cells[cell]}`)].join("\n");
}

const refuse = (code: string, message: string) => ({ isError: true, text: `${code}: ${message}; nothing was sent to the Lead` });

export async function submit(input: SubmitInput, peer: { id: string; cwd: string; parentAgentId: string | null }, deps: SubmitDeps): Promise<{ text: string; isError?: boolean }> {
  if (!peer.parentAgentId) return refuse("NO_LEAD", "no Lead created this session; give the six-cell handoff as your last message");
  const { candidate } = input;
  let cell: string;
  let changed: string[] = [];
  let identity: string | null = null;
  if (candidate.kind === "commit") {
    const base = await deps.commit(peer.cwd, candidate.base_sha);
    const head = await deps.commit(peer.cwd, candidate.candidate_sha);
    const missing = [base ? null : `base_sha ${candidate.base_sha}`, head ? null : `candidate_sha ${candidate.candidate_sha}`].filter(Boolean);
    if (!base || !head) return refuse("CANDIDATE_UNRESOLVED", `${missing.join(" and ")} is not a commit in ${peer.cwd}; read the SHAs again with git`);
    if (base === head) return refuse("CANDIDATE_SAME_AS_BASE", `candidate_sha is the baseline ${base}; commit your work, or use candidate kind 'none' or 'snapshot'`);
    changed = await deps.diffPaths(peer.cwd, base, head);
    cell = `base SHA ${base} + candidate SHA ${head} + branch ${candidate.branch} + worktree ${peer.cwd}`;
    identity = `${base}..${head}`;
  } else if (candidate.kind === "snapshot") {
    const files = candidate.files.map((file) => {
      const relative = path.relative(peer.cwd, path.resolve(peer.cwd, file.path));
      return { ...file, path: relative && !relative.startsWith("..") && !path.isAbsolute(relative) ? relative : file.path };
    });
    for (const file of files) {
      const actual = await deps.sha256(path.resolve(peer.cwd, file.path));
      if (actual === null) return refuse("SNAPSHOT_FILE_MISSING", `${file.path} cannot be read in ${peer.cwd}`);
      if (actual !== file.sha256) return refuse("SNAPSHOT_MISMATCH", `${file.path} has sha256 ${actual}, not ${file.sha256}; compute the checksum again after your last write`);
    }
    changed = files.map((file) => file.path);
    const head = await deps.head(peer.cwd);
    cell = `snapshot: ${files.map((file) => `${file.path} sha256 ${file.sha256}`).join("; ")}; ${head ? `base SHA ${head}` : "no Git checkout"}; worktree ${peer.cwd}`;
    identity = "snapshot";
  } else {
    const head = await deps.head(peer.cwd);
    cell = `none, no candidate: ${candidate.reason}; ${head ? `base SHA ${head}` : "no Git checkout"}; worktree ${peer.cwd}`;
  }
  const cells: Cells = {
    Outcome: `${input.outcome}; Done: ${input.done}; Not done: ${input.not_done}`,
    Candidate: cell,
    Scope: `Changed: ${changed.length ? changed.join(", ") : "none"}. Read: ${input.read}`,
    Verification: `Proof class: ${input.proof_class}. ${input.verification}`,
    "Unknown / risk": input.unknown_risk,
    Ownership: input.ownership,
  };
  const body = renderHandoff(input.task_id, input.round, cells);
  const parsed = classifyHandoff(body);
  const firstLine = (value: string) => value.split("\n")[0].trim();
  const hijacked = CELLS.filter((name) => firstLine(parsed.cells[name] ?? "") !== firstLine(cells[name]));
  if (!parsed.valid || hijacked.length) {
    return refuse("CELL_TEXT_AMBIGUOUS", `${[...parsed.reasons, ...hijacked.map((name) => `a line of a text field reads as the cell '${name}'`)].join("; ")}; do not start a line of a text field with a cell name`);
  }
  const submission: Submission = { id: deps.id(), taskId: input.task_id, round: String(input.round), candidate: identity, body, submittedAt: deps.now() };
  try {
    await deps.store(peer.id, submission);
  } catch (error) {
    deps.log.error(`${SUBMIT_TOOL}: store failed for peer ${peer.id}: ${describe(error)}`);
    return refuse("STORE_FAILED", `${describe(error)}; give the six-cell handoff as your last message`);
  }
  deps.log.info(`${SUBMIT_TOOL}: peer ${peer.id} submitted ${input.task_id} round ${input.round} (${candidate.kind})`);
  return { text: `HANDOFF_STORED ${input.task_id} round ${input.round}. It goes to the Lead when this turn ends. End your turn now: no more tool calls, and do not write the handoff again.` };
}

function git(worktree: string, args: string[]): Promise<string | null> {
  return new Promise((resolve) => execFile("git", ["-C", worktree, ...args], { encoding: "utf8", maxBuffer: 16 * 1024 * 1024 }, (error, stdout) => resolve(error ? null : stdout)));
}

export function hostDeps(log: Logger, store: SubmitDeps["store"]): SubmitDeps {
  return {
    log,
    store,
    now: () => new Date().toISOString(),
    id: () => randomUUID(),
    head: async (worktree) => (await git(worktree, ["rev-parse", "HEAD"]))?.trim() || null,
    commit: async (worktree, sha) => (await git(worktree, ["rev-parse", "--verify", "--quiet", `${sha}^{commit}`]))?.trim() || null,
    diffPaths: async (worktree, base, candidate) => ((await git(worktree, ["diff", "--name-only", base, candidate])) ?? "").split("\n").filter(Boolean),
    sha256: async (file) => readFile(file).then((data) => createHash("sha256").update(data).digest("hex"), () => null),
  };
}

export function submitTool(deps: SubmitDeps): AgentToolDefinition {
  return {
    name: SUBMIT_TOOL,
    title: "Hand work back to the Lead",
    description:
      "Give your handoff to the Lead: the six cells of § Handoff as fields. Call it once, as the last action of the turn, for every outcome including BLOCKED. " +
      "The candidate is checked against the worktree; a refusal sends nothing. After HANDOFF_STORED end the turn and write no handoff text.",
    input: submitInput,
    execute: (input, context) => submit(input as SubmitInput, context.agent, deps),
  };
}
