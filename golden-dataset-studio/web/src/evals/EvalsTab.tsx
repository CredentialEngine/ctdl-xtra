// Evals (docs/qrspi/evals/03-spec.md §6.3–6.4): how closely xtra's extract outputs match the golden dataset, scored
// by xtra's own scorer. The title is the comparison ([golden side] vs `xtra catalog extract` outputs over time), with
// the slim switch "scored against Human-reviewed | Rule-matched" at its right. Under it, one bar per extract output
// the Studio has seen; clicking one picks it, and a dashed bar (not scored against this golden side yet) holds the only
// Score button. Then the chosen pair as two chips, the exact matches, one bar per column, the outcome filter, Group
// by and the values. A value opens the shared diff (Split / Unified) with a note box and the saved page beside it.
//
// URL: #/c/<catalog>/evals?b=human|rule&g=<golden>&x=<output>&col=<column>&subj=<subject>&o=<outcome>&grp=column|subject
//      &off=<offset>&row=<row key>&wk=label|shape|diff|subject (Where it's wrong's grouping; none = auto)
//
// sme-fixes spec §8.4: each bar has an extra segment (striped: candidates with no golden value) and an unsure one; a
// column shows found (recall) and right (precision), and for a list property (durations) the courses exact; "Where
// it's wrong" groups the units that aren't a match, each group linking to its courses in the Rules tab. A column
// with no score says why with two facts: its candidates (values in xtra's extract output) and its golden values
// (rule-matched values on the Rule-matched side).
import { Fragment, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { api } from "../api/client";
import type { CatalogsSummary, ColumnSummary, ExtractOutputs, GoldenChoice, MatchRow, OutcomeCounts, ScoreBasis, ScoreBrief, ScoreDoc,
  ScoreOutcome, ScoreRow, ScoreValues, WrongGroups, WrongKey } from "../api/types";
import type { CapturedSelection } from "../pagepane";
import { addCapture, BY_ANYONE, newDraft, verdictEvent, type Draft } from "../rules/logic";
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

/** Every outcome, worst first (sme-fixes spec §8.1): the golden side's five, then `extra` (a candidate with no golden
 * partner). Scores from before sme-fixes have no unsure or extra (0). */
export const OUTCOMES: ScoreOutcome[] = ["missing", "wrong", "partial", "unsure", "match", "extra"];
/** What `values` counts: the golden units. */
export const GOLDEN_OUTCOMES: ScoreOutcome[] = OUTCOMES.filter((o) => o !== "extra");
/** The order of a bar's segments, left to right (bottom to top): matches first, the striped extras last. */
export const BAR_ORDER: ScoreOutcome[] = ["match", "partial", "unsure", "wrong", "missing", "extra"];
/** Each outcome's rule (xtra's scorer, Evals spec §2, sme-fixes spec §8.1), in the tab's terms: a **candidate** is a
 * value in xtra's extract output; a **golden value** is one the golden side holds. */
export const OUTCOME_RULE: Record<ScoreOutcome, string> = {
  match: "a candidate identical to the golden value", partial: "paired with a candidate, similarity ≥ 0.8",
  wrong: "paired with a candidate, similarity < 0.8", missing: "a golden value with no candidate",
  unsure: "golden says not on the page; xtra made no claim", extra: "a candidate with no golden value",
};
export const SIMILARITY = "Text is compared ignoring case and spacing, and again without punctuation, keeping the higher score. Numbers either match or are wrong. A list of objects (durations) pairs by description; an object is exact only when every field is.";
/** The two numbers per column, under plain names, with their formulas (sme-fixes Q10.9). */
export const FOUND_TIP = <span><b>Found</b> (recall): the golden values xtra got exactly.<br />
  found = match ÷ golden values = match ÷ (match + partial + wrong + missing + unsure)</span>;
export const RIGHT_TIP = <span><b>Right</b> (precision): the candidates that are exactly a golden value.<br />
  right = match ÷ candidates = match ÷ (match + partial + wrong + extra)</span>;
export const COURSES_TIP = <span><b>Courses exact</b>, for a list property (durations): courses whose whole list is exact
  (no wrong, missing or extra item) ÷ courses.</span>;
/** The two terms an unscored column's facts use. */
export const CANDIDATES_TIP = "Candidates: the values in xtra's extract output for this property.";
export const goldenTerm = (basis: ScoreBasis) => (basis === "human" ? "Golden values" : "Rule-matched values");
export const goldenTip = (basis: ScoreBasis) => basis === "human"
  ? "Golden values: the values a person reviewed (the golden dataset)."
  : "Rule-matched values: the values the Studio's rules matched, with the human-reviewed ones (the silver dataset).";
const HUMAN = "human-reviewed";
/** A column with a CTDL term is written with its prefix-free path ("creditValue>minValue"); a property with none is its
 * label ("Learning Type"), which has a space. */
export const hasCtdlTerm = (key: string) => !/\s/.test(key);
type Output = ExtractOutputs["outputs"][number];
type Counts = Partial<Record<ScoreOutcome, number>>;
const num = (c: Counts | OutcomeCounts | null | undefined, o: ScoreOutcome) => (c as Counts | null | undefined)?.[o] ?? 0;
const total = (c: Counts | OutcomeCounts | null | undefined) => OUTCOMES.reduce((t, o) => t + num(c, o), 0);

/** match ÷ golden values (found; the exact match rate). */
const rateOf = (c: Counts | null | undefined) => {
  const n = GOLDEN_OUTCOMES.reduce((t, o) => t + num(c, o), 0);
  return c && n ? num(c, "match") / n : null;
};
/** match ÷ candidates (right), or null when nothing was extracted. */
const rightOf = (c: Counts | OutcomeCounts | null | undefined) => {
  const n = num(c, "match") + num(c, "partial") + num(c, "wrong") + num(c, "extra");
  return c && n ? num(c, "match") / n : null;
};
const pct = (x: number | null | undefined) => (x === null || x === undefined ? "–" : `${Math.round(x * 100)}%`);

/** A value as the tab shows it: an object (a duration) as its fields, `description: … · timeRequired: …`. */
export function shown(v: string | null | undefined): string {
  if (!v || !v.startsWith("{")) return v ?? "";
  try {
    const o = JSON.parse(v) as Record<string, unknown>;
    return Object.entries(o).map(([k, x]) => `${k.split(":").pop()}: ${String(x)}`).join(" · ");
  } catch { return v; }
}

/** The two facts that say why a column isn't scored (it is only when it has both candidates and golden values): its
 * candidates in this extract output, and its golden values (rule-matched values on the Rule-matched side). `full` is
 * the sentence, `short` the chip's text. */
export interface Fact { term: string; short: string; full: string; tip: string }
export function unscoredFacts(key: string, col: ColumnSummary | undefined, doc: ScoreDoc, basis: ScoreBasis,
  implied: string[]): { candidates: Fact; golden: Fact } {
  const n = doc.candidates?.[key] ?? 0;
  const known = doc.xtra_extracts;
  const noTerm = !hasCtdlTerm(key);
  const extracts = !noTerm && (known ? known.includes(key) : !(doc.not_scored ?? []).includes(key));
  const candidates: Fact = { term: "Candidates", tip: CANDIDATES_TIP,
    ...(n > 0 ? { short: fmt(n), full: `${fmt(n)} candidate${n === 1 ? "" : "s"}` }
      : extracts ? { short: "none in this output", full: "No candidates in this output" }
        : { short: "none · xtra doesn't extract it", full: "No candidates: xtra doesn't extract this property" }) };
  const term = goldenTerm(basis), noun = term.toLowerCase();
  const g = col ? (basis === "human" ? col.human : col.human + col.rule) : 0;
  const status = !col || col.no_rule ? null : col.status === "needs work" ? "needs work" : col.status === "in review" ? "in review" : null;
  const golden: Fact = { term, tip: goldenTip(basis), ...(
    noTerm ? { short: "Studio only: no CTDL property", full: "Studio only: no CTDL property" }
      : implied.includes(key) ? { short: "not read from the page", full: "Not read from the page" }
        : g > 0 ? { short: `${fmt(g)}${status ? ` · Studio rule ${status}` : ""}`,
            full: `${fmt(g)} ${g === 1 ? noun.replace(/s$/, "") : noun}${status ? ` · the Studio rule is ${status}` : ""}` }
          : !col || col.no_rule ? { short: "none · no Studio rule yet", full: `No ${noun}: no Studio rule yet` }
            : status ? { short: `none · Studio rule ${status}`,
                full: `No ${noun}: the Studio rule ${status === "needs work" ? "needs work" : "is in review"}` }
              : { short: "none", full: `No ${noun}` }) };
  return { candidates, golden };
}
/** The golden side's name: the golden dataset (human-reviewed values), a version's silver dataset (rule-matched values). */
export const goldenName = (id: string) =>
  id === HUMAN ? "Golden dataset (human-reviewed)" : /^ruleset-v\d+$/.test(id) ? `Silver dataset ${id}` : `draft ${id}`;

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
  const wkParam = P.get("wk");
  const wk: WrongKey = wkParam === "label" || wkParam === "shape" || wkParam === "diff" || wkParam === "subject" ? wkParam : "auto";
  const nav = useCallback((ch: Record<string, string | number | null>, keepRow = false) => {
    const cur: Record<string, string | number | null> = { b: basis === "rule" ? "rule" : null, g: P.get("g"), x: P.get("x"), col, subj,
      o: outcome, grp, off: offset || null, row: keepRow ? rowKey : null, wk: wk === "auto" ? null : wk };
    go(href(cat, "evals", null, { ...cur, ...ch }), true);
  }, [cat, basis, P, col, subj, outcome, grp, offset, rowKey, wk]);

  const loadIndex = useCallback(() => api.extractOutputs(cat).then(setIdx, (e) => setError(String(e))), [cat]);
  useEffect(() => { void loadIndex(); }, [loadIndex]);
  // every property's column and its status here (the score lists them all, m8)
  const [sum, setSum] = useState<CatalogsSummary | null>(null);
  useEffect(() => {
    let live = true;
    api.catalogsSummary(basis).then((r) => live && setSum(r), () => live && setSum(null));
    return () => { live = false; };
  }, [basis]);

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
            ? <span className="evx-gchip big">{goldenName(HUMAN)}<span className="evx-gchip-d"> · as of {fmtDayTime(brief?.golden_as_of) || "now"}</span></span>
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
            <span className="evx-gchip">{basis === "human" ? `${goldenName(HUMAN)} · ${fmtDayTime(brief?.golden_as_of) || "now"}` : goldenName(g)}</span>
            {basis === "rule" && idx.goldens.find((z) => z.id === g)?.kind === "draft" && <span className="evx-draft">draft · unpublished</span>}
            <span className="evx-vs">vs</span>
            <span className="evx-xchip"><MiniBar c={(basis === "human" ? brief?.human_outcomes : brief?.rule_outcomes) ?? null} />
              {fmtDayTime(output.last_modified)}{output.id === latestOutput && <span className="muted"> (latest)</span>}</span>
          </div>
          {brief?.slot_names && <p className="evx-flag">This output uses slot names; re-extract with the current xtra-cli.</p>}
          {output.records_mismatch && <p className="evx-flag">The folder has {fmt(output.records)} records; its report says {fmt(output.records_written)} were written (an earlier run's records may be left over).</p>}
          {!brief && <p className="muted">Not scored against {goldenName(basis === "human" ? HUMAN : g)} yet: press <b>Score</b> on its bar.</p>}
          {brief && brief.status !== "done" && <p className="muted">{brief.status === "running" ? `Scoring (${brief.id})…`
            : `${brief.id} ${brief.status}${brief.error ? `: ${brief.error}` : ""}. Press Score on its bar to score it again.`}</p>}
          {doc && !result && <p className="muted">No {basis === "human" ? "human-reviewed" : "rule-matched"} values to score in {goldenName(basis === "human" ? HUMAN : g)}.</p>}
          {doc && result && view && <ScoreBody cat={cat} basis={basis} view={view} col={col} subj={subj} outcome={outcome} grp={grp} wk={wk} offset={offset}
            rowKey={rowKey} nav={nav} doc={doc} sum={sum} here={sum?.catalogs[catalog.catalog]?.columns ?? {}} />}
        </>}
      </section>

      {row && doc && output && <RowPanel key={`${doc.id}|${row.key}`} row={row} doc={doc} catalog={cat} ruleset={catalog.ruleset_version}
        goldenLabel={basis === "human" ? goldenName(HUMAN) : goldenName(doc.golden.id)}
        outputDay={fmtDay(output.last_modified)} idx={idx} me={me} onClose={() => nav({ row: null })} />}
      {info && doc && <InfoModal doc={doc} basis={basis} onClose={() => setInfo(false)} />}
    </div>
  );
}

