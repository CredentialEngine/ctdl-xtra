// The Sample drawer (facets.py): how the list is sampled. Modes:
// - Review order (Rules tab only): discussed first, then the likeliest problems mixed with a spread sample;
// - Autostratify: cross the strata that split the rows most evenly (or the ones picked here) and go through 3 records
//   of each combination, rarest combination first;
// - Shuffle: a seeded random order, with Reshuffle;
// - Manual select: every stratum as a histogram (one bar per bucket: how many records fall in it); click bars to filter.
// "Reviewed in other fields first" (Rules tab): records not reviewed for this rule yet, but marked or commented on in
// another rule, come first, so a record's fields get finished together.
// Who annotated a record isn't a stratum here: it's the Rules tab's "Annotated by" filter above the drawer (one way to
// do it; "Annotated in" says which ruleset version a record was annotated in).
// Filters stay on in every mode. When a filter or Autostratify is on, each record shows its strata tags (StrataTags).
import { useEffect, useRef, useState } from "react";
import { filterParams, type FacetFilter, type SampleInfo, type SampleOrder, type StrataTag, type StratumHist } from "../api/types";
import { fmt } from "./ui";
import "./sample.css";

export type SampleMode = SampleOrder | "manual";
export interface SamplePrefs { mode: SampleMode; filter: FacetFilter; cross: string[] | null; seed: number; prior: boolean }
export const samplePrefs = (mode: SampleMode): SamplePrefs => ({ mode, filter: {}, cross: null, seed: 0, prior: false });
const NOT_CROSSED = ["rule", "review", "signals", "annotated_in"];
const MODE_NAME: Record<SampleMode, string> = { review: "Review order", auto: "Autostratify", shuffle: "Shuffle", manual: "Manual select" };

/** The query parameters of a list request: `manual` keeps the list's default order (`fallback`). */
export function sampleQuery(p: SamplePrefs, fallback: SampleOrder) {
  return { order: p.mode === "manual" ? fallback : p.mode, f: filterParams(p.filter), seed: p.seed, prior: p.prior || undefined,
           cross: p.mode === "auto" && p.cross !== null ? (p.cross.length ? p.cross : [""]) : undefined };
}
export const sampleKey = (p: SamplePrefs, fallback: SampleOrder) => JSON.stringify(sampleQuery(p, fallback));

export function toggle(f: FacetFilter, dim: string, bucket: string): FacetFilter {
  const cur = new Set(f[dim] ?? []);
  if (cur.has(bucket)) cur.delete(bucket); else cur.add(bucket);
  const next = { ...f };
  if (cur.size) next[dim] = [...cur]; else delete next[dim];
  return next;
}

export function SampleDrawer({ sample, prefs, onPrefs, modes, storageKey, collapseOn }: {
  sample: SampleInfo | null; prefs: SamplePrefs; onPrefs: (p: SamplePrefs) => void; modes: SampleMode[]; storageKey: string;
  /** When this changes (the reader moves to another row), the drawer closes: it stays out of the way while reviewing. */
  collapseOn?: unknown;
}) {
  const [open, setOpen] = useState<boolean>(() => { try { return localStorage.getItem(storageKey) === "1"; } catch { return false; } });
  const firstCollapse = useRef(true);
  useEffect(() => {
    if (firstCollapse.current) { firstCollapse.current = false; return; }
    setOpen(false);
  }, [collapseOn]);
  const setOpenSaved = (v: boolean) => { setOpen(v); try { localStorage.setItem(storageKey, v ? "1" : "0"); } catch { /* private */ } };
  const set = (p: Partial<SamplePrefs>) => onPrefs({ ...prefs, ...p });
  const hs = sample?.histograms ?? [];
  const label = (id: string) => hs.find((h) => h.id === id)?.label ?? id;
  const chips = Object.entries(prefs.filter).flatMap(([d, bs]) => bs.map((b) => ({ d, b })));
  return (
    <div className={"sample" + (open ? " open" : "")} data-testid="sample">
      <div className="sm-head">
        <button className="sm-tog" aria-expanded={open} onClick={() => setOpenSaved(!open)}><span className="tw">{open ? "▾" : "▸"}</span>Sample</button>
        <div className="seg sm-modes" role="group" aria-label="Sample">
          {modes.map((m) => <button key={m} className={prefs.mode === m ? "on" : ""}
            onClick={() => { set({ mode: m }); if (m === "manual" || m === "auto") setOpenSaved(true); }}>{MODE_NAME[m]}</button>)}
        </div>
        {prefs.mode === "shuffle" && <button className="btn sm-btn" onClick={() => set({ seed: prefs.seed + 1 })}>Reshuffle</button>}
        {sample?.elsewhere !== undefined && (
          <label className={"sm-prior" + (sample.elsewhere ? "" : " faint")} title="Records nobody has reviewed for this rule yet, but someone marked or commented on in another rule">
            <input type="checkbox" checked={prefs.prior} onChange={(e) => set({ prior: e.target.checked })} />
            Reviewed in other fields first <span className="faint">({fmt(sample.elsewhere)})</span></label>
        )}
        {sample && <span className="faint sm-n">{fmt(sample.listed)}{sample.listed !== sample.total && <> of {fmt(sample.total)}</>}</span>}
      </div>
      {chips.length > 0 && (
        <div className="sm-chips">
          {chips.map(({ d, b }) => (
            <span key={d + b} className="sm-chip">{label(d)}: {b}
              <button aria-label={`Remove ${label(d)}: ${b}`} onClick={() => set({ filter: toggle(prefs.filter, d, b) })}>×</button></span>
          ))}
          <button className="sm-clear" onClick={() => set({ filter: {} })}>Clear filters</button>
        </div>
      )}
      {open && sample && prefs.mode === "auto" && <AutoPanel sample={sample} prefs={prefs} onCross={(cross) => set({ cross })} />}
      {open && sample && prefs.mode === "manual" && <ManualPanel hs={hs} filter={prefs.filter} onFilter={(filter) => set({ filter })} />}
      {open && prefs.mode === "shuffle" && <p className="sm-d faint">A random order of the records{chips.length ? " that pass the filters" : ""}. Reshuffle for another.</p>}
      {open && prefs.mode === "review" && <p className="sm-d faint">Discussed rows first, then rows with signals, with every 5th row from a spread sample.</p>}
    </div>
  );
}

