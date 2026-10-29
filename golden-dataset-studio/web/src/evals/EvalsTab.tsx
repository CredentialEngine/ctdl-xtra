// Evals (docs/qrspi/evals/03-spec.md §6.3–6.4): how closely xtra's extract outputs match the golden dataset, scored
// by xtra's own scorer. The title is the comparison ([golden side] vs `xtra catalog extract` outputs over time), with
// the slim switch "scored against Human-reviewed | Rule-matched" at its right. Under it, one bar per extract output
// the Studio has seen; clicking one picks it, and a dashed bar (not scored against this golden side yet) holds the only
// Score button. Then the chosen pair as two chips, the exact matches, one bar per column, the outcome filter, Group
// by and the values. A value opens the shared diff (Split / Unified) with a note box and the saved page beside it.
//
// URL: #/c/<catalog>/evals?b=human|rule&g=<golden>&x=<output>&col=<column>&subj=<subject>&o=<outcome>&grp=column|subject
//      &off=<offset>&row=<row key>
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { api } from "../api/client";
import type { ExtractOutputs, GoldenChoice, MatchRow, OutcomeCounts, ScoreBasis, ScoreBrief, ScoreDoc, ScoreOutcome, ScoreRow,
  ScoreValues } from "../api/types";
import type { CapturedSelection } from "../pagepane";
import { addCapture, newDraft, verdictEvent, type Draft } from "../rules/logic";
import { useReviewer } from "../shell/reviewer";
import { go, href } from "../shell/router";
import type { TabProps } from "../shell/tabProps";
import { fmt, Ico, toast, useKeyHints } from "../shell/ui";
import { fmtDay, fmtDayTime } from "../valuediff/diff";
import { comparedChip, DiffModeSwitch, MarkedWrong, NoteActions, RowNotes, useDiffMode, ValueDiff, ValuePage, WrongFlow } from "../valuediff/ValueDiff";
import { multiline } from "./commands";
import "./evals.css";

/** The ⓘ beside "scored against": which values each choice scores. */
export const BASIS_TIP = <span className="evx-tip-basis">
  <b>Rule-matched</b> scores every value in the golden dataset: the values the rules matched and the human-reviewed ones.
  <br /><b>Human-reviewed</b> scores only the values an expert reviewed.</span>;

export const OUTCOMES: ScoreOutcome[] = ["missing", "wrong", "partial", "match"];
/** Each outcome's rule (xtra's scorer, Evals spec §2). */
export const OUTCOME_RULE: Record<ScoreOutcome, string> = {
  match: "identical", partial: "similarity ≥ 0.8", wrong: "similarity < 0.8", missing: "nothing extracted",
};
export const SIMILARITY = "Text is compared ignoring case and spacing, and again without punctuation, keeping the higher score. Numbers either match or are wrong.";
const HUMAN = "human-reviewed";
type Output = ExtractOutputs["outputs"][number];
type Counts = Record<ScoreOutcome, number>;

const rateOf = (c: Counts | null | undefined) => {
  const n = c ? OUTCOMES.reduce((t, o) => t + c[o], 0) : 0;
  return c && n ? c.match / n : null;
};
const pct = (x: number | null | undefined) => (x === null || x === undefined ? "–" : `${Math.round(x * 100)}%`);
export const goldenName = (id: string) =>
  id === HUMAN ? "human-reviewed" : /^ruleset-v\d+$/.test(id) ? id.replace("ruleset-v", "ruleset v") : `draft ${id}`;

/** The score that shows an output against the chosen golden side: with Human-reviewed, the newest score of the
 * human-reviewed values (`human-reviewed`, or the latest version, whose human-reviewed tree each review rewrites);
 * with Rule-matched, the newest of the chosen golden dataset. A done score first, then a running one, then the rest. */
export function scoreFor(o: Output, basis: ScoreBasis, golden: string, latest: string | null): ScoreBrief | undefined {
  const mine = o.scores.filter((s) => basis === "human" ? s.golden === HUMAN || s.golden === latest : s.golden === golden)
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
  const outcomes = (s: ScoreBrief) => (basis === "human" ? s.human_outcomes : s.rule_outcomes);
  return mine.find((s) => s.status === "done" && outcomes(s)) ?? mine.find((s) => s.status === "running") ?? mine[0];
}