// --- the golden side ---------------------------------------------------------------------------------------------
/** Rule-matched: a searchable dropdown of silver datasets (one per ruleset version), the latest first with "(latest)" (older ones with their
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
  const label = (z: GoldenChoice) => (z.kind === "draft" ? `draft ${z.id}` : goldenName(z.id));
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
        {cur ? label(cur) : value ? goldenName(value) : "No silver dataset"}
        {cur && <span className="evx-gchip-d"> {cur.kind === "draft" ? "· unpublished" : cur.latest ? "(latest)" : `· ${fmtDayTime(cur.published_at)}`}</span>}
        <Ico name="chevron" className="evx-caret" />
      </button>
      {open && (
        <div className="evx-dd-m" role="listbox">
          <input className="evx-dd-q" placeholder="Find a silver dataset" value={q} autoFocus onChange={(e) => setQ(e.target.value)} />
          {versions.map(item)}
          {!versions.length && !q && <p className="muted evx-dd-none">No silver dataset published yet.</p>}
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
        const n = total(c);
        const on = o.id === picked;
        return (
          <div key={o.id} className={`evx-col${on ? " sel" : ""}`} data-testid="history-bar">
            <span className="evx-pc">{c ? pct(rateOf(c)) : "–"}</span>
            {c && n ? (
              <OutcomeTip counts={c}>
                <button className="evx-stack" style={{ height: CHART_H }} aria-label={`Extract output of ${fmtDay(o.last_modified)}: ${pct(rateOf(c))} exact matches`}
                  onClick={() => onPick(o.id)}>
                  {BAR_ORDER.map((k) => num(c, k) > 0 && <i key={k} className={`o-${k}`} style={{ height: `${(num(c, k) / n) * 100}%` }} />)}
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
  const n = total(c);
  return <i className="evx-mini">{c && n ? BAR_ORDER.map((k) => num(c, k) > 0 && <b key={k} className={`o-${k}`} style={{ height: `${Math.max(1, (num(c, k) / n) * 14)}px` }} />) : null}</i>;
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
        {BAR_ORDER.map((o) => (
          <tr key={o}><td><i className={`sw o-${o}`} />{o}</td>{counts && <td className="n">{fmt(num(counts, o))}</td>}<td>{OUTCOME_RULE[o]}</td></tr>
        ))}
      </tbody></table>
      <span className="ft">{SIMILARITY}</span>
    </>}>{children}</Tip>
  );
}

// --- the score ---------------------------------------------------------------------------------------------------
function ScoreBody({ cat, basis, view, col, subj, outcome, grp, wk, offset, rowKey, nav, doc, sum, here }: {
  cat: string; basis: ScoreBasis; view: ScoreValues; col: string | null; subj: string | null; outcome: ScoreOutcome | null;
  grp: string | null; wk: WrongKey; offset: number; rowKey: string | null;
  nav: (ch: Record<string, string | number | null>, keepRow?: boolean) => void;
  doc: ScoreDoc; sum: CatalogsSummary | null; here: Record<string, ColumnSummary>;
}) {
  const t = view.total;
  const implied = Object.keys(view.result?.implied ?? {});
  const leftOut = view.result?.left_out ?? [];
  const xtra = view.result?.xtra;
  const scored = new Map(view.columns.map((c) => [c.column, c]));
  const keys = sum?.columns ?? view.columns.map((c) => c.column);
  const required = sum?.required ?? [];
  const groups = [
    { title: "Required", keys: keys.filter((k) => required.includes(k)) },
    { title: "Other properties", keys: keys.filter((k) => !required.includes(k)) }].filter((g) => g.keys.length);
  const noun = goldenTerm(basis).toLowerCase();
  return (
    <>
      <div className="evx-rate" data-testid="headline">
        <b>{pct(t.values ? t.match / t.values : null)}</b>
        <span className="evx-rate-l">exact matches</span>
        <span className={`evx-basis-pill ${basis}`}>{basis === "human" ? "human-reviewed" : "rule-matched"}</span>
        <span className="muted">{fmt(t.match)} of {fmt(t.values)} values {basis === "human" ? "an expert reviewed" : "the rules matched"}</span>
      </div>
      <p className="muted small evx-fr" data-testid="found-right">
        <Tip tip={FOUND_TIP} width={360}><span tabIndex={0}>found <b>{pct(t.found ?? rateOf(t))}</b> of {fmt(t.values)} {noun}</span></Tip>
        {" · "}
        <Tip tip={RIGHT_TIP} width={360}><span tabIndex={0}>right <b>{pct(t.right ?? rightOf(t))}</b> of {fmt(t.extracted ?? num(t, "match") + num(t, "partial") + num(t, "wrong") + num(t, "extra"))} candidates</span></Tip>
        {num(t, "extra") > 0 && <> · <i className="sw o-extra" />{fmt(num(t, "extra"))} extra</>}
        {num(t, "unsure") > 0 && <> · <i className="sw o-unsure" />{fmt(num(t, "unsure"))} unsure</>}
      </p>
      {xtra && <p className="muted small evx-xtra" data-testid="xtra-line">xtra's own, over every column: {pct(xtra.exact_match_rate)} exact matches
        of {fmt(xtra.values)} values</p>}
      {leftOut.length > 0 && <p className="muted small">{fmt(leftOut.length)} pages left out: {leftOut[0].why}.</p>}

      <table className="evx-cols">
        <thead>
          <tr className="evx-colh">
            <th scope="col">Column</th><th scope="col">Units</th>
            <th scope="col" className="r"><Tip tip={FOUND_TIP} width={360}><span tabIndex={0}>Found</span></Tip></th>
            <th scope="col" className="r"><Tip tip={RIGHT_TIP} width={360}><span tabIndex={0}>Right</span></Tip></th>
            <th scope="col" className="r"><Tip tip={COURSES_TIP} width={320}><span tabIndex={0}>Courses</span></Tip></th>
            <th scope="col" className="r">{goldenTerm(basis)}</th>
          </tr>
        </thead>
        <tbody>
          <ColRow name="All columns" c={t} on={!col} total onClick={() => nav({ col: null, off: null })} />
          {groups.length
            ? groups.map((g) => (
              <Fragment key={g.title}>
                <tr className="evx-hrow"><th colSpan={6} scope="colgroup" className="evx-h">{g.title}</th></tr>
                {g.keys.map((k) => {
                  const name = sum?.labels[k] ?? k;
                  const sc = scored.get(k);
                  return sc
                    ? <ColRow key={k} name={name} mono={hasCtdlTerm(k)} c={sc} on={col === k} column={k}
                        onClick={() => nav({ col: col === k ? null : k, off: null })} />
                    : <Unscored key={k} k={k} name={name} facts={unscoredFacts(k, here[k], doc, basis, implied)} />;
                })}
              </Fragment>))
            : view.columns.map((p) => <ColRow key={p.column} name={p.column} c={p} on={col === p.column} column={p.column}
                onClick={() => nav({ col: col === p.column ? null : p.column, off: null })} />)}
        </tbody>
      </table>

      <WhereWrong cat={cat} doc={doc} basis={basis} col={col} wk={wk} nav={nav} />

      <div className="evx-controls">
        <div className="seg">
          <button className={!outcome ? "on" : ""} onClick={() => nav({ o: null, off: null })}>All <span>{fmt(total(view.outcomes))}</span></button>
          {OUTCOMES.map((o) => (
            <button key={o} className={outcome === o ? "on" : ""} disabled={!num(view.outcomes, o)} onClick={() => nav({ o: outcome === o ? null : o, off: null })}>
              <i className={`sw o-${o}`} />{o} <span>{fmt(num(view.outcomes, o))}</span>
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
            <i className={`sw o-${r.outcome}`} title={`${r.outcome}: ${OUTCOME_RULE[r.outcome]}`} />
            <span className="evx-row-c">{r.golden_record_id ?? r.page_stem}</span>
            {!col && <span className="evx-row-p mono">{r.column}{r.field ? ` · ${r.field}` : ""}</span>}
            <span className="evx-row-v">{rowText(r)}</span>
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

/** What a row of values says: the candidate, or why there is none. */
export function rowText(r: ScoreRow): ReactNode {
  if (r.outcome === "unsure") return <span className="muted">golden: not on the page · xtra made no claim</span>;
  if (r.outcome === "missing") {
    if (r.unit === "absent") return <span className="muted">golden: not on the page · candidate {shown(r.extracted_value) || "given"}</span>;
    return <span className="muted">{r.reason === "claimed not on the page" ? "xtra claims it isn't on the page" : "no candidate"}</span>;
  }
  if (r.outcome === "extra") {
    return r.unit === "absent" ? <span className="muted">xtra claims it isn't on the page (golden has a value)</span>
      : <>{shown(r.extracted_value)} <span className="muted">· {r.reason ?? "no golden value"}</span></>;
  }
  if (r.unit === "absent") return <span className="muted">not on the page</span>;
  return shown(r.outcome === "match" ? r.golden_value : r.extracted_value);
}

