// Evals (docs/qrspi/evals), in `xtra score`'s words: score an extraction against a baseline.
// Left: the extractions and the baselines (with what each baseline holds). Middle: one score — its match rate, the
// properties, and the rows, narrowed by a property, an outcome and a group. Right: the saved page of the selected row,
// with the baseline value at its recorded location and the extracted value where its text is found.
//
// URL: #/c/<catalog>/evals?x=<extraction>&b=full|hand|verified&v=<rs-NNNN|published>&p=<property>&o=<outcome>
//      &g=<group by>&gv=<group>&off=<offset>&row=<row key>
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { BaselineId, BaselineInfo, EvalJob, EvalsIndex, OutcomeCounts, ScoreOutcome, ScoreRow, ScoreView } from "../api/types";
import { PagePane, type Highlight } from "../pagepane";
import { useReviewer } from "../shell/reviewer";
import { go, href } from "../shell/router";
import type { TabProps } from "../shell/tabProps";
import { fmt, Ico, toast, useKeyHints } from "../shell/ui";
import { multiline } from "./commands";
import { wordDiff } from "./diff";
import "./evals.css";

const OUTCOMES: ScoreOutcome[] = ["missing", "wrong", "partial", "match"];
const OUTCOME_LABEL: Record<ScoreOutcome, string> = { missing: "missing", wrong: "wrong < 0.8", partial: "partial ≥ 0.8", match: "match" };
const BASELINES: { id: BaselineId; name: string; what: string }[] = [
  { id: "full", name: "Full catalog", what: "Every record of the Studio version, values approved by a person or by their rule" },
  { id: "hand", name: "Hand-checked", what: "Only the values a person confirmed, from the same Studio version" },
  { id: "verified", name: "Verified container", what: "xtra-golden-sets-verified: pages checked by hand before the Studio" },
];
const pct = (x: number | null | undefined) => (x === null || x === undefined ? "–" : `${Math.round(x * 100)}%`);
const rate = (c: OutcomeCounts) => (c.fields ? c.match / c.fields : null);

