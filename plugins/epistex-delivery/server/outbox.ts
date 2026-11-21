import { createHash } from "node:crypto";
import { mkdir, open, readdir, readFile, rename } from "node:fs/promises";
import { homedir } from "node:os";
import path from "node:path";

export interface OutboxCursor {
  epoch: string;
  seq: number;
}

export type DeliveryKind =
  | "HANDBACK_VALID"
  | "TURN_ENDED_INVALID_HANDOFF"
  | "TURN_ENDED_FAILED"
  | "TURN_ENDED_CANCELED"
  | "TURN_ENDED_NO_MESSAGE"
  | "PEER_REMINDED"
  | "PERMISSION_REQUESTED"
  | "BRIEF_INVALID";

export interface DeliveryRecord {
  deliveryId: string;
  peerAgentId: string;
  leadAgentId: string;
  recipientAgentId?: string;
  kind: DeliveryKind;
  outcome?: "completed" | "failed" | "canceled" | "unknown";
  turnId: string | null;
  taskId: string | null;
  round: string | null;
  candidate: string | null;
  messageId: string | null;
  cursor: OutboxCursor | null;
  reasons: string[];
  codes?: string[];
  warnings?: string[];
  briefCodes?: string[];
  ownedScope?: string[];
  toolCalls?: number;
  body: string;
  trailing?: string[];
  submitted?: boolean;
  state: "pending" | "sent";
  createdAt: string;
  sentAt?: string;
  sendReceipt?: string;
}

export interface Submission {
  id: string;
  taskId: string;
  round: string;
  candidate: string | null;
  body: string;
  submittedAt: string;
}

interface SentUpdate {
  deliveryId: string;
  state: "sent";
  sentAt: string;
  sendReceipt: string;
}

export function deliveryId(parts: {
  peerAgentId: string;
  taskId: string | null;
  round: string | null;
  candidate: string | null;
  lastMessageId: string;
}): string {
  const hash = createHash("sha256");
  for (const part of [parts.peerAgentId, parts.taskId ?? "?", parts.round ?? "?", parts.candidate ?? "?", parts.lastMessageId]) {
    hash.update(part, "utf8");
    hash.update("\u0000");
  }
  return hash.digest("hex");
}

export function recipientOf(record: DeliveryRecord): string {
  return record.recipientAgentId ?? record.leadAgentId;
}

export function defaultOutboxDirectory(env: NodeJS.ProcessEnv = process.env): string {
  const home = env.PASEO_HOME?.trim() || "~/.paseo";
  const expanded = home === "~" || home.startsWith("~/") ? path.join(homedir(), home.slice(1)) : home;
  return path.join(path.resolve(expanded), "epistex-delivery");
}

async function appendSynced(file: string, line: string): Promise<void> {
  const handle = await open(file, "a");
  try {
    await handle.writeFile(line, "utf8");
    await handle.sync();
  } finally {
    await handle.close();
  }
}

async function syncDirectory(directory: string): Promise<void> {
  const handle = await open(directory, "r");
  try {
    await handle.sync();
  } catch {
  } finally {
    await handle.close();
  }
}

export class Outbox {
  private readonly byId = new Map<string, DeliveryRecord>();
  private cursors: Record<string, OutboxCursor> = {};
  private submissions: Record<string, Submission> = {};
  private readonly warnings: string[] = [];
  readonly directory: string;

  constructor(directory: string) {
    this.directory = directory;
  }

  async load(): Promise<string[]> {
    this.byId.clear();
    this.cursors = {};
    this.submissions = {};
    this.warnings.length = 0;
    await mkdir(this.directory, { recursive: true });
    const names = (await readdir(this.directory)).filter((name) => name.endsWith(".jsonl")).sort();
    for (const name of names) {
      const text = await readFile(path.join(this.directory, name), "utf8");
      const lines = text.split("\n");
      lines.forEach((line, index) => {
        if (!line) return;
        let parsed: DeliveryRecord | SentUpdate;
        try {
          parsed = JSON.parse(line);
        } catch {
          this.warnings.push(`${name}:${index + 1}: unreadable line skipped`);
          return;
        }
        if ("kind" in parsed) {
          this.byId.set(parsed.deliveryId, parsed);
          return;
        }
        const record = this.byId.get(parsed.deliveryId);
        if (!record) {
          this.warnings.push(`${name}:${index + 1}: update for unknown delivery ${parsed.deliveryId}`);
          return;
        }
        this.byId.set(parsed.deliveryId, { ...record, state: "sent", sentAt: parsed.sentAt, sendReceipt: parsed.sendReceipt });
      });
    }
    try {
      this.cursors = JSON.parse(await readFile(this.cursorsPath(), "utf8"));
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") this.warnings.push(`cursors.json unreadable: ${String(error)}`);
      this.cursors = {};
    }
    try {
      this.submissions = JSON.parse(await readFile(this.submissionsPath(), "utf8"));
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") this.warnings.push(`submissions.json unreadable: ${String(error)}`);
      this.submissions = {};
    }
    return [...this.warnings];
  }

