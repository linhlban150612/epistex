// Port of parse_handoff/classify_handoff from setup/check-handoff. Keep both in step: the fixtures
// under tests/fixtures/handoffs/ are run through both parsers and the JSON must be identical.

export const CELLS = ["Outcome", "Candidate", "Scope", "Verification", "Unknown / risk", "Ownership"] as const;
export type CellName = (typeof CELLS)[number];

// Markup a Peer may put before a cell name or the header: quote, heading and table marks, a bullet,
// a number ("1.", "1)", "(1)") and Markdown emphasis, in any order.
export const PREFIX = "(?:[ \\t|>#]|[-+*][ \\t]+|[0-9]+[.)][ \\t]*|\\([0-9]+\\)[ \\t]*|\\*\\*|__|[*_`])*";
export const EMPH = "(?:\\*\\*|__|[*_`])";
// Codex writes Unicode spaces (em space, no-break space) between a cell name and its text.
const WS = " \\t\\u00a0\\u2000-\\u200b\\u202f\\u205f\\u3000";
/** The pattern with every `[ \t…]` class widened to the Unicode spaces of WS. */
const ws = (pattern: string) => pattern.replaceAll("[ \\t", "[" + WS);
// Round is the first token after "Round:"; a trailing note such as "(not changed by me)" is tolerated.
const HEADER = new RegExp(
  ws(`^${PREFIX}Task ID${EMPH}?[ \\t]*:${EMPH}?[ \\t]*(.+?)[ \\t]*\\|[ \\t]*${EMPH}?Round${EMPH}?[ \\t]*:${EMPH}?[ \\t]*([^\\s|]+)`),
);
// Cell name at line start after optional markup. The name is exact (any case, free spacing around
// "/"), then: closing emphasis, one parenthesised note, and a colon, a table bar, two spaces, one
// space after closing emphasis, or the end of the line. One plain space does not end the name, so a
// renamed cell ("Candidate identity:", "Scope / coverage", "Risks") and a sentence do not match.
const CELL_START = new RegExp(
  ws(`^${PREFIX}(${CELLS.map((cell) => cell.replace(" / ", "[ \\t]*/[ \\t]*")).join("|")})${EMPH}?(?:[ \\t]*\\([^()\\n]*\\))?${EMPH}?` +
    `(?:[ \\t]*:${EMPH}?[ \\t]*|[ \\t]*\\|[ \\t]*|[ \\t]{2,}|(?<=[*_\`])[ \\t]+|[ \\t]*$)`),
  "iu",
);
const CANONICAL = new Map<string, CellName>(CELLS.map((cell) => [cell.replaceAll(" ", "").toLowerCase(), cell]));
// Python's \w and \b are Unicode-aware; emulate them so a hex run glued to a letter is not a token.
const W = "\\p{L}\\p{N}_";
const B = `(?:(?<=[${W}])(?![${W}])|(?<![${W}])(?=[${W}]))`;
export const SHA = new RegExp(`${B}[0-9a-f]{7,40}${B}`, "gu");
export const SHA256 = new RegExp(`${B}[0-9a-f]{64}${B}`, "gu");
export const PATH = new RegExp(`[${W}.~\\-]*/[${W}.\\-]+|${B}[${W}\\-]+\\.[A-Za-z][A-Za-z0-9]{0,7}${B}`, "u");
const NO_CANDIDATE = new RegExp(
  `${B}(?:none|n/a|no (?:candidate|commits?|writes?|changes?|diff)|not committed|nothing (?:written|committed|changed))${B}` +
    "|không (?:có )?(?:candidate|commit|ghi|thay đổi)",
  "iu",
);
// Sub-label of the Verification cell: how far the Peer's own evidence goes.
const PROOF_CLASSES = ["observed", "e2e", "tests-only", "none"] as const;
const PROOF = new RegExp(ws(`${B}Proof class${EMPH}?[ \\t]*:${EMPH}?[ \\t]*[*_\`]*(${PROOF_CLASSES.join("|")})${B}`), "iu");
const STOPPED = new RegExp(`${B}(?:BLOCKED|REOPEN_REQUEST|DEPENDENCY_REQUEST)${B}`, "u");

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
  /** The Verification cell's `Proof class:` value in lower case, or null. */
  proof: string | null;
  reasons: string[];
  codes: string[];
  valid: boolean;
}