export default function EvalsTab({ catalog, route }: TabProps) {
  const me = useReviewer();
  const cat = catalog.short;
  const [idx, setIdx] = useState<EvalsIndex | null>(null);
  const [view, setView] = useState<ScoreView | null>(null);
  const [info, setInfo] = useState<Record<string, BaselineInfo | null>>({});
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<EvalJob | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const [cmdOpen, setCmdOpen] = useState(false);

  const P = route.params;
  const latest = idx?.scores[0];
  const x = P.get("x") ?? latest?.extraction ?? idx?.extractions[0]?.id ?? null;
  const b = (P.get("b") as BaselineId | null) ?? latest?.baseline ?? "full";
  const v = P.get("v") ?? (latest && latest.baseline !== "verified" ? latest.version : null)
    ?? idx?.versions.find((g) => g.id !== "published")?.id ?? idx?.versions[0]?.id ?? "";
  const prop = P.get("p"), outcome = P.get("o") as ScoreOutcome | null, group = P.get("g"), gv = P.get("gv");
  const offset = +(P.get("off") || 0), rowKey = P.get("row");
  const nav = useCallback((ch: Record<string, string | number | null>, keepRow = false) => {
    const cur: Record<string, string | number | null> = { x, b, v, p: prop, o: outcome, g: group, gv, off: offset || null, row: keepRow ? rowKey : null };
    go(href(cat, "evals", null, { ...cur, ...ch }), true);
  }, [cat, x, b, v, prop, outcome, group, gv, offset, rowKey]);

  const loadIndex = useCallback(() => api.evals(cat).then((r) => {
    setIdx(r);
    const running = r.jobs.find((j) => j.status === "running");
    if (running) setJob(running);
  }, (e) => setError(String(e))), [cat]);
  useEffect(() => { loadIndex(); }, [loadIndex]);

  // what each baseline holds (for the nav)
  useEffect(() => {
    if (!idx || !v) return;
    for (const bl of BASELINES) {
      const k = bl.id === "verified" ? "verified" : `${bl.id}@${v}`;
      if (k in info) continue;
      setInfo((m) => ({ ...m, [k]: null }));
      api.baseline(cat, bl.id, v).then((r) => setInfo((m) => ({ ...m, [k]: r })), () => setInfo((m) => ({ ...m, [k]: null })));
    }
  }, [idx, v, cat, info]);

  const score = useMemo(() => idx?.scores.find((s) => s.extraction === x && s.baseline === b && (b === "verified" || s.version === v)),
    [idx, x, b, v]);
  useEffect(() => {
    if (!score) { setView(null); return; }
    let live = true;
    api.score(cat, score.eval, { kind: score.kind, property: prop, outcome, group, value: gv, offset })
      .then((r) => live && setView(r), (e) => live && setError(String(e)));
    return () => { live = false; };
  }, [cat, score, prop, outcome, group, gv, offset]);

  useEffect(() => {
    if (!job || job.status !== "running") return;
    const t = setInterval(() => api.job(job.id).then((j) => {
      setJob(j);
      if (j.status === "running") return;
      loadIndex();
      if (j.status === "done") {
        toast(j.result?.eval ? "Scored" : "Extraction ready");
        if (j.result?.run) nav({ x: j.result.run, p: null, o: null, gv: null, off: null });
      } else toast(`${j.label}: ${j.status}${j.error ? ` (${j.error})` : ""}`);
    }), 1200);
    return () => clearInterval(t);
  }, [job, loadIndex, nav]);

  useKeyHints(<span><span className="mono">golden-datasets xtra run</span> · <span className="mono">golden-datasets eval run</span> do the same from the CLI</span>, []);

  if (error) return <div className="doc"><div className="doc-in"><p className="muted">{error}</p></div></div>;
  if (!idx) return <div className="evx" />;
  const running = job?.status === "running";
  const extraction = idx.extractions.find((e) => e.id === x);
  const bl = BASELINES.find((z) => z.id === b)!;
  const binfo = info[b === "verified" ? "verified" : `${b}@${v}`];
  const version = idx.versions.find((g) => g.id === v);
  const golden = b === "verified" ? "verified" : v;
  const row = view?.rows.items.find((r) => r.key === rowKey) ?? null;
  const start = async (p: Promise<EvalJob>) => { try { setJob(await p); } catch (e) { toast(String(e)); } };

  return (
    <div className={`evx ${row ? "with-page" : ""}`}>
      <aside className="evx-nav">
        <div className="evx-sec-h">Extractions
          <button className="evx-link" disabled={!idx.allow_runs || running} onClick={() => setNewOpen(true)}
            title={idx.allow_runs ? "Run xtra-cli extract, or take what it last wrote" : "Start the Studio with --allow-runs to add extractions here"}>+ New</button>
        </div>
        {idx.extractions.map((e) => (
          <button key={e.id} className={`evx-item ${e.id === x ? "on" : ""}`} onClick={() => nav({ x: e.id, off: null })}>
            <span className="evx-item-t">{e.title}</span>
            <span className="evx-item-d">{e.scope} · {fmt(e.records)} records · {e.id}</span>
          </button>
        ))}
        {!idx.extractions.length && <p className="evx-empty">None yet.</p>}

        <div className="evx-sec-h">Baselines</div>
        <label className="evx-ver">Studio version
          <select value={v} onChange={(e) => nav({ v: e.target.value, p: null, o: null, gv: null, off: null })}>
            {idx.versions.map((g) => <option key={g.id} value={g.id}>{g.id === "published" ? "published" : g.id}{g.approved ? "" : " (unpublished)"}</option>)}
          </select>
        </label>
        {BASELINES.map((z) => {
          const i = info[z.id === "verified" ? "verified" : `${z.id}@${v}`];
          return (
            <div key={z.id} className={`evx-bl ${z.id === b ? "on" : ""}`}>
              <button className="evx-item" onClick={() => nav({ b: z.id, p: null, o: null, gv: null, off: null })} title={z.what}>
                <span className="evx-item-t">{z.name}</span>
                <span className="evx-item-d">{i ? `${fmt(i.records)} records · ${fmt(i.fields)} fields` : "…"}</span>
              </button>
              {z.id === b && i && (
                <ul className="evx-props">
                  {i.properties.map((p) => <li key={p.property}><span>{p.property}</span><span>{fmt(p.fields)}</span></li>)}
                  {i.not_scored.map((p) => <li key={p.property} className="off" title={`Not scored: ${p.why}`}><span>{p.property}</span><span>not scored</span></li>)}
                  {!i.properties.length && <li className="off"><span>No values</span></li>}
                </ul>
              )}
            </div>
          );
        })}
      </aside>

      <section className="evx-main">
        {job && (running || job.status === "failed") && <JobBar job={job} onCancel={() => api.cancelJob(job.id).then(setJob)} onClose={() => setJob(null)} />}
        <header className="evx-head">
          <div className="evx-title">
            <span>{extraction?.title ?? "No extraction"}</span>
            <span className="evx-arrow">scored against</span>
            <span>{bl.name}{b !== "verified" && version ? ` · ${v}` : ""}</span>
            {b !== "verified" && version && !version.approved && <span className="evx-tag" title="An extraction that isn't published: its rules may not be approved">unpublished</span>}
          </div>
          <div className="evx-actions">
            {(score || extraction) && <button className="evx-icon" onClick={() => setCmdOpen(!cmdOpen)} title="Run it yourself"><Ico name="terminal" /></button>}
            {extraction && <button className="btn" disabled={!idx.allow_runs || running}
              title={idx.allow_runs ? "" : "Start the Studio with --allow-runs to score here"}
              onClick={() => start(api.startScore(cat, { xtra_run: extraction.id, golden, by: me }))}>{score ? "Score again" : "Score"}</button>}
          </div>
        </header>
        {cmdOpen && <Commands extractionCmds={extraction?.commands ?? []} scoreCmds={(view?.eval.commands ?? []).filter((c) => b === "verified" || c.includes(`/baseline/${view?.kind}`))} onClose={() => setCmdOpen(false)} />}

        {!score && extraction && (
          <div className="evx-cta">
            <p>{extraction.title} hasn't been scored against {bl.name.toLowerCase()}{b !== "verified" ? ` (${v})` : ""} yet.</p>
            {idx.allow_runs
              ? <button className="btn primary" disabled={running} onClick={() => start(api.startScore(cat, { xtra_run: extraction.id, golden, by: me }))}>Score it</button>
              : <p className="muted">Start the Studio with <span className="mono">--allow-runs</span>, or run <span className="mono">golden-datasets eval run --xtra-run {extraction.id} --golden {golden}</span>.</p>}
          </div>
        )}
        {score && view && (
          <ScoreBody view={view} binfo={binfo} prop={prop} outcome={outcome} group={group} gv={gv} offset={offset}
            rowKey={rowKey} nav={nav} />
        )}
      </section>

      {row && <PageSide row={row} catalog={cat} ruleset={catalog.ruleset_version} onClose={() => nav({ row: null }, false)} />}
      {newOpen && <NewExtraction idx={idx} version={v} onClose={() => setNewOpen(false)}
        onStart={(body) => { setNewOpen(false); start(api.startExtraction(cat, { ...body, by: me })); }} />}
    </div>
  );
}

