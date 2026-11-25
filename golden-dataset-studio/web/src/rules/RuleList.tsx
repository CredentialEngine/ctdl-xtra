// Left column of the Rules tab (spec §7.2; property-rules spec §4.8): the rule groups, each a button that opens or shuts it
// (`collapsed` starts it shut), one status icon per rule, "14 / 1,062 reviewed". Status appears only here. Search (m4):
// "/" focuses it, it matches a rule's name, its CTDL term and its parent's name; with text the groups open, the ones with
// no match fold into one grey line, Esc clears, ↓ or Enter open a result. With the "Annotated by" filter on (`counts`),
// each rule shows how many of its rows pass it instead (its meaning in a tooltip after a second), and rules with none are
// dimmed (Evals spec §6.7). `top` sits above the groups (the ruleset picker); with `talk`, a thread per rule (opened under it).
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import type { Discussion, RuleGroup, RulesResponse, Topic } from "../api/types";
import { Ico } from "../shell/icons";
import { fmt } from "../shell/ui";
import type { RuleSummaryX } from "./api";
import { Composer, Thread } from "./Discussion";
import { isField, matchesRule } from "./logic";
import { Tip } from "../evals/EvalsTab";
import { classOfRule, recordNoun } from "../shell/klass";

export type PostTalk = (target: { kind: "rule" | "ruleset"; rule_id: string | null }, note: string, topic: Topic) => Promise<boolean>;

/** The search's match in a name or a term, marked (the rest as it is). */
function hit(text: string, query: string): ReactNode {
  if (!query) return text;
  const esc = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return text.split(new RegExp(`(${esc})`, "i")).map((part, i) => (i % 2 ? <mark key={i}>{part}</mark> : part));
}

/** A group's line under its name: rules on another locator are counted; a tier with no rule yet says how many are not
 * started; the rest say how many are approved. */
const COUNTED: Record<string, string> = { "not-started": "properties", program: "rules" };
const groupSub = (g: RuleGroup) => (COUNTED[g.id] ? `${g.rules.length} ${COUNTED[g.id]}`
  : g.rules.length && g.not_started === g.rules.length ? `${g.rules.length} not started`
  : `${g.approved} of ${g.rules.length} approved`);
const groupKey = (g: RuleGroup) => `${g.cls ?? ""}:${g.id}`;

