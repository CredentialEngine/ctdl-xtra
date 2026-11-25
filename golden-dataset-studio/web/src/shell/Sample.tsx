// The Sample drawer (facets.py): how the list is sampled. Modes:
// - Review order (Rules tab only): discussed first, then the likeliest problems mixed with a spread sample;
// - Autostratify: cross the strata that split the rows most evenly (or the ones picked here) and go through 3 records
//   of each combination, rarest combination first;
// - Shuffle: a seeded random order, with Reshuffle;
// - Manual select: every stratum as a histogram (one bar per bucket: how many records fall in it); click bars to filter.
// "Reviewed in other properties first" (Rules tab): records not reviewed for this rule yet, but marked or commented on in
// another rule, come first, so a record's properties get finished together.
// Who annotated a record isn't a stratum here: it's the Rules tab's "Annotated by" filter above the drawer (one way to
// do it; "Annotated in" says which ruleset version a record was annotated in).
// Filters stay on in every mode. When a filter or Autostratify is on, each record shows its strata tags (StrataTags).
import { useEffect, useRef, useState, type ReactNode } from "react";
import { filterParams, type FacetFilter, type SampleInfo, type SampleOrder, type StrataTag, type StratumHist } from "../api/types";
import { Ico } from "./icons";
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

interface DrawerProps {
  sample: SampleInfo | null; prefs: SamplePrefs; onPrefs: (p: SamplePrefs) => void; modes: SampleMode[]; storageKey: string;
  /** Another filter row in the same box, under the Sample row and laid out like it (the Rules tab's Annotated by): its
   * label, then its controls in a `.sm-ctl`. With it, each row's controls sit at the right, like the tab pickers. */
  filters?: ReactNode;
  /** When this changes (the reader moves to another row), the drawer closes: it stays out of the way while reviewing. */
  collapseOn?: unknown;
}
interface Drawer {
  sample: SampleInfo | null; prefs: SamplePrefs; set: (p: Partial<SamplePrefs>) => void; filters?: ReactNode;
  open: boolean; setOpenSaved: (v: boolean) => void;
}

export function SampleDrawer({ sample, prefs, onPrefs, modes, storageKey, collapseOn, filters }: DrawerProps) {
  const [open, setOpenSaved] = useDrawerOpen(storageKey, collapseOn);
  const drawer: Drawer = { sample, prefs, set: (p) => onPrefs({ ...prefs, ...p }), filters, open, setOpenSaved };
  const prior = sample?.elsewhere !== undefined && <PriorToggle elsewhere={sample.elsewhere} drawer={drawer} />;
  return (
    <div className={"sample" + (open ? " open" : "") + (filters ? " sm-rows" : "")} data-testid="sample">
      <DrawerHead drawer={drawer} modes={modes} prior={prior} />
      {filters && <div className="sm-head sm-row">{filters}</div>}
      {filters && open && prior && <div className="sm-head sm-row">{prior}</div>}
      <FilterChips drawer={drawer} />
      <ModePanel drawer={drawer} />
    </div>
  );
}

function DrawerHead({ drawer, modes, prior }: { drawer: Drawer; modes: SampleMode[]; prior: ReactNode }) {
  const { open, setOpenSaved, prefs, set, filters, sample } = drawer;
  return (
    <div className="sm-head">
      <button className="sm-tog" aria-expanded={open} onClick={() => setOpenSaved(!open)}><Ico name={open ? "chevron" : "chevron-right"} className="tw" />Sample</button>
      <div className="sm-ctl">
        {prefs.mode === "shuffle" && <button className="btn sm-btn" onClick={() => set({ seed: prefs.seed + 1 })}>Reshuffle</button>}
        <ModeButtons drawer={drawer} modes={modes} />
      </div>
      {!filters && prior}
      {!filters && sample && <ListedCount sample={sample} />}
    </div>
  );
}

function ModeButtons({ drawer: { prefs, set, setOpenSaved }, modes }: { drawer: Drawer; modes: SampleMode[] }) {
  return (
    <div className="seg sm-modes" role="group" aria-label="Sample">
      {modes.map((m) => <button key={m} className={prefs.mode === m ? "on" : ""}
        onClick={() => { set({ mode: m }); if (m === "manual" || m === "auto") setOpenSaved(true); }}>{MODE_NAME[m]}</button>)}
    </div>
  );
}

function PriorToggle({ elsewhere, drawer: { prefs, set } }: { elsewhere: number; drawer: Drawer }) {
  return (
    <label className={"sm-prior" + (elsewhere ? "" : " faint")} title="Records nobody has reviewed for this rule yet, but someone marked or commented on in another rule">
      <input type="checkbox" checked={prefs.prior} onChange={(e) => set({ prior: e.target.checked })} />
      Reviewed in other properties first <span className="faint">({fmt(elsewhere)})</span></label>
  );
}

function ListedCount({ sample }: { sample: SampleInfo }) {
  return <span className="faint sm-n">{fmt(sample.listed)}{sample.listed !== sample.total && <> of {fmt(sample.total)}</>}</span>;
}

