// Port of parse_handoff/classify_handoff from setup/check-handoff. Keep both in step: the fixtures
// under tests/fixtures/handoffs/ are run through both parsers and the JSON must be identical.

export const CELLS = ["Outcome", "Candidate", "Scope", "Verification", "Unknown / risk", "Ownership"] as const;
export type CellName = (typeof CELLS)[number];

// Round is the first token after "Round:"; a trailing note such as "(not changed by me)" is tolerated.
const HEADER = /^Task ID:\s*(.+?)\s*\|\s*Round:\s*(\S+)/;
// Cell name at line start, optionally wrapped in Markdown emphasis (**Outcome**, *Outcome*, `Outcome`),
// followed by two spaces, a colon, or the end of the line.
const CELL_START = new RegExp(
  `^(?:[*_\`]{1,2})?(${CELLS.map(escapeRegExp).join("|")})(?:[*_\`]{1,2})?(?:\\s{2,}|\\s*:\\s*|\\s*$|(?<=[*_\`])\\s+)`,
);
// Python's \b is Unicode-aware; emulate it so a hex run glued to a letter is not a token.
const SHA = /(?<![\p{L}\p{N}_])[0-9a-f]{7,40}(?![\p{L}\p{N}_])/gu;
const SNAPSHOT = /snapshot|checksum|uncommitted|no candidate SHA/i;

export interface HandoffHeader {
  task: string;
  round: string;
}

export interface ParsedHandoff {
  header: HandoffHeader | null;
  cells: Partial<Record<CellName, string>>;
}

export interface HandoffClassification extends ParsedHandoff {
  missing: CellName[];
  shas: string[];
  snapshot: boolean;
  reasons: string[];
  valid: boolean;
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\\/]/g, "\\$&");
}

/** Python str.splitlines(): every line boundary, no trailing empty element. */
export function splitLines(text: string): string[] {
  const lines = text.split(/\r\n|[\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]/);
  if (lines.length > 0 && lines[lines.length - 1] === "") lines.pop();
  return lines;
}

export function parseHandoff(text: string): ParsedHandoff {
  let header: HandoffHeader | null = null;
  const cells: Partial<Record<CellName, string>> = {};
  let current: CellName | null = null;
  for (const line of splitLines(text)) {
    if (header === null) {
      const match = HEADER.exec(line.trim());
      if (match) header = { task: match[1], round: match[2] };
      continue;
    }
    const match = CELL_START.exec(line);
    if (match) {
      current = match[1] as CellName;
      cells[current] = line.slice(match[0].length).trim();
    } else if (current && line.trim()) {
      cells[current] += "\n" + line.trim();
    }
  }
  return { header, cells };
}

/**
 * Shape check without a brief or repository: the plugin's HANDBACK_VALID test. `shas` are the hex
 * tokens of the Candidate cell, unresolved, so `valid` means "looks like a complete handback", not
 * READY_FOR_REVIEW; the Lead still runs setup/check-handoff.
 */
export function classifyHandoff(text: string): HandoffClassification {
  const { header, cells } = parseHandoff(text);
  const reasons: string[] = [];
  if (header === null) reasons.push("handoff header 'Task ID: … | Round: …' not found");
  const missing = CELLS.filter((cell) => !cells[cell]);
  if (missing.length) reasons.push("missing cells: " + missing.join(", "));
  const candidate = cells.Candidate ?? "";
  const shas = [...candidate.matchAll(SHA)].map((match) => match[0]);
  const snapshot = SNAPSHOT.test(candidate);
  if (header !== null && !missing.length && shas.length < 2 && !snapshot) {
    reasons.push(`Candidate cell needs base SHA and candidate SHA (found ${shas.length})`);
  }
  return { header, cells, missing, shas, snapshot, reasons, valid: reasons.length === 0 };
}