function AutoPanel({ sample, prefs, onCross }: { sample: SampleInfo; prefs: SamplePrefs; onCross: (c: string[]) => void }) {
  const can = sample.histograms.filter((h) => !h.uniform && !NOT_CROSSED.includes(h.id));
  const on = new Set(sample.cross);
  const flip = (id: string) => onCross(on.has(id) ? sample.cross.filter((c) => c !== id) : [...sample.cross, id]);
  const n = sample.cell_count ?? sample.cells.length;
  return (
    <div className="sm-panel" data-testid="auto-panel">
      <p className="sm-d">Goes through <b>3 records of each combination</b> of the strata crossed, the rarest combinations
        first (the ones least like the bulk of the records), then the rest the same way.
        {" "}{sample.cross.length ? <>{sample.cross.map((c) => sample.histograms.find((h) => h.id === c)?.label ?? c).join(" × ")}: <b>{fmt(n)}</b> combinations.</> : "Nothing crossed: pick strata below."}</p>
      <div className="sm-cross" aria-label="Strata to cross">
        {can.map((h) => <button key={h.id} className={"sm-dim" + (on.has(h.id) ? " on" : "")} aria-pressed={on.has(h.id)}
          title={h.help} onClick={() => flip(h.id)}>{h.label} <span className="faint">{h.buckets.length}</span></button>)}
      </div>
      {prefs.cross === null && <p className="sm-d faint">Picked automatically: the strata that split the records most evenly (2–8 buckets each).</p>}
    </div>
  );
}

function ManualPanel({ hs, filter, onFilter }: { hs: StratumHist[]; filter: FacetFilter; onFilter: (f: FacetFilter) => void }) {
  const shown = hs.filter((h) => !h.uniform);
  const uniform = hs.filter((h) => h.uniform);
  const [active, setActive] = useState<string | null>(null);
  const cur = shown.find((h) => h.id === active) ?? shown[0];
  return (
    <div className="sm-panel" data-testid="manual-panel">
      <div className="sm-dims" role="tablist" aria-label="Strata">
        {shown.map((h) => <button key={h.id} role="tab" aria-selected={cur?.id === h.id} title={h.help}
          className={"sm-dim" + (cur?.id === h.id ? " on" : "") + (filter[h.id] ? " filtered" : "")}
          onClick={() => setActive(h.id)}>{h.label}</button>)}
      </div>
      {cur && <Bars h={cur} filter={filter} onFilter={onFilter} />}
      {uniform.length > 0 && <div className="sm-uni faint">Same for every record: {uniform.map((h) => `${h.label} (${h.buckets[0]?.id ?? "—"})`).join(" · ")}</div>}
    </div>
  );
}

function Bars({ h, filter, onFilter }: { h: StratumHist; filter: FacetFilter; onFilter: (f: FacetFilter) => void }) {
  const max = Math.max(1, ...h.buckets.map((b) => b.count));
  return (
    <div className="sm-bars" data-testid="sample-bars">
      {h.buckets.map((b) => (
        <button key={b.id} className={"sm-bar" + (b.on ? " on" : "")} onClick={() => onFilter(toggle(filter, h.id, b.id))}
          title={`${b.id}: ${fmt(b.count)} records. Click to ${b.on ? "remove the filter" : "show only these"}.`}>
          <span className="sm-l">{b.id}</span>
          <span className="sm-v"><span className="bar" style={{ width: `${(100 * b.count) / max}%` }} /></span>
          <span className="sm-c">{fmt(b.count)}</span>
        </button>
      ))}
    </div>
  );
}

/** Why a record is in the list: its bucket in each crossed or filtered stratum. */
export function StrataTags({ tags }: { tags?: StrataTag[] }) {
  if (!tags?.length) return null;
  return <div className="sm-tags">{tags.map((t) => <span key={t.dim} className="sm-tag" title={t.label}><span className="k">{t.label}</span> {t.bucket}</span>)}</div>;
}
