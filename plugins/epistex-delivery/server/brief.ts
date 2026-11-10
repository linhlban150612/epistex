// Port of check_text from setup/check-brief, for the brief a Lead sends as a Peer's first prompt.
// Keep both in step: brief.test.ts runs the same texts through both and the codes must be identical.
import { CELLS, EMPH, PATH, PREFIX, SHA, SHA256, splitLines } from "./handoff.ts";

const W = "\\p{L}\\p{N}_";
const B = `(?:(?<=[${W}])(?![${W}])|(?<![${W}])(?=[${W}]))`;
const NOTE = "(?:[ \\t]*\\([^()\\n]*\\))?";
const LABELS = {
  "Task ID": "(?:Project[ \\t]*/[ \\t]*)?Task ID",
  "Owned scope": "Owned scope",
  Authority: "Authority",
} as const;
// Label at line start after optional markup, an optional note in parentheses, then the value; or
// label with a colon inside a line, after a sentence or segment mark.
const field = (label: string) =>
  new RegExp(
    `(?:^${PREFIX}(?:${label})${EMPH}?${NOTE}${EMPH}?[ \\t]*[:|=]?|[.;,/|—–(-][ \\t]+${EMPH}?(?:${label})${EMPH}?[ \\t]*:)${EMPH}?[ \\t]*(.*)$`,
    "imu",
  );
const ROUND_NUMBER = new RegExp(`${B}round[*_\`]*${NOTE}[ \\t]*[:=]?[ \\t]*[*_\`]*(\\d+)${B}`, "iu");
const ROUND_LABEL = new RegExp(`${B}round[*_\`]*${NOTE}[ \\t]*:[ \\t]*[*_\`]*(\\S+)`, "iu");
const BASELINE = new RegExp(`${B}base(?:line)?${B}`, "iu");
const HANDOFF = new RegExp(`^${PREFIX}Handoff${B}.*(?:\\n(?![ \\t]*$).*)*`, "gimu");
const PEER_PROMPT = /§[ \t]*Handoff|(?:Peer|role) prompt|PEER\.md|Peer Handoff|six-cell handoff/iu;
const CELL_NAMES = CELLS.map((cell) => new RegExp(`(?<![${W}])${cell.replace(" / ", "[ \\t]*/[ \\t]*")}(?![${W}])`, "iu"));
// Paseo wraps a message from another agent: <paseo-system … kind="agent-message" source-agent-id="…">, body XML-escaped.
const ENVELOPE = /<paseo-system((?:\s+[a-z-]+="[^"<>]*")+)>\n([\s\S]*?)\n<\/paseo-system>/g;
const ENTITIES: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" };

/** Value of a template field: the rest of its line, else its continuation on the next line. */
function fieldValue(text: string, label: string): string | null {
  const match = field(label).exec(text);
  if (!match) return null;
  const value = match[1].replace(/^[ \t|]+|[ \t|]+$/g, "");
  if (value) return value;
  const following = text.slice(match.index + match[0].length).split("\n")[1];
  // A continuation is indented or a list item; a line at the margin is the next field.
  return following !== undefined && /^(?:[ \t]+\S|[-*+][ \t])/u.test(following) ? following.trim() : "";
}

/** A base/baseline line with a commit SHA, or a sha256 checksum with a path; the identity may be on the next line. */
function hasBaseline(text: string): boolean {
  const lines = splitLines(text);
  return lines.some((line, index) => {
    if (!BASELINE.test(line)) return false;
    return [line, lines.slice(index, index + 2).join(" ")].some((candidate) =>
      candidate.search(SHA256) >= 0 ? PATH.test(candidate.replace(SHA256, "")) : candidate.search(SHA) >= 0,
    );
  });
}

/** Shape codes of a text brief, as `setup/check-brief - --json` reports them; empty when the brief passes. */
export function checkBrief(brief: string): string[] {
  const text = brief.replace(/\r\n?/g, "\n");
  const codes: string[] = [];
  if (!fieldValue(text, LABELS["Task ID"])?.split(/[ \t]*[|;,][ \t]*/)[0]) codes.push("TASK_ID_MISSING");
  if (!ROUND_NUMBER.test(text)) codes.push(ROUND_LABEL.test(text) ? "ROUND_NOT_NUMBER" : "ROUND_MISSING");
  if (!fieldValue(text, LABELS["Owned scope"])) codes.push("OWNED_SCOPE_MISSING");
  if (!fieldValue(text, LABELS.Authority)) codes.push("AUTHORITY_MISSING");
  if (!hasBaseline(text)) codes.push("BASELINE_MISSING");
  for (const [paragraph] of text.matchAll(HANDOFF)) {
    if (!CELL_NAMES.every((name) => name.test(paragraph)) && !PEER_PROMPT.test(paragraph)) {
      codes.push("CELLS_REDEFINED");
      break;
    }
  }
  return codes;
}

/**
 * The brief inside a Peer's first user message: the body of the first Paseo agent-message envelope
 * from this Lead. Role instructions an ACP launcher put before it are left out. Null when the
 * message has no such envelope, so text that is not a Lead brief is never checked.
 */
export function briefOf(userMessage: string, leadAgentId: string): string | null {
  for (const [, attributes, body] of userMessage.matchAll(ENVELOPE)) {
    if (/\skind="agent-message"/.test(attributes) && attributes.includes(` source-agent-id="${leadAgentId}"`)) {
      return body.replace(/&(amp|lt|gt|quot|apos);/g, (_, entity: string) => ENTITIES[entity]);
    }
  }
  return null;
}
