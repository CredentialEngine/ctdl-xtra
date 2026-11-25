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

type AddForm = ReturnType<typeof useAddCatalog>;
type ShownCatalogs = ReturnType<typeof useShownCatalogs>;
interface AddRequest {
  picked: CrawledCatalog | null; crawl: string; setBusy: (b: boolean) => void; setError: (e: string) => void;
  onAdded: () => void; onClose: () => void;
}

export function AddCatalogModal({ onClose, onAdded }: { onClose: () => void; onAdded: () => void }) {
  const form = useAddCatalog(onClose, onAdded);
  return (
    <div className="ac-back" onClick={onClose}>
      <div className="ac" role="dialog" aria-modal="true" aria-labelledby="ac-h" onClick={(e) => e.stopPropagation()}>
        <div className="ac-head">
          <h2 id="ac-h">{form.picked ? `Add ${form.picked.name}` : <>Add a catalog <Info /></>}</h2>
          <button className="ac-x" aria-label="Close" onClick={onClose}>×</button>
        </div>
        <div className="ac-body">{!form.picked ? <SearchStep form={form} /> : <ConfirmStep form={form} picked={form.picked} />}</div>
        <AddFoot form={form} onClose={onClose} />
      </div>
    </div>
  );
}

function SearchStep({ form }: { form: AddForm }) {
  return <>
    <input ref={form.input} className="ac-search" placeholder="Search by name or URL" value={form.query}
           onChange={(e) => form.setQuery(e.target.value)} onKeyDown={form.onKey} aria-label="Search crawled catalogs" />
    <div className="ac-res"><CrawlResults form={form} /></div>
  </>;
}

function CrawlResults({ form }: { form: AddForm }) {
  if (form.error) return <p className="ac-empty">{form.error}</p>;
  if (!form.items) return <p className="ac-empty">Loading crawled catalogs…</p>;
  if (!form.list.shown.length) return <p className="ac-empty">No crawled catalog matches “{form.query}”.</p>;
  return (
    <table className="ac-t">
      <thead><tr><th>Catalog</th><th>Last crawled</th><th className="num">Pages</th><th>Crawl</th></tr></thead>
      <tbody>
        {form.list.shown.map((c, i) => <CrawlRow key={c.catalog} c={c} i={i} form={form} />)}
      </tbody>
    </table>
  );
}

function CrawlRow({ c, i, form }: { c: CrawledCatalog; i: number; form: AddForm }) {
  const { list: { sel, setSel }, query, choose } = form;
  return (
    <tr className={`${i === sel ? "sel" : ""} ${pickable(c) ? "" : "dim"}`}
        onMouseEnter={() => pickable(c) && setSel(i)} onClick={() => choose(c)}>
      <td><div className="nm"><Mark text={c.name} query={query} /></div>
        <div className="u"><Mark text={host(c.seed_url)} query={query} /></div></td>
      <td>{day(c.finished_at)}</td>
      <td className="num">{fmt(c.pages)}</td>
      <td><CrawlChip c={c} /></td>
    </tr>
  );
}

function CrawlChip({ c }: { c: CrawledCatalog }) {
  if (c.added) return <span className="ac-chip in">Already added</span>;
  if (c.adding) return <span className="ac-chip in">Adding…</span>;
  if (!c.pages) return <span className="ac-chip in">No pages</span>;
  return <span className={`ac-chip ${STATUS[c.status].cls}`}>{STATUS[c.status].t}</span>;
}

function ConfirmStep({ form, picked }: { form: AddForm; picked: CrawledCatalog }) {
  const { run, error } = form;
  return <>
    <FoundTable form={form} picked={picked} />
    {run && run.status !== "complete" && (
      <p className="ac-warn">This crawl isn't complete, so the golden dataset won't be either.</p>)}
    {error && <p className="ac-warn">{error}</p>}
  </>;
}

function FoundTable({ form, picked }: { form: AddForm; picked: CrawledCatalog }) {
  const { run } = form;
  return (
    <table className="ac-found">
      <tbody>
        <tr><th>Name</th><td>{picked.name}</td></tr>
        <tr><th>Catalog URL</th><td className="mono">{picked.seed_url}</td></tr>
        <tr><th>Crawl</th><td><CrawlSelect form={form} picked={picked} /></td></tr>
        <tr><th>Pages</th><td>{fmt(run?.pages)}</td></tr>
        <tr><th>Status</th><td>{run && <span className={`ac-chip ${STATUS[run.status].cls}`}>{STATUS[run.status].t}</span>}</td></tr>
      </tbody>
    </table>
  );
}