/** All classes (mockup w4-rules-all-classes): a heading per class above its groups, with what it has. */
export interface ClassHead { name: string; sub: string }
const joinNames = (names: string[]) => (names.length < 2 ? names.join("")
  : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`);

export function RuleList({ rules, active, onPick, talk, onTalk, top, bottom, counts, countTip, onImprove, aiStat, heads }: {
  rules: RulesResponse; active: string | null; onPick: (id: string) => void; talk?: Discussion | null; onTalk?: PostTalk;
  /** All classes: each class's heading, by class (its groups carry `cls`) */
  heads?: Record<string, ClassHead> | null;
  counts?: Record<string, number> | null; countTip?: (n: number) => string;
  top?: ReactNode; /** after every group: the fix bar (Improve rules with AI…), last so labeling comes first */ bottom?: ReactNode;
  /** ✦ Improve on every row, beside Comment (one-rule-runs §1.1): starts a run on that one rule */
  onImprove?: (r: RuleSummaryX) => void;
  /** a rule's AI status as one more row counter (working, in line, decisions waiting): null for none */
  aiStat?: (r: RuleSummaryX) => ReactNode;
}) {
  let first = true;
  const [openTalk, setOpenTalk] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [toggled, setToggled] = useState<Record<string, boolean>>({});  // a group the reader opened or shut
  const search = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const q = query.trim();
  const searching = q !== "";
  const isOpen = (g: RuleGroup) => searching || (toggled[groupKey(g)] ?? !g.collapsed);
  const shown = rules.groups.map((g) => ({ g, open: isOpen(g), list: searching ? g.rules.filter((r) => matchesRule(r, q)) : g.rules }));
  const firstResult = searching ? shown.flatMap((x) => x.list)[0] : undefined;
  const folded = searching ? shown.filter((x) => x.list.length === 0).map((x) => x.g.label) : [];
  const properties = rules.groups.filter((g) => g.kind === "property").reduce((n, g) => n + g.rules.length, 0);
  const allRules = rules.groups.reduce((n, g) => n + g.rules.length, 0);

  // "/" focuses the search from anywhere (not from inside a field)
  useEffect(() => {
    const on = (e: globalThis.KeyboardEvent) => {
      if (e.key !== "/" || isField(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      e.preventDefault();
      search.current?.focus();
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, []);

  const items = () => [...(listRef.current?.querySelectorAll<HTMLElement>(".rule-item[data-rule]") ?? [])];
  const onSearchKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") { e.stopPropagation(); setQuery(""); }
    else if (e.key === "ArrowDown") { e.preventDefault(); items()[0]?.focus(); }
    else if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); if (firstResult) onPick(firstResult.rule_id); }
  };
  const onItemKey = (e: KeyboardEvent<HTMLDivElement>, id: string) => {
    if (e.key === "Enter") { onPick(id); return; }
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const all = items();
    const next = all[all.indexOf(e.currentTarget) + (e.key === "ArrowDown" ? 1 : -1)];
    if (next) next.focus();
    else if (e.key === "ArrowUp") search.current?.focus();
  };

  return (
    <div className="rule-list" data-tour="rule-list" ref={listRef}>
      {top}
      <div className="rule-search-box">
        <input ref={search} className="rule-search" type="search" value={query} aria-label="Search the rules"
          placeholder={heads ? `Search ${properties} properties in ${Object.keys(heads).length} classes` : `Search ${properties} properties`}
          onChange={(e) => setQuery(e.target.value)} onKeyDown={onSearchKey} />
      </div>
      {shown.filter((x) => !searching || x.list.length > 0).map(({ g, open, list }, i, all) => (
        <div key={groupKey(g)} className="rule-group" data-group={g.id} data-class={g.cls}>
          {heads && g.cls && heads[g.cls] && all[i - 1]?.g.cls !== g.cls && (
            <div className="cls-h" data-testid="class-heading">{heads[g.cls].name}<span>{heads[g.cls].sub}</span></div>)}
          <button type="button" className="group-h" aria-expanded={open} disabled={searching}
            onClick={() => setToggled((t) => ({ ...t, [groupKey(g)]: !open }))}>
            <Ico name="chevron" className={`grp-car${open ? " open" : ""}`} />
            <span className="panel-title">{g.label}</span>
            <span className="sub">{searching ? `${list.length} of ${g.rules.length} match` : groupSub(g)}</span>
          </button>
          {open && list.map((r: RuleSummaryX) => {
            const tour = first;
            first = false;
            const notes = r.comments + (r.page_questions ?? 0);
            const child = r.subtitle.startsWith("part of ");  // a child: its parent's name, no path (#8)
            return (
              <div key={r.rule_id}>
              <div className={`rule-item${r.rule_id === active ? " on" : ""}${counts && !counts[r.rule_id] ? " dim" : ""}`} role="button" tabIndex={0}
                data-rule={r.rule_id} onClick={() => onPick(r.rule_id)} onKeyDown={(e) => onItemKey(e, r.rule_id)}>
                <div className="ico" title={r.status} data-tour={tour ? "rule-status" : undefined}><Ico name={r.status} /></div>
                <div style={{ minWidth: 0 }}>
                  <div className="nm">{hit(r.title, q)}{r.record_key && <span className="rl-tag">record key</span>}</div>
                  <div className={`id${r.kind === "property" && !child ? "" : " plain"}`} title={r.subtitle}>
                    {hit(r.subtitle, q)}{r.list && <span className="rl-tag">list</span>}</div>
                </div>
                <div className="meta">
                  {counts
                    ? counts[r.rule_id]
                      ? <Tip delay={1000} width={260} tip={countTip?.(counts[r.rule_id])}>
                          <span className="rev match">{fmt(counts[r.rule_id])}</span></Tip>
                      : <span className="rev match none">—</span>
                    : <span className={`rev${r.reviewed ? "" : " none"}`} title={`${recordNoun(r.rule_id && classOfRule(r.rule_id) || undefined)[1]} with a verdict / all ${recordNoun(classOfRule(r.rule_id) || undefined)[1]}`}
                        data-tour={tour ? "reviewed-count" : undefined}>{fmt(r.reviewed)} / {fmt(r.total)} reviewed</span>}
                  {notes > 0 && <span className="stat open" title="comments and questions for the institution"><Ico name="bubble" />{notes}</span>}
                  {aiStat?.(r)}
                  {(onImprove || (talk && onTalk)) && (
                    <span className="rule-acts">
                      {onImprove && (
                        <Tip width={320} tip={<><span className="hd">Improve {r.title} with AI</span>Claude may make small changes to
                          other rules if this one needs it. Every check covers all {fmt(allRules)} rules.</>}>
                          <button className="cb rule-act" aria-label={`Improve ${r.title} with AI`}
                            onClick={(e) => { e.stopPropagation(); onImprove(r); }}><Ico name="spark" /></button>
                        </Tip>
                      )}
                      {talk && onTalk && (() => {
                        const n = talk.rules[r.rule_id]?.length ?? 0;
                        const on = openTalk === r.rule_id;
                        return (
                          <Tip width={260} tip={n ? `${n} comment${n === 1 ? "" : "s"} on ${r.title} as a whole: open them, or add one`
                            : `Comment on ${r.title} as a whole`}>
                            <button className={"cb rule-act talk" + (n ? " has" : "") + (on ? " on" : "")} aria-expanded={on}
                              aria-label={`Comment on ${r.title}`}
                              onClick={(e) => { e.stopPropagation(); setOpenTalk(on ? null : r.rule_id); }}>
                              <Ico name="open" />{n > 0 && <span className="n">{n}</span>}</button>
                          </Tip>
                        );
                      })()}
                    </span>
                  )}
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
      {folded.length > 0 && <div className="rl-nomatch faint">{joinNames(folded)}: no match</div>}
      {bottom}
    </div>
  );
}