/** A column with no score: "Not scored" and its two facts, each with a tooltip saying what the term means. */
function Unscored({ k, name, facts }: { k: string; name: string; facts: { candidates: Fact; golden: Fact } }) {
  return (
    <tr className="evx-unscored" data-column={k}>
      <td className={hasCtdlTerm(k) ? "mono" : undefined}>{name}</td>
      <td colSpan={5} className="evx-why">
        <span className="evx-ns">Not scored</span>
        {[facts.candidates, facts.golden].map((f) => (
          <Tip key={f.term} width={320} tip={<>{f.tip}<br /><b>{f.full}</b></>}>
            <span className="evx-fact" tabIndex={0} title={f.full} data-fact={f.term}><span className="muted">{f.term}:</span> {f.short}</span>
          </Tip>
        ))}
      </td>
    </tr>
  );
}

function ColRow({ name, c, on, total: all = false, mono = true, column, onClick }: { name: string; c: OutcomeCounts; on: boolean; total?: boolean;
  mono?: boolean; column?: string; onClick: () => void }) {
  return (
    <tr className={`${on && !all ? "on" : ""}${all ? " all" : ""}`} onClick={onClick} data-column={column}>
      <td className={all || !mono ? "" : "mono"}>{name}</td>
      <td className="evx-barcell"><OutcomeTip counts={c}><Bar c={c} /></OutcomeTip></td>
      <td className="r" data-num="found"><b>{pct(c.found !== undefined ? c.found : c.values ? c.match / c.values : null)}</b></td>
      <td className="r" data-num="right">{pct(c.right !== undefined ? c.right : rightOf(c))}</td>
      <td className="r muted" data-num="courses">{c.list && c.courses ? pct((c.courses_exact ?? 0) / c.courses) : ""}</td>
      <td className="r muted">{fmt(c.values)}{all ? " values" : ""}</td>
    </tr>
  );
}