/** Python str.splitlines(): every line boundary, no trailing empty element. */
export function splitLines(text: string): string[] {
  const lines = text.split(/\r\n|[\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]/);
  if (lines.length > 0 && lines[lines.length - 1] === "") lines.pop();
  return lines;
}

/** Cell text without the table bar that closes a Markdown table row. */
function clean(text: string): string {
  return text.trim().replace(/[ \t]*\|[ \t]*$/, "");
}

export function parseHandoff(text: string): ParsedHandoff {
  let header: HandoffHeader | null = null;
  const cells: Partial<Record<CellName, string>> = {};
  let current: CellName | null = null;
  for (const line of splitLines(text)) {
    if (header === null) {
      const match = HEADER.exec(line);
      if (match) header = { task: match[1].replace(/^[*_ \t]+|[*_ \t]+$/g, ""), round: match[2].replace(/[*_`]+$/, "") };
      continue;
    }
    const match = CELL_START.exec(line);
    const name = match ? CANONICAL.get(match[1].replace(new RegExp(ws("[ \\t]"), "g"), "").toLowerCase()) : undefined;
    if (match && name && !(name in cells)) {
      // A later line that repeats a cell name is text of the current cell.
      current = name;
      cells[current] = clean(line.slice(match[0].length));
    } else if (current && line.trim() && !/^[ \t|:-]+$/.test(line)) {
      cells[current] += "\n" + clean(line);
    }
  }
  return { header, cells };
}

/**
 * Shape check without a brief or repository: the plugin's HANDBACK_VALID test. `shas` are the hex
 * tokens of the Candidate cell, unresolved, so `valid` means "looks like a complete handback", not
 * READY_FOR_REVIEW; the Lead still runs setup/check-handoff. `codes` are the machine-readable form
 * of `reasons`: HEADER_MISSING, CELL_MISSING:<name>, CANDIDATE_IDENTITY, PROOF_CLASS.
 */
export function classifyHandoff(text: string): HandoffClassification {
  const { header, cells } = parseHandoff(text);
  const reasons: string[] = [];
  const codes: string[] = [];
  if (header === null) {
    reasons.push("handoff header 'Task ID: … | Round: …' not found");
    codes.push("HEADER_MISSING");
  }
  const missing = CELLS.filter((cell) => !cells[cell]);
  if (missing.length) {
    reasons.push("missing cells: " + missing.join(", "));
    codes.push(...missing.map((cell) => "CELL_MISSING:" + cell));
  }
  const candidate = cells.Candidate ?? "";
  const shas = [...candidate.matchAll(SHA)].map((match) => match[0]);
  // Candidate identity, one of: two commit SHAs; a sha256 checksum with a path; a turn that stopped
  // (BLOCKED, REOPEN_REQUEST, DEPENDENCY_REQUEST), where any non-empty cell is enough; or a base SHA
  // with a clear statement that there is no candidate.
  const snapshot = candidate.search(SHA256) >= 0 && PATH.test(candidate.replace(SHA256, ""));
  const stopped = STOPPED.test(cells.Outcome ?? "");
  const baseOnly = shas.length >= 1 && NO_CANDIDATE.test(candidate);
  if (header !== null && !missing.length && shas.length < 2 && !snapshot && !stopped && !baseOnly) {
    reasons.push(`Candidate cell needs base SHA and candidate SHA (found ${shas.length})`);
    codes.push("CANDIDATE_IDENTITY");
  }
  // A handoff with a candidate states its proof class; a stopped turn or one without a candidate has none.
  const proof = PROOF.exec(cells.Verification ?? "")?.[1].toLowerCase() ?? null;
  if (header !== null && !missing.length && (shas.length >= 2 || snapshot) && !stopped && !baseOnly && proof === null) {
    reasons.push(`Verification cell needs 'Proof class: ${PROOF_CLASSES.join(" | ")}'`);
    codes.push("PROOF_CLASS");
  }
  return { header, cells, missing, shas, snapshot, proof, reasons, codes, valid: reasons.length === 0 };
}
