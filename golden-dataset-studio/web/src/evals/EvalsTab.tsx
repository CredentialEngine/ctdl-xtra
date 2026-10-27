// Evals (docs/qrspi/evals): score an xtra-cli extraction against a version of the golden dataset, see how it did,
// and drill into the segments that don't agree. Runs and evals are started from here (when the server allows it)
// and run as jobs; everything they write stays in the Studio's own folder.
//
// URL: #/c/<catalog>/evals/<ev-id>?g=hand|full&f=<dim=bucket|…>&dim=<heatmap dimension>&off=<row offset>
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { EvalJob, EvalOutcome, EvalRow, EvalsIndex, EvalView } from "../api/types";
import { useReviewer } from "../shell/reviewer";
import { go, href } from "../shell/router";
import type { TabProps } from "../shell/tabProps";
import { fmt, toast, useKeyHints } from "../shell/ui";
import { wordDiff } from "./diff";
import "./evals.css";

const OUTCOMES: EvalOutcome[] = ["exact", "partial", "wrong", "missing"];
const OUTCOME_LABEL: Record<EvalOutcome, string> = {
  exact: "exact", partial: "partial (≥ 0.8)", wrong: "wrong (< 0.8)", missing: "missing",
};
const PAGE = 50;
const pct = (x: number | null | undefined) => (x === null || x === undefined ? "–" : `${Math.round(x * 100)}%`);

type Golden = "hand" | "full";
type Tip = { x: number; y: number; body: ReactNode } | null;

