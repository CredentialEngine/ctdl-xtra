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
