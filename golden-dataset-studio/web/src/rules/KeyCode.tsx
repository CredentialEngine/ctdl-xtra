// The record key on a row (LearningProgram spec, item 13; mockups w2-rules-id-card, w2-rules-id-generated): the
// record's External Identifier with a faint dotted underline, grey when it was generated (`program-<name>`: the page
// prints no code, issue #368). Hovering it opens a small card: the identifier, where it came from on the page (as
// inline code), and the page rule and its URL pattern. Asked for once, on first hover. (Why the sample picked a row
// is the Sample drawer's: no tags under the rows, approved item 13.)
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { KeySource } from "../api/types";
import { parseRoute } from "../shell/router";

const cache = new Map<string, Promise<KeySource | null>>();

function source(occ: string): Promise<KeySource | null> {
  const cat = parseRoute(location.hash).catalog ?? "";
  const k = `${location.hash.split("?")[0]}|${occ}`;
  if (!cache.has(k)) cache.set(k, api.keySource(cat, occ).catch(() => null));
  return cache.get(k)!;
}

export function KeyCode({ id, occ, generated }: { id: string | null; occ: string | null; generated?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const [at, setAt] = useState<{ left: number; top: number } | null>(null);
  const [src, setSrc] = useState<KeySource | null | undefined>(undefined);
  const timer = useRef<number>();
  useEffect(() => () => window.clearTimeout(timer.current), []);
  if (!id) return <div className="code">—</div>;
  const show = () => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      const r = ref.current?.getBoundingClientRect();
      if (!r) return;
      setAt({ left: r.left - 4, top: r.bottom + 8 });
      if (occ && src === undefined) source(occ).then(setSrc);
    }, 250);
  };
  const hide = () => { window.clearTimeout(timer.current); setAt(null); };
  return (
    <div ref={ref} className={`code k${generated ? " gen" : ""}`} onMouseEnter={show} onMouseLeave={hide}
      data-testid="record-key">
      {id}
      {at && (
        <div className="idcard" style={{ left: at.left, top: at.top }} role="tooltip" data-testid="key-card">
          <div className="h">External Identifier{(src?.generated ?? generated) ? ", generated" : ""}</div>
          <div className="idv">{id}</div>
          <dl>
            <dt>From</dt>
            <dd>{src === undefined ? <span className="faint">…</span>
              : (src?.generated ?? generated)
                ? <>the page prints no code, so it is <code>{id.split("-")[0]}-</code> plus the name{src?.text ? <>, <code>{src.text}</code></> : null},
                    lower case, spaces as hyphens (issue #368)</>
                : src?.text ? <>the page, <code>{src.text}</code></> : <>the page</>}</dd>
            {src?.page_rule && <><dt>Page rule</dt>
              <dd>{src.page_rule}{src.url_pattern ? <>, URL pattern <code>{src.url_pattern}</code></> : null}</dd></>}
          </dl>
        </div>
      )}
    </div>
  );
}
