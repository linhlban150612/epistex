import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { test } from "node:test";
import { Delivery, formatDelivery, type AgentSnapshot, type DeliveryPaseo, type TimelineEntry, type TimelinePage } from "./delivery.ts";
import { Outbox } from "./outbox.ts";
import type { Logger, TurnEndedEvent } from "./plugin.ts";

const FIXTURES = path.resolve(import.meta.dirname, "../../../tests/fixtures/handoffs");
const VALID = await readFile(path.join(FIXTURES, "valid.txt"), "utf8");
const MISSING = await readFile(path.join(FIXTURES, "missing-cell.txt"), "utf8");

interface Sent {
  agentId: string;
  text: string;
  options: Record<string, unknown>;
}

/** Fake of the PaseoApi slice: per-agent snapshots, timeline pages served in order, recorded sends. */
function fakePaseo(agents: Record<string, AgentSnapshot | null>, pages: Record<string, TimelinePage[]> = {}) {
  const sent: Sent[] = [];
  const refetches: Array<{ agentId: string; options: unknown }> = [];
  let failSend: Error | null = null;
  const paseo: DeliveryPaseo = {
    agents: {
      ref: (agentId) => ({
        refresh: async () => {
          const agent = agents[agentId];
          return agent ? { agent } : null;
        },
        timeline: {
          refetch: async (options) => {
            refetches.push({ agentId, options });
            const queue = pages[agentId] ?? [];
            return queue.length > 1 ? queue.shift()! : (queue[0] ?? { epoch: "e0", entries: [] });
          },
        },
        send: async (text, options) => {
          if (failSend) throw failSend;
          sent.push({ agentId, text, options });
        },
      }),
    },
  };
  return { paseo, sent, refetches, agents, setFailSend: (error: Error | null) => (failSend = error) };
}

function assistant(text: string, seqEnd: number, extra: Partial<TimelineEntry> & { messageId?: string } = {}): TimelineEntry {
  const { messageId, ...rest } = extra;
  return { item: { type: "assistant_message", text, ...(messageId ? { messageId } : {}) }, turnId: "t1", seqEnd, ...rest };
}

function peerTurn(overrides: Partial<TurnEndedEvent> = {}): TurnEndedEvent {
  return {
    agent: { id: "peer-1", workspaceId: null, parentAgentId: "lead-1", provider: "codex-peer", cwd: "/w", title: null },
    turnId: "t1",
    outcome: { kind: "completed" },
    timeline: [],
    ...overrides,
  };
}

const leadIdle: AgentSnapshot = { id: "lead-1", provider: "amp-lead", status: "idle" };
const leadRunning: AgentSnapshot = { id: "lead-1", provider: "amp-lead", status: "running" };

