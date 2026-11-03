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

test("server without on(): nothing registered, error logged", () => {
  const { lines, log } = recorder();
  const cleanup = contribute({ handle: () => {} }, { log });
  assert.equal(typeof cleanup, "function");
  assert.equal(lines.length, 1);
  assert.match(lines[0], /^error .*no on\(\).*nothing registered/);
});

test("server rejecting agent.turn_ended: nothing registered, error logged", () => {
  const { lines, log } = recorder();
  const registered: string[] = [];
  const server = {
    on: (name: string) => {
      registered.push(name);
      throw new Error(`Unknown hook: ${name}`);
    },
  };
  contribute(server, { log });
  assert.deepEqual(registered, ["agent.turn_ended"]);
  assert.equal(lines.length, 1);
  assert.match(lines[0], /^error cannot register agent.turn_ended: Unknown hook: agent.turn_ended/);
});

test("server.on without unsubscribe: nothing registered, error logged", () => {
  const { lines, log } = recorder();
  contribute({ on: () => undefined }, { log });
  assert.equal(lines.length, 1);
  assert.match(lines[0], /^error server.on did not return an unsubscribe function/);
});

test("compatible server: hook registered, handler errors logged, cleanup unsubscribes", async () => {
  const { lines, log } = recorder();
  let handler: ((event: TurnEndedEvent, context: unknown) => Promise<void>) | null = null;
  let unsubscribed = 0;
  const server = {
    on: (name: string, fn: typeof handler) => {
      assert.equal(name, "agent.turn_ended");
      handler = fn;
      return () => {
        unsubscribed += 1;
      };
    },
  };
  const seen: string[] = [];
  const cleanup = contribute(server, {
    log,
    onTurnEnded: async (e) => {
      seen.push(e.agent.id);
      if (e.turnId === "boom") throw new Error("handler boom");
    },
  });
  assert.ok(handler);
  await handler!(event, {});
  await handler!({ ...event, turnId: "boom" }, {});
  assert.deepEqual(seen, ["peer-1", "peer-1"]);
  assert.deepEqual(lines, [
    "info registered agent.turn_ended (Paseo >=0.14.0 <0.16)",
    "error agent.turn_ended handler failed for peer-1: handler boom",
  ]);
  cleanup();
  assert.equal(unsubscribed, 1);
});