function FilterChips({ drawer: { sample, prefs, set, filters, open } }: { drawer: Drawer }) {
  const chips = filterChips(prefs.filter);
  if (!(chips.length > 0 || (filters && !open && prefs.prior))) return null;
  return (
    <div className="sm-chips">
      {chips.map(({ d, b }) => (
        <span key={d + b} className="sm-chip">{labelOf(sample, d)}: {b}
          <button aria-label={`Remove ${labelOf(sample, d)}: ${b}`} onClick={() => set({ filter: toggle(prefs.filter, d, b) })}>×</button></span>
      ))}
      {filters && !open && prefs.prior && <span className="sm-chip">Reviewed in other properties first
        <button aria-label="Stop putting rows reviewed in other properties first" onClick={() => set({ prior: false })}>×</button></span>}
      {chips.length > 0 && <button className="sm-clear" onClick={() => set({ filter: {} })}>Clear filters</button>}
    </div>
  );
}

function ModePanel({ drawer: { open, sample, prefs, set } }: { drawer: Drawer }) {
  if (!open) return null;
  if (sample && prefs.mode === "auto") return <AutoPanel sample={sample} prefs={prefs} onCross={(cross) => set({ cross })} />;
  if (sample && prefs.mode === "manual") return <ManualPanel hs={sample.histograms} filter={prefs.filter} onFilter={(filter) => set({ filter })} />;
  if (prefs.mode === "shuffle") {
    const filtered = filterChips(prefs.filter).length > 0;
    return <p className="sm-d faint">A random order of the records{filtered ? " that pass the filters" : ""}. Reshuffle for another.</p>;
  }
  if (prefs.mode === "review") return <p className="sm-d faint">Discussed rows first, then rows with signals, with every 5th row from a spread sample.</p>;
  return null;
}

function AutoPanel({ sample, prefs, onCross }: { sample: SampleInfo; prefs: SamplePrefs; onCross: (c: string[]) => void }) {
  return (
    <div className="sm-panel" data-testid="auto-panel">
      <p className="sm-d">Goes through <b>3 records of each combination</b> of the strata crossed, the rarest combinations
        first (the ones least like the bulk of the records), then the rest the same way.
        {" "}<Crossed sample={sample} /></p>
      <CrossButtons sample={sample} onCross={onCross} />
      {prefs.cross === null && <p className="sm-d faint">Picked automatically: the strata that split the records most evenly (2–8 buckets each).</p>}
    </div>
  );
}

function Crossed({ sample }: { sample: SampleInfo }) {
  if (!sample.cross.length) return <>{"Nothing crossed: pick strata below."}</>;
  const n = sample.cell_count ?? sample.cells.length;
  return <>{sample.cross.map((c) => sample.histograms.find((h) => h.id === c)?.label ?? c).join(" × ")}: <b>{fmt(n)}</b> combinations.</>;
}

function CrossButtons({ sample, onCross }: { sample: SampleInfo; onCross: (c: string[]) => void }) {
  const can = sample.histograms.filter((h) => !h.uniform && !NOT_CROSSED.includes(h.id));
  const on = new Set(sample.cross);
  const flip = (id: string) => onCross(on.has(id) ? sample.cross.filter((c) => c !== id) : [...sample.cross, id]);
  return (
    <div className="sm-cross" aria-label="Strata to cross">
      {can.map((h) => <button key={h.id} className={"sm-dim" + (on.has(h.id) ? " on" : "")} aria-pressed={on.has(h.id)}
        title={h.help} onClick={() => flip(h.id)}>{h.label} <span className="faint">{h.buckets.length}</span></button>)}
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
      <StrataTabs shown={shown} cur={cur} filter={filter} onActivate={setActive} />
      {cur && <Bars h={cur} filter={filter} onFilter={onFilter} />}
      {uniform.length > 0 && <div className="sm-uni faint">Same for every record: {uniform.map((h) => `${h.label} (${h.buckets[0]?.id ?? "—"})`).join(" · ")}</div>}
    </div>
  );
}

function StrataTabs({ shown, cur, filter, onActivate }: {
  shown: StratumHist[]; cur: StratumHist | undefined; filter: FacetFilter; onActivate: (id: string) => void;
}) {
  return (
    <div className="sm-dims" role="tablist" aria-label="Strata">
      {shown.map((h) => <button key={h.id} role="tab" aria-selected={cur?.id === h.id} title={h.help}
        className={"sm-dim" + (cur?.id === h.id ? " on" : "") + (filter[h.id] ? " filtered" : "")}
        onClick={() => onActivate(h.id)}>{h.label}</button>)}
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

function useDrawerOpen(storageKey: string, collapseOn: unknown): [boolean, (v: boolean) => void] {
  const [open, setOpen] = useState<boolean>(() => { try { return localStorage.getItem(storageKey) === "1"; } catch { return false; } });
  useCloseOnChange(collapseOn, setOpen);
  const setOpenSaved = (v: boolean) => { setOpen(v); try { localStorage.setItem(storageKey, v ? "1" : "0"); } catch { /* private */ } };
  return [open, setOpenSaved];
}

// not on the first render: only when `collapseOn` changes afterwards
function useCloseOnChange(collapseOn: unknown, setOpen: (open: boolean) => void) {
  const firstCollapse = useRef(true);
  useEffect(() => {
    if (firstCollapse.current) { firstCollapse.current = false; return; }
    setOpen(false);
  }, [collapseOn, setOpen]);
}

function labelOf(sample: SampleInfo | null, id: string): string {
  return sample?.histograms.find((h) => h.id === id)?.label ?? id;
}

function filterChips(filter: FacetFilter): { d: string; b: string }[] {
  return Object.entries(filter).flatMap(([d, bs]) => bs.map((b) => ({ d, b })));
}
