// Turn-ended delivery: read the Peer's last assistant message, classify it with the shared parser,
// record it in the outbox (fsync) and hand it to the Lead. Event-gated only: no timers, no polling.
import { classifyHandoff } from "./handoff.ts";
import { deliveryId, type DeliveryKind, type DeliveryRecord, type Outbox, type OutboxCursor } from "./outbox.ts";
import type { Logger, TurnEndedEvent } from "./plugin.ts";

/** A Lead seat's agent-profile id, e.g. `codex-lead`, `droid-lead--gpt-6-1-sol--medium`. */
export const LEAD_PROVIDER = /^[a-z]+-lead(--.*)?$/;
const PAGE_LIMIT = 200;
const MAX_PAGES = 20;
const NO_HOOK_AGENT: TurnEndedEvent["agent"] = { id: "", workspaceId: null, parentAgentId: null, provider: "", cwd: "", title: null };

// The slice of PaseoApi (0.14.0, unchanged in 0.15.0) the plugin uses, typed structurally so tests can supply a fake.
export interface TimelineEntry {
  item: { type: string; text?: string; messageId?: string };
  turnId?: string | null;
  seqEnd: number;
}
export interface TimelinePage {
  epoch: string;
  reset?: boolean;
  staleCursor?: boolean;
  hasNewer?: boolean;
  entries: TimelineEntry[];
}
export interface AgentSnapshot {
  id: string;
  provider: string;
  status: string;
  archivedAt?: string | null;
}
export interface AgentHandle {
  refresh(): Promise<{ agent: AgentSnapshot } | null>;
  timeline: {
    refetch(options: { direction: "tail" | "after"; cursor?: OutboxCursor; limit?: number }): Promise<TimelinePage>;
  };
  send(
    text: string,
    options: { sourceAgentId: string; activeTurnBehavior: "steer"; messageId: string },
  ): Promise<void>;
}
export interface DeliveryPaseo {
  agents: { ref(agentId: string): AgentHandle };
}

export interface DeliveryOptions {
  outbox: Outbox;
  log: Logger;
  now?: () => string;
}

export function formatDelivery(record: DeliveryRecord): string {
  const lines = [
    "[epistex-delivery]",
    `delivery-id: ${record.deliveryId}`,
    `kind: ${record.kind}`,
    `peer: ${record.peerAgentId}  task: ${record.taskId ?? "?"}  round: ${record.round ?? "?"}`,
  ];
  if (record.kind !== "HANDBACK_VALID") lines.push(`reasons: ${record.reasons.join("; ")}`);
  const trailing = record.trailing ?? [];
  if (trailing.length) lines.push(`warning: trailing_text_after_handoff (${trailing.length} message(s))`);
  lines.push("---", record.body);
  if (trailing.length) lines.push("--- trailing text after handoff ---", ...trailing);
  return lines.join("\n");
}

function describeOutcome(outcome: TurnEndedEvent["outcome"]): string {
  if (outcome.kind === "failed") return `turn failed: ${outcome.error.message}`;
  if (outcome.kind === "canceled") return `turn canceled: ${outcome.reason}`;
  return "turn completed";
}

export class Delivery {
  private readonly outbox: Outbox;
  private readonly log: Logger;
  private readonly now: () => string;
  private loaded: Promise<void> | null = null;
  private reconciled: Promise<void> | null = null;

  constructor(options: DeliveryOptions) {
    this.outbox = options.outbox;
    this.log = options.log;
    this.now = options.now ?? (() => new Date().toISOString());
  }

  /** Load the outbox once, on the first event. */
  ready(): Promise<void> {
    this.loaded ??= this.outbox.load().then((warnings) => {
      for (const warning of warnings) this.log.error(`outbox: ${warning}`);
    });
    return this.loaded;
  }