  records(): DeliveryRecord[] {
    return [...this.byId.values()];
  }

  get(deliveryId: string): DeliveryRecord | undefined {
    return this.byId.get(deliveryId);
  }

  pendingFor(recipientAgentId: string): DeliveryRecord[] {
    return this.records()
      .filter((record) => recipientOf(record) === recipientAgentId && record.state === "pending")
      .sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  }

  watchedPeers(): string[] {
    return Object.keys(this.cursors).sort();
  }

  latestFor(peerAgentId: string): DeliveryRecord | undefined {
    return this.records()
      .filter((record) => record.peerAgentId === peerAgentId)
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0];
  }

  forTurn(peerAgentId: string, turnId: string): DeliveryRecord | undefined {
    return this.records()
      .filter((record) => record.peerAgentId === peerAgentId && record.turnId === turnId)
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0];
  }

  async append(record: DeliveryRecord): Promise<void> {
    if (this.byId.has(record.deliveryId)) throw new Error(`duplicate delivery ${record.deliveryId}`);
    await mkdir(this.directory, { recursive: true });
    await appendSynced(this.receiptPath(record.leadAgentId), JSON.stringify(record) + "\n");
    this.byId.set(record.deliveryId, record);
  }

  async markSent(deliveryId: string, sendReceipt: string, sentAt = new Date().toISOString()): Promise<DeliveryRecord> {
    const record = this.byId.get(deliveryId);
    if (!record) throw new Error(`unknown delivery ${deliveryId}`);
    const update: SentUpdate = { deliveryId, state: "sent", sentAt, sendReceipt };
    await appendSynced(this.receiptPath(record.leadAgentId), JSON.stringify(update) + "\n");
    const sent: DeliveryRecord = { ...record, state: "sent", sentAt, sendReceipt };
    this.byId.set(deliveryId, sent);
    return sent;
  }

  cursor(peerAgentId: string): OutboxCursor | null {
    return this.cursors[peerAgentId] ?? null;
  }

  async setCursor(peerAgentId: string, cursor: OutboxCursor): Promise<void> {
    await this.writeCursors({ ...this.cursors, [peerAgentId]: cursor });
  }

  async unwatch(peerAgentId: string): Promise<void> {
    if (!(peerAgentId in this.cursors)) return;
    const { [peerAgentId]: _dropped, ...next } = this.cursors;
    await this.writeCursors(next);
  }

  submission(peerAgentId: string): Submission | null {
    return this.submissions[peerAgentId] ?? null;
  }

  async setSubmission(peerAgentId: string, submission: Submission): Promise<void> {
    const next = { ...this.submissions, [peerAgentId]: submission };
    await this.replace(this.submissionsPath(), next);
    this.submissions = next;
  }

  async clearSubmission(peerAgentId: string, id: string): Promise<void> {
    if (this.submissions[peerAgentId]?.id !== id) return;
    const { [peerAgentId]: _dropped, ...next } = this.submissions;
    await this.replace(this.submissionsPath(), next);
    this.submissions = next;
  }

  private async writeCursors(next: Record<string, OutboxCursor>): Promise<void> {
    await this.replace(this.cursorsPath(), next);
    this.cursors = next;
  }

  private async replace(file: string, value: unknown): Promise<void> {
    await mkdir(this.directory, { recursive: true });
    const temp = `${file}.${process.pid}.tmp`;
    const handle = await open(temp, "w");
    try {
      await handle.writeFile(JSON.stringify(value, null, 2) + "\n", "utf8");
      await handle.sync();
    } finally {
      await handle.close();
    }
    await rename(temp, file);
    await syncDirectory(this.directory);
  }

  receiptPath(leadAgentId: string): string {
    if (!/^[A-Za-z0-9._-]+$/.test(leadAgentId)) throw new Error(`unsafe lead agent id ${JSON.stringify(leadAgentId)}`);
    return path.join(this.directory, `${leadAgentId}.jsonl`);
  }

  cursorsPath(): string {
    return path.join(this.directory, "cursors.json");
  }

  submissionsPath(): string {
    return path.join(this.directory, "submissions.json");
  }
}
