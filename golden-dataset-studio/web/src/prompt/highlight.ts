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
const VARIABLE = /^## (Rule `|The \d+ rules|Questions for the institution)/;

export function lineKinds(text: string): LineKind[] {
  const lines = text.replace(/\n$/, "").split("\n");
  const out: LineKind[] = [];
  let section: LineKind = "boiler", inRule = false, defDone = false, inDef = false, inFence = false;
  for (const line of lines) {
    if (!inFence && line.startsWith("## ")) {
      section = VARIABLE.test(line) ? "var" : "boiler";
      inRule = line.startsWith("## Rule `");
      defDone = false;
    }
    const fence = /^\s*```/.test(line);
    if (fence && !inFence) {
      inFence = true;
      inDef = inRule && !defDone && /^\s*```json/.test(line);
      out.push(inDef ? "def" : section);
      continue;
    }
    if (fence && inFence) {
      out.push(inDef ? "def" : section);
      if (inDef) defDone = true;
      inFence = inDef = false;
      continue;
    }
    out.push(inDef ? "def" : section);
  }
  return out;
}

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
