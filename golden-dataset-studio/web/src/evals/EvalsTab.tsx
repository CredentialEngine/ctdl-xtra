// Evals (docs/qrspi/evals): xtra's extract outputs scored against a golden dataset, with xtra's own scorer.
// Left: the extract outputs the Studio has seen, the golden dataset, and the basis (human-reviewed or rule-matched).
// Middle: one score — its exact-match rate, the columns, and the values, narrowed by a column and an outcome. Right:
// the saved page of the selected value, with the golden value at its recorded location and the extracted value where
// its text is found. (Step 4 of the plan replaces this with the spec's §6.3 design.)
//
// URL: #/c/<catalog>/evals?x=<output>&g=<golden>&b=human|rule&col=<column>&o=<outcome>&off=<offset>&row=<row key>
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { ExtractOutputs, OutcomeCounts, ScoreBasis, ScoreDoc, ScoreOutcome, ScoreRow, ScoreValues } from "../api/types";
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
const BASES: { id: ScoreBasis; name: string }[] = [{ id: "human", name: "Human-reviewed" }, { id: "rule", name: "Rule-matched" }];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const when = (iso: string | null | undefined) => {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};
const pct = (x: number | null | undefined) => (x === null || x === undefined ? "–" : `${(x * 100).toFixed(1)}%`);
const rate = (c: OutcomeCounts) => (c.values ? c.match / c.values : null);

