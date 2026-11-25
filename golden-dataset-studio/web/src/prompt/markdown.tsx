// A small Markdown renderer for the prompt preview. It covers what prompt.py writes — headings, paragraphs,
// nested bullet and numbered lists, tables, fenced code, inline code, bold, italic and links — and builds React elements
// only: the text (which quotes catalog pages) is never interpreted as HTML.
import { Fragment, type ReactNode } from "react";
import { Ico } from "../shell/icons";

export type Block =
  | { t: "h"; level: number; text: string }
  | { t: "p"; text: string }
  | { t: "code"; text: string; lang: string }
  | { t: "list"; ordered: boolean; start?: number; items: { text: string; children: Block[] }[] }
  | { t: "table"; head: string[]; rows: string[][] };

const LIST_ITEM = /^(\s*)([-*]|\d+\.)\s+(.*)$/;
const TABLE_ROW = /^\s*\|.*\|\s*$/;
const TABLE_RULE = /^\s*\|(\s*:?-+:?\s*\|)+\s*$/;
const FENCE = /^\s*```(\S*)/;
const FENCE_END = /^\s*```\s*$/;
const HEADING = /^(#{1,6})\s+(.*)$/;

export function Markdown({ text }: { text: string }) {
  return <div className="md">{parse(text).map(renderBlock)}</div>;
}

function renderBlock(b: Block, key: number): ReactNode {
  switch (b.t) {
    case "h":
      return renderHeading(b, key);
    case "p":
      return <p key={key}>{inline(b.text)}</p>;
    case "code":
      return <pre key={key}><code>{b.text}</code></pre>;
    case "list":
      return renderList(b, key);
    case "table":
      return renderTable(b, key);
  }
}

function renderHeading(b: Extract<Block, { t: "h" }>, key: number): ReactNode {
  const H = `h${Math.min(6, b.level)}` as "h1";
  return <H key={key}>{inline(b.text)}</H>;
}

function renderList(b: Extract<Block, { t: "list" }>, key: number): ReactNode {
  const L = b.ordered ? "ol" : "ul";
  return <L key={key} start={b.ordered && b.start !== 1 ? b.start : undefined}>{b.items.map((it, i) => <li key={i}>{inline(it.text)}{it.children.map(renderBlock)}</li>)}</L>;
}

function renderTable(b: Extract<Block, { t: "table" }>, key: number): ReactNode {
  // a header of empty cells (a two-column "name | value" table) isn't shown
  return (
    <div key={key} className="md-table"><table>
      {b.head.some((h) => h) && <thead><tr>{b.head.map((h, i) => <th key={i}>{inline(h)}</th>)}</tr></thead>}
      <tbody>{b.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{inline(c)}</td>)}</tr>)}</tbody>
    </table></div>
  );
}

const INLINE = /(`[^`\n]+`)|(\*\*[^*]+\*\*)|(\*[^*\s][^*]*\*)|(\[[^\]]+\]\([^)\s]+\))/g;

/** Inline Markdown → React nodes (code, bold, italic, links). */
export function inline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  let key = 0;
  for (const m of text.matchAll(INLINE)) {
    const at = m.index ?? 0;
    if (at > last) nodes.push(text.slice(last, at));
    nodes.push(inlineNode(m, key++));
    last = at + m[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function inlineNode(m: RegExpMatchArray, key: number): ReactNode {
  const s = m[0];
  if (m[1]) return <code key={key} className={s.startsWith("`golden-datasets ") ? "cmd" : undefined}>{s.slice(1, -1)}</code>;
  if (m[2]) return <strong key={key}>{inline(s.slice(2, -2))}</strong>;
  if (m[3]) return <em key={key}>{inline(s.slice(1, -1))}</em>;
  return linkNode(s, key);
}

