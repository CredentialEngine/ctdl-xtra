import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
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

const TOKEN = /(<\/?)([a-zA-Z][\w:-]*)|(\s)([a-zA-Z_:][\w:.-]*)(=)/g;

/** Colour tag names and attribute names in one piece of markup. */
export function colorize(text: string, key: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let i = 0;
  for (const m of text.matchAll(TOKEN)) {
    const at = m.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    if (m[2]) {
      out.push(m[1], <span key={`${key}t${i++}`} className="tag">{m[2]}</span>);
    } else {
      out.push(m[3], <span key={`${key}a${i++}`} className="attr">{m[4]}</span>, m[5]);
    }
    last = at + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function SourceView({ catalog, stem, target }: { catalog: string; stem: string; target: Highlight | null }) {
  const url = sourceUrl(catalog, stem, target);
  const [data, setData] = useState<{ url: string; r: SourceResponse | null; error?: string } | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    const hit = boxRef.current?.querySelector(".hit, .hitline");
    if (hit && typeof (hit as HTMLElement).scrollIntoView === "function") {
      // scroll only the source box, not the page around it
      const box = boxRef.current!;
      const top = (hit as HTMLElement).offsetTop - box.clientHeight / 3;
      box.scrollTop = Math.max(0, top);
    }
  }, [data]);

  if (!data || data.url !== url) return <div className="gpp-src" ref={boxRef}><span className="faint">Loading…</span></div>;
  if (!data.r) return <div className="gpp-src" ref={boxRef}>Couldn't load the markup ({data.error}).</div>;
  const r = data.r;
  const badge = target?.badge;
  const kind = target?.kind ?? "value";
  const marksByLine = new Map<number, { start: number; end: number }[]>();
  r.marks.forEach((m) => marksByLine.set(m.line, [...(marksByLine.get(m.line) ?? []), m]));
  const firstMark = r.marks.length ? r.marks[0] : null;
  let badgeShown = false;

  return (
    <div className="gpp-src" ref={boxRef}>
      <div className="gpp-src-path">{r.found ? r.css_path : `${r.css_path ? "Not found: " + r.css_path + " · " : ""}showing ${r.context_path}`}</div>
      {r.lines.map((line, li) => {
        const inEl = r.element != null && li >= r.element[0] && li <= r.element[1];
        const marks = marksByLine.get(li) ?? [];
        const parts: ReactNode[] = [];
        let pos = 0;
        marks.forEach((m, mi) => {
          if (m.start > pos) parts.push(...colorize(line.slice(pos, m.start), `${li}p${mi}`));
          if (!badgeShown && badge != null && firstMark && firstMark.line === li) {
            parts.push(<span key={`${li}b`} className={`gpp-src-badge ${kind}`}>{badge}</span>);
            badgeShown = true;
          }
          parts.push(<span key={`${li}m${mi}`} className={`hit ${kind}`}>{colorize(line.slice(m.start, m.end), `${li}h${mi}`)}</span>);
          pos = m.end;
        });
        if (pos < line.length) parts.push(...colorize(line.slice(pos), `${li}r`));
        const lead = !badgeShown && badge != null && !firstMark && r.element && li === r.element[0];
        if (lead) badgeShown = true;
        return (
          <div key={li} className={`gpp-src-line${inEl ? " hitline" : ""}`}>
            {lead && <span className={`gpp-src-badge ${kind}`}>{badge}</span>}
            {parts.length ? parts : " "}
          </div>
        );
      })}
      {r.truncated && <div className="faint gpp-src-more">… markup outside this window is not shown</div>}
    </div>
  );
}