export default function EvalsTab({ catalog, route }: TabProps) {
  const me = useReviewer();
  const cat = catalog.short;
  const [idx, setIdx] = useState<ExtractOutputs | null>(null);
  const [doc, setDoc] = useState<ScoreDoc | null>(null);
  const [view, setView] = useState<ScoreValues | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cmdOpen, setCmdOpen] = useState(false);

  const P = route.params;
  const x = P.get("x") ?? idx?.outputs[0]?.id ?? null;
  const output = idx?.outputs.find((o) => o.id === x);
  const goldens = useMemo(() => [...new Set(["human-reviewed", ...(idx?.latest_golden ? [idx.latest_golden] : []),
    ...(output?.scores.map((s) => s.golden) ?? [])])], [idx, output]);
  const g = P.get("g") ?? idx?.latest_golden ?? "human-reviewed";
  const b = (P.get("b") as ScoreBasis | null) ?? "human";
  const col = P.get("col"), outcome = P.get("o") as ScoreOutcome | null;
  const offset = +(P.get("off") || 0), rowKey = P.get("row");
  const nav = useCallback((ch: Record<string, string | number | null>, keepRow = false) => {
    const cur: Record<string, string | number | null> = { x, g, b, col, o: outcome, off: offset || null, row: keepRow ? rowKey : null };
    go(href(cat, "evals", null, { ...cur, ...ch }), true);
  }, [cat, x, g, b, col, outcome, offset, rowKey]);

  const loadIndex = useCallback(() => api.extractOutputs(cat).then(setIdx, (e) => setError(String(e))), [cat]);
  useEffect(() => { loadIndex(); }, [loadIndex]);

  const brief = output?.scores.find((s) => s.golden === g);
  useEffect(() => {
    if (!brief) { setDoc(null); return; }
    let live = true;
    api.scoreDoc(cat, brief.id).then((d) => live && setDoc(d), (e) => live && setError(String(e)));
    return () => { live = false; };
  }, [cat, brief]);

  // a running score: poll until it's done, then reload the list
  useEffect(() => {
    if (!doc || doc.status !== "running") return;
    const t = setInterval(() => api.scoreDoc(cat, doc.id).then((d) => {
      if (d.status === "running") return;
      setDoc(d);
      loadIndex();
      toast(d.status === "done" ? "Scored" : `${d.id}: ${d.status}${d.error ? ` (${d.error})` : ""}`);
    }), 1500);
    return () => clearInterval(t);
  }, [cat, doc, loadIndex]);

  useEffect(() => {
    if (!doc || doc.status !== "done" || !doc.results[b]) { setView(null); return; }
    let live = true;
    api.scoreValues(cat, doc.id, { basis: b, column: col, outcome, offset })
      .then((r) => live && setView(r), (e) => live && setError(String(e)));
    return () => { live = false; };
  }, [cat, doc, b, col, outcome, offset]);

  useKeyHints(<span><span className="mono">golden-datasets score</span> does the same from the CLI</span>, []);

  if (error) return <div className="doc"><div className="doc-in"><p className="muted">{error}</p></div></div>;
  if (!idx) return <div className="evx" />;
  const row = view?.rows.items.find((r) => r.key === rowKey) ?? null;
  const score = async () => {
    if (!output) return;
    try { setDoc(await api.startScore(cat, { golden: g, output: output.id, by: me })); loadIndex(); } catch (e) { toast(String(e)); }
  };

  return (
    <div className={`evx ${row ? "with-page" : ""}`}>
      <aside className="evx-nav">
        <div className="evx-sec-h">Extract outputs</div>
        <p className="evx-def">What <span className="mono">xtra catalog extract</span> wrote for {catalog.name}. The Studio keeps a copy of each one it sees.</p>
        {idx.outputs.map((o) => (
          <button key={o.id} className={`evx-item ${o.id === x ? "on" : ""}`} onClick={() => nav({ x: o.id, off: null })}>
            <span className="evx-item-t">{when(o.last_modified)}{o === idx.outputs[0] ? " (latest)" : ""}</span>
            <span className="evx-item-d">{fmt(o.records)} records{o.records_mismatch ? ` · the report says ${fmt(o.records_written)}` : ""} · {o.scores.length} scores</span>
          </button>
        ))}
        {!idx.outputs.length && <p className="evx-empty">{idx.error ?? "None yet."}</p>}

        <div className="evx-sec-h">Golden dataset</div>
        <label className="evx-ver">Scored against
          <select value={g} onChange={(e) => nav({ g: e.target.value, col: null, o: null, off: null })}>
            {goldens.map((id) => <option key={id} value={id}>{id === "human-reviewed" ? "Human-reviewed values" : id.replace("ruleset-v", "ruleset v")}</option>)}
          </select>
        </label>
        {BASES.map((z) => (
          <button key={z.id} className={`evx-item ${z.id === b ? "on" : ""}`} onClick={() => nav({ b: z.id, col: null, o: null, off: null })}>
            <span className="evx-item-t">{z.name}</span>
            <span className="evx-item-d">{doc?.golden.values ? `${fmt(doc.golden.values[z.id])} values` : ""}</span>
          </button>
        ))}
      </aside>

      <section className="evx-main">
        <header className="evx-head">
          <div className="evx-title">
            <span>{output ? `Extract output of ${when(output.last_modified)}` : "No extract output"}</span>
            <span className="evx-arrow">vs</span>
            <span>{g === "human-reviewed" ? `Human-reviewed values${doc ? ` · as of ${when(doc.golden.as_of)}` : ""}` : g}</span>
            {doc?.golden.kind === "draft" && <span className="evx-tag" title="An extraction that isn't published">draft</span>}
          </div>
          <div className="evx-actions">
            {doc && <button className="evx-icon" onClick={() => setCmdOpen(!cmdOpen)} title="Run it yourself"><Ico name="terminal" /></button>}
          </div>
        </header>
        {cmdOpen && doc && <Commands doc={doc} onClose={() => setCmdOpen(false)} />}

        {output && (!doc || doc.status === "failed" || doc.status === "interrupted") && (
          <div className="evx-cta">
            <p>{doc ? <><b>{doc.id} {doc.status}.</b> {doc.error}</> : <b>Not scored yet.</b>} Scoring runs <span className="mono">xtra score extraction match</span> on
              the human-reviewed values and on every rule-matched value. It takes a few seconds.</p>
            <button className="btn primary" disabled={!!idx.running} onClick={score}>Score</button>
          </div>
        )}
        {doc?.status === "running" && <p className="muted">Scoring ({doc.id})…</p>}
        {doc?.status === "done" && doc.slot_names && <p className="muted small">{doc.error}</p>}
        {doc?.status === "done" && !doc.results[b] && <p className="muted">No {b === "human" ? "human-reviewed" : "rule-matched"} values to score in {g}.</p>}
        {doc?.status === "done" && view && <ScoreBody view={view} col={col} outcome={outcome} offset={offset} rowKey={rowKey} nav={nav} />}
      </section>

      {row && <PageSide row={row} catalog={cat} ruleset={catalog.ruleset_version} onClose={() => nav({ row: null }, false)} />}
    </div>
  );
}