function linkNode(s: string, key: number): ReactNode {
  const [, label, url] = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(s)!;
  if (!/^https?:\/\//.test(url)) return <Fragment key={key}>{s}</Fragment>;
  // every link opens a new tab, and says so with the external-link icon
  return <a key={key} href={url} target="_blank" rel="noopener noreferrer" className="md-ext"
    title="Opens in a new tab">{inline(label)}<Ico name="ext" /></a>;
}

interface Cursor { lines: string[]; i: number }

/** Parse Markdown into blocks. Indentation of 2+ spaces under a list item nests a list (or continues its text). */
export function parse(md: string): Block[] {
  const cursor: Cursor = { lines: md.replace(/\r\n?/g, "\n").split("\n"), i: 0 };
  const blocks: Block[] = [];
  while (!atEnd(cursor)) {
    if (current(cursor).trim() === "") cursor.i++;
    else blocks.push(readBlock(cursor));
  }
  return blocks;
}

function readBlock(cursor: Cursor): Block {
  const line = current(cursor);
  if (FENCE.test(line)) return readFence(cursor);
  if (HEADING.test(line)) return readHeading(cursor);
  if (startsTable(cursor)) return readTable(cursor);
  const item = LIST_ITEM.exec(line);
  if (item) return readList(cursor, item[1].length);
  return readParagraph(cursor);
}

function readFence(cursor: Cursor): Block {
  const line = current(cursor);
  const lang = FENCE.exec(line)![1];
  const pad = indentOf(line);
  const body: string[] = [];
  cursor.i++;
  while (!atEnd(cursor) && !FENCE_END.test(current(cursor))) {
    body.push(current(cursor).slice(Math.min(pad, indentOf(current(cursor)))));
    cursor.i++;
  }
  cursor.i++;
  return { t: "code", text: body.join("\n"), lang };
}

function readHeading(cursor: Cursor): Block {
  const [, hashes, text] = HEADING.exec(current(cursor))!;
  cursor.i++;
  return { t: "h", level: hashes.length, text };
}

function startsTable({ lines, i }: Cursor): boolean {
  return TABLE_ROW.test(lines[i]) && i + 1 < lines.length && TABLE_RULE.test(lines[i + 1]);
}

function readTable(cursor: Cursor): Block {
  const head = cells(current(cursor));
  cursor.i += 2;
  const rows: string[][] = [];
  while (!atEnd(cursor) && TABLE_ROW.test(current(cursor))) { rows.push(cells(current(cursor))); cursor.i++; }
  return { t: "table", head, rows };
}

function readList(cursor: Cursor, indent: number): Block {
  const marker = LIST_ITEM.exec(current(cursor))![2];
  const ordered = /\d/.test(marker);
  const start = ordered ? parseInt(marker, 10) : undefined;  // "2." after a paragraph keeps counting
  const items: { text: string; children: Block[] }[] = [];
  while (!atEnd(cursor)) {
    const m = LIST_ITEM.exec(current(cursor));
    if (!m || m[1].length !== indent) break;
    items.push(readListItem(cursor, indent, m[3]));
    skipBlankBetweenItems(cursor, indent);
  }
  return { t: "list", ordered, start, items };
}

/** Continuation lines and nested lists (deeper indentation) belong to the item. */
function readListItem(cursor: Cursor, indent: number, text: string): { text: string; children: Block[] } {
  const item = { text, children: [] as Block[] };
  cursor.i++;
  while (!atEnd(cursor) && current(cursor).trim() !== "") {
    const nested = LIST_ITEM.exec(current(cursor));
    if (nested && nested[1].length > indent) item.children.push(readList(cursor, nested[1].length));
    else if (!nested && indentOf(current(cursor)) > indent) { item.text += " " + current(cursor).trim(); cursor.i++; }
    else break;
  }
  return item;
}

/** A blank line between items of the same list keeps the list going. */
function skipBlankBetweenItems(cursor: Cursor, indent: number): void {
  const { lines, i } = cursor;
  if (i >= lines.length || lines[i].trim() !== "" || i + 1 >= lines.length) return;
  const next = LIST_ITEM.exec(lines[i + 1]);
  if (next && next[1].length === indent) cursor.i++;
}

function readParagraph(cursor: Cursor): Block {
  const para: string[] = [current(cursor).trim()];
  cursor.i++;
  while (!atEnd(cursor) && continuesParagraph(current(cursor))) { para.push(current(cursor).trim()); cursor.i++; }
  return { t: "p", text: para.join(" ") };
}

function continuesParagraph(line: string): boolean {
  return line.trim() !== "" && !LIST_ITEM.test(line) && !/^(#{1,6})\s/.test(line) && !/^\s*```/.test(line);
}

/** The cells of `| a | b \| c |`: split on unescaped pipes, `\|` read as `|`. */
export function cells(line: string): string[] {
  const inner = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return inner.split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, "|"));
}

function atEnd({ lines, i }: Cursor): boolean {
  return i >= lines.length;
}

function current({ lines, i }: Cursor): string {
  return lines[i];
}

function indentOf(line: string): number {
  return line.length - line.trimStart().length;
}