export default function EvalsTab({ catalog, route }: TabProps) {
  const me = useReviewer();
  const cat = catalog.short;
  const [idx, setIdx] = useState<ExtractOutputs | null>(null);
  const [doc, setDoc] = useState<ScoreDoc | null>(null);
  const [view, setView] = useState<ScoreValues | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState(false);

  const P = route.params;
  const basis: ScoreBasis = P.get("b") === "rule" ? "rule" : "human";
  const latestGolden = idx?.latest_golden ?? null;
  const g = basis === "human" ? HUMAN : P.get("g") ?? latestGolden ?? idx?.goldens[0]?.id ?? "";
  const x = P.get("x") ?? idx?.outputs[0]?.id ?? null;
  const col = P.get("col"), subj = P.get("subj"), outcome = P.get("o") as ScoreOutcome | null;
  const grp = P.get("grp"), offset = +(P.get("off") || 0), rowKey = P.get("row");
  const nav = useCallback((ch: Record<string, string | number | null>, keepRow = false) => {
    const cur: Record<string, string | number | null> = { b: basis === "rule" ? "rule" : null, g: P.get("g"), x: P.get("x"), col, subj,
      o: outcome, grp, off: offset || null, row: keepRow ? rowKey : null };
    go(href(cat, "evals", null, { ...cur, ...ch }), true);
  }, [cat, basis, P, col, subj, outcome, grp, offset, rowKey]);

  const loadIndex = useCallback(() => api.extractOutputs(cat).then(setIdx, (e) => setError(String(e))), [cat]);
  useEffect(() => { void loadIndex(); }, [loadIndex]);

  const output = idx?.outputs.find((o) => o.id === x);
  const brief = output ? scoreFor(output, basis, g, latestGolden) : undefined;
  const running = !!idx && (!!idx.running || idx.outputs.some((o) => o.scores.some((s) => s.status === "running")));
  // a score running: reload the list until it's done
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => { void loadIndex(); }, 1500);
    return () => clearInterval(t);
  }, [running, loadIndex]);

  const sid = brief?.status === "done" ? brief.id : null;
  useEffect(() => {
    if (!sid) { setDoc(null); return; }
    let live = true;
    api.scoreDoc(cat, sid).then((d) => live && setDoc(d), (e) => live && setError(String(e)));
    return () => { live = false; };
  }, [cat, sid]);

  useEffect(() => {
    if (!doc || doc.id !== sid || !doc.results[basis]) { setView(null); return; }
    let live = true;
    api.scoreValues(cat, doc.id, { basis, column: col, subject: subj, outcome, group: grp, offset })
      .then((r) => live && setView(r), (e) => live && setError(String(e)));
    return () => { live = false; };
  }, [cat, doc, sid, basis, col, subj, outcome, grp, offset]);

  useKeyHints(<span><span className="mono">golden-datasets score</span> does the same from the CLI</span>, []);

  const startScore = useCallback(async (o: Output) => {
    try { await api.startScore(cat, { golden: g, output: o.id, by: me }); await loadIndex(); } catch (e) { toast(String(e)); }
  }, [cat, g, me, loadIndex]);

  if (error) return <div className="doc"><div className="doc-in"><p className="muted">{error}</p></div></div>;
  if (!idx) return <div className="evx" />;
  const row = view?.rows.items.find((r) => r.key === rowKey) ?? null;
  const outputs = [...idx.outputs].reverse();  // oldest first, left to right
  const latestOutput = idx.outputs[0]?.id;
  const result = doc?.results[basis] ?? null;

  return (
    <div className={`evx${row ? " with-row" : ""}`}>
      <section className="evx-main">
        <header className="evx-title">
          {basis === "human"
            ? <span className="evx-gchip big">Human-reviewed values<span className="evx-gchip-d"> · as of {fmtDayTime(brief?.golden_as_of) || "now"}</span></span>
            : <GoldenPicker goldens={idx.goldens} value={g} onPick={(id) => nav({ g: id, col: null, subj: null, o: null, off: null })} />}
          <span className="evx-vs">vs</span><code className="evx-cmd">xtra catalog extract</code><span>outputs over time</span>
          {doc && <button className="evx-info" title="Where these come from" aria-label="Where these come from" onClick={() => setInfo(true)}>i</button>}
          <span className="grow" />
          <span className="evx-basis">scored against
            <span className="seg xs" role="group" aria-label="Scored against">
              <button className={basis === "human" ? "on" : ""} onClick={() => nav({ b: null, col: null, subj: null, o: null, off: null })}>Human-reviewed</button>
              <button className={basis === "rule" ? "on" : ""} onClick={() => nav({ b: "rule", col: null, subj: null, o: null, off: null })}>Rule-matched</button>
            </span>
            <Tip width={300} tip={BASIS_TIP}><span className="evx-i" tabIndex={0} aria-label="What each scores">ⓘ</span></Tip>
          </span>
          {row && <DiffModeSwitch />}
        </header>

        {outputs.length ? (
          <div className="evx-chartrow">
            <History outputs={outputs} latest={latestOutput} basis={basis} golden={g} latestGolden={latestGolden} picked={x}
              busy={!!idx.running} onPick={(id) => nav({ x: id === latestOutput ? null : id, off: null })} onScore={startScore} />
            <div className="evx-legend-v">
              {OUTCOMES.map((o) => <OutcomeTip key={o} counts={result?.outcomes ?? null}><span className="evx-k"><i className={`sw o-${o}`} />{o}</span></OutcomeTip>)}
              <span className="faint evx-hint">Click a bar to compare with that extract output. A dashed bar hasn't been scored yet.</span>
            </div>
          </div>
        ) : <p className="muted evx-empty">{idx.error ?? "xtra hasn't written an extract output for this catalog yet."}</p>}

        {output && <>
          <div className="evx-pair">
            <span className="evx-gchip">{basis === "human" ? `human-reviewed · ${fmtDayTime(brief?.golden_as_of) || "now"}` : goldenName(g)}</span>
            {basis === "rule" && idx.goldens.find((z) => z.id === g)?.kind === "draft" && <span className="evx-draft">draft · unpublished</span>}
            <span className="evx-vs">vs</span>
            <span className="evx-xchip"><MiniBar c={(basis === "human" ? brief?.human_outcomes : brief?.rule_outcomes) ?? null} />
              {fmtDayTime(output.last_modified)}{output.id === latestOutput && <span className="muted"> (latest)</span>}</span>
          </div>
          {brief?.slot_names && <p className="evx-flag">This output uses slot names; re-extract with the current xtra-cli.</p>}
          {output.records_mismatch && <p className="evx-flag">The folder has {fmt(output.records)} records; its report says {fmt(output.records_written)} were written (an earlier run's records may be left over).</p>}
          {!brief && <p className="muted">Not scored against {basis === "human" ? "the human-reviewed values" : goldenName(g)} yet: press <b>Score</b> on its bar.</p>}
          {brief && brief.status !== "done" && <p className="muted">{brief.status === "running" ? `Scoring (${brief.id})…`
            : `${brief.id} ${brief.status}${brief.error ? `: ${brief.error}` : ""}. Press Score on its bar to score it again.`}</p>}
          {doc && !result && <p className="muted">No {basis === "human" ? "human-reviewed" : "rule-matched"} values to score in {goldenName(g)}.</p>}
          {doc && result && view && <ScoreBody basis={basis} view={view} col={col} subj={subj} outcome={outcome} grp={grp} offset={offset}
            rowKey={rowKey} nav={nav} />}
        </>}
      </section>

      {row && doc && output && <RowPanel key={`${doc.id}|${row.key}`} row={row} doc={doc} catalog={cat} ruleset={catalog.ruleset_version}
        goldenLabel={basis === "human" ? "human-reviewed values" : `golden dataset ${goldenName(doc.golden.id)}`}
        outputDay={fmtDay(output.last_modified)} idx={idx} me={me} onClose={() => nav({ row: null })} />}
      {info && doc && <InfoModal doc={doc} basis={basis} onClose={() => setInfo(false)} />}
    </div>
  );
}

// --- the golden side ---------------------------------------------------------------------------------------------
/** Rule-matched: a searchable dropdown of golden datasets, the latest first with "(latest)" (older ones with their
 * date); drafts (unpublished extractions) are tucked away under their own heading, never first. */
function GoldenPicker({ goldens, value, onPick }: { goldens: GoldenChoice[]; value: string; onPick: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [drafts, setDrafts] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const off = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", off);
    return () => document.removeEventListener("mousedown", off);
  }, [open]);
  const cur = goldens.find((z) => z.id === value);
  const label = (z: GoldenChoice) => z.kind === "draft" ? `draft ${z.id}` : `ruleset v${z.ruleset_version}`;
  const when = (z: GoldenChoice) => z.kind === "draft" ? `ruleset v${z.ruleset_version}, unpublished`
    : z.latest ? "(latest)" : fmtDayTime(z.published_at);
  const hit = (z: GoldenChoice) => !q || `${label(z)} ${z.id}`.toLowerCase().includes(q.toLowerCase());
  const versions = goldens.filter((z) => z.kind === "version" && hit(z));
  const draftList = goldens.filter((z) => z.kind === "draft" && hit(z));
  const showDrafts = drafts || (!!q && draftList.length > 0) || cur?.kind === "draft";
  const item = (z: GoldenChoice) => (
    <button key={z.id} className={`evx-dd-i${z.id === value ? " on" : ""}${z.kind === "draft" ? " draft" : ""}`}
      onClick={() => { onPick(z.id); setOpen(false); setQ(""); }}>
      <span>{label(z)}</span><span className="muted">{when(z)}</span>
    </button>
  );
  return (
    <span className="evx-dd" ref={box}>
      <button className="evx-gchip big dd" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen(!open)}>
        {cur ? label(cur) : value || "No golden dataset"}
        {cur && <span className="evx-gchip-d"> {cur.kind === "draft" ? "· unpublished" : cur.latest ? "(latest)" : `· ${fmtDayTime(cur.published_at)}`}</span>}
        <Ico name="chevron" className="evx-caret" />
      </button>
      {open && (
        <div className="evx-dd-m" role="listbox">
          <input className="evx-dd-q" placeholder="Find a golden dataset" value={q} autoFocus onChange={(e) => setQ(e.target.value)} />
          {versions.map(item)}
          {!versions.length && !q && <p className="muted evx-dd-none">No golden dataset published yet.</p>}
          {draftList.length > 0 && (showDrafts
            ? <><div className="evx-dd-h">Drafts · unpublished extractions, scored as if published</div>{draftList.map(item)}</>
            : <button className="evx-dd-more" onClick={() => setDrafts(true)}>Drafts ({draftList.length}) <Ico name="chevron-right" /></button>)}
        </div>
      )}
    </span>
  );
}