export default function EvalsTab({ catalog, route }: TabProps) {
  const me = useReviewer();
  const [idx, setIdx] = useState<EvalsIndex | null>(null);
  const [view, setView] = useState<EvalView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [panel, setPanel] = useState<"run" | "eval" | null>(null);
  const [job, setJob] = useState<EvalJob | null>(null);
  const [showLog, setShowLog] = useState(false);
  const [tip, setTip] = useState<Tip>(null);

  const evalId = route.id ?? idx?.evals[0]?.id ?? null;
  const golden: Golden = route.params.get("g") === "hand" ? "hand" : "full";
  const filters = useMemo(() => (route.params.get("f") || "").split("|").filter(Boolean), [route.params]);
  const dim = route.params.get("dim") || "template";
  const offset = +(route.params.get("off") || 0);
  const nav = useCallback((p: { id?: string | null; g?: Golden; f?: string[]; dim?: string; off?: number }) => {
    go(href(catalog.short, "evals", p.id === undefined ? evalId : p.id, {
      g: (p.g ?? golden) === "full" ? null : "hand", f: (p.f ?? filters).join("|") || null,
      dim: (p.dim ?? dim) === "template" ? null : p.dim ?? dim, off: (p.off ?? (p.f || p.g || p.id ? 0 : offset)) || null,
    }), true);
  }, [catalog.short, evalId, golden, filters, dim, offset]);

  const loadIndex = useCallback(() => api.evals(catalog.short).then((r) => {
    setIdx(r);
    const running = r.jobs.find((j) => j.status === "running");
    if (running) setJob(running);
    return r;
  }, (e) => { setError(String(e)); return null; }), [catalog.short]);
  useEffect(() => { loadIndex(); }, [loadIndex]);

  useEffect(() => {
    if (!evalId) { setView(null); return; }
    let live = true;
    api.evalView(catalog.short, evalId, { golden, f: filters, dim, offset, limit: PAGE })
      .then((v) => live && setView(v), (e) => live && setError(String(e)));
    return () => { live = false; };
  }, [catalog.short, evalId, golden, filters, dim, offset]);

  // poll the running job; when it ends, reload the lists and open the eval it made
  useEffect(() => {
    if (!job || job.status !== "running") return;
    const t = setInterval(() => api.job(job.id).then((j) => {
      setJob(j);
      if (j.status !== "running") {
        loadIndex();
        if (j.status === "done" && j.result?.eval) { toast(`${j.result.eval} is ready`); nav({ id: j.result.eval, f: [] }); }
        else if (j.status === "done") toast(`${j.result?.run} is ready`);
        else toast(`${j.label}: ${j.status}${j.error ? ` (${j.error})` : ""}`);
      }
    }), 1200);
    return () => clearInterval(t);
  }, [job, loadIndex, nav]);

  useKeyHints(<span><span className="mono">golden-datasets xtra run</span> and <span className="mono">golden-datasets eval run</span> do the same from the CLI</span>, []);

  const toggleFilter = (d: string, b: string) => {
    const k = `${d}=${b}`;
    nav({ f: filters.includes(k) ? filters.filter((x) => x !== k) : [...filters, k] });
  };
  const setFilters = (pairs: [string, string][]) => {
    const keep = filters.filter((x) => !pairs.some(([d]) => x.startsWith(`${d}=`)));
    nav({ f: [...keep, ...pairs.map(([d, b]) => `${d}=${b}`)] });
  };
  const start = async (p: Promise<EvalJob>) => {
    try { setJob(await p); setPanel(null); setShowLog(true); } catch (e) { toast(String(e)); }
  };

  if (error) return <div className="doc"><div className="doc-in"><p className="muted">{error}</p></div></div>;
  if (!idx) return <div className="doc"><div className="doc-in"><h1>Evals</h1></div></div>;
  const running = job?.status === "running";
  const ev = view?.eval;

  return (
    <div className="doc evals" onMouseLeave={() => setTip(null)}>
      <div className="ev-in">
        <div className="ev-top">
          <h1>Evals</h1>
          <label className="ev-pick">Eval{" "}
            <select value={evalId ?? ""} onChange={(e) => nav({ id: e.target.value, f: [] })}>
              {idx.evals.map((e) => (
                <option key={e.id} value={e.id}>{e.id} · {e.xtra_run} vs {e.golden.golden}</option>
              ))}
            </select>
          </label>
          <div className="seg" title="Score against the values a person confirmed, or against every golden value">
            <button className={golden === "hand" ? "on" : ""} onClick={() => nav({ g: "hand" })}>Hand-checked only</button>
            <button className={golden === "full" ? "on" : ""} onClick={() => nav({ g: "full" })}>Full: hand + rule</button>
          </div>
          <span className="grow" />
          <button className="btn" disabled={!idx.allow_runs || running} onClick={() => setPanel(panel === "run" ? null : "run")}
            title={idx.allow_runs ? "Run xtra-cli extract into the Studio's folder" : "Start the Studio with --allow-runs to start runs here"}>
            ▶ New xtra run</button>
          <button className="btn" disabled={!idx.allow_runs || running || !idx.runs.length}
            onClick={() => setPanel(panel === "eval" ? null : "eval")}
            title={idx.allow_runs ? "Score an xtra run against a golden version" : "Start the Studio with --allow-runs to start evals here"}>
            ▶ Run eval</button>
        </div>

        {panel === "run" && <RunPanel idx={idx} onStart={(b) => start(api.startXtraRun(catalog.short, { ...b, by: me }))} />}
        {panel === "eval" && <EvalPanel idx={idx} onStart={(b) => start(api.startEval(catalog.short, { ...b, by: me }))} />}
        {job && (job.status === "running" || showLog) && (
          <div className={`ev-job ${job.status}`}>
            <span className={`ev-dot ${job.status}`} />
            <b>{job.label}</b>
            <span className="muted">{job.status === "running" ? job.log[job.log.length - 1] ?? "starting…" : job.status}</span>
            <span className="grow" />
            <button className="btn sm" onClick={() => setShowLog(!showLog)}>{showLog ? "Hide log" : "Log"}</button>
            {job.status === "running" && <button className="btn sm" onClick={() => api.cancelJob(job.id).then(setJob)}>Cancel</button>}
            {job.status !== "running" && <button className="btn sm" onClick={() => { setJob(null); setShowLog(false); }}>✕</button>}
            {showLog && <pre className="ev-log">{job.log.join("\n")}</pre>}
          </div>
        )}

        {!evalId && <p className="muted">No evals yet. {idx.allow_runs
          ? "Start an xtra run (or import the team's records/), then run an eval."
          : <>Run <span className="mono">golden-datasets xtra run --import</span> and <span className="mono">golden-datasets eval run --xtra-run x-0001</span>, or start the Studio with <span className="mono">--allow-runs</span>.</>}</p>}

        {ev && view && (
          <>
            <EvalHeader idx={idx} view={view} />
            <div className="ev-grid">
              <section className="ev-card wide">
                <h2>Outcomes by property <span className="muted">· both goldens{filters.length ? ", filtered" : ""}</span></h2>
                <OutcomeBars view={view} golden={golden} setTip={setTip}
                  onPick={(g, p, o) => { if (g !== golden) nav({ g, f: [...filters.filter((x) => !x.startsWith("property=") && !x.startsWith("outcome=")), `property=${p}`, `outcome=${o}`] }); else setFilters([["property", p], ["outcome", o]]); }} />
                <Legend />
              </section>
              <section className="ev-card">
                <h2>Similarity of values that aren't exact <span className="muted">· {golden === "hand" ? "hand-checked" : "full"}</span></h2>
                <Histogram view={view} setTip={setTip} onPick={(b) => setFilters([["similarity", b]])} />
              </section>
            </div>

            <section className="ev-card">
              <div className="ev-h">
                <h2>Segments</h2>
                <label>by{" "}
                  <select value={dim} onChange={(e) => nav({ dim: e.target.value })}>
                    {view.dims.filter((d) => d.id !== "property").map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
                  </select>
                </label>
                <span className="muted">cell: share of values that aren't exact (count)</span>
              </div>
              <div className="ev-seg">
                <Heatmap view={view} setTip={setTip} onPick={(b, p) => setFilters(p ? [[dim, b], ["property", p]] : [[dim, b]])} />
                <Disagree view={view} onPick={(d) => setFilters([[d.dim, d.bucket], ["property", d.property]])} />
              </div>
            </section>

            <section className="ev-card">
              <FilterBar view={view} filters={filters} onToggle={toggleFilter} onClear={() => nav({ f: [] })} />
              <Rows view={view} catalog={catalog.short} offset={offset} onPage={(o) => nav({ off: o })} />
            </section>

            <History idx={idx} current={ev.id} onPick={(id) => nav({ id, f: [] })} />
          </>
        )}
      </div>
      {tip && <div className="ev-tip" style={{ left: tip.x + 14, top: tip.y + 14 }}>{tip.body}</div>}
    </div>
  );
}

// --- panels ---------------------------------------------------------------------------------------------------
function RunPanel({ idx, onStart }: { idx: EvalsIndex; onStart: (b: { ref?: string; sample?: boolean; import?: boolean; then_eval?: string | null }) => void }) {
  const [ref, setRef] = useState(idx.default_ref);
  const [sample, setSample] = useState(true);
  const [imp, setImp] = useState(false);
  const [then, setThen] = useState<string>(idx.goldens[0]?.id ?? "");
  return (
    <div className="ev-panel">
      <label><input type="radio" checked={!imp} onChange={() => setImp(false)} /> Extract with xtra-cli at{" "}
        <input className="mono" value={ref} onChange={(e) => setRef(e.target.value)} disabled={imp} size={34} /></label>
      {!imp && (
        <span className="seg">
          <button className={sample ? "on" : ""} onClick={() => setSample(true)}>Golden sample (quick)</button>
          <button className={!sample ? "on" : ""} onClick={() => setSample(false)}>All pages</button>
        </span>
      )}
      <label><input type="radio" checked={imp} onChange={() => setImp(true)} /> Import the team's current <span className="mono">records/</span></label>
      <label>then score against{" "}
        <select value={then} onChange={(e) => setThen(e.target.value)}>
          <option value="">(don't score)</option>
          {idx.goldens.map((g) => <option key={g.id} value={g.id}>{g.label}</option>)}
        </select>
      </label>
      <button className="btn primary" onClick={() => onStart({ ref, sample, import: imp, then_eval: then || null })}>Start</button>
      <p className="muted small">Writes only into the Studio's folder (<span className="mono">xtra-runs/x-NNNN/</span>); the team's records/ and reports aren't touched.</p>
    </div>
  );
}

function EvalPanel({ idx, onStart }: { idx: EvalsIndex; onStart: (b: { xtra_run: string; golden: string }) => void }) {
  const [run, setRun] = useState(idx.runs[0]?.id ?? "");
  const [golden, setGolden] = useState(idx.goldens[0]?.id ?? "published");
  return (
    <div className="ev-panel">
      <label>xtra run{" "}
        <select value={run} onChange={(e) => setRun(e.target.value)}>
          {idx.runs.map((r) => <option key={r.id} value={r.id}>{r.id} · {r.kind === "import" ? "imported records/" : `${r.ref} @ ${r.commit?.slice(0, 7)}`} · {r.scope}</option>)}
        </select>
      </label>
      <label>vs golden{" "}
        <select value={golden} onChange={(e) => setGolden(e.target.value)}>
          {idx.goldens.map((g) => <option key={g.id} value={g.id}>{g.label}</option>)}
        </select>
      </label>
      <button className="btn primary" onClick={() => onStart({ xtra_run: run, golden })}>Start</button>
      <p className="muted small">Scores against the hand-checked and the full golden, with <span className="mono">xtra score extraction match</span>.</p>
    </div>
  );
}

function EvalHeader({ idx, view }: { idx: EvalsIndex; view: EvalView }) {
  const ev = view.eval;
  const run = idx.runs.find((r) => r.id === ev.xtra_run);
  const label = idx.goldens.find((g) => g.id === ev.golden.golden)?.label ?? ev.golden.golden;
  const s = ev.summary[view.golden];
  return (
    <div className="ev-head">
      <div>
        <b>{ev.id}</b>: <b>{ev.xtra_run}</b>{" "}
        <span className="muted">({run?.kind === "import" ? "imported records/" : `${run?.ref} @ ${run?.commit?.slice(0, 7)}`}, {run?.scope}, {fmt(run?.records_written)} records)</span>
        {" "}vs <b>{label}</b>{!ev.golden.approved && <span className="pill needs" title="Built from an extraction that isn't published: its rules may not be approved">unapproved</span>}
      </div>
      <div className="ev-stats">
        {(["hand", "full"] as Golden[]).map((g) => {
          const k = ev.summary[g];
          return (
            <div key={g} className={`ev-stat ${g === view.golden ? "on" : ""}`}>
              <span className="muted">{g === "hand" ? "Hand-checked" : "Full"}</span>
              <b>{k.fields_total ? pct(k.exact_match_rate) : "–"}</b>
              <span className="muted">{k.fields_total ? `exact of ${fmt(k.fields_total)} values`
                : k.fields_total === 0 ? "none of its values are on this run's pages" : "no values to score"}</span>
            </div>
          );
        })}
      </div>
      {s.left_out.length > 0 && <div className="muted small">{s.left_out.length} pages left out of this baseline: {s.left_out[0].why}.</div>}
      <details className="ev-cmds">
        <summary>Run it yourself</summary>
        <pre>{["az login", 'export AZURE_STORAGE_CONNECTION_STRING="$(az storage account show-connection-string -n ceteststorage --query connectionString -o tsv)"',
          ...(run?.commands ?? []), ...ev.commands].join("\n\n")}</pre>
      </details>
    </div>
  );
}

// --- charts ---------------------------------------------------------------------------------------------------
function Legend() {
  return (
    <div className="ev-legend">
      {OUTCOMES.map((o) => <span key={o}><i className={`sw o-${o}`} />{OUTCOME_LABEL[o]}</span>)}
    </div>
  );
}

function OutcomeBars({ view, golden, setTip, onPick }: {
  view: EvalView; golden: Golden; setTip: (t: Tip) => void; onPick: (g: Golden, property: string, o: EvalOutcome) => void;
}) {
  const props = Array.from(new Set([...view.goldens.full.by_property, ...view.goldens.hand.by_property].map((p) => p.property)));
  return (
    <div className="ev-bars">
      {props.map((p) => (
        <div key={p} className="ev-barset">
          <div className="ev-prop">{p}</div>
          {(["hand", "full"] as Golden[]).map((g) => {
            const row = view.goldens[g].by_property.find((x) => x.property === p);
            return (
              <div key={g} className={`ev-bar-row ${g === golden ? "on" : ""}`}>
                <span className="ev-g">{g === "hand" ? "hand" : "full"}</span>
                <div className="ev-track">
                  {row ? OUTCOMES.filter((o) => row[o] > 0).map((o) => (
                    <div key={o} className={`ev-segm o-${o}`} style={{ flexGrow: row[o] }}
                      onClick={() => onPick(g, p, o)}
                      onMouseMove={(e) => setTip({ x: e.clientX, y: e.clientY, body: <><b>{p}</b> · {g === "hand" ? "hand-checked" : "full"}<br />{OUTCOME_LABEL[o]}: {fmt(row[o])} of {fmt(row.fields)} ({pct(row[o] / row.fields)})<br /><span className="muted">click to see these rows</span></> })}
                      onMouseLeave={() => setTip(null)} />
                  )) : <div className="ev-none">no values</div>}
                </div>
                <span className="ev-n">{row ? <><b>{pct(row.exact / row.fields)}</b> <span className="muted">of {fmt(row.fields)}</span></> : ""}</span>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

const simBucket = (x: number) => (x >= 0.95 ? "0.95–1" : x >= 0.9 ? "0.90–0.95" : x >= 0.8 ? "0.80–0.90" : x >= 0.5 ? "0.50–0.80" : "< 0.50");

function Histogram({ view, setTip, onPick }: { view: EvalView; setTip: (t: Tip) => void; onPick: (bucket: string) => void }) {
  const W = 420, H = 150, L = 34, R = 10, B = 22, T = 8;
  const bins = view.histogram;
  const max = Math.max(1, ...bins.map((b) => b.partial + b.wrong));
  const PW = W - L - R;
  const bw = PW / bins.length;
  const y = (n: number) => T + (H - T - B) * (1 - n / max);
  const total = bins.reduce((s, b) => s + b.partial + b.wrong, 0);
  if (!total) return <p className="muted">Every value here is exact or missing.</p>;
  return (
    <svg className="ev-hist" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Similarity histogram">
      {[0, max].map((n) => <text key={n} x={L - 6} y={y(n) + 4} textAnchor="end" className="ax">{fmt(n)}</text>)}
      <line x1={L} x2={L + PW} y1={H - B} y2={H - B} className="base" />
      {bins.map((b, i) => {
        const n = b.partial + b.wrong;
        if (!n) return null;
        const x = L + i * bw + 1, h = H - B - y(n);
        return (
          <g key={i} onClick={() => onPick(simBucket(b.lo))}
            onMouseMove={(e) => setTip({ x: e.clientX, y: e.clientY, body: <>similarity {b.lo.toFixed(2)}–{b.hi.toFixed(2)}<br />{fmt(n)} values ({b.lo >= 0.8 ? "partial" : "wrong"})<br /><span className="muted">click to see them</span></> })}
            onMouseLeave={() => setTip(null)}>
            <rect x={L + i * bw} y={T} width={bw} height={H - B - T} fill="transparent" />
            <path className={b.lo >= 0.8 ? "o-partial-f" : "o-wrong-f"}
              d={`M${x},${H - B} v${-(h - 3)} q0,-3 3,-3 h${bw - 8} q3,0 3,3 v${h - 3} z`} />
          </g>
        );
      })}
      <line x1={L + 0.8 * PW} x2={L + 0.8 * PW} y1={T - 4} y2={H - B} className="thr" />
      <text x={L + 0.8 * PW - 4} y={T + 6} textAnchor="end" className="ax">wrong ← 0.8 → partial</text>
      {[0, 0.5, 1].map((v) => <text key={v} x={L + v * PW} y={H - 6} textAnchor="middle" className="ax">{v}</text>)}
    </svg>
  );
}

// sequential blue ramp (reference palette steps 100–650) for the share of values that aren't exact
const RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#104281"];
const rampColor = (rate: number) => RAMP[Math.min(RAMP.length - 1, Math.floor(rate * RAMP.length))];

function Heatmap({ view, setTip, onPick }: { view: EvalView; setTip: (t: Tip) => void; onPick: (bucket: string, property?: string) => void }) {
  const [all, setAll] = useState(false);
  const hm = view.heatmap;
  const rows = all ? hm.rows : hm.rows.slice(0, 14);
  if (!hm.rows.length) return <p className="muted">No rows.</p>;
  return (
    <div className="ev-heat-wrap">
      <table className="ev-heat">
        <thead><tr><th>{hm.label}</th><th className="n">values</th>{hm.properties.map((p) => <th key={p}>{p}</th>)}</tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.bucket}>
              <th onClick={() => onPick(r.bucket)} className="click">{r.bucket}</th>
              <td className="n">{fmt(r.n)}</td>
              {hm.properties.map((p) => {
                const c = r.cells[p];
                if (!c) return <td key={p} />;
                const rate = c.bad / c.n, small = c.n < 5;
                const dark = rate >= 3 / 7 && !small;
                return (
                  <td key={p} className={`cell ${small ? "small" : ""}`} onClick={() => onPick(r.bucket, p)}
                    style={{ background: rampColor(rate), color: dark ? "#fff" : "#101828" }}
                    onMouseMove={(e) => setTip({ x: e.clientX, y: e.clientY, body: <><b>{hm.label}: {r.bucket}</b> · {p}<br />{fmt(c.bad)} of {fmt(c.n)} aren't exact ({pct(rate)})<br /><span className="muted">{p} overall: {pct(hm.base[p])}{small ? " · fewer than 5 values" : ""}</span></> })}
                    onMouseLeave={() => setTip(null)}>
                    {pct(rate)} <span className="cnt">({fmt(c.n)})</span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {hm.rows.length > 14 && <button className="btn sm" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${hm.rows.length}`}</button>}
      <div className="ev-ramp"><span className="muted">0%</span>{RAMP.map((c) => <i key={c} style={{ background: c }} />)}<span className="muted">100% not exact</span></div>
    </div>
  );
}

function Disagree({ view, onPick }: { view: EvalView; onPick: (d: EvalView["disagree"][number]) => void }) {
  return (
    <div className="ev-dis">
      <h3>Disagree most</h3>
      <p className="muted small">Segments whose values miss more than their property does overall, by how many extra misses.</p>
      {!view.disagree.length && <p className="muted">Nothing stands out.</p>}
      {view.disagree.map((d) => (
        <button key={`${d.dim}|${d.bucket}|${d.property}`} className="ev-dis-item" onClick={() => onPick(d)}>
          <span><b>{d.dim_label}: {d.bucket}</b> × {d.property}</span>
          <span className="muted">{fmt(d.bad)} of {fmt(d.n)} not exact ({pct(d.rate)} vs {pct(d.base)}) · <b>+{Math.round(d.excess)}</b></span>
        </button>
      ))}
    </div>
  );
}

// --- filters and rows -----------------------------------------------------------------------------------------
function FilterBar({ view, filters, onToggle, onClear }: { view: EvalView; filters: string[]; onToggle: (d: string, b: string) => void; onClear: () => void }) {
  const [d, setD] = useState("");
  const dimOf = view.dims.find((x) => x.id === d);
  return (
    <div className="ev-filters">
      <b>{fmt(view.rows.total)} values</b>
      {filters.map((f) => {
        const [k, ...rest] = f.split("="); const b = rest.join("=");
        const label = view.dims.find((x) => x.id === k)?.label ?? k;
        return <button key={f} className="ev-chip" onClick={() => onToggle(k, b)}>{label}: {b} ✕</button>;
      })}
      <select value={d} onChange={(e) => setD(e.target.value)}>
        <option value="">Add a filter…</option>
        {view.dims.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
      </select>
      {dimOf && (
        <select value="" onChange={(e) => { if (e.target.value) { onToggle(d, e.target.value); setD(""); } }}>
          <option value="">{dimOf.label}…</option>
          {dimOf.buckets.map((b) => <option key={b.bucket} value={b.bucket}>{b.bucket} ({fmt(b.n)})</option>)}
        </select>
      )}
      {filters.length > 0 && <button className="btn sm" onClick={onClear}>Clear</button>}
    </div>
  );
}

function Rows({ view, catalog, offset, onPage }: { view: EvalView; catalog: string; offset: number; onPage: (o: number) => void }) {
  const { total, items } = view.rows;
  return (
    <>
      <table className="ev-rows">
        <thead><tr><th>Course</th><th>Property</th><th>Outcome</th><th>Golden → xtra</th><th>Approved by</th><th>Extractor</th></tr></thead>
        <tbody>{items.map((r, i) => <RowLine key={`${r.page_stem}|${r.entity}|${r.property}|${i}`} r={r} catalog={catalog} />)}</tbody>
      </table>
      <div className="ev-pager">
        <button className="btn sm" disabled={offset === 0} onClick={() => onPage(Math.max(0, offset - PAGE))}>Previous</button>
        <span className="muted">{total ? `${fmt(offset + 1)}–${fmt(Math.min(total, offset + PAGE))} of ${fmt(total)}` : "no rows"}, worst first</span>
        <button className="btn sm" disabled={offset + PAGE >= total} onClick={() => onPage(offset + PAGE)}>Next</button>
      </div>
    </>
  );
}

function RowLine({ r, catalog }: { r: EvalRow; catalog: string }) {
  const parts = useMemo(() => (r.outcome === "partial" || r.outcome === "wrong") ? wordDiff(r.golden_value ?? "", r.xtra_value ?? "") : null,
    [r.golden_value, r.xtra_value, r.outcome]);
  const [open, setOpen] = useState(false);
  return (
    <tr>
      <td>{r.golden_record_id ? <a href={href(catalog, "records", r.golden_record_id)} title={r.page_stem}>{r.golden_record_id}</a> : <span className="mono">{r.page_stem}</span>}
        {r.courses_on_page > 1 && <div className="muted small">course {r.entity + 1} of {r.courses_on_page} on the page</div>}</td>
      <td>{r.property}</td>
      <td><span className={`ev-out o-${r.outcome}`}><i className={`sw o-${r.outcome}`} />{r.outcome}</span>
        {r.similarity !== null && r.outcome !== "exact" && <div className="muted small">{r.similarity.toFixed(2)}</div>}</td>
      <td className={`ev-val ${open ? "open" : ""}`} onClick={() => setOpen(!open)} title={open ? "Click to shorten" : "Click to show the whole value"}>
        {r.outcome === "exact" && <div className="txt">{r.golden_value}</div>}
        {r.outcome === "missing" && <><div className="txt">{r.golden_value}</div><div className="muted small">xtra emitted nothing</div></>}
        {parts && <div className="diff">{parts.map((p, i) => p.op === "del" ? <del key={i}>{p.text}</del> : p.op === "ins" ? <ins key={i}>{p.text}</ins> : <span key={i}>{p.text}</span>)}</div>}
      </td>
      <td>{r.approval === "human" ? <span className="pill approved">{r.approved_by ?? "a person"}</span> : <span className="pill review">rule</span>}</td>
      <td className="mono small">{r.template_id ?? "–"}</td>
    </tr>
  );
}

function History({ idx, current, onPick }: { idx: EvalsIndex; current: string; onPick: (id: string) => void }) {
  const goldens = Array.from(new Set(idx.evals.map((e) => e.golden.golden)));
  const runs = idx.runs.filter((r) => idx.evals.some((e) => e.xtra_run === r.id));
  const ref = useRef<HTMLDivElement>(null);
  if (idx.evals.length < 2) return null;
  return (
    <section className="ev-card" ref={ref}>
      <h2>History <span className="muted">· exact match rate, hand-checked / full; the newest eval of each pair</span></h2>
      <table className="ev-hist-grid">
        <thead><tr><th>xtra run</th>{goldens.map((g) => <th key={g}>{idx.goldens.find((x) => x.id === g)?.label ?? g}</th>)}</tr></thead>
        <tbody>{runs.map((r) => (
          <tr key={r.id}>
            <th>{r.id} <span className="muted small">{r.kind === "import" ? "imported" : r.commit?.slice(0, 7)} · {r.scope}</span></th>
            {goldens.map((g) => {
              const e = idx.evals.find((x) => x.xtra_run === r.id && x.golden.golden === g);
              if (!e) return <td key={g} className="muted">–</td>;
              return (
                <td key={g} className={`click ${e.id === current ? "on" : ""}`} onClick={() => onPick(e.id)}>
                  {pct(e.summary.hand.exact_match_rate)} / <b>{pct(e.summary.full.exact_match_rate)}</b>
                  <span className="muted small"> {e.id}</span>
                </td>
              );
            })}
          </tr>
        ))}</tbody>
      </table>
    </section>
  );
}
