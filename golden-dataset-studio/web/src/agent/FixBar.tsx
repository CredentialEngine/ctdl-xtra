// The fix bar at the bottom of the Rules tab's rule list (spec §1): how many rules need work and one button that hands
// them all to Claude. It sits after the rules so that labeling comes first; a run works on every rule at once.
import type { RulesResponse } from "../api/types";
import { fmt } from "../shell/ui";
import { RunButton } from "./RunButton";
import { openRuns } from "./api";
import "./agent.css";

export function fixCounts(rules: RulesResponse) {
  const all = rules.groups.flatMap((g) => g.rules);
  const needing = all.filter((r) => r.status === "needs work");
  return {
    rules: needing.length,
    wrong: needing.reduce((n, r) => n + r.open_wrong, 0),
    missing: needing.reduce((n, r) => n + r.open_missing, 0),
    questions: all.reduce((n, r) => n + (r.questions ?? 0), 0),
  };
}

const pastRuns = <button className="linkish fb-past" onClick={() => openRuns()}>Past AI runs</button>;

export function FixBar({ catalog, name, rules }: { catalog: string; name: string; rules: RulesResponse }) {
  const n = fixCounts(rules);
  const s = (k: number, w: string) => `${fmt(k)} ${w}${k === 1 ? "" : "s"}`;
  if (!n.rules) {
    return <div className="fix-bar is-clear" data-testid="fix-bar">
      <span className="fb-t">Nothing to fix: no rule has open wrong or missing verdicts.</span>{pastRuns}</div>;
  }
  const detail = [n.wrong && `${fmt(n.wrong)} wrong`, n.missing && `${fmt(n.missing)} missing`,
                  n.questions && s(n.questions, "question") + " for the institution"].filter(Boolean).join(" · ");
  const label = n.rules === 1 ? "Improve the rule with Claude" : `Improve all ${n.rules} rules with Claude`;
  return (
    <div className="fix-bar" data-testid="fix-bar" data-tour="fix-bar">
      <div className="fb-t"><b>{s(n.rules, "rule")} need{n.rules === 1 ? "s" : ""} work</b>
        {detail && <span className="faint"> · {detail}</span>}</div>
      <RunButton catalog={catalog} scope={{ kind: "needs_work" }} label={label}
        confirm={`Improve ${s(n.rules, "rule")} on ${name} with Claude? It gets every open wrong and missing verdict.`} />
      {pastRuns}
    </div>
  );
}