// --- the history chart -------------------------------------------------------------------------------------------
const CHART_H = 150;

function History({ outputs, latest, basis, golden, latestGolden, picked, busy, onPick, onScore }: {
  outputs: Output[]; latest: string | undefined; basis: ScoreBasis; golden: string; latestGolden: string | null; picked: string | null;
  busy: boolean; onPick: (id: string) => void; onScore: (o: Output) => void;
}) {
  return (
    <div className="evx-hist" data-testid="history">
      {outputs.map((o) => {
        const s = scoreFor(o, basis, golden, latestGolden);
        const c = s?.status === "done" ? (basis === "human" ? s.human_outcomes : s.rule_outcomes) : null;
        const n = c ? OUTCOMES.reduce((t, k) => t + c[k], 0) : 0;
        const on = o.id === picked;
        return (
          <div key={o.id} className={`evx-col${on ? " sel" : ""}`} data-testid="history-bar">
            <span className="evx-pc">{c ? pct(rateOf(c)) : "–"}</span>
            {c && n ? (
              <OutcomeTip counts={c}>
                <button className="evx-stack" style={{ height: CHART_H }} aria-label={`Extract output of ${fmtDay(o.last_modified)}: ${pct(rateOf(c))} exact matches`}
                  onClick={() => onPick(o.id)}>
                  {OUTCOMES.slice().reverse().map((k) => c[k] > 0 && <i key={k} className={`o-${k}`} style={{ height: `${(c[k] / n) * 100}%` }} />)}
                </button>
              </OutcomeTip>
            ) : (
              <div className="evx-empty-bar" style={{ height: CHART_H }} onClick={() => onPick(o.id)}>
                {s?.status === "running" ? <span className="evx-run">Scoring…</span> : <>
                  {s && (s.status === "failed" || s.status === "interrupted") && <span className="evx-bad" title={s.error ?? ""}>{s.status}</span>}
                  {c && !n ? <span className="faint evx-none">no values</span>
                    : <button className="btn sm evx-score" disabled={busy} onClick={(e) => { e.stopPropagation(); onScore(o); }}>Score</button>}
                </>}
              </div>
            )}
            <span className="evx-x">{fmtDay(o.last_modified)}{o.id === latest && <><br />(latest)</>}</span>
          </div>
        );
      })}
    </div>
  );
}

