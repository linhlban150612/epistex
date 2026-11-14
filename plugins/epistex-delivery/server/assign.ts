// epistex_assign: the Lead's typed way to give a task to a new Peer. The brief fields are a schema,
// so a brief without a task, a scope, an authority or a baseline, or with a round above the rework
// limit, cannot be sent; the baseline is compared with the worktree before the Peer starts.
// The Peer is created through the plugin API, which has no finish notification: the delivery
// receipt is the only report the Lead gets.
import { execFile } from "node:child_process";
import { readFile, stat } from "node:fs/promises";
import { homedir } from "node:os";
import path from "node:path";
import { z } from "zod";
import type { AgentToolDefinition } from "@getpaseo/plugin/server";
import { checkBrief } from "./brief.ts";
import { describe, type Logger } from "./plugin.ts";

export const ASSIGN_TOOL = "epistex_assign";
/** A Peer seat's provider id, e.g. `droid-peer`, `droid-peer-2`. A Lead cannot create another role with this tool. */
export const PEER_PROVIDER = /^[a-z]+-peer(-\d+)?$/;
/** First candidate plus two rework rounds (agents/LEAD.md § Acceptance). */
const REWORK_LIMIT = 3;
const commitSha = z.string().regex(/^[0-9a-f]{7,40}$/, "a commit SHA: 7 to 40 lower-case hex digits");

export const assignInput = z.object({
  task_id: z.string().trim().min(1).regex(/^[^|\n]+$/, "one line without '|'").describe("Task ID. A new step or a new scope is a new Task ID."),
  round: z.number().int().min(1).max(REWORK_LIMIT).describe("1 for a new task. Above 1 only for a replacement Peer on the same task; rework goes to the same Peer with send_agent_prompt."),
  profile: z.string().trim().min(1).describe("Agent profile id of a Peer seat, as list_profiles shows it."),
  worktree: z.string().refine((value) => path.isAbsolute(value), "an absolute path").describe("Directory the Peer works in."),
  owned_scope: z.array(z.string().trim().min(1).regex(/^\S+$/, "one path or glob without spaces")).min(1).describe("Concrete paths or globs the Peer may write."),
  commit_allowed: z.boolean().describe("true: a commit is required. false: a commit is forbidden."),
  baseline: z.discriminatedUnion("kind", [
    z.object({ kind: z.literal("commit"), base_sha: commitSha.describe("HEAD of the worktree now.") }),
    z.object({ kind: z.literal("snapshot"), path: z.string().trim().min(1), sha256: z.string().regex(/^[0-9a-f]{64}$/) }),
  ]).describe("Identity of the state the Peer starts from: a commit, or a file with its sha256 when there is no commit."),
  title: z.string().trim().min(1).max(80),
  brief: z.string().trim().min(1).describe("The rest of the assignment template: disposition, objective, verified facts, MUST HOLD, ALREADY DECIDED, excluded scope, verification. Do not repeat the fields above and do not define a handoff format."),
});
export type AssignInput = z.infer<typeof assignInput>;

export interface PeerProfile {
  id: string;
  provider: string;
  model: string;
  modeId?: string;
  thinkingOptionId?: string;
}

export interface AssignDeps {
  /** HEAD commit of a worktree, or null when the directory is not a Git checkout. */
  head(worktree: string): Promise<string | null>;
  isDirectory(directory: string): Promise<boolean>;
  profiles(): Promise<PeerProfile[]>;
  log: Logger;
}

interface AssignPaseo {
  agents: {
    create(options: {
      config: { provider: string; modeId?: string; thinkingOptionId?: string };
      cwd: string;
      parent: string;
      title: string;
      prompt: string;
    }): Promise<{ id?: string }>;
  };
}

/** The brief a Peer receives: the template fields of agents/LEAD.md, then the Lead's text. It passes setup/check-brief. */
export function renderBrief(input: AssignInput): string {
  const baseline = input.baseline.kind === "commit" ? `base ${input.baseline.base_sha}` : `baseline snapshot sha256 ${input.baseline.sha256} path ${input.baseline.path}`;
  return [
    `Task ID: ${input.task_id}`,
    `Round: ${input.round}`,
    `Repository root + workspace: ${input.worktree}; ${baseline}`,
    `Owned scope: ${input.owned_scope.join(", ")}`,
    `Authority: edit files in owned scope; commit ${input.commit_allowed ? "required" : "forbidden"}`,
    "",
    input.brief,
    "",
    "Handoff contract: candidate per § Ownership; six cells per § Handoff in the Peer prompt",
  ].join("\n");
}

