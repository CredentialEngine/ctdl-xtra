// Light markdown colouring for the prompt preview (screen 09): headings, `code` and `golden-datasets …` commands.
// Pure, so it is tested without a DOM; the text itself is never interpreted as HTML.

export interface Seg { cls: "h1" | "h2" | "h3" | "code" | "cmd" | null; text: string }

const TICKS = /`([^`\n]+)`/g;

export function highlightLine(line: string): Seg[] {
  if (line.startsWith("# ")) return [{ cls: "h1", text: line }];
  if (line.startsWith("## ")) return [{ cls: "h2", text: line }];
  if (line.startsWith("### ")) return [{ cls: "h3", text: line }];
  const out: Seg[] = [];
  let last = 0;
  for (const m of line.matchAll(TICKS)) {
    const at = m.index ?? 0;
    if (at > last) out.push({ cls: null, text: line.slice(last, at) });
    out.push({ cls: m[1].startsWith("golden-datasets ") ? "cmd" : "code", text: m[0] });
    last = at + m[0].length;
  }
  if (last < line.length || out.length === 0) out.push({ cls: null, text: line.slice(last) });
  return out;
}

export function highlight(text: string): Seg[][] {
  return text.replace(/\n$/, "").split("\n").map(highlightLine);
}

/** The file name of "Download .md". */
export function downloadName(catalogShort: string, scope: string): string {
  return `golden-datasets-prompt-${catalogShort}-${scope}.md`.replace(/[^A-Za-z0-9._-]+/g, "-");
}

/** What a prompt line is, for the preview: `boiler` is the same in every prompt (setup, context, limits, how to
 * work); `var` comes from the rule and its annotations (each "## Rule" section, "## The N rules", the questions);
 * `def` is the rule's definition itself (the first ```json block of a rule section), what Claude changes. */
export type LineKind = "boiler" | "var" | "def";
const VARIABLE = /^## (Rule `|The \d+ rules|Questions for the institution|Comments on the ruleset)/;

/** Consecutive lines of one kind, as text: the rendered preview draws each run in its own band. */
export function runs(text: string): { kind: LineKind; text: string }[] {
  const lines = text.replace(/\n$/, "").split("\n");
  const kinds = lineKinds(text);
  const out: { kind: LineKind; text: string }[] = [];
  lines.forEach((l, i) => {
    const last = out[out.length - 1];
    if (last && last.kind === kinds[i]) last.text += "\n" + l;
    else out.push({ kind: kinds[i], text: l });
  });
  return out;
}

export function lineKinds(text: string): LineKind[] {
  const state: KindState = { section: "boiler", inRule: false, defDone: false, inDef: false, inFence: false };
  return text.replace(/\n$/, "").split("\n").map((line) => kindOf(line, state));
}

interface KindState { section: LineKind; inRule: boolean; defDone: boolean; inDef: boolean; inFence: boolean }

function kindOf(line: string, state: KindState): LineKind {
  if (!state.inFence && line.startsWith("## ")) enterSection(line, state);
  const fence = /^\s*```/.test(line);
  if (fence && state.inFence) return closeFence(state);
  if (fence) openFence(line, state);
  return currentKind(state);
}

function enterSection(heading: string, state: KindState): void {
  state.section = VARIABLE.test(heading) ? "var" : "boiler";
  state.inRule = heading.startsWith("## Rule `");
  state.defDone = false;
}

function openFence(line: string, state: KindState): void {
  state.inFence = true;
  state.inDef = state.inRule && !state.defDone && /^\s*```json/.test(line);
}

function closeFence(state: KindState): LineKind {
  const kind = currentKind(state);
  if (state.inDef) state.defDone = true;
  state.inFence = state.inDef = false;
  return kind;
}

function currentKind(state: KindState): LineKind {
  return state.inDef ? "def" : state.section;
}