function MiniBar({ c }: { c: Counts | null }) {
  const n = c ? OUTCOMES.reduce((t, k) => t + c[k], 0) : 0;
  return <i className="evx-mini">{c && n ? OUTCOMES.slice().reverse().map((k) => c[k] > 0 && <b key={k} className={`o-${k}`} style={{ height: `${Math.max(1, (c[k] / n) * 14)}px` }} />) : null}</i>;
}

/** A dark tooltip under its children while hovered or focused, fixed to the viewport so a scrolling column never
 * clips it; `delay` (ms) holds it back on hover so passing the pointer over doesn't flash it. */
export function Tip({ tip, width = 340, delay = 0, children }: { tip: ReactNode; width?: number; delay?: number; children: ReactNode }) {
  const [at, setAt] = useState<{ left: number; top: number; maxWidth: number } | null>(null);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const open = (el: HTMLElement) => {
    const r = el.getBoundingClientRect();
    setAt({ left: r.left + r.width / 2, top: r.bottom + 8, maxWidth: Math.min(width, window.innerWidth - 16) });
  };
  const show = (e: { currentTarget: HTMLElement }) => {
    const el = e.currentTarget;
    window.clearTimeout(timer.current);
    if (delay > 0) timer.current = window.setTimeout(() => open(el), delay); else open(el);
  };
  const hide = () => { window.clearTimeout(timer.current); setAt(null); };
  // centred under its children, then kept inside the window
  const place = (el: HTMLSpanElement | null) => {
    if (!el) return;
    const r = el.getBoundingClientRect();
    const left = Math.max(8, Math.min(r.left, window.innerWidth - r.width - 8));
    if (Math.abs(left - r.left) > 0.5) el.style.left = `${parseFloat(el.style.left) + left - r.left}px`;
  };
  return (
    <span className="evx-tipw" onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}>
      {children}
      {at && createPortal(<span ref={place} className="evx-tip" role="tooltip" style={{ ...at, transform: "translateX(-50%)" }}>{tip}</span>,
        document.body)}
    </span>
  );
}

