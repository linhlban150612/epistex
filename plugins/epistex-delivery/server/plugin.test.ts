import assert from "node:assert/strict";
import { test } from "node:test";
import { contribute, type Logger, type TurnEndedEvent } from "./plugin.ts";

function recorder() {
  const lines: string[] = [];
  const log: Logger = { info: (m) => lines.push(`info ${m}`), error: (m) => lines.push(`error ${m}`) };
  return { lines, log };
}

const event: TurnEndedEvent = {
  agent: { id: "peer-1", workspaceId: null, parentAgentId: "lead-1", provider: "codex-peer", cwd: "/w", title: null },
  turnId: "t1",
  outcome: { kind: "completed" },
  timeline: [],
};

test("0.14 server with only on(): nothing registered, error logged", () => {
  const { lines, log } = recorder();
  let called = 0;
  const cleanup = contribute({ on: () => { called += 1; return () => {}; } }, { log });
  assert.equal(called, 0);
  assert.equal(typeof cleanup, "function");
  assert.equal(lines.length, 1);
  assert.match(lines[0], /^error .*no addHook\(\).*nothing registered/);
});

test("server rejecting agent.permission.before: the hook already added is removed, nothing registered", () => {
  const { lines, log } = recorder();
  const registered: string[] = [];
  let unsubscribed = 0;
  const server = {
    addHook: (name: string) => {
      registered.push(name);
      if (name === "agent.permission.before") throw new Error(`Unknown hook: ${name}`);
      return () => {
        unsubscribed += 1;
      };
    },
  };
  contribute(server, { log });
  assert.deepEqual(registered, ["agent.turn.after", "agent.permission.before"]);
  assert.equal(unsubscribed, 1, "agent.turn.after must not stay registered alone");
  assert.equal(lines.length, 1);
  assert.match(lines[0], /^error cannot register agent.permission.before: Unknown hook: agent.permission.before/);
});

test("server.addHook without unsubscribe: nothing registered, error logged", () => {
  const { lines, log } = recorder();
  contribute({ addHook: () => undefined }, { log });
  assert.equal(lines.length, 1);
  assert.match(lines[0], /^error server.addHook did not return an unsubscribe function/);
});

test("compatible server: both hooks registered and routed, handler errors logged, cleanup unsubscribes", async () => {
  const { lines, log } = recorder();
  const handlers = new Map<string, (event: unknown, context: unknown) => Promise<void>>();
  let unsubscribed = 0;
  const server = {
    addHook: (name: string, fn: (event: unknown, context: unknown) => Promise<void>) => {
      handlers.set(name, fn);
      return () => {
        unsubscribed += 1;
      };
    },
  };
  const seen: string[] = [];
  const cleanup = contribute(server, {
    log,
    onTurnEnded: async (e) => {
      seen.push(`turn ${e.agent.id}`);
      if (e.turnId === "boom") throw new Error("handler boom");
    },
    onPermission: async (e) => {
      seen.push(`permission ${e.request.id}`);
    },
  });
  assert.deepEqual([...handlers.keys()], ["agent.turn.after", "agent.permission.before"]);
  await handlers.get("agent.turn.after")!(event, {});
  await handlers.get("agent.turn.after")!({ ...event, turnId: "boom" }, {});
  await handlers.get("agent.permission.before")!({ agent: event.agent, request: { id: "req-1" } }, {});
  assert.deepEqual(seen, ["turn peer-1", "turn peer-1", "permission req-1"]);
  assert.deepEqual(lines, [
    "info registered agent.turn.after, agent.permission.before (Paseo >=0.15.0 <0.16)",
    "error agent.turn.after handler failed for peer-1: handler boom",
  ]);
  cleanup();
  assert.equal(unsubscribed, 2);
});