function CrawlSelect({ form, picked }: { form: AddForm; picked: CrawledCatalog }) {
  return (
    <select value={form.crawl} onChange={(e) => form.setCrawl(e.target.value)} aria-label="Crawl">
      {picked.crawls.filter((k) => k.pages > 0).map((k, i) => (
        <option key={k.crawl} value={k.crawl}>{day(k.finished_at)}{i === 0 ? " (latest)" : ""}</option>))}
    </select>
  );
}

function AddFoot({ form, onClose }: { form: AddForm; onClose: () => void }) {
  const { picked, busy, list: { shown, sel } } = form;
  return (
    <div className="ac-foot">
      {picked
        ? <button className="ac-back-link" onClick={form.back}>← Back</button>
        : <span className="ac-keys">↑↓ to move · Enter to choose</span>}
      <button className="btn" onClick={onClose}>Cancel</button>
      {picked
        ? <button className="btn primary" disabled={busy} onClick={form.add}>{busy ? "Adding…" : "Add catalog"}</button>
        : <button className="btn primary" disabled={!shown[sel] || !pickable(shown[sel])}
                  onClick={() => form.choose(shown[sel])}>Next</button>}
    </div>
  );
}

function useAddCatalog(onClose: () => void, onAdded: () => void) {
  const [error, setError] = useState<string | null>(null);
  const items = useCrawledCatalogs(setError);
  const [query, setQuery] = useState("");
  const pick = usePick(setError);
  const input = useFocusWhileSearching(pick.picked);
  useCloseOnEscape(onClose);
  const list = useShownCatalogs(items, query);
  const [busy, setBusy] = useState(false);
  const add = () => addPicked({ picked: pick.picked, crawl: pick.crawl, setBusy, setError, onAdded, onClose });
  const onKey = (e: React.KeyboardEvent) => moveOrChoose(e, list, pick.choose);
  return { items, error, query, setQuery, input, list, busy, add, onKey, ...pick };
}

function useCrawledCatalogs(setError: (e: string) => void): CrawledCatalog[] | null {
  const [items, setItems] = useState<CrawledCatalog[] | null>(null);
  useEffect(() => { api.crawls().then((r) => setItems(r.items), (e) => setError(String(e.message ?? e))); }, []);
  return items;
}

function usePick(setError: (e: string | null) => void) {
  const [picked, setPicked] = useState<CrawledCatalog | null>(null);
  const [crawl, setCrawl] = useState("");
  const choose = (c: CrawledCatalog | undefined) => {
    if (c && pickable(c)) { setPicked(c); setCrawl(c.crawl); }
  };
  const back = () => { setPicked(null); setError(null); };
  return { picked, crawl, setCrawl, choose, back, run: picked?.crawls.find((k) => k.crawl === crawl) };
}

function useFocusWhileSearching(picked: CrawledCatalog | null) {
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { if (!picked) input.current?.focus(); }, [picked]);
  return input;
}

function useCloseOnEscape(onClose: () => void) {
  useEffect(() => {
    const on = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onClose]);
}

function useShownCatalogs(items: CrawledCatalog[] | null, query: string) {
  const [sel, setSel] = useState(0);
  const shown = useMemo(() => (items ?? []).filter((c) => matches(c, query)), [items, query]);
  useEffect(() => { setSel(Math.max(0, shown.findIndex(pickable))); }, [shown]);
  return { shown, sel, setSel };
}

function moveOrChoose(e: React.KeyboardEvent, { shown, sel, setSel }: ShownCatalogs, choose: (c: CrawledCatalog | undefined) => void): void {
  if (e.key === "ArrowDown") { e.preventDefault(); stepTo(shown, sel, 1, setSel); }
  else if (e.key === "ArrowUp") { e.preventDefault(); stepTo(shown, sel, -1, setSel); }
  else if (e.key === "Enter") { e.preventDefault(); choose(shown[sel]); }
}

function stepTo(shown: CrawledCatalog[], sel: number, d: number, setSel: (i: number) => void): void {
  for (let i = sel + d; i >= 0 && i < shown.length; i += d) if (pickable(shown[i])) return setSel(i);
}

async function addPicked({ picked, crawl, setBusy, setError, onAdded, onClose }: AddRequest): Promise<void> {
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
}