/** Hovering a bar or a legend colour: each outcome, its count and its rule, and how similarity is computed. */
export function OutcomeTip({ counts, title, children }: { counts: Counts | OutcomeCounts | null; title?: string; children: ReactNode }) {
  return (
    <Tip tip={<>
      {title && <span className="hd">{title}</span>}
      <table><tbody>
        {OUTCOMES.slice().reverse().map((o) => (
          <tr key={o}><td><i className={`sw o-${o}`} />{o}</td>{counts && <td className="n">{fmt(counts[o])}</td>}<td>{OUTCOME_RULE[o]}</td></tr>
        ))}
      </tbody></table>
      <span className="ft">{SIMILARITY}</span>
    </>}>{children}</Tip>
  );
}

// --- the score ---------------------------------------------------------------------------------------------------
function ScoreBody({ basis, view, col, subj, outcome, grp, offset, rowKey, nav }: {
  basis: ScoreBasis; view: ScoreValues; col: string | null; subj: string | null; outcome: ScoreOutcome | null; grp: string | null;
  offset: number; rowKey: string | null; nav: (ch: Record<string, string | number | null>, keepRow?: boolean) => void;
}) {
  const t = view.total;
  const implied = Object.keys(view.result?.implied ?? {});
  const leftOut = view.result?.left_out ?? [];
  return (
    <>
      <div className="evx-rate" data-testid="headline">
        <b>{pct(t.values ? t.match / t.values : null)}</b>
        <span className="evx-rate-l">exact matches</span>
        <span className={`evx-basis-pill ${basis}`}>{basis === "human" ? "human-reviewed" : "rule-matched"}</span>
        <span className="muted">{fmt(t.match)} of {fmt(t.values)} values {basis === "human" ? "an expert reviewed" : "the rules matched"}</span>
      </div>
      {leftOut.length > 0 && <p className="muted small">{fmt(leftOut.length)} pages left out: {leftOut[0].why}.</p>}

      <table className="evx-cols">
        <tbody>
          <ColRow name="All columns" c={t} on={!col} total onClick={() => nav({ col: null, off: null })} />
          {view.columns.map((p) => <ColRow key={p.column} name={p.column} c={p} on={col === p.column}
            onClick={() => nav({ col: col === p.column ? null : p.column, off: null })} />)}
        </tbody>
      </table>
      {implied.length > 0 && <p className="faint evx-ns">not scored: {implied.join(", ")} (not read from the page)</p>}

      <div className="evx-controls">
        <div className="seg">
          <button className={!outcome ? "on" : ""} onClick={() => nav({ o: null, off: null })}>All <span>{fmt(view.outcomes.values)}</span></button>
          {OUTCOMES.map((o) => (
            <button key={o} className={outcome === o ? "on" : ""} disabled={!view.outcomes[o]} onClick={() => nav({ o: outcome === o ? null : o, off: null })}>
              <i className={`sw o-${o}`} />{o} <span>{fmt(view.outcomes[o])}</span>
            </button>
          ))}
        </div>
        {col && <button className="evx-chip" onClick={() => nav({ col: null, off: null })}>{col} ✕</button>}
        {subj && <button className="evx-chip" onClick={() => nav({ subj: null, off: null })}>Subject: {subj} ✕</button>}
        <span className="grow" />
        <label className="evx-group">Group by
          <select value={grp ?? ""} onChange={(e) => nav({ grp: e.target.value || null, off: null })}>
            <option value="">nothing</option><option value="column">column</option><option value="subject">subject</option>
          </select>
        </label>
      </div>

      {grp && view.groups && (
        <div className="evx-groups" data-testid="groups">
          {view.groups.map((gr) => {
            const on = grp === "column" ? col === gr.name : subj === gr.name;
            const pick = () => nav(grp === "column" ? { col: on ? null : gr.name, off: null } : { subj: on ? null : gr.name, off: null });
            return (
              <button key={gr.name} className={`evx-grow${on ? " on" : ""}`} onClick={pick}>
                <span className={`evx-grow-n${grp === "column" ? " mono" : ""}`}>{gr.name}</span>
                <OutcomeTip counts={gr}><Bar c={gr} /></OutcomeTip>
                <span className="evx-grow-r"><b>{pct(gr.values ? gr.match / gr.values : null)}</b> <span className="muted">{fmt(gr.values)}</span></span>
              </button>
            );
          })}
        </div>
      )}

      <div className="evx-rows">
        {view.rows.items.map((r) => (
          <button key={r.key} className={`evx-row${r.key === rowKey ? " on" : ""}${col ? " one-col" : ""}`} onClick={() => nav({ row: r.key }, true)}>
            <i className={`sw o-${r.outcome}`} title={r.outcome} />
            <span className="evx-row-c">{r.golden_record_id ?? r.page_stem}</span>
            {!col && <span className="evx-row-p mono">{r.column}</span>}
            <span className="evx-row-v">{r.outcome === "missing" ? <span className="muted">nothing extracted</span>
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

function ColRow({ name, c, on, total = false, onClick }: { name: string; c: OutcomeCounts; on: boolean; total?: boolean; onClick: () => void }) {
  return (
    <tr className={`${on && !total ? "on" : ""}${total ? " all" : ""}`} onClick={onClick}>
      <td className={total ? "" : "mono"}>{name}</td>
      <td className="evx-barcell"><OutcomeTip counts={c}><Bar c={c} /></OutcomeTip></td>
      <td className="r"><b>{pct(c.values ? c.match / c.values : null)}</b></td>
      <td className="r muted">{fmt(c.values)}{total ? " values" : ""}</td>
    </tr>
  );
}

export function Bar({ c }: { c: OutcomeCounts }) {
  return (
    <span className="evx-bar" role="img" aria-label={OUTCOMES.map((o) => `${o} ${c[o]}`).join(", ")}>
      {OUTCOMES.slice().reverse().filter((o) => c[o] > 0).map((o) => <i key={o} className={`o-${o}`} style={{ flexGrow: c[o] }} />)}
    </span>
  );
}

// --- one value: the diff, the note box, the page -----------------------------------------------------------------
function RowPanel({ row, doc, catalog, ruleset, goldenLabel, outputDay, idx, me, onClose }: {
  row: ScoreRow; doc: ScoreDoc; catalog: string; ruleset: number; goldenLabel: string; outputDay: string; idx: ExtractOutputs;
  me: string; onClose: () => void;
}) {
  const mode = useDiffMode();
  const [m, setM] = useState<MatchRow | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const load = useCallback(() => {
    if (!row.rule_id || !row.occurrence_key) return;
    api.match(catalog, row.rule_id, row.occurrence_key).then(setM, () => setM(null));
  }, [catalog, row.rule_id, row.occurrence_key]);
  useEffect(() => { load(); }, [load]);
  const outputOf = (score: string) => {
    const o = idx.outputs.find((x) => x.scores.some((s) => s.id === score));
    return o ? fmtDay(o.last_modified) : null;
  };
  const target = m && { kind: "match" as const, rule_id: m.rule_id, occurrence_key: m.occurrence_key, page_stem: m.page_stem };
  const compared = { kind: "extract" as const, score: doc.id, value: row.extracted_value };
  const saveNote = async (note: string) => {
    if (!target) return false;
    try {
      await api.annotate(catalog, { type: "comment", author: me, target, note, compared_with: compared });
      toast("Note saved");
      load();
      return true;
    } catch (e) { toast(`Couldn't save: ${String(e)}`); return false; }
  };
  const saveWrong = async () => {
    if (!target || !m || !draft) return;
    if (!draft.captures.length) { toast("Select the right text on the page first"); return; }
    try {
      await api.annotate(catalog, { ...verdictEvent(me, target, m.verdict, { draft }), compared_with: compared });
      toast("Marked wrong");
      setDraft(null);
      load();
    } catch (e) { toast(`Couldn't save: ${String(e)}`); }
  };
  const marked = m?.state === "wrong" && m.verdict?.verdict === "wrong" ? m.verdict : null;
  const capture = (c: CapturedSelection) => setDraft((d) => (d ? { ...d, captures: addCapture(d.captures, c) } : d));
  const [atEnd, setAtEnd] = useState(false);
  const scrolled = (el: HTMLElement) => setAtEnd(el.scrollTop + el.clientHeight >= el.scrollHeight - 24);
  return (
    <section className="evx-panel" data-testid="row-panel">
      <header className="evx-panel-h">
        <b>{row.golden_record_id}</b><span className="mono">{row.column}</span>
        <span className="evx-out"><i className={`sw o-${row.outcome}`} />{row.outcome}{row.similarity !== null && row.outcome !== "match" ? ` · ${row.similarity.toFixed(2)}` : ""}</span>
        <span className="grow" />
        {row.rule_id && <a className="muted small" href={href(catalog, "rules", row.rule_id, { row: row.occurrence_key })}>Open in Rules →</a>}
        <button className="evx-icon" onClick={onClose} title="Close" aria-label="Close">✕</button>
      </header>
      <div className="evx-panel-b" onScroll={(e) => scrolled(e.currentTarget)}>
        <ValueDiff a={row.golden_value} b={row.extracted_value} aLabel={goldenLabel} bLabel={`extract output ${outputDay}`}
          mode={mode} bEmpty="nothing extracted" />
        {marked ? <MarkedWrong verdict={marked} what="the golden value" column={row.column} compared={comparedChip(marked.compared_with, outputOf)} />
          : draft ? <WrongFlow draft={draft} onChange={setDraft} onSave={() => void saveWrong()} onCancel={() => setDraft(null)} />
          : <NoteActions wrongLabel="The golden value is wrong…" onSave={saveNote} disabled={!target}
              onWrong={() => m && setDraft(newDraft("wrong", m.verdict, m.state))} />}
        {!row.rule_id && <p className="faint small">This value has no row in the Studio's latest extraction, so it can't be annotated here.</p>}
        {m && <RowNotes comments={m.comments} label={(c) => comparedChip(c.compared_with, outputOf)} />}
        <ValuePage catalog={catalog} stem={row.page_stem} url={row.source_url ?? ""} title={row.golden_record_id ?? row.page_stem}
          golden={{ cssPath: row.golden_css_path, charStart: row.golden_char_start, charEnd: row.golden_char_end, text: row.golden_value }}
          other={row.outcome === "match" ? null : row.extracted_value} captures={draft?.captures ?? []} capturing={!!draft}
          onCapture={capture} onRemove={(i) => setDraft((d) => (d ? { ...d, captures: d.captures.filter((_, j) => j !== i) } : d))}
          labels={{ golden: "golden value", other: "extracted value" }} ruleset={ruleset} />
      </div>
      <div className={"evx-more" + (atEnd ? " gone" : "")} aria-hidden>Scroll for more <Ico name="chevron" /></div>
    </section>
  );
}

// --- where these come from ---------------------------------------------------------------------------------------
function InfoModal({ doc, basis, onClose }: { doc: ScoreDoc; basis: ScoreBasis; onClose: () => void }) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);
  const cmd = doc.commands[basis === "human" ? 0 : 1];  // human-reviewed tree, then rule-matched (score.json)
  const text = cmd ? multiline(cmd) : "";
  const draft = doc.golden.kind === "draft";
  return (
    <div className="evx-back" onClick={onClose}>
      <div className="evx-modal" role="dialog" aria-label="Where these come from" onClick={(e) => e.stopPropagation()}>
        <div className="evx-modal-h"><h2>Where these come from</h2><button className="btn sm" onClick={onClose}>Close</button></div>
        <table className="evx-where">
          <thead><tr><th>What</th><th>Where</th><th>Notes</th></tr></thead>
          <tbody>
            <tr><td>Extract output</td><td className="mono">{doc.output.path}/records/</td>
              <td className="muted">Written by engineers with <code>xtra catalog extract</code>. Each run overwrites it; the Studio keeps a copy of what it scored.</td></tr>
            <tr><td>Golden dataset</td><td className="mono">{doc.golden.from}{draft ? "" : `/${basis === "human" ? "human-reviewed" : "rule-matched"}/`}</td>
              <td className="muted">{draft ? "A draft: an unpublished extraction, scored as if it were published." : "Published from this Studio."}
                {doc.golden.kind === "human-reviewed" || basis === "human" ? ` Read as of ${fmtDayTime(doc.golden.as_of)}.` : ""}</td></tr>
            <tr><td>Score</td><td>{fmtDayTime(doc.finished_at ?? doc.created_at)}</td>
              <td className="muted"><code>xtra score extraction match</code>{doc.scorer.xtra_cli_commit ? `, xtra-cli ${doc.scorer.xtra_cli_commit.slice(0, 7)}${doc.scorer.xtra_cli_commit.endsWith("+dirty") ? "+dirty" : ""}` : ""} · {doc.id}</td></tr>
          </tbody>
        </table>
        <div className="evx-term">
          <pre>{text || "# a draft has no files for xtra score to read"}</pre>
          {text && <button className="evx-copy" onClick={() => navigator.clipboard.writeText(text).then(() => toast("Copied"))}><Ico name="copy" />Copy</button>}
        </div>
      </div>
    </div>
  );
}
