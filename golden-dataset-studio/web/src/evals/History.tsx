// The history chart: one bar per extract output, oldest first; a dashed bar (not scored yet) holds the Score button.
import type { OutcomeCounts, ScoreBasis, ScoreBrief } from "../api/types";
import { fmtDay } from "../valuediff/diff";
import { BAR_ORDER, num, OUTCOMES, outcomesOf, pct, rateOf, scoreFor, total, type Counts, type Output } from "./score";
import { OutcomeTip } from "./Tip";

const CHART_H = 150;

interface HistoryProps {
  outputs: Output[]; latest: string | undefined; basis: ScoreBasis; golden: string; latestGolden: string | null; picked: string | null;
  busy: boolean; onPick: (id: string) => void; onScore: (o: Output) => void;
}
type BarProps = Omit<HistoryProps, "outputs"> & { output: Output };

export function History({ outputs, ...bar }: HistoryProps) {
  return <div className="evx-hist" data-testid="history">{outputs.map((o) => <HistoryBar key={o.id} output={o} {...bar} />)}</div>;
}

/** Each outcome's colour; with `counts`, a hover shows each outcome's count. */
export function OutcomeLegend({ counts }: { counts: Counts | OutcomeCounts | null }) {
  return (
    <div className="evx-legend-v">
      {OUTCOMES.map((o) => <OutcomeTip key={o} counts={counts}><span className="evx-k"><i className={`sw o-${o}`} />{o}</span></OutcomeTip>)}
      <LegendHint />
    </div>
  );
}

export function PlainLegend() {
  return (
    <div className="evx-legend-v">
      {OUTCOMES.map((o) => <span key={o} className="evx-k"><i className={`sw o-${o}`} />{o}</span>)}
      <LegendHint />
    </div>
  );
}

function HistoryBar({ output, latest, basis, golden, latestGolden, picked, busy, onPick, onScore }: BarProps) {
  const brief = scoreFor(output, basis, golden, latestGolden);
  const counts = brief?.status === "done" ? outcomesOf(brief, basis) : null;
  return (
    <div className={`evx-col${output.id === picked ? " sel" : ""}`} data-testid="history-bar">
      <span className="evx-pc">{counts ? pct(rateOf(counts)) : "–"}</span>
      {counts && total(counts) ? <StackedBar output={output} counts={counts} onPick={onPick} />
        : <EmptyBar output={output} brief={brief} counts={counts} busy={busy} onPick={onPick} onScore={onScore} />}
      <span className="evx-x">{fmtDay(output.last_modified)}{output.id === latest && <><br />(latest)</>}</span>
    </div>
  );
}

function LegendHint() {
  return <span className="faint evx-hint">Click a bar to compare with that extract output. A dashed bar hasn't been scored yet.</span>;
}

function StackedBar({ output, counts, onPick }: { output: Output; counts: Counts; onPick: (id: string) => void }) {
  const n = total(counts);
  return (
    <OutcomeTip counts={counts}>
      <button className="evx-stack" style={{ height: CHART_H }} aria-label={`Extract output of ${fmtDay(output.last_modified)}: ${pct(rateOf(counts))} exact matches`}
        onClick={() => onPick(output.id)}>
        {BAR_ORDER.map((k) => num(counts, k) > 0 && <i key={k} className={`o-${k}`} style={{ height: `${(num(counts, k) / n) * 100}%` }} />)}
      </button>
    </OutcomeTip>
  );
}

function EmptyBar({ output, brief, counts, busy, onPick, onScore }: Pick<BarProps, "output" | "busy" | "onPick" | "onScore"> & {
  brief: ScoreBrief | undefined; counts: Counts | null | undefined }) {
  return (
    <div className="evx-empty-bar" style={{ height: CHART_H }} onClick={() => onPick(output.id)}>
      {brief?.status === "running" ? <span className="evx-run">Scoring…</span> : <>
        {brief && (brief.status === "failed" || brief.status === "interrupted") && <span className="evx-bad" title={brief.error ?? ""}>{brief.status}</span>}
        {counts && !total(counts) ? <span className="faint evx-none">no values</span>
          : <button className="btn sm evx-score" disabled={busy} onClick={(e) => { e.stopPropagation(); onScore(output); }}>Score</button>}
      </>}
    </div>
  );
}