// --- Where it's wrong (sme-fixes spec §8.4) ----------------------------------------------------------------------
const WRONG_KEYS: { key: WrongKey; label: string }[] = [
  { key: "auto", label: "the likely cause" }, { key: "label", label: "description label" }, { key: "shape", label: "value shape" },
  { key: "diff", label: "word diff" }, { key: "subject", label: "course subject" }];
const WRONG_SHOWN = 12;

/** Every unit that isn't a match (under the picked column, or all), grouped by outcome × field × a key, biggest group
 * first: each group's count, one example (golden → candidate), and its courses, each a link to its row in the Rules
 * tab (anyone's annotations shown). */
function WhereWrong({ cat, doc, basis, col, wk, nav }: { cat: string; doc: ScoreDoc; basis: ScoreBasis; col: string | null; wk: WrongKey;
  nav: (ch: Record<string, string | number | null>, keepRow?: boolean) => void }) {
  const [w, setW] = useState<WrongGroups | null>(null);
  const [all, setAll] = useState(false);
  useEffect(() => {
    let live = true;
    api.scoreWrong(cat, doc.id, { basis, column: col, key: wk }).then((r) => live && setW(r), () => live && setW(null));
    return () => { live = false; };
  }, [cat, doc.id, basis, col, wk]);
  if (!w) return null;
  const shownGroups = all ? w.groups : w.groups.slice(0, WRONG_SHOWN);
  const term = goldenTerm(basis).toLowerCase().replace(/s$/, "");
  const link = (t: { rule_id: string | null; occurrence_key: string | null }) =>
    t.rule_id ? href(cat, "rules", t.rule_id, { row: t.occurrence_key, by: BY_ANYONE }) : null;
  return (
    <section className="evx-wrong" data-testid="where-wrong">
      <header className="evx-wrong-h">
        <h3>Where it's wrong</h3>
        <span className="muted small">{col ? <span className="mono">{col}</span> : "every column"} · every unit that isn't an exact match, grouped by reason, biggest group first</span>
        <span className="grow" />
        <label className="evx-group">Group by
          <select value={wk} aria-label="Where it's wrong: group by" onChange={(e) => nav({ wk: e.target.value === "auto" ? null : e.target.value })}>
            {WRONG_KEYS.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
          </select>
        </label>
      </header>
      {w.groups.length === 0 ? <p className="muted small">Nothing: every unit matched.</p> : (
        <table className="evx-wrong-t">
          <thead><tr><th className="r">Units</th><th>Reason (outcome · field · how it differs)</th><th>Grouped by</th><th>Example ({term} → candidate)</th><th>Courses</th></tr></thead>
          <tbody>
            {shownGroups.map((g) => {
              const ex = link(g.example);
              return (
                <tr key={`${g.outcome}|${g.field}|${g.column}|${g.by}|${g.key}`} data-testid="wrong-group">
                  <td className="r"><button className="evx-link" title="Show these values" onClick={() => nav({ col: g.column, o: g.outcome, off: null })}>{fmt(g.units)}</button></td>
                  <td>
                    <Tip tip={OUTCOME_RULE[g.outcome]} width={260}><span className={`evx-ob o-${g.outcome}`} tabIndex={0}>{g.outcome}</span></Tip>
                    {!col && <span className="mono"> {g.column}</span>}
                    {g.field && <span className="mono"> {g.field}</span>}
                    {g.reason && <span> {g.reason}</span>}
                  </td>
                  <td className="muted">{g.by} <span className="mono">{g.key}</span></td>
                  <td className="evx-wrong-ex">
                    <span>{g.example.golden_value === null ? <i className="muted">none</i> : shown(g.example.golden_value)}</span>
                    <span className="muted"> → </span>
                    <span>{g.example.extracted_value === null ? <i className="muted">none</i> : shown(g.example.extracted_value)}</span>
                    {ex && <a className="small" href={ex}> {g.example.golden_record_id ?? "open"} in Rules →</a>}
                  </td>
                  <td className="evx-wrong-c">
                    <span className="muted">{fmt(g.courses)}</span>{" "}
                    {g.targets.map((t, i) => {
                      const h = link(t);
                      return h ? <a key={i} className="evx-cc" href={h}>{t.golden_record_id ?? "?"}</a>
                        : <span key={i} className="evx-cc muted">{t.golden_record_id ?? "?"}</span>;
                    })}
                    {g.courses > g.targets.length && <span className="muted small"> +{fmt(g.courses - g.targets.length)}</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {w.groups.length > WRONG_SHOWN && <button className="btn sm" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${fmt(w.groups.length)} groups`}</button>}
    </section>
  );
}

/** One bar: the golden side's outcomes, then the extras striped (candidates with no golden value). */
export function Bar({ c }: { c: OutcomeCounts }) {
  return (
    <span className="evx-bar" role="img" aria-label={BAR_ORDER.map((o) => `${o} ${num(c, o)}`).join(", ")}>
      {BAR_ORDER.filter((o) => num(c, o) > 0).map((o) => <i key={o} className={`o-${o}`} style={{ flexGrow: num(c, o) }} />)}
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
            <tr><td>{basis === "human" ? goldenName(HUMAN) : goldenName(doc.golden.id)}</td><td className="mono">{doc.golden.from}{draft ? "" : `/${basis === "human" ? "human-reviewed" : "rule-matched"}/`}</td>
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