// --- the score ----------------------------------------------------------------------------------------------
function ScoreBody({ view, binfo, prop, outcome, group, gv, offset, rowKey, nav }: {
  view: ScoreView; binfo: BaselineInfo | null | undefined; prop: string | null; outcome: ScoreOutcome | null;
  group: string | null; gv: string | null; offset: number; rowKey: string | null;
  nav: (ch: Record<string, string | number | null>, keepRow?: boolean) => void;
}) {
  const t = view.total;
  const leftOut = view.eval.summary[view.kind]?.left_out ?? [];
  const missingProps = (binfo?.properties ?? []).filter((p) => !view.properties.some((q) => q.property === p.property));
  return (
    <>
      <div className="evx-rate">
        <b>{pct(t.match_rate)}</b>
        <span>match rate</span>
        <span className="muted">{fmt(t.match)} of {fmt(t.fields)} fields match · {fmt(t.records)} records</span>
      </div>
      {leftOut.length > 0 && <p className="muted small">{leftOut.length} pages left out: {leftOut[0].why}.</p>}

      <table className="evx-props-t">
        <tbody>
          <PropRow name="All properties" c={t} on={!prop} onClick={() => nav({ p: null, off: null })} />
          {view.properties.map((p) => <PropRow key={p.property} name={p.property} c={p} on={prop === p.property}
            onClick={() => nav({ p: prop === p.property ? null : p.property, off: null })} />)}
          {missingProps.map((p) => <tr key={p.property} className="off"><td>{p.property}</td><td colSpan={3} className="muted">not in this group</td></tr>)}
        </tbody>
      </table>
      <Legend />

      <div className="evx-controls">
        <div className="seg">
          <button className={!outcome ? "on" : ""} onClick={() => nav({ o: null, off: null })}>All <span>{fmt(view.outcomes.fields)}</span></button>
          {OUTCOMES.map((o) => (
            <button key={o} className={outcome === o ? "on" : ""} disabled={!view.outcomes[o]} onClick={() => nav({ o: outcome === o ? null : o, off: null })}>
              <i className={`sw o-${o}`} />{o} <span>{fmt(view.outcomes[o])}</span>
            </button>
          ))}
        </div>
        <label className="evx-group">Group by
          <select value={group ?? ""} onChange={(e) => nav({ g: e.target.value || null, gv: null, off: null })}>
            <option value="">nothing</option>
            {view.group_choices.map((g) => <option key={g.id} value={g.id}>{g.label}</option>)}
          </select>
        </label>
      </div>

      {group && (
        <div className="evx-groups">
          {gv !== null && <button className="evx-chip" onClick={() => nav({ gv: null, off: null })}>{view.group_choices.find((g) => g.id === group)?.label}: {gv} ✕</button>}
          {gv === null && <p className="muted small">Worst first: the share of fields that don't match{prop ? ` (${prop})` : ""}. Click a group to see its rows.</p>}
          {gv === null && view.groups.slice(0, 12).map((g) => (
            <button key={g.value} className="evx-grow" onClick={() => nav({ gv: g.value, off: null })}>
              <span className="evx-grow-n">{g.value}</span>
              <Bar c={g} />
              <span className="evx-grow-r">{pct(1 - (rate(g) ?? 0))} don't match <span className="muted">of {fmt(g.fields)}</span></span>
            </button>
          ))}
          {gv === null && view.groups.length > 12 && <p className="muted small">and {view.groups.length - 12} more groups</p>}
        </div>
      )}

      <div className="evx-rows">
        {view.rows.items.map((r) => (
          <button key={r.key} className={`evx-row ${r.key === rowKey ? "on" : ""}`} onClick={() => nav({ row: r.key }, true)}>
            <i className={`sw o-${r._o}`} title={r._o} />
            <span className="evx-row-c">{r.golden_record_id ?? r.page_stem}</span>
            <span className="evx-row-p">{r.property}</span>
            <span className="evx-row-v">{r._o === "missing" ? <span className="muted">nothing extracted · baseline: {r.golden_value}</span>
              : r._o === "match" ? r.golden_value : r.xtra_value}</span>
            <span className="evx-row-s">{r._o === "partial" || r._o === "wrong" ? r.similarity?.toFixed(2) : ""}</span>
          </button>
        ))}
        {!view.rows.items.length && <p className="muted">No fields here.</p>}
      </div>
      {view.rows.total > view.rows.page && (
        <div className="evx-pager">
          <button className="btn sm" disabled={offset === 0} onClick={() => nav({ off: Math.max(0, offset - view.rows.page) || null })}>Previous</button>
          <span className="muted">{fmt(offset + 1)}–{fmt(Math.min(view.rows.total, offset + view.rows.page))} of {fmt(view.rows.total)}, worst first</span>
          <button className="btn sm" disabled={offset + view.rows.page >= view.rows.total} onClick={() => nav({ off: offset + view.rows.page })}>Next</button>
        </div>
      )}
    </>
  );
}

function PropRow({ name, c, on, onClick }: { name: string; c: OutcomeCounts; on: boolean; onClick: () => void }) {
  return (
    <tr className={on ? "on" : ""} onClick={onClick}>
      <td>{name}</td>
      <td className="evx-barcell"><Bar c={c} /></td>
      <td className="r"><b>{pct(rate(c))}</b></td>
      <td className="r muted">{fmt(c.fields)}</td>
    </tr>
  );
}

function Bar({ c }: { c: OutcomeCounts }) {
  return (
    <span className="evx-bar" role="img" aria-label={OUTCOMES.map((o) => `${o} ${c[o]}`).join(", ")}>
      {OUTCOMES.filter((o) => c[o] > 0).map((o) => (
        <i key={o} className={`o-${o}`} style={{ flexGrow: c[o] }} title={`${OUTCOME_LABEL[o]}: ${fmt(c[o])} of ${fmt(c.fields)}`} />
      ))}
    </span>
  );
}

function Legend() {
  return <div className="evx-legend">{OUTCOMES.map((o) => <span key={o}><i className={`sw o-${o}`} />{OUTCOME_LABEL[o]}</span>)}</div>;
}

// --- the page of the selected row ---------------------------------------------------------------------------
function PageSide({ row, catalog, ruleset, onClose }: { row: ScoreRow; catalog: string; ruleset: number; onClose: () => void }) {
  const highlights = useMemo<Highlight[]>(() => {
    const h: Highlight[] = [];
    if (row.golden_css_path) h.push({ id: "baseline", kind: "expected", cssPath: row.golden_css_path,
      charStart: row.golden_char_start, charEnd: row.golden_char_end, text: row.golden_value });
    if (row.xtra_value && row._o !== "match") {
      h.push({ id: "extracted", kind: "mark", cssPath: "body", text: row.xtra_value });
      if (row.xtra_value.length > 90) h.push({ id: "extracted-start", kind: "mark", cssPath: "body", text: row.xtra_value.slice(0, 80) });
    }
    return h;
  }, [row]);
  const parts = useMemo(() => (row._o === "partial" || row._o === "wrong") ? wordDiff(row.golden_value ?? "", row.xtra_value ?? "") : null, [row]);
  return (
    <section className="evx-page">
      <header className="evx-page-h">
        <div>
          <b>{row.golden_record_id}</b> · {row.property}
          <span className="evx-out"><i className={`sw o-${row._o}`} />{row._o}{row.similarity !== null && row._o !== "match" ? ` · ${row.similarity.toFixed(2)}` : ""}</span>
        </div>
        <a href={href(catalog, "records", row.golden_record_id)} className="muted small">Open in Records →</a>
        <button className="evx-icon" onClick={onClose} title="Close">✕</button>
      </header>
      <div className="evx-vals">
        <div><span className="evx-k"><i className="sw base" />Baseline value</span><div className="evx-v">{row.golden_value}</div></div>
        <div><span className="evx-k"><i className="sw xtra" />Extracted value</span>
          <div className="evx-v">{row._o === "missing" ? <span className="muted">nothing extracted</span>
            : parts ? parts.map((p, i) => p.op === "del" ? <del key={i}>{p.text}</del> : p.op === "ins" ? <ins key={i}>{p.text}</ins> : <span key={i}>{p.text}</span>)
            : row.xtra_value}</div>
          {parts && <div className="muted small">struck: in the baseline, not extracted · green: extracted, not in the baseline</div>}</div>
      </div>
      <div className="evx-pane">
        <PagePane catalog={catalog} tabs={[{ stem: row.page_stem, url: row.source_url ?? "", title: row.golden_record_id ?? row.page_stem }]}
          activeStem={row.page_stem} onActivate={() => {}} highlights={highlights} focusId={row.golden_css_path ? "baseline" : "extracted"}
          ruleset={ruleset}
          legend={<span className="evx-pane-legend"><span><i className="sw base" />baseline value{row.golden_css_path ? "" : " (no location: a constant or the URL)"}</span>
            {row.xtra_value && row._o !== "match" && <span><i className="sw xtra" />extracted value, where its text is on the page</span>}</span>} />
      </div>
    </section>
  );
}

// --- runs ---------------------------------------------------------------------------------------------------
function JobBar({ job, onCancel, onClose }: { job: EvalJob; onCancel: () => void; onClose: () => void }) {
  const [log, setLog] = useState(false);
  return (
    <div className={`evx-job ${job.status}`}>
      <span className={`evx-dot ${job.status}`} />
      <b>{job.label}</b>
      <span className="evx-job-l">{job.status === "running" ? job.log[job.log.length - 1] ?? "starting…" : job.error ?? job.status}</span>
      <button className="evx-link" onClick={() => setLog(!log)}>{log ? "hide log" : "log"}</button>
      {job.status === "running" ? <button className="evx-link" onClick={onCancel}>cancel</button> : <button className="evx-link" onClick={onClose}>✕</button>}
      {log && <pre className="evx-log">{job.log.join("\n")}</pre>}
    </div>
  );
}

function Commands({ extractionCmds, scoreCmds, onClose }: { extractionCmds: string[]; scoreCmds: string[]; onClose: () => void }) {
  const all = [...extractionCmds, ...scoreCmds].map(multiline);
  const azure = all.some((c) => c.includes("azure://"));
  const text = [...(azure ? ["az login", 'export AZURE_STORAGE_CONNECTION_STRING="$(az storage account show-connection-string \\\n  -n ceteststorage --query connectionString -o tsv)"'] : []), ...all].join("\n\n");
  return (
    <div className="evx-cmds">
      <div className="evx-cmds-h"><Ico name="terminal" /> Run it yourself
        <span className="grow" />
        <button className="btn sm" onClick={() => navigator.clipboard.writeText(text).then(() => toast("Copied"))}><Ico name="copy" />Copy</button>
        <button className="evx-icon" onClick={onClose} title="Close">✕</button>
      </div>
      <pre>{text || "# nothing to show: this extraction was copied from xtra-cli-output"}</pre>
    </div>
  );
}

function NewExtraction({ idx, version, onClose, onStart }: {
  idx: EvalsIndex; version: string; onClose: () => void;
  onStart: (b: { source: "extract" | "latest"; ref?: string; scope?: "sample" | "all"; then_score?: string | null }) => void;
}) {
  const o = idx.extract_options;
  const [source, setSource] = useState<"extract" | "latest">("extract");
  const [ref, setRef] = useState(idx.default_ref);
  const [scope, setScope] = useState<"sample" | "all">("sample");
  const [then, setThen] = useState<string>(version);
  return (
    <div className="evx-modal-bg" onClick={onClose}>
      <div className="evx-modal" onClick={(e) => e.stopPropagation()}>
        <h2>New extraction</h2>
        <label className={`evx-opt ${source === "extract" ? "on" : ""}`}>
          <input type="radio" checked={source === "extract"} onChange={() => setSource("extract")} />
          <div>
            <b>Run xtra-cli extract</b>
            <p className="muted">Runs <span className="mono">xtra catalog extract --with-template</span> on the saved pages, into the Studio's own folder.</p>
            {source === "extract" && (
              <div className="evx-opt-body">
                <label>Code <input className="mono" value={ref} onChange={(e) => setRef(e.target.value)} size={32} /> <span className="muted small">branch, tag or commit</span></label>
                <div className="evx-scope">
                  <label><input type="radio" checked={scope === "sample"} onChange={() => setScope("sample")} /> Review sample: {o.sample_pages ?? "the"} pages discovery picked for review <span className="muted">· about 10 s</span></label>
                  <label><input type="radio" checked={scope === "all"} onChange={() => setScope("all")} /> All course pages{o.course_pages ? `: ${fmt(o.course_pages)} pages` : ""} <span className="muted">· about 8 min</span></label>
                </div>
              </div>
            )}
          </div>
        </label>
        <label className={`evx-opt ${source === "latest" ? "on" : ""}`}>
          <input type="radio" checked={source === "latest"} onChange={() => setSource("latest")} disabled={!o.latest} />
          <div>
            <b>Use xtra-cli's latest extraction</b>
            <p className="muted">{o.latest
              ? <>Copies the <span className="mono">records/</span> xtra-cli last wrote for this crawl: {fmt(o.latest.records)} records from {o.latest.scope === "sample" ? "the review sample" : "all course pages"}. Nothing is extracted.</>
              : "xtra-cli hasn't written records/ for this crawl."}</p>
          </div>
        </label>
        <label className="evx-then">Then score it against
          <select value={then} onChange={(e) => setThen(e.target.value)}>
            <option value="">nothing yet</option>
            {idx.versions.map((g) => <option key={g.id} value={g.id}>Full catalog and hand-checked · {g.id}</option>)}
            <option value="verified">Verified container</option>
          </select>
        </label>
        <div className="evx-modal-f">
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" onClick={() => onStart({ source, ref, scope, then_score: then || null })}>Start</button>
        </div>
      </div>
    </div>
  );
}
