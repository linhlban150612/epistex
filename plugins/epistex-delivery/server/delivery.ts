// Turn-ended delivery: read the Peer's last assistant message, classify it with the shared parser,
// record it in the outbox (fsync) and hand it to the Lead. Event-gated only: no timers, no polling.
import { briefIdentity, briefOf, checkBrief, outsideScope, ownedScope } from "./brief.ts";
import { classifyHandoff } from "./handoff.ts";
import { deliveryId, recipientOf, type DeliveryKind, type DeliveryRecord, type Outbox, type OutboxCursor } from "./outbox.ts";
import { describe, type Logger, type PermissionEvent, type TurnEndedEvent } from "./plugin.ts";

/** A Lead seat's agent-profile id, e.g. `codex-lead`, `droid-lead--gpt-6-1-sol--medium`. */
export const LEAD_PROVIDER = /^[a-z]+-lead(--.*)?$/;
/** A Supervisor seat's agent-profile id, e.g. `codex-supervisor`. */
export const SUPERVISOR_PROVIDER = /^[a-z]+-supervisor(--.*)?$/;
const PARENT_LABEL = "paseo.parent-agent-id";
const PAGE_LIMIT = 200;
const MAX_PAGES = 20;
const NO_HOOK_AGENT: TurnEndedEvent["agent"] = { id: "", workspaceId: null, parentAgentId: null, provider: "", cwd: "", title: null };

// The slice of PaseoApi (Paseo >=0.15.0 <0.16) the plugin uses, typed structurally so tests can supply a fake.
export interface TimelineEntry {
  item: {
    type: string;
    text?: string;
    messageId?: string;
    /** Set on a `tool_call` row that is a delivered agent message, not a provider tool call. */
    agentMessage?: { event: string; sender: { id: string }; text: string };
  };
  turnId?: string | null;
  seqEnd: number;
}
export interface TimelinePage {
  epoch: string;
  reset?: boolean;
  staleCursor?: boolean;
  hasNewer?: boolean;
  hasOlder?: boolean;
  entries: TimelineEntry[];
}
export interface AgentSnapshot {
  id: string;
  provider: string;
  status: string;
  archivedAt?: string | null;
  labels?: Record<string, string>;
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
  agents: {
    ref(agentId: string): AgentHandle;
    /** Absent on a daemon without the agent list; the early brief check is then skipped. */
    list?(options: { filter: { labels: Record<string, string> }; page: { limit: number } }): Promise<{ entries: Array<{ agent: AgentSnapshot }> }>;
  };
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
  if (record.kind === "PERMISSION_REQUESTED") {
    lines.push(`lead: ${record.leadAgentId}`, "---", record.body);
    return lines.join("\n");
  }
  if (record.kind === "BRIEF_INVALID") {
    lines.push(`codes: ${record.codes?.join(", ") ?? ""}`, `reasons: ${record.reasons.join("; ")}`);
    return lines.join("\n");
  }
  if (record.kind !== "HANDBACK_VALID") {
    if (record.codes?.length) lines.push(`codes: ${record.codes.join(", ")}`);
    lines.push(`reasons: ${record.reasons.join("; ")}`);
  }
  const trailing = record.trailing ?? [];
  if (trailing.length) lines.push(`warning: trailing_text_after_handoff (${trailing.length} message(s))`);
  for (const warning of record.warnings ?? []) lines.push(`warning: ${warning}`);
  lines.push("---", record.body);
  if (trailing.length) lines.push("--- trailing text after handoff ---", ...trailing);
  return lines.join("\n");
}

/** Highest round a task may reach (first candidate plus two rework rounds) before the Lead must REOPEN or reset (agents/LEAD.md § Acceptance). */
const REWORK_LIMIT = 3;