  /**
   * Catch up after a plugin or daemon restart. `contribute()` receives no PaseoApi, so this runs
   * on the first lifecycle event instead of at start (still event-gated, never on a timer).
   * Watched Peers are those with a stored cursor; a Peer the plugin never saw is left alone so
   * a fresh install does not replay old handbacks the Lead already handled natively.
   * A Peer that is gone, archived or closed gets one catch-up attempt and is then unwatched, so a
   * dead Peer (e.g. its cwd was deleted) is not read again on every later plugin start.
   */
  reconcile(paseo: DeliveryPaseo): Promise<void> {
    this.reconciled ??= this.ready().then(async () => {
      const leads = new Set<string>();
      for (const peerAgentId of this.outbox.watchedPeers()) {
        const latest = this.outbox.latestFor(peerAgentId);
        if (!latest) continue;
        let finished = false;
        try {
          const peer = (await paseo.agents.ref(peerAgentId).refresh())?.agent;
          finished = !peer || !!peer.archivedAt || peer.status === "closed";
          if (!peer || peer.status === "running" || peer.status === "initializing") continue;
          const synthetic: TurnEndedEvent = { agent: { ...NO_HOOK_AGENT, id: peerAgentId, parentAgentId: latest.leadAgentId, provider: peer.provider }, turnId: null, outcome: { kind: "completed" }, timeline: [] };
          await this.recordTurn(synthetic, latest.leadAgentId, paseo);
        } catch (error) {
          // A Peer whose cwd is gone (deleted scratch clone) makes the timeline read fail; one
          // such Peer must not stop the catch-up of the others or the delivery of live events.
          this.log.error(`reconcile: peer ${peerAgentId} skipped: ${error instanceof Error ? error.message : String(error)}`);
        } finally {
          if (finished) {
            await this.outbox.unwatch(peerAgentId);
            this.log.info(`reconcile: peer ${peerAgentId} is gone, archived or closed; unwatched`);
          }
        }
      }
      for (const record of this.outbox.records()) if (record.state === "pending") leads.add(record.leadAgentId);
      for (const leadAgentId of leads) await this.flush(leadAgentId, paseo);
      this.log.info(`reconciled ${this.outbox.watchedPeers().length} watched peer(s), ${leads.size} lead(s) with pending deliveries`);
    });
    return this.reconciled;
  }

  async onTurnEnded(event: TurnEndedEvent, paseo: DeliveryPaseo): Promise<void> {
    try {
      await this.reconcile(paseo);
    } catch (error) {
      // Never let a failed catch-up block the live event; retry the catch-up on the next one.
      this.reconciled = null;
      this.log.error(`reconcile failed; will retry on the next event: ${error instanceof Error ? error.message : String(error)}`);
    }
    const { agent } = event;
    if (LEAD_PROVIDER.test(agent.provider)) {
      await this.flush(agent.id, paseo);
      return;
    }
    if (!agent.parentAgentId) return; // root agent: out of scope
    const lead = (await paseo.agents.ref(agent.parentAgentId).refresh())?.agent;
    if (!lead || !LEAD_PROVIDER.test(lead.provider)) return; // parent is not a Lead seat
    await this.recordTurn(event, agent.parentAgentId, paseo);
    await this.flush(agent.parentAgentId, paseo, lead);
  }

  private async recordTurn(event: TurnEndedEvent, leadAgentId: string, paseo: DeliveryPaseo): Promise<void> {
    const peerAgentId = event.agent.id;
    const { page, entries } = await this.readAfterCursor(peerAgentId, paseo);
    const assistant = entries.filter((entry) => entry.item.type === "assistant_message");
    const inTurn = event.turnId ? assistant.filter((entry) => entry.turnId === event.turnId) : [];
    const candidates = inTurn.length ? inTurn : assistant;
    // Deliver the turn's last valid handoff, not only its last message: a Peer that writes a valid
    // handoff and then a filler line ("the handoff above stands") must not cost a resend round.
    // The text after it travels with the delivery as a warning for the Lead to read.
    let handoffAt = candidates.length - 1;
    for (let index = candidates.length - 1; index >= 0; index -= 1) {
      if (classifyHandoff(candidates[index].item.text ?? "").valid) {
        handoffAt = index;
        break;
      }
    }
    const last = candidates[handoffAt];
    const trailing = candidates.slice(handoffAt + 1).map((entry) => entry.item.text ?? "");
    const end = entries.at(-1);
    const cursor: OutboxCursor | null = end ? { epoch: page.epoch, seq: end.seqEnd } : this.outbox.cursor(peerAgentId);

    let kind: DeliveryKind;
    let reasons: string[];
    let taskId: string | null = null;
    let round: string | null = null;
    let candidate: string | null = null;
    let body = "";
    let lastMessageId: string;
    if (!last) {
      if (event.turnId && this.outbox.forTurn(peerAgentId, event.turnId)) {
        this.log.info(`turn ${event.turnId} of ${peerAgentId} already recorded; replay ignored`);
        return;
      }
      if (event.outcome.kind === "completed") {
        // Nothing new after the cursor: the turn's message (if any) was delivered already.
        this.log.info(`turn ${event.turnId ?? "?"} of ${peerAgentId} completed without a new assistant message; nothing to deliver`);
        if (cursor) await this.outbox.setCursor(peerAgentId, cursor);
        return;
      }
      kind = "TURN_ENDED_NO_MESSAGE";
      reasons = [`${describeOutcome(event.outcome)}; no assistant message after cursor`];
      lastMessageId = `turn:${event.turnId ?? "?"}:${event.outcome.kind}`;
    } else {
      body = last.item.text ?? "";
      const result = classifyHandoff(body);
      taskId = result.header?.task ?? null;
      round = result.header?.round ?? null;
      candidate = result.shas.length >= 2 ? result.shas.join("..") : result.snapshot ? "snapshot" : null;
      kind = result.valid ? "HANDBACK_VALID" : "TURN_ENDED_INVALID_HANDOFF";
      reasons = result.valid ? [] : [describeOutcome(event.outcome), ...result.reasons];
      lastMessageId = last.item.messageId ?? `seq:${page.epoch}:${last.seqEnd}`;
    }
    const id = deliveryId({ peerAgentId, taskId, round, candidate, lastMessageId });
    if (this.outbox.get(id)) {
      this.log.info(`delivery ${id.slice(0, 12)} already recorded for ${peerAgentId}; replay`);
    } else {
      await this.outbox.append({
        deliveryId: id,
        peerAgentId,
        leadAgentId,
        kind,
        turnId: event.turnId ?? last?.turnId ?? null,
        taskId,
        round,
        candidate,
        messageId: last?.item.messageId ?? null,
        cursor,
        reasons,
        body,
        ...(trailing.length ? { trailing } : {}),
        state: "pending",
        createdAt: this.now(),
      });
      this.log.info(`recorded ${kind} ${id.slice(0, 12)} from ${peerAgentId} for lead ${leadAgentId}`);
    }
    if (cursor) await this.outbox.setCursor(peerAgentId, cursor); // only after the record is durable
  }

