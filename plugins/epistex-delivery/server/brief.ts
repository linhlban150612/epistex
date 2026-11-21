import { CELLS, EMPH, PATH, PREFIX, SHA, SHA256, splitLines } from "./handoff.ts";

const W = "\\p{L}\\p{N}_";
const B = `(?:(?<=[${W}])(?![${W}])|(?<![${W}])(?=[${W}]))`;
const NOTE = "(?:[ \\t]*\\([^()\\n]*\\))?";
const LABELS = {
  "Task ID": "(?:Project[ \\t]*/[ \\t]*)?Task[ _]ID",
  "Owned scope": "Owned[ _]scope",
  Authority: "Authority",
} as const;
const field = (label: string) =>
  new RegExp(
    `(?:^${PREFIX}(?:${label})${EMPH}?${NOTE}${EMPH}?[ \\t]*[:|=]?|[.;,/|—–(-][ \\t]+${EMPH}?(?:${label})${EMPH}?[ \\t]*:)${EMPH}?[ \\t]*(.*)$`,
    "imu",
  );
const CONTINUATION = /^(?:[ \t]+\S|[-*+][ \t]|[0-9]+[.)][ \t])/u;
const ROUND_NUMBER = new RegExp(`${B}round[*_\`]*${NOTE}[ \\t]*[:=]?[ \\t]*[*_\`]*(\\d+)${B}`, "iu");
const ROUND_LABEL = new RegExp(`${B}round[*_\`]*${NOTE}[ \\t]*:[ \\t]*[*_\`]*(\\S+)`, "iu");
const BASELINE = new RegExp(`${B}base(?:line)?${B}`, "iu");
const HANDOFF = new RegExp(`^${PREFIX}Handoff${B}.*(?:\\n(?![ \\t]*$).*)*`, "gimu");
const PEER_PROMPT = /§[ \t]*Handoff|(?:Peer|role) prompt|PEER\.md|Peer Handoff|six-cell handoff/iu;
const CELL_NAMES = CELLS.map((cell) => new RegExp(`(?<![${W}])${cell.replace(" / ", "[ \\t]*/[ \\t]*")}(?![${W}])`, "iu"));
const ENVELOPE = /<paseo-system((?:\s+[a-z-]+="[^"<>]*")+)>\n([\s\S]*?)\n<\/paseo-system>/g;
const ENTITIES: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" };

function fieldValue(text: string, label: string): string | null {
  const match = field(label).exec(text);
  if (!match) return null;
  const value = match[1].replace(/^[ \t|]+|[ \t|]+$/g, "");
  if (value) return value;
  const following = text.slice(match.index + match[0].length).split("\n")[1];
  return following !== undefined && CONTINUATION.test(following) ? following.trim() : "";
}

function hasBaseline(text: string): boolean {
  const lines = splitLines(text);
  return lines.some((line, index) => {
    if (!BASELINE.test(line)) return false;
    return [line, lines.slice(index, index + 2).join(" ")].some((candidate) =>
      candidate.search(SHA256) >= 0 ? PATH.test(candidate.replace(SHA256, "")) : candidate.search(SHA) >= 0,
    );
  });
}

export function briefIdentity(brief: string): { taskId: string | null; round: string | null } {
  const text = brief.replace(/\r\n?/g, "\n");
  const value = fieldValue(text, LABELS["Task ID"])?.split(/[ \t]*[|;,][ \t]*/)[0];
  const task = /Project[ \t]*\/[ \t]*Task[ _]ID/i.test(text) ? value?.split(/[ \t]+\/[ \t]+/).pop() : value;
  return { taskId: task?.replace(/^[*_`]+|[*_`.]+$/g, "") || null, round: ROUND_NUMBER.exec(text)?.[1] ?? null };
}

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

export function briefOf(userMessage: string, leadAgentId: string): string | null {
  for (const [, attributes, body] of userMessage.matchAll(ENVELOPE)) {
    if (/\skind="agent-message"/.test(attributes) && attributes.includes(` source-agent-id="${leadAgentId}"`)) {
      return body.replace(/&(amp|lt|gt|quot|apos);/g, (_, entity: string) => ENTITIES[entity]);
    }
  }
  return null;
}

function splitPaths(text: string, globs = false): string[] {
  const quotes = globs ? /^[`'"()[\]]+|[`'"()[\]]+$/g : /^[`'"*()[\]]+|[`'"*()[\]]+$/g;
  const clean = (token: string) => {
    for (;;) {
      const stripped = token.replace(quotes, "").replace(/[.:;,]+$/, "");
      if (stripped === token) return token;
      token = stripped;
    }
  };
  const paths = text.split(/[\s,;]+/).map(clean).filter((token) => token && /[/.]/.test(token) && !/[()]/.test(token));
  return [...new Set(paths)];
}

export function ownedScope(brief: string): string[] {
  const text = brief.replace(/\r\n?/g, "\n");
  const match = field(LABELS["Owned scope"]).exec(text);
  if (!match) return [];
  const lines = [match[1]];
  for (const line of text.slice(match.index + match[0].length).split("\n").slice(1)) {
    if (!CONTINUATION.test(line)) break;
    lines.push(line);
  }
  return splitPaths(lines.join("\n"), true);
}

function inScope(file: string, pattern: string): boolean {
  const norm = (value: string) => value.replace(/^\.\//, "");
  const glob = norm(pattern).replace(/\/+$/, "");
  let source = "";
  for (let at = 0; at < glob.length; at += 1) {
    if (glob.startsWith("**/", at)) {
      source += "(?:.*/)?";
      at += 2;
    } else if (glob.startsWith("**", at)) {
      source += ".*";
      at += 1;
    } else source += glob[at] === "*" ? "[^/]*" : glob[at] === "?" ? "[^/]" : glob[at].replace(/[.+^${}()|[\]\\]/g, "\\$&");
  }
  return new RegExp(`^${source}(?:/.*)?$`, "u").test(norm(file));
}

export function outsideScope(scopeCell: string, owned: string[]): string[] {
  const changed = /Changed:([\s\S]*?)(?:Read:|$)/.exec(scopeCell);
  if (!changed || !owned.length) return [];
  return splitPaths(changed[1]).filter((file) => !owned.some((pattern) => inScope(file, pattern))).sort();
}
