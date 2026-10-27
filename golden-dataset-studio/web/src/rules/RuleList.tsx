// Left column of the Rules tab (spec §7.2): rules by kind, one status icon each, "14 / 1,062 reviewed".
// Status appears only here.
import type { RulesResponse } from "../api/types";
import { Ico } from "../shell/icons";
import { fmt } from "../shell/ui";
import type { RuleSummaryX } from "./api";

export function RuleList({ rules, active, onPick }: { rules: RulesResponse; active: string | null; onPick: (id: string) => void }) {
  let first = true;
  return (
    <div className="rule-list" data-tour="rule-list">
      {rules.groups.map((g) => (
        <div key={g.kind} className="rule-group">
          <div className="group-h"><span className="panel-title">{g.label}</span>
            <span className="sub">{g.approved} of {g.rules.length} approved</span></div>
          {g.rules.map((r: RuleSummaryX) => {
            const tour = first;
            first = false;
            const notes = r.comments + (r.page_questions ?? 0);
            return (
              <div key={r.rule_id} className={`rule-item${r.rule_id === active ? " on" : ""}`} role="button" tabIndex={0}
                data-rule={r.rule_id} onClick={() => onPick(r.rule_id)} onKeyDown={(e) => { if (e.key === "Enter") onPick(r.rule_id); }}>
                <div className="ico" title={r.status} data-tour={tour ? "rule-status" : undefined}><Ico name={r.status} /></div>
                <div style={{ minWidth: 0 }}>
                  <div className="nm">{r.title}</div>
                  <div className={`id${r.kind === "field" ? "" : " plain"}`} title={r.subtitle}>{r.subtitle}</div>
                </div>
                <div className="meta">
                  <span className={`rev${r.reviewed ? "" : " none"}`} title="courses with a verdict / all courses"
                    data-tour={tour ? "reviewed-count" : undefined}>{fmt(r.reviewed)} / {fmt(r.total)} reviewed</span>
                  {notes > 0 && <span className="stat open" title="comments and questions for the institution"><Ico name="bubble" />{notes}</span>}
                </div>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
