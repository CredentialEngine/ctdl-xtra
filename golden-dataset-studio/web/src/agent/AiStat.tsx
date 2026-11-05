// A rule's AI status in the sidebar (one-rule-runs §1.1, §1.7): one more row counter, like the comment count. A run
// working on the rule shows the run bar's pulsing dot and its minutes; a run in line shows a clock and its place
// ("◷ 2nd"); a last run that needs decisions shows "? 1" in amber. A click opens the rule's AI runs, or that report.
import type { RuleSummaryX } from "../rules/api";
import { ordinal, openRuns } from "./api";
import { useAgent } from "./state";

export function useAiStat(): (r: RuleSummaryX) => JSX.Element | null {
  const { runs, recent } = useAgent();
  return (r) => {
    const live = runs.find((x) => x.scope.rules?.includes(r.rule_id));
    const rule = { id: r.rule_id, name: r.title };
    const click = (run?: string) => (e: React.MouseEvent) => { e.stopPropagation(); openRuns(run, run ? undefined : rule); };
    if (live?.state === "waiting") {
      const place = live.queue?.place;
      const mins = live.queue?.start_in_min;
      return (
        <span className="stat" role="button" tabIndex={0} onClick={click()} data-testid="ai-stat"
          title={`Waiting for a free place${place ? `: ${ordinal(place)} in line` : ""}${mins != null ? `, about ${Math.max(1, mins)} min` : ""}`}>
          <span aria-hidden="true">◷</span>{place ? ordinal(place) : "in line"}</span>);
    }
    if (live) {
      const m = live.queue?.minutes_so_far ?? 0;
      return (
        <span className="stat" role="button" tabIndex={0} onClick={click()} data-testid="ai-stat"
          title={`Claude is working on this rule: ${m} min. Click: its AI runs`}>
          <span className="run-pulse" aria-hidden="true" />{m} min</span>);
    }
    const last = recent[r.rule_id];
    if (last?.state === "needs_you" && last.to_do_count) {
      const n = last.to_do_count;
      return (
        <span className="stat sig" role="button" tabIndex={0} onClick={click(last.run_id)} data-testid="ai-stat"
          title={`The last AI run needs ${n} decision${n === 1 ? "" : "s"} from you. Click: its report`}>?&nbsp;{n}</span>);
    }
    return null;
  };
}