/**
 * Warnings for a Peer-turn receipt. A round is counted only when it is a plain number. `earlier` are
 * the receipts already stored. A Peer that reports a task for the first time, at a round above one
 * that another Peer of this Lead reported, means the Lead used Round as a step counter or moved the
 * task between Peers. Two review lanes on one round, and rework by the same Peer, do not warn.
 */
export function roundWarnings(
  receipt: Pick<DeliveryRecord, "peerAgentId" | "leadAgentId" | "taskId" | "round">,
  earlier: DeliveryRecord[],
): string[] {
  if (receipt.taskId === null || !/^\d+$/.test(receipt.round ?? "")) return [];
  const round = Number(receipt.round);
  const warnings: string[] = [];
  if (round > REWORK_LIMIT) warnings.push(`round ${round} exceeds rework limit ${REWORK_LIMIT}; REOPEN or context-reset required`);
  const sameTask = earlier.filter((record) => record.leadAgentId === receipt.leadAgentId && record.taskId === receipt.taskId);
  const reused =
    !sameTask.some((record) => record.peerAgentId === receipt.peerAgentId) &&
    sameTask.some((record) => /^\d+$/.test(record.round ?? "") && Number(record.round) < round);
  if (reused) warnings.push("task reused across peers");
  return warnings;
}

/**
 * Tool calls in one Peer session above which a receipt warns the Lead. In 179 Peer sessions over
 * seven days the 95th percentile was 168 calls; the sessions above it lost the brief's rules.
 */
export const TOOL_CALL_LIMIT = 150;
/** Paths named in one scope warning; the rest are counted. */
const SCOPE_WARNING_PATHS = 5;
const BRIEF_INVALID_REASON =
  "the brief you sent to this Peer failed setup/check-brief; this is not a handoff; the Peer still works on that brief";

/** Identity of the one early brief warning a Peer can get. */
function briefDeliveryId(peerAgentId: string): string {
  return deliveryId({ peerAgentId, taskId: null, round: null, candidate: null, lastMessageId: "brief" });
}

