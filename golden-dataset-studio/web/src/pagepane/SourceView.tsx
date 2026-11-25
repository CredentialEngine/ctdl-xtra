import { useEffect, useRef, useState } from "react";
import type { ReactNode, RefObject } from "react";
import type { Highlight } from "./paint";

export interface SourceResponse {
  stem: string;
  css_path: string | null;
  found: boolean;
  context_path: string;
  first_line: number;
  lines: string[];
  element: [number, number] | null;
  marks: { line: number; start: number; end: number }[];
  text: string | null;
  truncated: boolean;
}

type Mark = SourceResponse["marks"][number];

interface Loaded { url: string; r: SourceResponse | null; error?: string }

export function SourceView({ catalog, stem, target }: { catalog: string; stem: string; target: Highlight | null }) {
  const url = sourceUrl(catalog, stem, target);
  const data = useSource(url);
  const boxRef = useScrollToHit(data);
  if (!data || data.url !== url) return <div className="gpp-src" ref={boxRef}><span className="faint">Loading…</span></div>;
  if (!data.r) return <div className="gpp-src" ref={boxRef}>Couldn't load the markup ({data.error}).</div>;
  return <SourceListing source={data.r} target={target} boxRef={boxRef} />;
}

export function sourceUrl(catalog: string, stem: string, target: Highlight | null): string {
  const q = new URLSearchParams();
  if (target) {
    q.set("css_path", target.cssPath);
    if (target.charStart != null && target.charEnd != null) {
      q.set("char_start", String(target.charStart));
      q.set("char_end", String(target.charEnd));
    }
    if (target.text) q.set("text", target.text.slice(0, 300));
  }
  const qs = q.toString();
  return `/api/catalogs/${encodeURIComponent(catalog)}/pages/${encodeURIComponent(stem)}/source${qs ? `?${qs}` : ""}`;
}

function useSource(url: string): Loaded | null {
  const [data, setData] = useState<Loaded | null>(null);
  useEffect(() => {
    let live = true;
    fetch(url)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then((r: SourceResponse) => live && setData({ url, r }))
      .catch((e: Error) => live && setData({ url, r: null, error: e.message }));
    return () => {
      live = false;
    };
  }, [url]);
  return data;
}

/** Scrolls only the source box, not the page around it, so the highlighted markup is in view. */
function useScrollToHit(data: Loaded | null): RefObject<HTMLDivElement> {
  const boxRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const hit = boxRef.current?.querySelector(".hit, .hitline");
    if (hit && typeof (hit as HTMLElement).scrollIntoView === "function") {
      const box = boxRef.current!;
      const top = (hit as HTMLElement).offsetTop - box.clientHeight / 3;
      box.scrollTop = Math.max(0, top);
    }
  }, [data]);
  return boxRef;
}

function SourceListing({ source, target, boxRef }: { source: SourceResponse; target: Highlight | null; boxRef: RefObject<HTMLDivElement> }) {
  return (
    <div className="gpp-src" ref={boxRef}>
      <div className="gpp-src-path">{pathLabel(source)}</div>
      {sourceLines(source, target)}
      {source.truncated && <div className="faint gpp-src-more">… markup outside this window is not shown</div>}
    </div>
  );
}

function pathLabel(r: SourceResponse): string | null {
  return r.found ? r.css_path : `${r.css_path ? "Not found: " + r.css_path + " · " : ""}showing ${r.context_path}`;
}

/** The target's badge, shown once: on its first mark, else at the start of its element. */
interface BadgeSlot { badge: Highlight["badge"]; kind: string; firstMark: Mark | null; shown: boolean }

function sourceLines(r: SourceResponse, target: Highlight | null): ReactNode[] {
  const slot: BadgeSlot = { badge: target?.badge, kind: target?.kind ?? "value", firstMark: r.marks[0] ?? null, shown: false };
  const marksByLine = groupByLine(r.marks);
  return r.lines.map((line, li) => sourceLine(r, line, li, marksByLine.get(li) ?? [], slot));
}

function groupByLine(marks: Mark[]): Map<number, Mark[]> {
  const marksByLine = new Map<number, Mark[]>();
  marks.forEach((m) => marksByLine.set(m.line, [...(marksByLine.get(m.line) ?? []), m]));
  return marksByLine;
}

function sourceLine(r: SourceResponse, line: string, li: number, marks: Mark[], slot: BadgeSlot): ReactNode {
  const inEl = r.element != null && li >= r.element[0] && li <= r.element[1];
  const parts = markedParts(line, li, marks, slot);
  const lead = !slot.shown && slot.badge != null && !slot.firstMark && r.element && li === r.element[0];
  if (lead) slot.shown = true;
  return (
    <div key={li} className={`gpp-src-line${inEl ? " hitline" : ""}`}>
      {lead && <span className={`gpp-src-badge ${slot.kind}`}>{slot.badge}</span>}
      {parts.length ? parts : " "}
    </div>
  );
}

function markedParts(line: string, li: number, marks: Mark[], slot: BadgeSlot): ReactNode[] {
  const parts: ReactNode[] = [];
  let pos = 0;
  marks.forEach((m, mi) => {
    if (m.start > pos) parts.push(...colorize(line.slice(pos, m.start), `${li}p${mi}`));
    parts.push(...claimBadge(li, slot));
    parts.push(<span key={`${li}m${mi}`} className={`hit ${slot.kind}`}>{colorize(line.slice(m.start, m.end), `${li}h${mi}`)}</span>);
    pos = m.end;
  });
  if (pos < line.length) parts.push(...colorize(line.slice(pos), `${li}r`));
  return parts;
}

function claimBadge(li: number, slot: BadgeSlot): ReactNode[] {
  if (slot.shown || slot.badge == null || !slot.firstMark || slot.firstMark.line !== li) return [];
  slot.shown = true;
  return [<span key={`${li}b`} className={`gpp-src-badge ${slot.kind}`}>{slot.badge}</span>];
}

const TOKEN = /(<\/?)([a-zA-Z][\w:-]*)|(\s)([a-zA-Z_:][\w:.-]*)(=)/g;

/** Colour tag names and attribute names in one piece of markup. */
export function colorize(text: string, key: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let i = 0;
  for (const m of text.matchAll(TOKEN)) {
    const at = m.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    out.push(...tokenParts(m, `${key}${m[2] ? "t" : "a"}${i++}`));
    last = at + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function tokenParts(m: RegExpMatchArray, key: string): ReactNode[] {
  if (m[2]) return [m[1], <span key={key} className="tag">{m[2]}</span>];
  return [m[3], <span key={key} className="attr">{m[4]}</span>, m[5]];
}