async function scratch(fn: (delivery: Delivery, outbox: Outbox, lines: string[]) => Promise<void>) {
  const dir = await mkdtemp(path.join(tmpdir(), "epistex-delivery-"));
  const lines: string[] = [];
  const log: Logger = { info: (m) => lines.push(`info ${m}`), error: (m) => lines.push(`error ${m}`) };
  try {
    const outbox = new Outbox(path.join(dir, "epistex-delivery"));
    let tick = 0;
    const delivery = new Delivery({ outbox, log, now: () => `2026-11-02T00:00:0${tick++}.000Z` });
    await fn(delivery, outbox, lines);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

test("root agents and children of non-Lead parents are ignored", async () => {
  await scratch(async (delivery, outbox) => {
    const fake = fakePaseo({ "sup-1": { id: "sup-1", provider: "codex-supervisor", status: "idle" } });
    await delivery.onTurnEnded(peerTurn({ agent: { ...peerTurn().agent, parentAgentId: null } }), fake.paseo);
    await delivery.onTurnEnded(peerTurn({ agent: { ...peerTurn().agent, parentAgentId: "sup-1" } }), fake.paseo);
    await delivery.onTurnEnded(peerTurn({ agent: { ...peerTurn().agent, parentAgentId: "ghost" } }), fake.paseo);
    assert.equal(outbox.records().length, 0);
    assert.equal(fake.refetches.length, 0);
    assert.equal(fake.sent.length, 0);
  });
});

test("valid handback to an idle Lead: recorded, sent with steer, cursor advanced, message format exact", async () => {
  await scratch(async (delivery, outbox) => {
    const fake = fakePaseo(
      { "lead-1": leadIdle },
      { "peer-1": [{ epoch: "e1", entries: [assistant("working…", 3, { turnId: "t0" }), assistant(VALID, 9, { messageId: "m9" }), { item: { type: "tool_call" }, turnId: "t1", seqEnd: 10 }] }] },
    );
    await delivery.onTurnEnded(peerTurn(), fake.paseo);

    assert.deepEqual(fake.refetches.map((r) => r.options), [{ direction: "tail", limit: 200 }], "no cursor yet: read the tail");
    const [record] = outbox.records();
    assert.equal(record.kind, "HANDBACK_VALID");
    assert.equal(record.taskId, "T-1");
    assert.equal(record.round, "1");
    assert.equal(record.candidate, "3f2a9c1d4e5b6a7f8091a2b3c4d5e6f708192a3b..9c3b6e5f4a2d1c0b8e7f6a5d4c3b2a1908f7e6d5");
    assert.equal(record.messageId, "m9");
    assert.equal(record.turnId, "t1");
    assert.equal(record.state, "sent");
    assert.equal(record.sendReceipt, "accepted");
    assert.deepEqual(record.cursor, { epoch: "e1", seq: 10 }, "cursor covers the whole page, not only the message");
    assert.deepEqual(outbox.cursor("peer-1"), { epoch: "e1", seq: 10 });

    assert.equal(fake.sent.length, 1);
    assert.equal(fake.sent[0].agentId, "lead-1");
    assert.deepEqual(fake.sent[0].options, { sourceAgentId: "peer-1", activeTurnBehavior: "steer", messageId: record.deliveryId });
    assert.equal(
      fake.sent[0].text,
      ["[epistex-delivery]", `delivery-id: ${record.deliveryId}`, "kind: HANDBACK_VALID", "peer: peer-1  task: T-1  round: 1", "---", VALID].join("\n"),
    );
    assert.match(record.deliveryId, /^[0-9a-f]{64}$/);
  });
});

test("invalid handoff carries the parser reasons; a turn with no assistant message is still delivered", async () => {
  await scratch(async (delivery, outbox) => {
    const fake = fakePaseo(
      { "lead-1": leadIdle },
      { "peer-1": [{ epoch: "e1", entries: [assistant(MISSING, 4)] }], "peer-2": [{ epoch: "e2", entries: [{ item: { type: "tool_call" }, turnId: "t2", seqEnd: 1 }] }] },
    );
    await delivery.onTurnEnded(peerTurn(), fake.paseo);
    await delivery.onTurnEnded(
      peerTurn({ agent: { ...peerTurn().agent, id: "peer-2" }, turnId: "t2", outcome: { kind: "failed", error: { message: "provider exited" } } }),
      fake.paseo,
    );
    const invalid = outbox.records().find((r) => r.peerAgentId === "peer-1")!;
    assert.equal(invalid.kind, "TURN_ENDED_INVALID_HANDOFF");
    assert.equal(invalid.taskId, "T-1");
    assert.deepEqual(invalid.reasons, ["turn completed", "missing cells: Ownership"]);
    assert.match(fake.sent[0].text, /^kind: TURN_ENDED_INVALID_HANDOFF\npeer: peer-1  task: T-1  round: 1\nreasons: turn completed; missing cells: Ownership\n---\n/m);

    const none = outbox.records().find((r) => r.peerAgentId === "peer-2")!;
    assert.equal(none.kind, "TURN_ENDED_NO_MESSAGE");
    assert.equal(none.body, "");
    assert.equal(none.taskId, null);
    assert.deepEqual(none.reasons, ["turn failed: provider exited; no assistant message after cursor"]);
    assert.equal(fake.sent[1].text, formatDelivery(none));
    assert.match(fake.sent[1].text, /peer: peer-2  task: \?  round: \?\nreasons: turn failed: provider exited; no assistant message after cursor\n---\n$/);
    assert.deepEqual(outbox.cursor("peer-2"), { epoch: "e2", seq: 1 });
  });
});

test("busy Lead: record stays pending; the Lead's own turn_ended flushes it in createdAt order", async () => {
  await scratch(async (delivery, outbox, lines) => {
    const fake = fakePaseo(
      { "lead-1": leadRunning },
      { "peer-1": [{ epoch: "e1", entries: [assistant(VALID, 1, { messageId: "a" })] }], "peer-2": [{ epoch: "e1", entries: [assistant(VALID, 1, { messageId: "b" })] }] },
    );
    await delivery.onTurnEnded(peerTurn(), fake.paseo);
    await delivery.onTurnEnded(peerTurn({ agent: { ...peerTurn().agent, id: "peer-2" } }), fake.paseo);
    assert.equal(fake.sent.length, 0);
    assert.deepEqual(outbox.pendingFor("lead-1").map((r) => r.peerAgentId), ["peer-1", "peer-2"]);
    assert.ok(lines.some((l) => /lead lead-1 is running; 1 delivery\(ies\) stay pending/.test(l)));

    fake.agents["lead-1"] = leadIdle;
    await delivery.onTurnEnded(
      peerTurn({ agent: { id: "lead-1", workspaceId: null, parentAgentId: "sup-1", provider: "amp-lead", cwd: "/w", title: null }, turnId: "lt1" }),
      fake.paseo,
    );
    assert.deepEqual(fake.sent.map((s) => s.options.sourceAgentId), ["peer-1", "peer-2"]);
    assert.equal(outbox.pendingFor("lead-1").length, 0);
    assert.equal(outbox.records().length, 2, "the Lead's own turn is never recorded as a handback");
  });
});

test("a replayed hook for the same message adds no record and no second send", async () => {
  await scratch(async (delivery, outbox) => {
    const page: TimelinePage = { epoch: "e1", entries: [assistant(VALID, 5, { messageId: "m5" })] };
    const fake = fakePaseo({ "lead-1": leadIdle }, { "peer-1": [page] });
    await delivery.onTurnEnded(peerTurn(), fake.paseo);
    // Second event: the cursor now points past the message, so `after` returns nothing new.
    const empty: TimelinePage = { epoch: "e1", entries: [] };
    const replay = fakePaseo({ "lead-1": leadIdle }, { "peer-1": [empty] });
    await delivery.onTurnEnded(peerTurn(), replay.paseo);
    assert.deepEqual(replay.refetches.map((r) => r.options), [{ direction: "after", cursor: { epoch: "e1", seq: 5 }, limit: 200 }]);
    // Nothing after the cursor: that is a NO_MESSAGE turn for a *different* identity, so one new record…
    assert.equal(outbox.records().length, 2);
    // …but the same page served again (daemon replayed the hook before the cursor moved) is a no-op.
    const again = fakePaseo({ "lead-1": leadIdle }, { "peer-1": [page] });
    await outbox.setCursor("peer-1", { epoch: "e1", seq: 0 });
    await delivery.onTurnEnded(peerTurn(), again.paseo);
    assert.equal(outbox.records().length, 2);
    assert.equal(again.sent.length, 0);
    assert.equal(replay.sent.length, 1);
  });
});

test("stale cursor or changed epoch falls back to the tail; hasNewer pages are followed", async () => {
  await scratch(async (delivery, outbox) => {
    await outbox.load();
    await outbox.setCursor("peer-1", { epoch: "old", seq: 40 });
    const fake = fakePaseo(
      { "lead-1": leadIdle },
      {
        "peer-1": [
          { epoch: "new", staleCursor: true, reset: true, entries: [] },
          { epoch: "new", hasNewer: true, entries: [assistant("draft", 1, { messageId: "d" })] },
          { epoch: "new", entries: [assistant(VALID, 2, { messageId: "final" })] },
        ],
      },
    );
    await delivery.onTurnEnded(peerTurn(), fake.paseo);
    assert.deepEqual(
      fake.refetches.map((r) => r.options),
      [
        { direction: "after", cursor: { epoch: "old", seq: 40 }, limit: 200 },
        { direction: "tail", limit: 200 },
        { direction: "after", cursor: { epoch: "new", seq: 1 }, limit: 200 },
      ],
    );
    const [record] = outbox.records();
    assert.equal(record.kind, "HANDBACK_VALID");
    assert.equal(record.messageId, "final");
    assert.deepEqual(outbox.cursor("peer-1"), { epoch: "new", seq: 2 });
  });
});

test("a failing send leaves the record pending and durable for the next event", async () => {
  await scratch(async (delivery, outbox, lines) => {
    const fake = fakePaseo({ "lead-1": leadIdle }, { "peer-1": [{ epoch: "e1", entries: [assistant(VALID, 1, { messageId: "m" })] }] });
    fake.setFailSend(new Error("socket closed"));
    await delivery.onTurnEnded(peerTurn(), fake.paseo);
    assert.equal(outbox.pendingFor("lead-1").length, 1);
    assert.ok(lines.some((l) => /^error send of [0-9a-f]{12} to lead-1 failed: socket closed/.test(l)));

    const reloaded = new Outbox(outbox.directory);
    await reloaded.load();
    assert.equal(reloaded.pendingFor("lead-1").length, 1, "record was fsynced before the send attempt");

    fake.setFailSend(null);
    await delivery.flush("lead-1", fake.paseo);
    assert.equal(fake.sent.length, 1);
    assert.equal(outbox.pendingFor("lead-1").length, 0);
  });
});
