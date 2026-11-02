import assert from "node:assert/strict";
import { appendFile, mkdtemp, readFile, rm } from "node:fs/promises";
import { homedir, tmpdir } from "node:os";
import path from "node:path";
import { test } from "node:test";
import { defaultOutboxDirectory, deliveryId, Outbox, type DeliveryRecord } from "./outbox.ts";

function record(overrides: Partial<DeliveryRecord> = {}): DeliveryRecord {
  return {
    deliveryId: "d1",
    peerAgentId: "peer-1",
    leadAgentId: "lead-1",
    kind: "HANDBACK_VALID",
    turnId: "t1",
    taskId: "T-1",
    round: "1",
    candidate: "abc1234",
    messageId: "m1",
    cursor: { epoch: "e1", seq: 7 },
    reasons: [],
    body: "Task ID: T-1 | Round: 1\n...",
    state: "pending",
    createdAt: "2026-11-02T00:00:01.000Z",
    ...overrides,
  };
}

async function scratch(fn: (dir: string) => Promise<void>) {
  const dir = await mkdtemp(path.join(tmpdir(), "epistex-outbox-"));
  try {
    await fn(path.join(dir, "epistex-delivery"));
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

test("deliveryId is stable, writes unknown fields as ?, and keeps field boundaries", () => {
  const base = { peerAgentId: "peer-1", taskId: "T-1", round: "1", candidate: "abc1234", lastMessageId: "m1" };
  const id = deliveryId(base);
  assert.match(id, /^[0-9a-f]{64}$/);
  assert.equal(deliveryId({ ...base }), id);
  assert.equal(deliveryId({ ...base, taskId: null }), deliveryId({ ...base, taskId: "?" }));
  assert.notEqual(deliveryId({ ...base, lastMessageId: "m2" }), id);
  assert.notEqual(deliveryId({ ...base, taskId: "T-", round: "11" }), deliveryId({ ...base, taskId: "T-1", round: "1" }));
});

test("default directory honours PASEO_HOME and expands ~", () => {
  assert.equal(defaultOutboxDirectory({}), path.join(homedir(), ".paseo", "epistex-delivery"));
  assert.equal(defaultOutboxDirectory({ PASEO_HOME: "/srv/paseo" }), "/srv/paseo/epistex-delivery");
  assert.equal(defaultOutboxDirectory({ PASEO_HOME: "~/alt" }), path.join(homedir(), "alt", "epistex-delivery"));
  assert.equal(defaultOutboxDirectory({ PASEO_HOME: "  " }), path.join(homedir(), ".paseo", "epistex-delivery"));
});

test("append, markSent and reload fold receipts per lead; pending order is by createdAt", async () => {
  await scratch(async (dir) => {
    const outbox = new Outbox(dir);
    await outbox.load();
    await outbox.append(record({ deliveryId: "d2", createdAt: "2026-11-02T00:00:02.000Z" }));
    await outbox.append(record());
    await outbox.append(record({ deliveryId: "d3", leadAgentId: "lead-2", peerAgentId: "peer-2" }));
    await assert.rejects(outbox.append(record()), /duplicate delivery d1/);
    await outbox.markSent("d2", "accepted", "2026-11-02T00:00:03.000Z");
    assert.deepEqual(outbox.pendingFor("lead-1").map((r) => r.deliveryId), ["d1"]);

    const lines = (await readFile(path.join(dir, "lead-1.jsonl"), "utf8")).trimEnd().split("\n");
    assert.equal(lines.length, 3, "two records and one sent update, append-only");
    assert.deepEqual(JSON.parse(lines[2]), { deliveryId: "d2", state: "sent", sentAt: "2026-11-02T00:00:03.000Z", sendReceipt: "accepted" });

    const reloaded = new Outbox(dir);
    assert.deepEqual(await reloaded.load(), []);
    assert.equal(reloaded.get("d2")?.state, "sent");
    assert.equal(reloaded.get("d2")?.sendReceipt, "accepted");
    assert.equal(reloaded.get("d1")?.state, "pending");
    assert.deepEqual(reloaded.pendingFor("lead-2").map((r) => r.deliveryId), ["d3"]);
    assert.equal(reloaded.forTurn("peer-1", "t1")?.deliveryId, "d2", "newest record for the turn");
    assert.equal(reloaded.forTurn("peer-1", "nope"), undefined);
  });
});

test("a torn last line and an orphan update are skipped with warnings, not fatal", async () => {
  await scratch(async (dir) => {
    const outbox = new Outbox(dir);
    await outbox.load();
    await outbox.append(record());
    await appendFile(path.join(dir, "lead-1.jsonl"), '{"deliveryId":"zz","state":"sent","sentAt":"x","sendReceipt":"y"}\n{"deliveryId":"d9","kind":"HANDBACK_VA');
    const reloaded = new Outbox(dir);
    const warnings = await reloaded.load();
    assert.equal(reloaded.records().length, 1);
    assert.deepEqual(warnings, ["lead-1.jsonl:2: update for unknown delivery zz", "lead-1.jsonl:3: unreadable line skipped"]);
  });
});

test("cursors persist through temp file + rename and survive reload", async () => {
  await scratch(async (dir) => {
    const outbox = new Outbox(dir);
    await outbox.load();
    assert.equal(outbox.cursor("peer-1"), null);
    await outbox.setCursor("peer-1", { epoch: "e1", seq: 3 });
    await outbox.setCursor("peer-2", { epoch: "e9", seq: 1 });
    await outbox.setCursor("peer-1", { epoch: "e1", seq: 8 });
    const reloaded = new Outbox(dir);
    await reloaded.load();
    assert.deepEqual(reloaded.cursor("peer-1"), { epoch: "e1", seq: 8 });
    assert.deepEqual(reloaded.cursor("peer-2"), { epoch: "e9", seq: 1 });
    const files = JSON.parse(await readFile(path.join(dir, "cursors.json"), "utf8"));
    assert.deepEqual(Object.keys(files).sort(), ["peer-1", "peer-2"]);
  });
});

test("receipt file names are confined to the outbox directory", async () => {
  await scratch(async (dir) => {
    const outbox = new Outbox(dir);
    await outbox.load();
    await assert.rejects(outbox.append(record({ leadAgentId: "../escape" })), /unsafe lead agent id/);
  });
});
