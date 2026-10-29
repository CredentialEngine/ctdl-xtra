// Left column of the Rules tab (spec §7.2): rules by kind, one status icon each, "14 / 1,062 reviewed".
// Status appears only here. With the "Annotated by" filter on (`counts`), each rule shows how many of its rows pass it
// instead (its meaning in a tooltip after a second), and rules with none are dimmed (Evals spec §6.7). `top` sits above the groups (the ruleset picker); with `talk`, a thread per rule
// (opened under it).
import { useState, type ReactNode } from "react";
import type { Discussion, RulesResponse, Topic } from "../api/types";
import { Ico } from "../shell/icons";
import { fmt } from "../shell/ui";
import type { RuleSummaryX } from "./api";
import { Composer, Thread } from "./Discussion";
import { Tip } from "../evals/EvalsTab";

export type PostTalk = (target: { kind: "rule" | "ruleset"; rule_id: string | null }, note: string, topic: Topic) => Promise<boolean>;

export function RuleList({ rules, active, onPick, talk, onTalk, top, bottom, counts, countTip }: {
  rules: RulesResponse; active: string | null; onPick: (id: string) => void; talk?: Discussion | null; onTalk?: PostTalk;
  counts?: Record<string, number> | null; countTip?: (n: number, field: boolean) => string;
  top?: ReactNode; /** after every group: the fix bar (Improve all rules), last so labeling comes first */ bottom?: ReactNode;
}) {
  let first = true;
  const [openTalk, setOpenTalk] = useState<string | null>(null);
  return (
    <div className="rule-list" data-tour="rule-list">
      {top}
      {rules.groups.map((g) => (
        <div key={g.kind} className="rule-group">
          <div className="group-h"><span className="panel-title">{g.label}</span>
            <span className="sub">{g.approved} of {g.rules.length} approved</span></div>
          {g.rules.map((r: RuleSummaryX) => {
            const tour = first;
            first = false;
            const notes = r.comments + (r.page_questions ?? 0);
            return (
              <div key={r.rule_id}>
              <div className={`rule-item${r.rule_id === active ? " on" : ""}${counts && !counts[r.rule_id] ? " dim" : ""}`} role="button" tabIndex={0}
                data-rule={r.rule_id} onClick={() => onPick(r.rule_id)} onKeyDown={(e) => { if (e.key === "Enter") onPick(r.rule_id); }}>
                <div className="ico" title={r.status} data-tour={tour ? "rule-status" : undefined}><Ico name={r.status} /></div>
                <div style={{ minWidth: 0 }}>
                  <div className="nm">{r.title}</div>
                  <div className={`id${r.kind === "field" ? "" : " plain"}`} title={r.subtitle}>{r.subtitle}</div>
                </div>
                <div className="meta">
                  {counts
                    ? counts[r.rule_id]
                      ? <Tip delay={1000} width={260} tip={countTip?.(counts[r.rule_id], r.kind === "field")}>
                          <span className="rev match">{fmt(counts[r.rule_id])}</span></Tip>
                      : <span className="rev match none">—</span>
                    : <span className={`rev${r.reviewed ? "" : " none"}`} title="courses with a verdict / all courses"
                        data-tour={tour ? "reviewed-count" : undefined}>{fmt(r.reviewed)} / {fmt(r.total)} reviewed</span>}
                  {notes > 0 && <span className="stat open" title="comments and questions for the institution"><Ico name="bubble" />{notes}</span>}
                  {talk && onTalk && (() => {
                    const n = talk.rules[r.rule_id]?.length ?? 0;
                    const on = openTalk === r.rule_id;
                    return (
                      <button className={"rule-talk-btn" + (n ? " has" : "") + (on ? " on" : "")} aria-expanded={on}
                        title={n ? `${n} comment${n === 1 ? "" : "s"} on this whole rule` : "Comment on this whole rule"}
                        onClick={(e) => { e.stopPropagation(); setOpenTalk(on ? null : r.rule_id); }}>
                        <Ico name="open" />{n > 0 ? n : "Discuss"}</button>
                    );
                  })()}
                </div>
              </div>
              {talk && onTalk && openTalk === r.rule_id && (
                <div className="rule-talk" data-testid="rule-talk">
                  <Thread items={talk.rules[r.rule_id] ?? []} />
                  <Composer placeholder={`A thought about ${r.title} as a whole…`} question
                    onPost={(note, topic) => onTalk({ kind: "rule", rule_id: r.rule_id }, note, topic)} />
                </div>
              )}
              </div>
            );
          })}
        </div>
      ))}
      {bottom}
    </div>
  );
}
