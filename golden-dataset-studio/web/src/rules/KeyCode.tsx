// The record key on a row (LearningProgram spec, item 13; mockups w2-rules-id-card, w2-rules-id-generated): the
// record's External Identifier with a faint dotted underline, grey when it was generated (`program-<name>`: the page
// prints no code, issue #368). Hovering it opens a small card: the identifier, where it came from on the page (as
// inline code), and the page rule and its URL pattern. Asked for once, on first hover. (Why the sample picked a row
// is the Sample drawer's: no tags under the rows, approved item 13.)
import { useEffect, useRef, useState, type RefObject } from "react";
import { api } from "../api/client";
import type { KeySource } from "../api/types";
import { parseRoute } from "../shell/router";

const cache = new Map<string, Promise<KeySource | null>>();

export function KeyCode({ id, occ, generated }: { id: string | null; occ: string | null; generated?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const card = useKeyCard(ref, occ);
  if (!id) return <div className="code">—</div>;
  return (
    <div ref={ref} className={`code k${generated ? " gen" : ""}`} onMouseEnter={card.show} onMouseLeave={card.hide}
      data-testid="record-key">
      {id}
      {card.at && <KeyCard id={id} at={card.at} src={card.src} generated={generated} />}
    </div>
  );
}

/** A page rule's URL regex as a short path to read (the full regex is the tooltip): each alternative's literal start,
 * "…" where the pattern takes over (`/graduate/collegeofbusinessandeconomics/…`); a group of plain words stays as it
 * is (`/(undergraduate|graduate)/`). Over two alternatives, or over 60 characters, it says how many more. */
export function shortPattern(re: string): string {
  const parts = alternatives(withoutOuterGroup(re.replace(/^\^/, "").replace(/\$$/, ""))).map(literalStart);
  const shown = parts.slice(0, 2).join(" or ");
  const more = parts.length - 2;
  if (shown.length > 60) return `${parts[0].length > 60 ? `${parts[0].slice(0, 59)}…` : parts[0]}${parts.length > 1 ? `, and ${parts.length - 1} more` : ""}`;
  return more > 0 ? `${shown}, and ${more} more` : shown;
}

/** Shows the card 250 ms after the pointer arrives, asking where the key came from once. */
function useKeyCard(ref: RefObject<HTMLDivElement>, occ: string | null) {
  const [at, setAt] = useState<{ left: number; top: number } | null>(null);
  const [src, setSrc] = useState<KeySource | null | undefined>(undefined);
  const timer = useRef<number>();
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const open = () => {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    setAt({ left: r.left - 4, top: r.bottom + 8 });
    if (occ && src === undefined) source(occ).then(setSrc);
  };
  const show = () => { window.clearTimeout(timer.current); timer.current = window.setTimeout(open, 250); };
  const hide = () => { window.clearTimeout(timer.current); setAt(null); };
  return { at, src, show, hide };
}

interface KeyCardProps { id: string; at: { left: number; top: number }; src: KeySource | null | undefined; generated?: boolean }

function KeyCard({ id, at, src, generated }: KeyCardProps) {
  return (
    <div className="idcard" style={{ left: at.left, top: at.top }} role="tooltip" data-testid="key-card">
      <div className="h">External Identifier{(src?.generated ?? generated) ? ", generated" : ""}</div>
      <div className="idv">{id}</div>
      <dl>
        <dt>From</dt>
        <dd><KeyOrigin id={id} src={src} generated={generated} /></dd>
        {src?.page_rule && <><dt>Page rule</dt>
          <dd>{src.page_rule}{src.url_pattern ? <UrlPattern pattern={src.url_pattern} /> : null}</dd></>}
      </dl>
    </div>
  );
}

function KeyOrigin({ id, src, generated }: { id: string; src: KeySource | null | undefined; generated?: boolean }) {
  if (src === undefined) return <span className="faint">…</span>;
  if (src?.generated ?? generated) {
    return <>the page prints no code, so it is <code>{id.split("-")[0]}-</code> plus the name{src?.text ? <>, <code>{src.text}</code></> : null},
      lower case, spaces as hyphens (issue #368)</>;
  }
  return src?.text ? <>the page, <code>{src.text}</code></> : <>the page</>;
}

function UrlPattern({ pattern }: { pattern: string }) {
  const [path, more] = shortPattern(pattern).split(", and ");
  return <>, URL pattern <code title={pattern}>{path}</code>{more ? `, and ${more}` : ""}</>;
}

function source(occ: string): Promise<KeySource | null> {
  const cat = parseRoute(location.hash).catalog ?? "";
  const k = `${location.hash.split("?")[0]}|${occ}`;
  if (!cache.has(k)) cache.set(k, api.keySource(cat, occ).catch(() => null));
  return cache.get(k)!;
}

function withoutOuterGroup(body: string): string {
  return body.startsWith("(") && closingParen(body, 0) === body.length - 1 ? body.slice(1, -1) : body;
}

/** The regex's top-level alternatives (split at "|" outside groups and classes). */
function alternatives(body: string): string[] {
  const alts: string[] = [];
  for (let d = 0, start = 0, j = 0; j <= body.length; j++) {
    const c = body[j];
    if (c === "\\") { j++; continue; }
    if (c === "(" || c === "[") d++;
    else if (c === ")" || c === "]") d--;
    else if ((c === "|" && d === 0) || j === body.length) { alts.push(body.slice(start, j)); start = j + 1; }
  }
  return alts;
}

/** An alternative's literal start, "…" where the pattern takes over; a group of plain words is kept. */
function literalStart(a: string): string {
  let out = "";
  for (let j = 0; j < a.length; j++) {
    const c = a[j];
    if (c === "\\" && /[/.\-_]/.test(a[j + 1] ?? "")) { out += a[++j]; continue; }
    const k = c === "(" ? closingParen(a, j) : -1;
    if (k > 0 && /^[\w|-]+$/.test(a.slice(j + 1, k))) { out += a.slice(j, k + 1); j = k; continue; }
    if (/[\\[(.*+?{|^$)]/.test(c)) return `${out}…`;
    out += c;
  }
  return out;
}

/** The index of the ")" that closes the "(" at i. */
function closingParen(s: string, i: number): number {
  for (let d = 0, j = i; j < s.length; j++) {
    if (s[j] === "\\") { j++; continue; }
    if (s[j] === "(") d++;
    else if (s[j] === ")" && --d === 0) return j;
  }
  return -1;
}
