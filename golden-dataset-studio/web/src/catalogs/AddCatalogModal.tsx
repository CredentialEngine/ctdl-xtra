// Add a catalog (spec §7.1): search the catalogs xtra-cli has already crawled, pick one, confirm, add it.
// Every value shown comes from the crawl's crawl.json; nothing is typed in. The Studio never starts a crawl:
// the ⓘ beside the title says so.
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { CrawledCatalog, CrawlStatus } from "../api/types";
import { currentReviewer } from "../shell/reviewer";
import { fmt, fmtDate } from "../shell/ui";
import "./addcatalog.css";

export const STATUS: Record<CrawlStatus, { t: string; cls: string }> = {
  complete: { t: "Complete", cls: "ok" },
  limit_reached: { t: "Hit page limit", cls: "warn" },
  incomplete: { t: "Not finished", cls: "bad" },
};
const host = (url: string | null) => (url ?? "").replace(/^https?:\/\//, "").replace(/\/$/, "");
const day = (iso: string | null) => (iso ? fmtDate(iso) : "—");

export function matches(c: CrawledCatalog, query: string): boolean {
  const hay = `${c.name} ${c.catalog} ${c.seed_url ?? ""}`.toLowerCase();
  return query.toLowerCase().split(/\s+/).filter(Boolean).every((w) => hay.includes(w));
}
const pickable = (c: CrawledCatalog) => !c.added && !c.adding && c.pages > 0;

function Mark({ text, query }: { text: string; query: string }) {
  const w = query.trim().split(/\s+/)[0]?.toLowerCase();
  const i = w ? text.toLowerCase().indexOf(w) : -1;
  if (i < 0) return <>{text}</>;
  return <>{text.slice(0, i)}<mark>{text.slice(i, i + w.length)}</mark>{text.slice(i + w.length)}</>;
}

function Info() {
  const [open, setOpen] = useState(false);
  return (
    <span className="ac-info-wrap" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button type="button" className="ac-info" aria-label="About this list" aria-expanded={open}
              onClick={() => setOpen(true)} onBlur={() => setOpen(false)}>i</button>
      {open && <span className="ac-tip" role="tooltip">
        Only catalogs the xTRA engine has already crawled can be found here. For a new catalog, ask engineering to
        crawl it.</span>}
    </span>
  );
}

export function AddCatalogModal({ onClose, onAdded }: { onClose: () => void; onAdded: () => void }) {
  const [items, setItems] = useState<CrawledCatalog[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [sel, setSel] = useState(0);
  const [picked, setPicked] = useState<CrawledCatalog | null>(null);
  const [crawl, setCrawl] = useState("");
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => { api.crawls().then((r) => setItems(r.items), (e) => setError(String(e.message ?? e))); }, []);
  useEffect(() => { if (!picked) input.current?.focus(); }, [picked]);
  useEffect(() => {
    const on = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onClose]);

  const shown = useMemo(() => (items ?? []).filter((c) => matches(c, query)), [items, query]);
  useEffect(() => { setSel(Math.max(0, shown.findIndex(pickable))); }, [shown]);

  const choose = (c: CrawledCatalog | undefined) => {
    if (c && pickable(c)) { setPicked(c); setCrawl(c.crawl); }
  };
  const onKey = (e: React.KeyboardEvent) => {
    const step = (d: number) => {
      for (let i = sel + d; i >= 0 && i < shown.length; i += d) if (pickable(shown[i])) return setSel(i);
    };
    if (e.key === "ArrowDown") { e.preventDefault(); step(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); step(-1); }
    else if (e.key === "Enter") { e.preventDefault(); choose(shown[sel]); }
  };
  const add = async () => {
    if (!picked) return;
    setBusy(true);
    try {
      await api.addCatalog(picked.catalog, { crawl, by: currentReviewer() || undefined });
      onAdded();
      onClose();
    } catch (e) {
      setError(String((e as Error).message ?? e));
      setBusy(false);
    }
  };
  const run = picked?.crawls.find((k) => k.crawl === crawl);

  return (
    <div className="ac-back" onClick={onClose}>
      <div className="ac" role="dialog" aria-modal="true" aria-labelledby="ac-h" onClick={(e) => e.stopPropagation()}>
        <div className="ac-head">
          <h2 id="ac-h">{picked ? `Add ${picked.name}` : <>Add a catalog <Info /></>}</h2>
          <button className="ac-x" aria-label="Close" onClick={onClose}>×</button>
        </div>
        {!picked ? (
          <div className="ac-body">
            <input ref={input} className="ac-search" placeholder="Search by name or URL" value={query}
                   onChange={(e) => setQuery(e.target.value)} onKeyDown={onKey} aria-label="Search crawled catalogs" />
            <div className="ac-res">
              {error ? <p className="ac-empty">{error}</p>
                : !items ? <p className="ac-empty">Loading crawled catalogs…</p>
                : !shown.length ? <p className="ac-empty">No crawled catalog matches “{query}”.</p>
                : (
                  <table className="ac-t">
                    <thead><tr><th>Catalog</th><th>Last crawled</th><th className="num">Pages</th><th>Crawl</th></tr></thead>
                    <tbody>
                      {shown.map((c, i) => (
                        <tr key={c.catalog} className={`${i === sel ? "sel" : ""} ${pickable(c) ? "" : "dim"}`}
                            onMouseEnter={() => pickable(c) && setSel(i)} onClick={() => choose(c)}>
                          <td><div className="nm"><Mark text={c.name} query={query} /></div>
                            <div className="u"><Mark text={host(c.seed_url)} query={query} /></div></td>
                          <td>{day(c.finished_at)}</td>
                          <td className="num">{fmt(c.pages)}</td>
                          <td>{c.added ? <span className="ac-chip in">Already added</span>
                            : c.adding ? <span className="ac-chip in">Adding…</span>
                            : !c.pages ? <span className="ac-chip in">No pages</span>
                            : <span className={`ac-chip ${STATUS[c.status].cls}`}>{STATUS[c.status].t}</span>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
            </div>
          </div>
        ) : (
          <div className="ac-body">
            <table className="ac-found">
              <tbody>
                <tr><th>Name</th><td>{picked.name}</td></tr>
                <tr><th>Catalog URL</th><td className="mono">{picked.seed_url}</td></tr>
                <tr><th>Crawl</th><td>
                  <select value={crawl} onChange={(e) => setCrawl(e.target.value)} aria-label="Crawl">
                    {picked.crawls.filter((k) => k.pages > 0).map((k, i) => (
                      <option key={k.crawl} value={k.crawl}>{day(k.finished_at)}{i === 0 ? " (latest)" : ""}</option>))}
                  </select></td></tr>
                <tr><th>Pages</th><td>{fmt(run?.pages)}</td></tr>
                <tr><th>Status</th><td>{run && <span className={`ac-chip ${STATUS[run.status].cls}`}>{STATUS[run.status].t}</span>}</td></tr>
              </tbody>
            </table>
            {run && run.status !== "complete" && (
              <p className="ac-warn">This crawl isn't complete, so the golden dataset won't be either.</p>)}
            {error && <p className="ac-warn">{error}</p>}
          </div>
        )}
        <div className="ac-foot">
          {picked
            ? <button className="ac-back-link" onClick={() => { setPicked(null); setError(null); }}>← Back</button>
            : <span className="ac-keys">↑↓ to move · Enter to choose</span>}
          <button className="btn" onClick={onClose}>Cancel</button>
          {picked
            ? <button className="btn primary" disabled={busy} onClick={add}>{busy ? "Adding…" : "Add catalog"}</button>
            : <button className="btn primary" disabled={!shown[sel] || !pickable(shown[sel])}
                      onClick={() => choose(shown[sel])}>Next</button>}
        </div>
      </div>
    </div>
  );
}