  /** Timeline entries after the Peer's stored cursor; falls back to the tail when the cursor is stale. */
  private async readAfterCursor(peerAgentId: string, paseo: DeliveryPaseo): Promise<{ page: TimelinePage; entries: TimelineEntry[] }> {
    const timeline = paseo.agents.ref(peerAgentId).timeline;
    const stored = this.outbox.cursor(peerAgentId);
    let page = stored
      ? await timeline.refetch({ direction: "after", cursor: stored, limit: PAGE_LIMIT })
      : await timeline.refetch({ direction: "tail", limit: PAGE_LIMIT });
    if (stored && (page.reset || page.staleCursor || page.epoch !== stored.epoch)) {
      this.log.info(`cursor for ${peerAgentId} is stale; reading the tail`);
      page = await timeline.refetch({ direction: "tail", limit: PAGE_LIMIT });
    }
    const entries = [...page.entries];
    for (let pages = 1; page.hasNewer && entries.length && pages < MAX_PAGES; pages += 1) {
      const next = await timeline.refetch({ direction: "after", cursor: { epoch: page.epoch, seq: entries.at(-1)!.seqEnd }, limit: PAGE_LIMIT });
      if (next.reset || next.staleCursor || next.epoch !== page.epoch) break;
      entries.push(...next.entries);
      page = { ...next, epoch: page.epoch };
    }
    return { page, entries };
  }

  /** Send every pending record for a Lead, but only while the Lead is not mid-turn. */
  async flush(leadAgentId: string, paseo: DeliveryPaseo, snapshot?: AgentSnapshot): Promise<void> {
    const pending = this.outbox.pendingFor(leadAgentId);
    if (!pending.length) return;
    const handle = paseo.agents.ref(leadAgentId);
    const lead = snapshot ?? (await handle.refresh())?.agent;
    if (!lead) {
      this.log.error(`lead ${leadAgentId} not found; ${pending.length} delivery(ies) stay pending`);
      return;
    }
    if (lead.status !== "idle" && lead.status !== "error") {
      this.log.info(`lead ${leadAgentId} is ${lead.status}; ${pending.length} delivery(ies) stay pending`);
      return;
    }
    for (const record of pending) {
      try {
        await handle.send(formatDelivery(record), {
          sourceAgentId: record.peerAgentId,
          activeTurnBehavior: "steer",
          messageId: record.deliveryId,
        });
      } catch (error) {
        this.log.error(`send of ${record.deliveryId.slice(0, 12)} to ${leadAgentId} failed: ${error instanceof Error ? error.message : String(error)}`);
        return; // keep order; retry on the next lifecycle event or plugin start
      }
      await this.outbox.markSent(record.deliveryId, "accepted", this.now());
      this.log.info(`sent ${record.kind} ${record.deliveryId.slice(0, 12)} to lead ${leadAgentId}`);
    }
  }
}
