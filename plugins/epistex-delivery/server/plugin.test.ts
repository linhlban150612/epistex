import assert from "node:assert/strict";
import { test } from "node:test";
import { contribute, type Logger, type OpenRequest, type TurnEndedEvent } from "./plugin.ts";

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

test("onOpen: its hook is registered apart from delivery; a failing or absent tool hook leaves delivery on", async () => {
  const request = { agentId: "a1", provider: "droid-lead", tools: [] } as unknown as OpenRequest;
  const withTool = { ...request, tools: [{ name: "x" }] } as unknown as OpenRequest;
  const build = (rejectOpen: boolean) => {
    const handlers = new Map<string, (payload: unknown) => Promise<unknown>>();
    const server = {
      addHook: (name: string, handler: (payload: unknown) => Promise<unknown>) => {
        if (rejectOpen && name === "agent.open.before") throw new Error(`Unknown hook: ${name}`);
        handlers.set(name, handler);
        return () => handlers.delete(name);
      },
    };
    return { handlers, server };
  };

  const ok = build(false);
  const first = recorder();
  const cleanup = contribute(ok.server, { log: first.log, onOpen: (r) => (r.provider === "droid-lead" ? withTool : undefined) });
  assert.deepEqual([...ok.handlers.keys()], ["agent.turn.after", "agent.permission.before", "agent.open.before"]);
  assert.equal(await ok.handlers.get("agent.open.before")!({ request }), withTool);
  assert.equal(await ok.handlers.get("agent.open.before")!({ request: { ...request, provider: "droid-peer" } }), undefined, "another seat keeps its request");
  cleanup();
  assert.equal(ok.handlers.size, 0);

  const throwing = build(false);
  const second = recorder();
  contribute(throwing.server, { log: second.log, onOpen: () => { throw new Error("boom"); } });
  assert.equal(await throwing.handlers.get("agent.open.before")!({ request }), undefined, "a failing handler must not stop the session from opening");
  assert.ok(second.lines.some((line) => /^error agent\.open\.before handler failed for a1: boom/.test(line)));

  const rejected = build(true);
  const third = recorder();
  contribute(rejected.server, { log: third.log, onOpen: () => undefined });
  assert.deepEqual([...rejected.handlers.keys()], ["agent.turn.after", "agent.permission.before"]);
  assert.ok(third.lines.some((line) => /^error cannot register agent\.open\.before: .*delivery stays on/.test(line)));

  const none = build(false);
  contribute(none.server, { log: recorder().log });
  assert.deepEqual([...none.handlers.keys()], ["agent.turn.after", "agent.permission.before"], "without onOpen nothing more is registered");
});