// --- the score ----------------------------------------------------------------------------------------------
function ScoreBody({ view, col, outcome, offset, rowKey, nav }: {
  view: ScoreValues; col: string | null; outcome: ScoreOutcome | null; offset: number; rowKey: string | null;
  nav: (ch: Record<string, string | number | null>, keepRow?: boolean) => void;
}) {
  const t = view.total;
  const leftOut = view.result?.left_out ?? [];
  const implied = Object.keys(view.result?.implied ?? {});
  return (
    <>
      <div className="evx-rate">
        <b>{pct(view.result?.exact_match_rate)}</b>
        <span>exact matches</span>
        <span className="muted">{fmt(t.match)} of {fmt(t.values)} values</span>
      </div>
      {leftOut.length > 0 && <p className="muted small">{leftOut.length} pages left out: {leftOut[0].why}.</p>}

      <table className="evx-props-t">
        <tbody>
          <PropRow name="All columns" c={t} on={!col} onClick={() => nav({ col: null, off: null })} />
          {view.columns.map((p) => <PropRow key={p.column} name={p.column} c={p} on={col === p.column}
            onClick={() => nav({ col: col === p.column ? null : p.column, off: null })} />)}
          {implied.map((p) => <tr key={p} className="off"><td>{p}</td><td colSpan={3} className="muted">not scored: implied, not read from the page</td></tr>)}
        </tbody>
      </table>
      <Legend />

      <div className="evx-controls">
        <div className="seg">
          <button className={!outcome ? "on" : ""} onClick={() => nav({ o: null, off: null })}>All <span>{fmt(view.outcomes.values)}</span></button>
          {OUTCOMES.map((o) => (
            <button key={o} className={outcome === o ? "on" : ""} disabled={!view.outcomes[o]} onClick={() => nav({ o: outcome === o ? null : o, off: null })}>
              <i className={`sw o-${o}`} />{o} <span>{fmt(view.outcomes[o])}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="evx-rows">
        {view.rows.items.map((r) => (
          <button key={r.key} className={`evx-row ${r.key === rowKey ? "on" : ""}`} onClick={() => nav({ row: r.key }, true)}>
            <i className={`sw o-${r.outcome}`} title={r.outcome} />
            <span className="evx-row-c">{r.golden_record_id ?? r.page_stem}</span>
            <span className="evx-row-p">{r.column}</span>
            <span className="evx-row-v">{r.outcome === "missing" ? <span className="muted">nothing extracted · golden: {r.golden_value}</span>
              : r.outcome === "match" ? r.golden_value : r.extracted_value}</span>
            <span className="evx-row-s">{r.outcome === "partial" || r.outcome === "wrong" ? r.similarity?.toFixed(2) : ""}</span>
          </button>
        ))}
        {!view.rows.items.length && <p className="muted">No values here.</p>}
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
      <td className="r muted">{fmt(c.values)}</td>
    </tr>
  );
}

function Bar({ c }: { c: OutcomeCounts }) {
  return (
    <span className="evx-bar" role="img" aria-label={OUTCOMES.map((o) => `${o} ${c[o]}`).join(", ")}>
      {OUTCOMES.filter((o) => c[o] > 0).map((o) => (
        <i key={o} className={`o-${o}`} style={{ flexGrow: c[o] }} title={`${OUTCOME_LABEL[o]}: ${fmt(c[o])} of ${fmt(c.values)}`} />
      ))}
    </span>
  );
}

function Legend() {
  return <div className="evx-legend">{OUTCOMES.map((o) => <span key={o}><i className={`sw o-${o}`} />{OUTCOME_LABEL[o]}</span>)}</div>;
}

// --- the page of the selected value -------------------------------------------------------------------------
function PageSide({ row, catalog, ruleset, onClose }: { row: ScoreRow; catalog: string; ruleset: number; onClose: () => void }) {
  const highlights = useMemo<Highlight[]>(() => {
    const h: Highlight[] = [];
    if (row.golden_css_path) h.push({ id: "golden", kind: "expected", cssPath: row.golden_css_path,
      charStart: row.golden_char_start, charEnd: row.golden_char_end, text: row.golden_value });
    if (row.extracted_value && row.outcome !== "match") {
      h.push({ id: "extracted", kind: "mark", cssPath: "body", text: row.extracted_value });
      if (row.extracted_value.length > 90) h.push({ id: "extracted-start", kind: "mark", cssPath: "body", text: row.extracted_value.slice(0, 80) });
    }
    return h;
  }, [row]);
  const parts = useMemo(() => (row.outcome === "partial" || row.outcome === "wrong") ? wordDiff(row.golden_value ?? "", row.extracted_value ?? "") : null, [row]);
  return (
    <section className="evx-page">
      <header className="evx-page-h">
        <div>
          <b>{row.golden_record_id}</b> · {row.column}
          <span className="evx-out"><i className={`sw o-${row.outcome}`} />{row.outcome}{row.similarity !== null && row.outcome !== "match" ? ` · ${row.similarity.toFixed(2)}` : ""}</span>
        </div>
        <a href={href(catalog, "records", row.golden_record_id)} className="muted small">Open in Records →</a>
        <button className="evx-icon" onClick={onClose} title="Close">✕</button>
      </header>
      <div className="evx-vals">
        <div><span className="evx-k"><i className="sw base" />Golden value</span><div className="evx-v">{row.golden_value}</div></div>
        <div><span className="evx-k"><i className="sw xtra" />Extracted value</span>
          <div className="evx-v">{row.outcome === "missing" ? <span className="muted">nothing extracted</span>
            : parts ? parts.map((p, i) => p.op === "del" ? <del key={i}>{p.text}</del> : p.op === "ins" ? <ins key={i}>{p.text}</ins> : <span key={i}>{p.text}</span>)
            : row.extracted_value}</div>
          {parts && <div className="muted small">struck: in the golden dataset, not extracted · green: extracted, not in the golden dataset</div>}</div>
      </div>
      <div className="evx-pane">
        <PagePane catalog={catalog} tabs={[{ stem: row.page_stem, url: row.source_url ?? "", title: row.golden_record_id ?? row.page_stem }]}
          activeStem={row.page_stem} onActivate={() => {}} highlights={highlights} focusId={row.golden_css_path ? "golden" : "extracted"}
          ruleset={ruleset}
          legend={<span className="evx-pane-legend"><span><i className="sw base" />golden value</span>
            {row.extracted_value && row.outcome !== "match" && <span><i className="sw xtra" />extracted value, where its text is on the page</span>}</span>} />
      </div>
    </section>
  );
}

function Commands({ doc, onClose }: { doc: ScoreDoc; onClose: () => void }) {
  const all = doc.commands.map(multiline);
  const azure = all.some((c) => c.includes("azure://"));
  const text = [...(azure ? ["az login", 'export AZURE_STORAGE_CONNECTION_STRING="$(az storage account show-connection-string \\\n  -n ceteststorage --query connectionString -o tsv)"'] : []), ...all].join("\n\n");
  return (
    <div className="evx-cmds">
      <div className="evx-cmds-h"><Ico name="terminal" /> Run it yourself (rule-matched values)
        <span className="grow" />
        <button className="evx-icon" onClick={onClose} title="Close">✕</button>
      </div>
      <div className="evx-code">
        <pre>{text || "# a draft has no files for xtra score to read"}</pre>
        {text && <button className="evx-copy" onClick={() => navigator.clipboard.writeText(text).then(() => toast("Copied"))} title="Copy"><Ico name="copy" />Copy</button>}
      </div>
    </div>
  );
}
