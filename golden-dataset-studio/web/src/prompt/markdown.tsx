// A small Markdown renderer for the prompt preview. It covers what prompt.py writes — headings, paragraphs,
// nested bullet and numbered lists, tables, fenced code, inline code, bold, italic and links — and builds React elements
// only: the text (which quotes catalog pages) is never interpreted as HTML.
import { Fragment, type ReactNode } from "react";

export type Block =
  | { t: "h"; level: number; text: string }
  | { t: "p"; text: string }
  | { t: "code"; text: string; lang: string }
  | { t: "list"; ordered: boolean; items: { text: string; children: Block[] }[] }
  | { t: "table"; head: string[]; rows: string[][] };

const LIST_ITEM = /^(\s*)([-*]|\d+\.)\s+(.*)$/;
const TABLE_ROW = /^\s*\|.*\|\s*$/;
const TABLE_RULE = /^\s*\|(\s*:?-+:?\s*\|)+\s*$/;

/** The cells of `| a | b \| c |`: split on unescaped pipes, `\|` read as `|`. */
export function cells(line: string): string[] {
  const inner = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return inner.split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, "|"));
}

/** Parse Markdown into blocks. Indentation of 2+ spaces under a list item nests a list (or continues its text). */
export function parse(md: string): Block[] {
  const lines = md.replace(/\r\n?/g, "\n").split("\n");
  let i = 0;

  function parseList(indent: number): Block {
    const first = LIST_ITEM.exec(lines[i])!;
    const ordered = /\d/.test(first[2]);
    const items: { text: string; children: Block[] }[] = [];
    while (i < lines.length) {
      const m = LIST_ITEM.exec(lines[i]);
      if (!m || m[1].length !== indent) break;
      const item = { text: m[3], children: [] as Block[] };
      i++;
      // continuation lines and nested lists (deeper indentation)
      while (i < lines.length && lines[i].trim() !== "") {
        const n = LIST_ITEM.exec(lines[i]);
        const ind = lines[i].length - lines[i].trimStart().length;
        if (n && n[1].length > indent) item.children.push(parseList(n[1].length));
        else if (!n && ind > indent) { item.text += " " + lines[i].trim(); i++; }
        else break;
      }
      items.push(item);
      // a blank line between items of the same list keeps the list going
      if (i < lines.length && lines[i].trim() === "" && i + 1 < lines.length) {
        const n = LIST_ITEM.exec(lines[i + 1]);
        if (n && n[1].length === indent) i++;
      }
    }
    return { t: "list", ordered, items };
  }

  const out: Block[] = [];
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === "") { i++; continue; }
    const fence = /^\s*```(\S*)/.exec(line);
    if (fence) {
      const body: string[] = [];
      const pad = line.length - line.trimStart().length;
      i++;
      while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) { body.push(lines[i].slice(Math.min(pad, lines[i].length - lines[i].trimStart().length))); i++; }
      i++;
      out.push({ t: "code", text: body.join("\n"), lang: fence[1] });
      continue;
    }
    const h = /^(#{1,6})\s+(.*)$/.exec(line);
    if (h) { out.push({ t: "h", level: h[1].length, text: h[2] }); i++; continue; }
    if (TABLE_ROW.test(line) && i + 1 < lines.length && TABLE_RULE.test(lines[i + 1])) {
      const head = cells(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && TABLE_ROW.test(lines[i])) { rows.push(cells(lines[i])); i++; }
      out.push({ t: "table", head, rows });
      continue;
    }
    const li = LIST_ITEM.exec(line);
    if (li) { out.push(parseList(li[1].length)); continue; }
    const para: string[] = [line.trim()];
    i++;
    while (i < lines.length && lines[i].trim() !== "" && !LIST_ITEM.test(lines[i]) && !/^(#{1,6})\s/.test(lines[i])
           && !/^\s*```/.test(lines[i])) { para.push(lines[i].trim()); i++; }
    out.push({ t: "p", text: para.join(" ") });
  }
  return out;
}

const INLINE = /(`[^`\n]+`)|(\*\*[^*]+\*\*)|(\*[^*\s][^*]*\*)|(\[[^\]]+\]\([^)\s]+\))/g;

/** Inline Markdown → React nodes (code, bold, italic, links). */
export function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let k = 0;
  for (const m of text.matchAll(INLINE)) {
    const at = m.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    const s = m[0];
    if (m[1]) out.push(<code key={k++} className={s.startsWith("`golden-datasets ") ? "cmd" : undefined}>{s.slice(1, -1)}</code>);
    else if (m[2]) out.push(<strong key={k++}>{inline(s.slice(2, -2))}</strong>);
    else if (m[3]) out.push(<em key={k++}>{inline(s.slice(1, -1))}</em>);
    else {
      const [, label, url] = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(s)!;
      const safe = /^https?:\/\//.test(url);
      out.push(safe ? <a key={k++} href={url} target="_blank" rel="noopener noreferrer">{inline(label)}</a> : <Fragment key={k++}>{s}</Fragment>);
    }
    last = at + s.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function renderBlock(b: Block, key: number): ReactNode {
  switch (b.t) {
    case "h": {
      const H = `h${Math.min(6, b.level)}` as "h1";
      return <H key={key}>{inline(b.text)}</H>;
    }
    case "p":
      return <p key={key}>{inline(b.text)}</p>;
    case "code":
      return <pre key={key}><code>{b.text}</code></pre>;
    case "list": {
      const L = b.ordered ? "ol" : "ul";
      return <L key={key}>{b.items.map((it, i) => <li key={i}>{inline(it.text)}{it.children.map(renderBlock)}</li>)}</L>;
    }
    case "table":
      // a header of empty cells (a two-column "name | value" table) isn't shown
      return (
        <div key={key} className="md-table"><table>
          {b.head.some((h) => h) && <thead><tr>{b.head.map((h, i) => <th key={i}>{inline(h)}</th>)}</tr></thead>}
          <tbody>{b.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{inline(c)}</td>)}</tr>)}</tbody>
        </table></div>
      );
  }
}

export function Markdown({ text }: { text: string }) {
  return <div className="md">{parse(text).map(renderBlock)}</div>;
}