/** The text of a message this Lead sent to the Peer, else null. */
function leadMessage(entry: TimelineEntry, leadAgentId: string): string | null {
  // Paseo shows a prompt that is only an agent message as a tool_call row with `agentMessage`
  // (body already unescaped); a prompt with role instructions before the envelope stays a user_message.
  const message = entry.item.agentMessage;
  if (message) return message.event === "message" && message.sender.id === leadAgentId ? message.text : null;
  return entry.item.type === "user_message" ? briefOf(entry.item.text ?? "", leadAgentId) : null;
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
  /** Peers whose first prompt was read at a Lead turn end; in memory only, so a restart reads them once more. */
  private readonly briefChecked = new Set<string>();

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
      const recipients = new Set<string>();
      for (const peerAgentId of this.outbox.watchedPeers()) {
        const latest = this.outbox.latestFor(peerAgentId);
        if (!latest) continue;
        let finished = false;
        try {
          const peer = (await paseo.agents.ref(peerAgentId).refresh())?.agent;
          finished = !peer || !!peer.archivedAt || peer.status === "closed";
          if (!peer || peer.status === "running" || peer.status === "initializing") continue;
          const synthetic: TurnEndedEvent = { agent: { ...NO_HOOK_AGENT, id: peerAgentId, parentAgentId: latest.leadAgentId, provider: peer.provider }, turnId: null, outcome: { kind: "completed" }, timeline: [] };
          await this.recordTurn(synthetic, latest.leadAgentId, paseo, false);
        } catch (error) {
          // A Peer whose cwd is gone (deleted scratch clone) makes the timeline read fail; one
          // such Peer must not stop the catch-up of the others or the delivery of live events.
          this.log.error(`reconcile: peer ${peerAgentId} skipped: ${describe(error)}`);
        } finally {
          if (finished) {
            await this.outbox.unwatch(peerAgentId);
            this.log.info(`reconcile: peer ${peerAgentId} is gone, archived or closed; unwatched`);
          }
        }
      }
      for (const record of this.outbox.records()) if (record.state === "pending") recipients.add(recipientOf(record));
      for (const recipient of recipients) await this.flush(recipient, paseo);
      this.log.info(`reconciled ${this.outbox.watchedPeers().length} watched peer(s), ${recipients.size} recipient(s) with pending deliveries`);
    });
    return this.reconciled;
  }

  private async catchUp(paseo: DeliveryPaseo): Promise<void> {
    try {
      await this.reconcile(paseo);
    } catch (error) {
      // Never let a failed catch-up block the live event; retry the catch-up on the next one.
      this.reconciled = null;
      this.log.error(`reconcile failed; will retry on the next event: ${describe(error)}`);
    }
  }

  /** The Lead seat that created this agent, or null for a root agent or a non-Lead parent. */
  private async leadOf(agent: TurnEndedEvent["agent"], paseo: DeliveryPaseo): Promise<AgentSnapshot | null> {
    if (!agent.parentAgentId) return null;
    const lead = (await paseo.agents.ref(agent.parentAgentId).refresh())?.agent;
    return lead && LEAD_PROVIDER.test(lead.provider) ? lead : null;
  }

  async onTurnEnded(event: TurnEndedEvent, paseo: DeliveryPaseo): Promise<void> {
    await this.catchUp(paseo);
    const { agent } = event;
    if (LEAD_PROVIDER.test(agent.provider) || SUPERVISOR_PROVIDER.test(agent.provider)) {
      if (LEAD_PROVIDER.test(agent.provider)) await this.warnBriefs(agent.id, paseo);
      await this.flush(agent.id, paseo);
      return;
    }
    const lead = await this.leadOf(agent, paseo);
    if (!lead) return;
    await this.recordTurn(event, lead.id, paseo);
    await this.flush(lead.id, paseo, lead);
  }

  /**
   * A Peer waits on a permission: send its agent and request IDs to the Lead's Supervisor, or to the
   * Lead when it has no live Supervisor parent. The plugin never answers the request itself.
   */
  async onPermission(event: PermissionEvent, paseo: DeliveryPaseo): Promise<void> {
    await this.catchUp(paseo);
    const { agent, request } = event;
    const lead = await this.leadOf(agent, paseo);
    if (!lead) return;
    let recipient = lead;
    const supervisorId = lead.labels?.[PARENT_LABEL];
    if (supervisorId) {
      const supervisor = (await paseo.agents.ref(supervisorId).refresh())?.agent;
      if (supervisor && SUPERVISOR_PROVIDER.test(supervisor.provider) && !supervisor.archivedAt && supervisor.status !== "closed") {
        recipient = supervisor;
      }
    }
    const id = deliveryId({ peerAgentId: agent.id, taskId: null, round: null, candidate: null, lastMessageId: `permission:${request.id}` });
    if (this.outbox.get(id)) {
      this.log.info(`permission ${request.id} of ${agent.id} already recorded; replay`);
    } else {
      await this.outbox.append({
        deliveryId: id,
        peerAgentId: agent.id,
        leadAgentId: lead.id,
        ...(recipient.id !== lead.id ? { recipientAgentId: recipient.id } : {}),
        kind: "PERMISSION_REQUESTED",
        turnId: null,
        taskId: null,
        round: null,
        candidate: null,
        messageId: null,
        cursor: null,
        reasons: [],
        body: JSON.stringify({ agentId: agent.id, requestId: request.id, request }, null, 2),
        state: "pending",
        createdAt: this.now(),
      });
      this.log.info(`recorded PERMISSION_REQUESTED ${id.slice(0, 12)} from ${agent.id} for ${recipient.id}`);
    }
    await this.flush(recipient.id, paseo, recipient);
  }

  /**
   * Early brief check, on the Lead's own turn end (the turn in which it briefed its Peers): read the
   * first prompt of each child Peer that has no receipt yet and, when it fails check-brief, record
   * one BRIEF_INVALID delivery for the Lead. The Peer is not stopped. Only the first page of
   * children is read. A failure here must not stop the flush that follows.
   */
  private async warnBriefs(leadAgentId: string, paseo: DeliveryPaseo): Promise<void> {
    if (!paseo.agents.list) return;
    let peers: AgentSnapshot[];
    try {
      peers = (await paseo.agents.list({ filter: { labels: { [PARENT_LABEL]: leadAgentId } }, page: { limit: PAGE_LIMIT } })).entries.map((entry) => entry.agent);
    } catch (error) {
      this.log.error(`peers of ${leadAgentId} not listed; early brief check skipped: ${describe(error)}`);
      return;
    }
    for (const peer of peers) {
      if (this.briefChecked.has(peer.id) || this.outbox.cursor(peer.id) || peer.archivedAt || peer.status === "closed") continue;
      const id = briefDeliveryId(peer.id);
      if (this.outbox.get(id)) {
        this.briefChecked.add(peer.id);
        continue;
      }
      try {
        const page = await paseo.agents.ref(peer.id).timeline.refetch({ direction: "tail", limit: PAGE_LIMIT });
        const brief = await this.firstBrief(peer.id, leadAgentId, page, page.entries, paseo);
        if (brief === undefined) continue; // no first prompt yet: read again at the Lead's next turn end
        this.briefChecked.add(peer.id);
        const codes = brief === null ? [] : checkBrief(brief);
        if (!codes.length) continue;
        // The delivery id stays keyed on the Peer alone; task and round are for the Lead to read.
        const { taskId, round } = briefIdentity(brief!);
        await this.outbox.append({
          deliveryId: id,
          peerAgentId: peer.id,
          leadAgentId,
          kind: "BRIEF_INVALID",
          turnId: null,
          taskId,
          round,
          candidate: null,
          messageId: null,
          cursor: null,
          reasons: [BRIEF_INVALID_REASON],
          codes,
          body: "",
          state: "pending",
          createdAt: this.now(),
        });
        this.log.info(`recorded BRIEF_INVALID ${id.slice(0, 12)} for peer ${peer.id} of lead ${leadAgentId}`);
      } catch (error) {
        this.log.error(`brief of ${peer.id} not checked: ${describe(error)}`);
      }
    }
  }

  private async recordTurn(event: TurnEndedEvent, leadAgentId: string, paseo: DeliveryPaseo, outcomeKnown = true): Promise<void> {
    const peerAgentId = event.agent.id;
    // First read of this Peer: its first prompt is the Lead's brief, checked once below.
    const firstTurn = !this.outbox.cursor(peerAgentId);
    const { page, entries, end } = await this.readAfterCursor(peerAgentId, paseo);
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
    const cursor: OutboxCursor | null = end ? { epoch: page.epoch, seq: end.seqEnd } : this.outbox.cursor(peerAgentId);

    let kind: DeliveryKind;
    let reasons: string[];
    let codes: string[];
    const canceled = event.outcome.kind === "canceled" ? ["TURN_CANCELED"] : [];
    let taskId: string | null = null;
    let round: string | null = null;
    let candidate: string | null = null;
    let body = "";
    let lastMessageId: string;
    let scopeCell = "";
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
      codes = [...canceled, "NO_MESSAGE"];
      lastMessageId = `turn:${event.turnId ?? "?"}:${event.outcome.kind}`;
    } else {
      body = last.item.text ?? "";
      const result = classifyHandoff(body);
      taskId = result.header?.task ?? null;
      round = result.header?.round ?? null;
      candidate = result.shas.length >= 2 ? result.shas.join("..") : result.snapshot ? "snapshot" : null;
      scopeCell = result.cells.Scope ?? "";
      kind = result.valid ? "HANDBACK_VALID" : "TURN_ENDED_INVALID_HANDOFF";
      reasons = result.valid ? [] : [describeOutcome(event.outcome), ...result.reasons];
      codes = result.valid ? [] : [...canceled, ...result.codes];
      lastMessageId = last.item.messageId ?? `seq:${page.epoch}:${last.seqEnd}`;
    }
    const id = deliveryId({ peerAgentId, taskId, round, candidate, lastMessageId });
    if (this.outbox.get(id)) {
      this.log.info(`delivery ${id.slice(0, 12)} already recorded for ${peerAgentId}; replay`);
    } else {
      const warnings = roundWarnings({ peerAgentId, leadAgentId, taskId, round }, this.outbox.records());
      const brief = firstTurn ? ((await this.firstBrief(peerAgentId, leadAgentId, page, entries, paseo)) ?? null) : null;
      const briefCodes = brief === null ? null : checkBrief(brief);
      // Owned scope: the newest Lead message in this read that names one, else the first brief, else
      // the scope stored on an earlier receipt of this Peer.
      const messages = entries.map((entry) => leadMessage(entry, leadAgentId)).filter((text): text is string => text !== null);
      const newScope = [...messages.reverse(), ...(brief === null ? [] : [brief])].map(ownedScope).find((scope) => scope.length);
      const owned = newScope ?? this.outbox.records().filter((record) => record.peerAgentId === peerAgentId && record.ownedScope).at(-1)?.ownedScope ?? [];
      const outside = outsideScope(scopeCell, owned);
      if (outside.length) {
        const more = outside.length > SCOPE_WARNING_PATHS ? ` (+${outside.length - SCOPE_WARNING_PATHS} more)` : "";
        warnings.push(`declared change outside the brief's Owned scope: ${outside.slice(0, SCOPE_WARNING_PATHS).join(", ")}${more}`);
      }
      const toolCalls = entries.filter((entry) => entry.item.type === "tool_call" && !entry.item.agentMessage).length;
      const sessionCalls = this.outbox.records().reduce((sum, record) => sum + (record.peerAgentId === peerAgentId ? (record.toolCalls ?? 0) : 0), toolCalls);
      if (sessionCalls >= TOOL_CALL_LIMIT) warnings.push(`peer session at ${sessionCalls} tool calls (limit ${TOOL_CALL_LIMIT}); context-reset or a new Peer advised`);
      // The Lead already got BRIEF_INVALID for this Peer: do not repeat the warning.
      if (briefCodes?.length && !this.outbox.get(briefDeliveryId(peerAgentId))) warnings.push(`brief failed check-brief: ${briefCodes.join(", ")}`);
      await this.outbox.append({
        deliveryId: id,
        peerAgentId,
        leadAgentId,
        kind,
        outcome: outcomeKnown ? event.outcome.kind : "unknown",
        turnId: event.turnId ?? last?.turnId ?? null,
        taskId,
        round,
        candidate,
        messageId: last?.item.messageId ?? null,
        cursor,
        reasons,
        ...(codes.length ? { codes } : {}),
        ...(warnings.length ? { warnings } : {}),
        ...(briefCodes ? { briefCodes } : {}),
        ...(newScope ? { ownedScope: newScope } : {}),
        toolCalls,
        body,
        ...(trailing.length ? { trailing } : {}),
        state: "pending",
        createdAt: this.now(),
      });
      this.log.info(`recorded ${kind} ${id.slice(0, 12)} from ${peerAgentId} for lead ${leadAgentId}`);
    }
    if (cursor) await this.outbox.setCursor(peerAgentId, cursor); // only after the record is durable
  }

  /**
   * Timeline entries after the Peer's stored cursor; falls back to the tail when the cursor is stale.
   * A replaced timeline (new epoch, e.g. after an archive or reload) carries the old messages under
   * new IDs, so the tail is re-anchored after the last assistant text already recorded for this Peer.
   * `end` is the last entry read, including skipped ones, so the cursor still advances.
   */
  private async readAfterCursor(peerAgentId: string, paseo: DeliveryPaseo): Promise<{ page: TimelinePage; entries: TimelineEntry[]; end?: TimelineEntry }> {
    const timeline = paseo.agents.ref(peerAgentId).timeline;
    const stored = this.outbox.cursor(peerAgentId);
    let page = stored
      ? await timeline.refetch({ direction: "after", cursor: stored, limit: PAGE_LIMIT })
      : await timeline.refetch({ direction: "tail", limit: PAGE_LIMIT });
    const stale = !!stored && (!!page.reset || !!page.staleCursor || page.epoch !== stored.epoch);
    if (stale) {
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
    const end = entries.at(-1);
    const anchor = stale ? this.lastRecordedText(peerAgentId) : null;
    if (anchor !== null) {
      let at = entries.length - 1;
      while (at >= 0 && !(entries[at].item.type === "assistant_message" && entries[at].item.text === anchor)) at -= 1;
      if (at >= 0) {
        this.log.info(`tail of ${peerAgentId} re-anchored after its last recorded message; ${at + 1} entries skipped`);
        entries.splice(0, at + 1);
      }
    }
    return { page, entries, end };
  }

  /**
   * The brief that opened this Peer's session: the Lead's agent-message in the Peer's first user
   * message. Null when that prompt is not from this Lead; undefined when no first prompt was read.
   * A failure to read the start of the timeline must not stop the delivery.
   */
  private async firstBrief(peerAgentId: string, leadAgentId: string, page: TimelinePage, tail: TimelineEntry[], paseo: DeliveryPaseo): Promise<string | null | undefined> {
    let entries = tail;
    if (page.hasOlder) {
      try {
        const start = await paseo.agents.ref(peerAgentId).timeline.refetch({ direction: "after", cursor: { epoch: page.epoch, seq: 0 }, limit: PAGE_LIMIT });
        if (start.reset || start.staleCursor || start.epoch !== page.epoch) return undefined;
        entries = start.entries;
      } catch (error) {
        this.log.error(`brief of ${peerAgentId} not read: ${describe(error)}`);
        return undefined;
      }
    }
    const first = entries.find((entry) => entry.item.type === "user_message" || entry.item.agentMessage);
    return first ? leadMessage(first, leadAgentId) : undefined;
  }

  /** The last assistant text already recorded for a Peer: the newest receipt's trailing text, else its body. */
  private lastRecordedText(peerAgentId: string): string | null {
    const newest = this.outbox
      .records()
      .filter((record) => record.peerAgentId === peerAgentId && record.kind !== "PERMISSION_REQUESTED" && (record.body || record.trailing?.length))
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0];
    return newest ? (newest.trailing?.at(-1) ?? newest.body) : null;
  }

  /** Send every pending record for a recipient (Lead or Supervisor), but only while it is not mid-turn. */
  async flush(recipientAgentId: string, paseo: DeliveryPaseo, snapshot?: AgentSnapshot): Promise<void> {
    const pending = this.outbox.pendingFor(recipientAgentId);
    if (!pending.length) return;
    const handle = paseo.agents.ref(recipientAgentId);
    const recipient = snapshot ?? (await handle.refresh())?.agent;
    if (!recipient) {
      this.log.error(`recipient ${recipientAgentId} not found; ${pending.length} delivery(ies) stay pending`);
      return;
    }
    if (recipient.status !== "idle" && recipient.status !== "error") {
      this.log.info(`recipient ${recipientAgentId} is ${recipient.status}; ${pending.length} delivery(ies) stay pending`);
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
        this.log.error(`send of ${record.deliveryId.slice(0, 12)} to ${recipientAgentId} failed: ${describe(error)}`);
        return; // keep order; retry on the next lifecycle event or plugin start
      }
      await this.outbox.markSent(record.deliveryId, "accepted", this.now());
      this.log.info(`sent ${record.kind} ${record.deliveryId.slice(0, 12)} to ${recipientAgentId}`);
    }
  }
}