const refuse = (code: string, text: string) => ({ isError: true, text: `${code}: ${text}; no Peer was created` });

/** Check the assignment against the machine state and create the Peer. Every refusal names its code and creates nothing. */
export async function assign(input: AssignInput, lead: { id: string }, paseo: AssignPaseo, deps: AssignDeps): Promise<{ text: string; isError?: boolean }> {
  const profile = (await deps.profiles()).find((candidate) => candidate.id === input.profile);
  if (!profile) return refuse("PROFILE_UNKNOWN", `no agent profile '${input.profile}'; read the ids with list_profiles`);
  if (!PEER_PROVIDER.test(profile.provider)) return refuse("PROFILE_NOT_PEER", `profile '${profile.id}' is a ${profile.provider} seat; this tool creates Peer seats only`);
  if (!(await deps.isDirectory(input.worktree))) return refuse("WORKTREE_MISSING", `${input.worktree} is not a directory`);
  if (input.baseline.kind === "commit") {
    const head = await deps.head(input.worktree);
    if (head === null) return refuse("BASELINE_UNREADABLE", `${input.worktree} has no Git HEAD; use a snapshot baseline`);
    if (!head.startsWith(input.baseline.base_sha)) return refuse("BASELINE_STALE", `base_sha ${input.baseline.base_sha} is not HEAD ${head} of ${input.worktree}; read the state again`);
  }
  const prompt = renderBrief(input);
  // The fields above pass by construction; this catches a handoff format redefined in the Lead's text.
  const codes = checkBrief(prompt);
  if (codes.length) return refuse(codes.join(", "), "the brief text fails setup/check-brief; refer to § Handoff in the Peer prompt instead of defining cells");
  let peerId: string | undefined;
  try {
    peerId = (
      await paseo.agents.create({
        config: { provider: `${profile.provider}/${profile.model}`, ...(profile.modeId ? { modeId: profile.modeId } : {}), ...(profile.thinkingOptionId ? { thinkingOptionId: profile.thinkingOptionId } : {}) },
        cwd: input.worktree,
        parent: lead.id,
        title: input.title,
        prompt,
      })
    ).id;
  } catch (error) {
    deps.log.error(`${ASSIGN_TOOL}: create failed for lead ${lead.id}: ${describe(error)}`);
    return refuse("CREATE_FAILED", describe(error));
  }
  deps.log.info(`${ASSIGN_TOOL}: lead ${lead.id} assigned ${input.task_id} round ${input.round} to peer ${peerId ?? "?"} (${profile.id})`);
  return { text: `ASSIGNED ${input.task_id} round ${input.round} to peer ${peerId ?? "?"} (${profile.id}). End your turn and wait for its [epistex-delivery] message.` };
}

function paseoHome(env: NodeJS.ProcessEnv): string {
  const home = env.PASEO_HOME?.trim() || "~/.paseo";
  return path.resolve(home === "~" || home.startsWith("~/") ? path.join(homedir(), home.slice(1)) : home);
}

/** Dependencies on the daemon host: Git, the file system and `daemon.agentProfiles` of the live config. */
export function hostDeps(log: Logger, env: NodeJS.ProcessEnv = process.env): AssignDeps {
  return {
    log,
    head: (worktree) =>
      new Promise((resolve) => execFile("git", ["-C", worktree, "rev-parse", "HEAD"], { encoding: "utf8" }, (error, stdout) => resolve(error ? null : stdout.trim() || null))),
    isDirectory: async (directory) => (await stat(directory).catch(() => null))?.isDirectory() ?? false,
    profiles: async () => {
      const config = JSON.parse(await readFile(path.join(paseoHome(env), "config.json"), "utf8")) as { daemon?: { agentProfiles?: PeerProfile[] } };
      return Array.isArray(config.daemon?.agentProfiles) ? config.daemon.agentProfiles : [];
    },
  };
}

export function assignTool(deps: AssignDeps): AgentToolDefinition {
  return {
    name: ASSIGN_TOOL,
    title: "Assign a task to a new Peer",
    description:
      "Create one Peer and give it a task. Use this for every new Peer; do not use create_agent for a Peer. " +
      "The brief fields are checked and the baseline is compared with the worktree before the Peer starts; a refusal creates nothing. " +
      "The Peer reports through [epistex-delivery] only.",
    input: assignInput,
    execute: (input, context) => assign(input as AssignInput, context.agent, context.paseo as unknown as AssignPaseo, deps),
  };
}
