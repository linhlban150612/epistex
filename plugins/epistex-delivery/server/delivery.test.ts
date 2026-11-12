import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { test } from "node:test";
import { Delivery, formatDelivery, roundWarnings, type AgentSnapshot, type DeliveryPaseo, type TimelineEntry, type TimelinePage } from "./delivery.ts";
import { Outbox } from "./outbox.ts";
import type { Logger, PermissionEvent, TurnEndedEvent } from "./plugin.ts";

const FIXTURES = path.resolve(import.meta.dirname, "../../../tests/fixtures/handoffs");
const VALID = await readFile(path.join(FIXTURES, "valid.txt"), "utf8");
const MISSING = await readFile(path.join(FIXTURES, "missing-cell.txt"), "utf8");

interface Sent {
  agentId: string;
  text: string;
  options: Record<string, unknown>;
}

/** Fake of the PaseoApi slice: per-agent snapshots, timeline pages served in order, recorded sends. */
function fakePaseo(agents: Record<string, AgentSnapshot | null>, pages: Record<string, TimelinePage[] | Error> = {}) {
  const sent: Sent[] = [];
  const refetches: Array<{ agentId: string; options: unknown }> = [];
  let failSend: Error | null = null;
  const paseo: DeliveryPaseo = {
    agents: {
      list: async ({ filter }) => ({
        entries: Object.values(agents)
          .filter((agent): agent is AgentSnapshot => !!agent && Object.entries(filter.labels).every(([key, value]) => agent.labels?.[key] === value))
          .map((agent) => ({ agent })),
      }),
      ref: (agentId) => ({
        refresh: async () => {
          const agent = agents[agentId];
          return agent ? { agent } : null;
        },
        timeline: {
          refetch: async (options) => {
            refetches.push({ agentId, options });
            const queue = pages[agentId] ?? [];
            if (queue instanceof Error) throw queue;
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
    assert.equal(record.outcome, "completed");
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

test("round above the rework limit and a task reused across Peers add warnings; kind is unchanged", async () => {
  const receipt = (round: string | null, peerAgentId = "peer-1", taskId: string | null = "T-1") => ({ peerAgentId, leadAgentId: "lead-1", taskId, round });
  const limit = "round 4 exceeds rework limit 3; REOPEN or context-reset required";
  assert.deepEqual(roundWarnings(receipt("3"), []), []);
  assert.deepEqual(roundWarnings(receipt("4"), []), [limit]);
  assert.deepEqual(roundWarnings(receipt("?"), []), []);
  assert.deepEqual(roundWarnings(receipt(null), []), []);
  assert.deepEqual(roundWarnings(receipt("R4"), []), [], "only a plain number is counted");
  assert.deepEqual(roundWarnings(receipt("4", "peer-1", null), []), []);

  await scratch(async (delivery, outbox) => {
    const round = (n: number) => VALID.replace("Round: 1", `Round: ${n}`);
    const fake = fakePaseo(
      { "lead-1": leadIdle },
      {
        "peer-1": [{ epoch: "e1", entries: [assistant(round(1), 2)] }, { epoch: "e1", entries: [assistant(round(2), 4, { messageId: "m4" })] }],
        "peer-2": [{ epoch: "e2", entries: [assistant(round(1), 2)] }],
        "peer-3": [{ epoch: "e3", entries: [assistant(round(4), 2)] }],
      },
    );
    const peer2 = { agent: { ...peerTurn().agent, id: "peer-2" } };
    await delivery.onTurnEnded(peerTurn(), fake.paseo);
    await delivery.onTurnEnded(peerTurn(peer2), fake.paseo);
    await delivery.onTurnEnded(peerTurn({ turnId: "t2" }), fake.paseo);
    await delivery.onTurnEnded(peerTurn({ agent: { ...peerTurn().agent, id: "peer-3" } }), fake.paseo);
    const records = outbox.records();
    assert.deepEqual(records.map((r) => [r.peerAgentId, r.round, r.kind, r.warnings]), [
      ["peer-1", "1", "HANDBACK_VALID", undefined],
      ["peer-2", "1", "HANDBACK_VALID", undefined], // two lanes on one round are not reuse
      ["peer-1", "2", "HANDBACK_VALID", undefined], // rework by the same Peer
      ["peer-3", "4", "HANDBACK_VALID", [limit, "task reused across peers"]], // a new Peer at a higher round
    ]);
    assert.match(fake.sent[3].text, /round: 4\nwarning: round 4 exceeds rework limit 3; REOPEN or context-reset required\nwarning: task reused across peers\n---\n/);
    assert.equal(fake.sent[2].text, formatDelivery({ ...records[2], warnings: undefined }), "no warning line without a warning");
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
    assert.match(fake.sent[0].text, /^kind: TURN_ENDED_INVALID_HANDOFF\npeer: peer-1  task: T-1  round: 1\ncodes: CELL_MISSING:Ownership\nreasons: turn completed; missing cells: Ownership\n---\n/m);
    assert.deepEqual(invalid.codes, ["CELL_MISSING:Ownership"]);

    const none = outbox.records().find((r) => r.peerAgentId === "peer-2")!;
    assert.equal(none.kind, "TURN_ENDED_NO_MESSAGE");
    assert.equal(none.outcome, "failed");
    assert.equal(none.body, "");
    assert.equal(none.taskId, null);
    assert.deepEqual(none.reasons, ["turn failed: provider exited; no assistant message after cursor"]);
    assert.equal(fake.sent[1].text, formatDelivery(none));
    assert.match(fake.sent[1].text, /peer: peer-2  task: \?  round: \?\ncodes: NO_MESSAGE\nreasons: turn failed: provider exited; no assistant message after cursor\n---\n$/);
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
    assert.ok(lines.some((l) => /recipient lead-1 is running; 1 delivery\(ies\) stay pending/.test(l)));

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
  await scratch(async (delivery, outbox, lines) => {
    const page: TimelinePage = { epoch: "e1", entries: [assistant(VALID, 5, { messageId: "m5" })] };
    const fake = fakePaseo({ "lead-1": leadIdle }, { "peer-1": [page] });
    await delivery.onTurnEnded(peerTurn(), fake.paseo);
    // Replay after the cursor moved: `after` returns nothing and the turn is already recorded.
    const replay = fakePaseo({ "lead-1": leadIdle }, { "peer-1": [{ epoch: "e1", entries: [] }] });
    await delivery.onTurnEnded(peerTurn(), replay.paseo);
    assert.deepEqual(replay.refetches.map((r) => r.options), [{ direction: "after", cursor: { epoch: "e1", seq: 5 }, limit: 200 }]);
    assert.ok(lines.some((l) => /turn t1 of peer-1 already recorded; replay ignored/.test(l)));
    // Replay before the cursor moved: the same page yields the same delivery-id.
    const again = fakePaseo({ "lead-1": leadIdle }, { "peer-1": [page] });
    await outbox.setCursor("peer-1", { epoch: "e1", seq: 0 });
    await delivery.onTurnEnded(peerTurn(), again.paseo);
    assert.equal(outbox.records().length, 1);
    assert.equal(replay.sent.length + again.sent.length, 0);
    assert.ok(lines.some((l) => /already recorded for peer-1; replay/.test(l)));
  });
});

test("a completed turn with no new assistant message is logged, not delivered; a failed one is", async () => {
  await scratch(async (delivery, outbox, lines) => {
    const fake = fakePaseo({ "lead-1": leadIdle }, { "peer-1": [{ epoch: "e1", entries: [{ item: { type: "tool_call" }, turnId: "t1", seqEnd: 2 }] }] });
    await delivery.onTurnEnded(peerTurn(), fake.paseo);
    assert.equal(outbox.records().length, 0);
    assert.deepEqual(outbox.cursor("peer-1"), { epoch: "e1", seq: 2 }, "cursor still advances past the tool call");
    assert.ok(lines.some((l) => /turn t1 of peer-1 completed without a new assistant message/.test(l)));
    await delivery.onTurnEnded(peerTurn({ turnId: "t2", outcome: { kind: "canceled", reason: "daemon restart" } }), fake.paseo);
    assert.equal(outbox.records()[0]?.kind, "TURN_ENDED_NO_MESSAGE");
    assert.equal(outbox.records()[0]?.outcome, "canceled");
    assert.deepEqual(outbox.records()[0]?.reasons, ["turn canceled: daemon restart; no assistant message after cursor"]);
    assert.deepEqual(outbox.records()[0]?.codes, ["TURN_CANCELED", "NO_MESSAGE"]);
  });
});

test("the same turnId reopened with a different last message yields two distinct deliveries", async () => {
  await scratch(async (delivery, outbox) => {
    const second = VALID.replace("Round: 1", "Round: 2");
    const fake = fakePaseo(
      { "lead-1": leadIdle },
      { "peer-1": [{ epoch: "e1", entries: [assistant(VALID, 1, { messageId: "a" })] }, { epoch: "e1", entries: [assistant(second, 2, { messageId: "b" })] }] },
    );
    await delivery.onTurnEnded(peerTurn(), fake.paseo);
    await delivery.onTurnEnded(peerTurn(), fake.paseo);
    const ids = outbox.records().map((r) => r.deliveryId);
    assert.equal(ids.length, 2);
    assert.notEqual(ids[0], ids[1]);
    assert.deepEqual(outbox.records().map((r) => r.round), ["1", "2"]);
    assert.equal(fake.sent.length, 2);
  });
});

test("reconcile on the first event: watched peers are caught up, pending records resent, unseen peers untouched", async () => {
  await scratch(async (first, outbox) => {
    // Session 1: peer-1 delivered; peer-2 recorded but the Lead was busy, so it stays pending.
    const session1 = fakePaseo(
      { "lead-1": leadIdle },
      { "peer-1": [{ epoch: "e1", entries: [assistant(VALID, 1, { messageId: "a" })] }], "peer-2": [{ epoch: "e2", entries: [assistant(VALID, 1, { messageId: "b" })] }] },
    );
    await first.onTurnEnded(peerTurn(), session1.paseo);
    session1.agents["lead-1"] = leadRunning;
    await first.onTurnEnded(peerTurn({ agent: { ...peerTurn().agent, id: "peer-2" } }), session1.paseo);
    assert.equal(outbox.pendingFor("lead-1").length, 1);

    // Session 2: new plugin process, same outbox. peer-1 finished another turn while the plugin was
    // down; peer-2 is mid-turn; peer-9 was never seen; lead-1 is idle again.
    const lines: string[] = [];
    const log: Logger = { info: (m) => lines.push(`info ${m}`), error: (m) => lines.push(`error ${m}`) };
    const second = new Delivery({ outbox: new Outbox(outbox.directory), log, now: () => "2026-11-02T01:00:00.000Z" });
    const session2 = fakePaseo(
      {
        "lead-1": leadIdle,
        "peer-1": { id: "peer-1", provider: "codex-peer", status: "idle" },
        "peer-2": { id: "peer-2", provider: "codex-peer", status: "running" },
        "peer-9": { id: "peer-9", provider: "codex-peer", status: "idle" },
      },
      {
        "peer-1": [{ epoch: "e1", entries: [assistant(VALID.replace("Round: 1", "Round: 2"), 7, { messageId: "c", turnId: "t7" })] }],
        "peer-9": [{ epoch: "e9", entries: [assistant(VALID, 1, { messageId: "z" })] }],
      },
    );
    // The triggering event is an unrelated root agent; reconcile still runs first.
    await second.onTurnEnded(peerTurn({ agent: { ...peerTurn().agent, id: "root", parentAgentId: null } }), session2.paseo);

    assert.deepEqual(session2.refetches.map((r) => [r.agentId, r.options]), [["peer-1", { direction: "after", cursor: { epoch: "e1", seq: 1 }, limit: 200 }]]);
    assert.deepEqual(
      session2.sent.map((s) => [s.options.sourceAgentId, /^kind: (\S+)/m.exec(s.text)?.[1], /round: (\S+)/.exec(s.text)?.[1]]),
      [["peer-2", "HANDBACK_VALID", "1"], ["peer-1", "HANDBACK_VALID", "2"]],
      "pending peer-2 record first (older), then the caught-up peer-1 turn",
    );
    const reloaded = new Outbox(outbox.directory);
    await reloaded.load();
    assert.equal(reloaded.records().length, 3);
    assert.equal(reloaded.pendingFor("lead-1").length, 0);
    assert.equal(reloaded.latestFor("peer-1")?.turnId, "t7", "turnId taken from the timeline entry when the hook has none");
    assert.equal(reloaded.latestFor("peer-1")?.outcome, "unknown", "a catch-up does not know how the turn ended");
    assert.deepEqual(reloaded.cursor("peer-1"), { epoch: "e1", seq: 7 });
    assert.equal(reloaded.cursor("peer-9"), null);
    assert.ok(lines.some((l) => /reconciled 2 watched peer\(s\), 1 recipient\(s\) with pending deliveries/.test(l)));

    // Reconcile is once per process: a later event does not repeat it.
    await second.onTurnEnded(peerTurn({ agent: { ...peerTurn().agent, id: "root", parentAgentId: null } }), session2.paseo);
    assert.equal(session2.refetches.length, 1);
  });
});

test("reconcile skips a watched peer whose timeline read fails and still delivers the live event", async () => {
  await scratch(async (first, outbox) => {
    // Session 1: peer-1 and peer-2 delivered, so both have stored cursors.
    const session1 = fakePaseo(
      { "lead-1": leadIdle },
      { "peer-1": [{ epoch: "e1", entries: [assistant(VALID, 1, { messageId: "a" })] }], "peer-2": [{ epoch: "e2", entries: [assistant(VALID, 1, { messageId: "b" })] }] },
    );
    await first.onTurnEnded(peerTurn(), session1.paseo);
    await first.onTurnEnded(peerTurn({ agent: { ...peerTurn().agent, id: "peer-2" } }), session1.paseo);
    assert.equal(session1.sent.length, 2);

    // Session 2: peer-1's scratch clone was deleted, so Paseo rejects its timeline read (seen live on
    // 0.14.0); peer-2 finished another turn while the plugin was down; peer-3 ends a turn now.
    const lines: string[] = [];
    const log: Logger = { info: (m) => lines.push(`info ${m}`), error: (m) => lines.push(`error ${m}`) };
    const second = new Delivery({ outbox: new Outbox(outbox.directory), log, now: () => "2026-11-02T01:00:00.000Z" });
    const session2 = fakePaseo(
      {
        "lead-1": leadIdle,
        "peer-1": { id: "peer-1", provider: "codex-peer", status: "closed" },
        "peer-2": { id: "peer-2", provider: "codex-peer", status: "idle" },
        "peer-3": { id: "peer-3", provider: "codex-peer", status: "idle" },
      },
      {
        "peer-1": new Error("Invalid params: Working directory does not exist: /gone"),
        "peer-2": [{ epoch: "e2", entries: [assistant(VALID.replace("Round: 1", "Round: 2"), 5, { messageId: "c" })] }],
        "peer-3": [{ epoch: "e3", entries: [assistant(VALID, 1, { messageId: "d" })] }],
      },
    );
    await second.onTurnEnded(peerTurn({ agent: { ...peerTurn().agent, id: "peer-3" } }), session2.paseo);

    assert.deepEqual(
      session2.sent.map((s) => [s.options.sourceAgentId, /round: (\S+)/.exec(s.text)?.[1]]),
      [["peer-2", "2"], ["peer-3", "1"]],
      "the caught-up peer-2 turn, then the live peer-3 turn; peer-1 is skipped, not fatal",
    );
    assert.ok(lines.some((l) => /^error reconcile: peer peer-1 skipped: Invalid params: Working directory does not exist/.test(l)));
    assert.ok(lines.some((l) => /reconciled 1 watched peer\(s\), 1 recipient\(s\)/.test(l)), "reconcile completed despite the failing peer");

    // Reconcile completed, so a later event does not repeat it.
    const refetches = session2.refetches.length;
    await second.onTurnEnded(peerTurn({ agent: { ...peerTurn().agent, id: "root", parentAgentId: null } }), session2.paseo);
    assert.equal(session2.refetches.length, refetches);
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

test("a replaced timeline (new epoch) is re-anchored: the old handoff is not recorded again, a newer message is", async () => {
  await scratch(async (delivery, outbox, lines) => {
    const round2 = VALID.replace("Round: 1", "Round: 2");
    const replaced = (entries: TimelineEntry[]): TimelinePage[] => [{ epoch: "e2", staleCursor: true, entries: [] }, { epoch: "e2", entries }];
    const fake = fakePaseo(
      { "lead-1": leadIdle },
      {
        "peer-1": [{ epoch: "e1", entries: [assistant(VALID, 3, { messageId: "a" })] }],
        "peer-2": [{ epoch: "e1", entries: [assistant(VALID, 3, { messageId: "a2" })] }],
      },
    );
    const peer2 = { ...peerTurn().agent, id: "peer-2" };
    await delivery.onTurnEnded(peerTurn(), fake.paseo);
    await delivery.onTurnEnded(peerTurn({ agent: peer2 }), fake.paseo);
    assert.equal(outbox.records().length, 2);

    // The same history comes back under new message IDs; peer-2 also wrote a new handoff after it.
    const pages = {
      "peer-1": replaced([{ item: { type: "user_message", text: "brief" }, seqEnd: 1 }, assistant(VALID, 2, { messageId: "b" }), { item: { type: "tool_call" }, turnId: "t2", seqEnd: 4 }]),
      "peer-2": replaced([assistant(VALID, 2, { messageId: "b2" }), assistant(round2, 5, { messageId: "c2", turnId: "t2" })]),
    };
    const second = fakePaseo({ "lead-1": leadIdle }, pages);
    await delivery.onTurnEnded(peerTurn({ turnId: "t2" }), second.paseo);
    await delivery.onTurnEnded(peerTurn({ agent: peer2, turnId: "t2" }), second.paseo);

    const records = outbox.records();
    assert.equal(records.length, 3, "only peer-2's new handoff is recorded");
    assert.deepEqual([records[2].peerAgentId, records[2].round, records[2].messageId], ["peer-2", "2", "c2"]);
    assert.deepEqual(outbox.cursor("peer-1"), { epoch: "e2", seq: 4 }, "cursor advances past the skipped entries");
    assert.ok(lines.some((l) => /tail of peer-1 re-anchored after its last recorded message; 2 entries skipped/.test(l)));
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

function permission(requestId = "req-1"): PermissionEvent {
  return {
    agent: peerTurn().agent,
    request: { id: requestId, provider: "codex-peer", name: "Bash", kind: "tool", input: { command: "git push" } },
  } as PermissionEvent;
}

test("permission request: sent to the Lead's Supervisor with its IDs, recorded once, never answered", async () => {
  await scratch(async (delivery, outbox, lines) => {
    const lead: AgentSnapshot = { ...leadIdle, labels: { "paseo.parent-agent-id": "sup-1" } };
    const fake = fakePaseo({ "lead-1": lead, "sup-1": { id: "sup-1", provider: "claude-supervisor", status: "running" } });
    await delivery.onPermission(permission(), fake.paseo);
    const [record] = outbox.records();
    assert.equal(record.kind, "PERMISSION_REQUESTED");
    assert.equal(record.leadAgentId, "lead-1", "the receipt stays in the owning Lead's file");
    assert.equal(record.recipientAgentId, "sup-1");
    assert.equal(fake.sent.length, 0, "a running Supervisor is not disturbed");
    assert.ok(lines.some((l) => /recipient sup-1 is running; 1 delivery\(ies\) stay pending/.test(l)));

    // A replayed hook adds nothing; the Supervisor's own turn end flushes the record.
    await delivery.onPermission(permission(), fake.paseo);
    assert.equal(outbox.records().length, 1);
    fake.agents["sup-1"] = { id: "sup-1", provider: "claude-supervisor", status: "idle" };
    await delivery.onTurnEnded(
      peerTurn({ agent: { id: "sup-1", workspaceId: null, parentAgentId: null, provider: "claude-supervisor", cwd: "/s", title: null } }),
      fake.paseo,
    );
    assert.equal(outbox.records().length, 1, "the Supervisor's own turn is never recorded");
    assert.equal(fake.sent.length, 1);
    assert.equal(fake.sent[0].agentId, "sup-1");
    const body = JSON.stringify({ agentId: "peer-1", requestId: "req-1", request: permission().request }, null, 2);
    assert.equal(
      fake.sent[0].text,
      ["[epistex-delivery]", `delivery-id: ${record.deliveryId}`, "kind: PERMISSION_REQUESTED", "peer: peer-1  task: ?  round: ?", "lead: lead-1", "---", body].join("\n"),
    );
    assert.equal(outbox.pendingFor("sup-1").length, 0);
  });
});

test("permission request: goes to the Lead without a live Supervisor parent; ignored for non-Lead parents", async () => {
  await scratch(async (delivery, outbox) => {
    const fake = fakePaseo({
      "lead-1": { ...leadIdle, labels: { "paseo.parent-agent-id": "other-1" } },
      "other-1": { id: "other-1", provider: "codex-peer", status: "idle" },
      "lead-2": { id: "lead-2", provider: "amp-lead", status: "idle", labels: { "paseo.parent-agent-id": "sup-gone" } },
      "sup-gone": { id: "sup-gone", provider: "codex-supervisor", status: "idle", archivedAt: "2026-11-01T00:00:00Z" },
      "sup-1": { id: "sup-1", provider: "codex-supervisor", status: "idle" },
    });
    await delivery.onPermission(permission("a"), fake.paseo);
    await delivery.onPermission({ ...permission("b"), agent: { ...peerTurn().agent, id: "peer-2", parentAgentId: "lead-2" } }, fake.paseo);
    await delivery.onPermission({ ...permission("c"), agent: { ...peerTurn().agent, parentAgentId: "sup-1" } }, fake.paseo);
    assert.deepEqual(fake.sent.map((s) => s.agentId), ["lead-1", "lead-2"]);
    assert.deepEqual(outbox.records().map((r) => r.recipientAgentId), [undefined, undefined]);
  });
});

test("first receipt of a Peer checks the Lead's brief: a failed brief warns the Lead, a later turn is not checked again", async () => {
  const user = (body: string, seqEnd: number): TimelineEntry => ({
    item: { type: "user_message", text: `Role instructions for this session:\nOwned scope in the brief is your write authority.\n<paseo-system version="1" kind="agent-message" source-agent-id="lead-1" message-id="m0">\n${body}\n</paseo-system>` },
    seqEnd,
  });
  const good =
    "Task ID: T-1\nRound: 1\nBaseline: base 3f2a9c1d4e5b6a7f8091a2b3c4d5e6f708192a3b\nOwned scope: src/** &amp; docs\nAuthority: edit files in owned scope\n";
  await scratch(async (delivery, outbox) => {
    // The tail does not reach the first prompt: the start of the timeline is read once.
    const fake = fakePaseo(
      { "lead-1": leadIdle },
      { "peer-1": [{ epoch: "e1", hasOlder: true, entries: [assistant(VALID, 300, { messageId: "m9" })] }, { epoch: "e1", entries: [user("Fix the login bug. Round: 1", 1)] }] },
    );
    await delivery.onTurnEnded(peerTurn(), fake.paseo);
    assert.deepEqual(fake.refetches.map((r) => r.options), [
      { direction: "tail", limit: 200 },
      { direction: "after", cursor: { epoch: "e1", seq: 0 }, limit: 200 },
    ]);
    const [record] = outbox.records();
    assert.equal(record.kind, "HANDBACK_VALID", "a brief warning does not change the kind");
    assert.deepEqual(record.briefCodes, ["TASK_ID_MISSING", "OWNED_SCOPE_MISSING", "AUTHORITY_MISSING", "BASELINE_MISSING"]);
    assert.match(fake.sent[0].text, /^warning: brief failed check-brief: TASK_ID_MISSING, OWNED_SCOPE_MISSING, AUTHORITY_MISSING, BASELINE_MISSING$/m);

    const later = fakePaseo({ "lead-1": leadIdle }, { "peer-1": [{ epoch: "e1", entries: [user("rework", 301), assistant(VALID.replace("Round: 1", "Round: 2"), 310, { messageId: "m10", turnId: "t2" })] }] });
    await delivery.onTurnEnded(peerTurn({ turnId: "t2" }), later.paseo);
    assert.equal(outbox.records()[1].briefCodes, undefined);
    assert.doesNotMatch(later.sent[0].text, /check-brief/);
  });
  await scratch(async (delivery, outbox) => {
    const fake = fakePaseo({ "lead-1": leadIdle }, { "peer-1": [{ epoch: "e1", entries: [user(good, 1), assistant(VALID, 9)] }] });
    await delivery.onTurnEnded(peerTurn(), fake.paseo);
    assert.deepEqual(outbox.records()[0].briefCodes, [], "a passing brief is recorded with no codes");
    assert.doesNotMatch(fake.sent[0].text, /warning:/);
  });
  await scratch(async (delivery, outbox) => {
    // Paseo 0.15.4: a first prompt that is only the Lead's message is a tool_call row with agentMessage.
    const row = (id: string): TimelineEntry => ({
      item: { type: "tool_call", agentMessage: { event: "message", sender: { id }, text: "Task ID: T-1 | Round: 1. Read a.txt." } },
      seqEnd: 1,
    });
    const fake = fakePaseo({ "lead-1": leadIdle }, { "peer-1": [{ epoch: "e1", entries: [row("lead-1"), { item: { type: "tool_call" }, seqEnd: 2 }, assistant(VALID, 9)] }] });
    await delivery.onTurnEnded(peerTurn(), fake.paseo);
    assert.deepEqual(outbox.records()[0].briefCodes, ["OWNED_SCOPE_MISSING", "AUTHORITY_MISSING", "BASELINE_MISSING"]);
    assert.equal(outbox.records()[0].toolCalls, 1, "a delivered agent message is not a tool call");
    const other = fakePaseo({ "lead-1": leadIdle }, { "peer-2": [{ epoch: "e1", entries: [row("someone-else"), assistant(VALID.replace("T-1", "T-2"), 9)] }] });
    await delivery.onTurnEnded(peerTurn({ agent: { ...peerTurn().agent, id: "peer-2" } }), other.paseo);
    assert.equal(outbox.records()[1].briefCodes, undefined);
  });
  await scratch(async (delivery, outbox) => {
    // A first prompt that is not this Lead's agent-message (a Human prompt) is not checked.
    const fake = fakePaseo({ "lead-1": leadIdle }, { "peer-1": [{ epoch: "e1", entries: [{ item: { type: "user_message", text: "hello" }, seqEnd: 1 }, assistant(VALID, 9)] }] });
    await delivery.onTurnEnded(peerTurn(), fake.paseo);
    assert.equal(outbox.records()[0].briefCodes, undefined);
  });
});

test("tool calls are counted per Peer across receipts; at the limit the receipt warns the Lead", async () => {
  await scratch(async (delivery, outbox) => {
    const calls = (from: number, count: number, turnId: string): TimelineEntry[] =>
      Array.from({ length: count }, (_, index) => ({ item: { type: "tool_call" }, turnId, seqEnd: from + index }));
    const first = fakePaseo({ "lead-1": leadIdle }, { "peer-1": [{ epoch: "e1", entries: [...calls(1, 100, "t1"), assistant(VALID, 101, { messageId: "m1" })] }] });
    await delivery.onTurnEnded(peerTurn(), first.paseo);
    assert.equal(outbox.records()[0].toolCalls, 100);
    assert.doesNotMatch(first.sent[0].text, /tool calls/);

    // Another Peer of the same Lead has its own count.
    const other = fakePaseo({ "lead-1": leadIdle }, { "peer-2": [{ epoch: "e2", entries: [...calls(1, 49, "t1"), assistant(VALID.replace("T-1", "T-2"), 50, { messageId: "n1" })] }] });
    await delivery.onTurnEnded(peerTurn({ agent: { ...peerTurn().agent, id: "peer-2" } }), other.paseo);
    assert.doesNotMatch(other.sent[0].text, /tool calls/);

    const second = fakePaseo({ "lead-1": leadIdle }, { "peer-1": [{ epoch: "e1", entries: [...calls(102, 50, "t2"), assistant(VALID.replace("Round: 1", "Round: 2"), 152, { messageId: "m2", turnId: "t2" })] }] });
    await delivery.onTurnEnded(peerTurn({ turnId: "t2" }), second.paseo);
    const record = outbox.records().find((r) => r.messageId === "m2")!;
    assert.equal(record.toolCalls, 50);
    assert.equal(record.kind, "HANDBACK_VALID");
    assert.match(second.sent[0].text, /^warning: peer session at 150 tool calls \(limit 150\); context-reset or a new Peer advised$/m);
  });
});

test("Lead turn end: a new Peer's failed brief is delivered at once as BRIEF_INVALID, once, and not repeated at the first handback", async () => {
  const row = (text: string): TimelineEntry => ({ item: { type: "tool_call", agentMessage: { event: "message", sender: { id: "lead-1" }, text } }, seqEnd: 1 });
  const child = (id: string): AgentSnapshot => ({ id, provider: "codex-peer", status: "running", labels: { "paseo.parent-agent-id": "lead-1" } });
  const leadTurn = peerTurn({ agent: { ...peerTurn().agent, id: "lead-1", parentAgentId: null, provider: "amp-lead" } });
  const good = "Task ID: T-2\nRound: 1\nBaseline: base 3f2a9c1d4e5b6a7f8091a2b3c4d5e6f708192a3b\nOwned scope: src/**\nAuthority: edit files in owned scope\n";
  await scratch(async (delivery, outbox, lines) => {
    const pages = { "peer-1": [{ epoch: "e1", entries: [row("Task ID: T-1 | Round: 1. Read a.txt.")] }], "peer-2": [{ epoch: "e1", entries: [row(good)] }], "peer-3": [{ epoch: "e1", entries: [] }] };
    const fake = fakePaseo({ "lead-1": leadIdle, "peer-1": child("peer-1"), "peer-2": child("peer-2"), "peer-3": child("peer-3"), other: { id: "other", provider: "codex-peer", status: "running" } }, pages);
    await delivery.onTurnEnded(leadTurn, fake.paseo);
    assert.equal(fake.sent.length, 1, "only the failed brief is reported");
    assert.equal(fake.sent[0].agentId, "lead-1");
    assert.equal(
      fake.sent[0].text,
      `[epistex-delivery]\ndelivery-id: ${outbox.records()[0].deliveryId}\nkind: BRIEF_INVALID\npeer: peer-1  task: T-1  round: 1\n` +
        "codes: OWNED_SCOPE_MISSING, AUTHORITY_MISSING, BASELINE_MISSING\n" +
        "reasons: the brief you sent to this Peer failed setup/check-brief; this is not a handoff; the Peer still works on that brief",
    );
    assert.equal(outbox.cursor("peer-1"), null, "the early check does not move the Peer's cursor");

    // The Lead's next turn end: peer-1 and peer-2 are not read again; peer-3 (no prompt yet) is.
    const before = fake.refetches.length;
    await delivery.onTurnEnded(leadTurn, fake.paseo);
    assert.deepEqual(fake.refetches.slice(before).map((r) => r.agentId), ["peer-3"]);
    assert.equal(fake.sent.length, 1);

    // First handback of peer-1: briefCodes are stored, the warning is not sent a second time.
    pages["peer-1"] = [{ epoch: "e1", entries: [row("Task ID: T-1 | Round: 1. Read a.txt."), assistant(VALID, 9)] }];
    await delivery.onTurnEnded(peerTurn(), fake.paseo);
    const handback = outbox.records().at(-1)!;
    assert.equal(handback.kind, "HANDBACK_VALID");
    assert.deepEqual(handback.briefCodes, ["OWNED_SCOPE_MISSING", "AUTHORITY_MISSING", "BASELINE_MISSING"]);
    assert.doesNotMatch(fake.sent.at(-1)!.text, /check-brief/);
    assert.ok(!lines.some((line) => line.startsWith("error")), lines.join("\n"));
  });
  await scratch(async (delivery, outbox, lines) => {
    // A daemon whose agent list fails: logged, and the pending deliveries are still flushed.
    const fake = fakePaseo({ "lead-1": leadIdle });
    fake.paseo.agents.list = async () => {
      throw new Error("no list");
    };
    await delivery.onTurnEnded(leadTurn, fake.paseo);
    assert.equal(outbox.records().length, 0);
    assert.ok(lines.some((line) => /early brief check skipped: no list/.test(line)));
  });
});

test("declared changes outside the brief's Owned scope warn the Lead; the newest Lead message with a scope wins", async () => {
  const row = (text: string, seqEnd: number): TimelineEntry => ({ item: { type: "tool_call", agentMessage: { event: "message", sender: { id: "lead-1" }, text } }, seqEnd });
  const brief = (scope: string) => `Task ID: T-1\nRound: 1\nBaseline: base 3f2a9c1d4e5b6a7f8091a2b3c4d5e6f708192a3b\nOwned scope:\n${scope}\nAuthority: edit files in owned scope\n`;
  await scratch(async (delivery, outbox) => {
    // valid.txt declares `Changed: src/a.py src/b.py`.
    const fake = fakePaseo({ "lead-1": leadIdle }, { "peer-1": [{ epoch: "e1", entries: [row(brief("- `src/a.py`\n- docs/"), 1), assistant(VALID, 9)] }] });
    await delivery.onTurnEnded(peerTurn(), fake.paseo);
    assert.equal(outbox.records()[0].kind, "HANDBACK_VALID", "a scope warning does not change the kind");
    assert.deepEqual(outbox.records()[0].ownedScope, ["src/a.py", "docs/"]);
    assert.match(fake.sent[0].text, /^warning: declared change outside the brief's Owned scope: src\/b\.py$/m);

    // A later turn with no new brief reuses the stored scope.
    const second = fakePaseo({ "lead-1": leadIdle }, { "peer-1": [{ epoch: "e1", entries: [row("rework the parser", 10), assistant(VALID.replace("Round: 1", "Round: 2"), 12, { messageId: "m2", turnId: "t2" })] }] });
    await delivery.onTurnEnded(peerTurn({ turnId: "t2" }), second.paseo);
    assert.equal(outbox.records()[1].ownedScope, undefined);
    assert.match(second.sent[0].text, /Owned scope: src\/b\.py$/m);

    // A new brief widens the scope: no warning.
    const third = fakePaseo({ "lead-1": leadIdle }, { "peer-1": [{ epoch: "e1", entries: [row(brief("  src/**"), 13), assistant(VALID.replace("Round: 1", "Round: 3"), 15, { messageId: "m3", turnId: "t3" })] }] });
    await delivery.onTurnEnded(peerTurn({ turnId: "t3" }), third.paseo);
    assert.deepEqual(outbox.records()[2].ownedScope, ["src/**"]);
    assert.doesNotMatch(third.sent[0].text, /Owned scope/);
  });
  await scratch(async (delivery, outbox) => {
    // A directory name owns the files below it; a scope in prose (no path) is never compared.
    for (const [peer, scope] of [["peer-1", "- src/"], ["peer-2", "- the parser only"]] as const) {
      const fake = fakePaseo({ "lead-1": leadIdle }, { [peer]: [{ epoch: "e1", entries: [row(brief(scope), 1), assistant(VALID, 9)] }] });
      await delivery.onTurnEnded(peerTurn({ agent: { ...peerTurn().agent, id: peer } }), fake.paseo);
      assert.doesNotMatch(fake.sent[0].text, /warning:/);
    }
    assert.deepEqual(outbox.records().map((record) => record.ownedScope), [["src/"], undefined]);
  });
});
