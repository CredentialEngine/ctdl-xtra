// Left column of the Rules tab (spec §7.2; property-rules spec §4.8): the rule groups, each a button that opens or shuts it
// (`collapsed` starts it shut), one status icon per rule, "14 / 1,062 reviewed". Status appears only here. Search (m4):
// "/" focuses it, it matches a rule's name, its CTDL term and its parent's name; with text the groups open, the ones with
// no match fold into one grey line, Esc clears, ↓ or Enter open a result. With the "Annotated by" filter on (`counts`),
// each rule shows how many of its rows pass it instead (its meaning in a tooltip after a second), and rules with none are
// dimmed (Evals spec §6.7). `top` sits above the groups (the ruleset picker); with `talk`, a thread per rule (opened under it).
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode, type RefObject } from "react";
import type { Discussion, RuleGroup, RulesResponse, Topic } from "../api/types";
import { Ico } from "../shell/icons";
import { fmt } from "../shell/ui";
import type { RuleSummaryX } from "./api";
import { Composer, Thread } from "./Discussion";
import { isField, matchesRule } from "./logic";
import { Tip } from "../evals/EvalsTab";
import { classOfRule, recordNoun } from "../shell/klass";

export type PostTalk = (target: { kind: "rule" | "ruleset"; rule_id: string | null }, note: string, topic: Topic) => Promise<boolean>;

/** All classes (mockup w4-rules-all-classes): a heading per class above its groups, with what it has. */
export interface ClassHead { name: string; sub: string }

export function RuleList(p: RuleListProps) {
  const { list, listRef, search, query, setQuery, onSearchKey } = useRuleList(p);
  const view = list.view;
  return (
    <div className="rule-list" data-tour="rule-list" ref={listRef}>
      {p.top}
      <RuleSearch search={search} query={query} setQuery={setQuery} onKey={onSearchKey} view={view} heads={p.heads} />
      {view.groups.map((x, i, all) => <RuleGroupBlock key={groupKey(x.g)} x={x} previous={all[i - 1]} list={list} />)}
      {view.folded.length > 0 && <div className="rl-nomatch faint">{joinNames(view.folded)}: no match</div>}
      {p.bottom}
    </div>
  );
}

interface RuleListProps {
  rules: RulesResponse; active: string | null; onPick: (id: string) => void; talk?: Discussion | null; onTalk?: PostTalk;
  /** All classes: each class's heading, by class (its groups carry `cls`) */
  heads?: Record<string, ClassHead> | null;
  counts?: Record<string, number> | null; countTip?: (n: number) => string;
  top?: ReactNode; /** after every group: the fix bar (Improve rules with AI…), last so labeling comes first */ bottom?: ReactNode;
  /** ✦ Improve on every row, beside Comment (one-rule-runs §1.1): starts a run on that one rule */
  onImprove?: (r: RuleSummaryX) => void;
  /** a rule's AI status as one more row counter (working, in line, decisions waiting): null for none */
  aiStat?: (r: RuleSummaryX) => ReactNode;
}

interface ShownGroup { g: RuleGroup; open: boolean; list: RuleSummaryX[] }

type ListView = ReturnType<typeof listView>;

interface ListContext extends RuleListProps {
  view: ListView; openTalk: string | null; setOpenTalk: (id: string | null) => void;
  setToggled: (f: (t: Record<string, boolean>) => Record<string, boolean>) => void;
  onItemKey: (e: KeyboardEvent<HTMLDivElement>, id: string) => void;
}

function useRuleList(p: RuleListProps) {
  const [query, setQuery] = useState("");
  const [toggled, setToggled] = useState<Record<string, boolean>>({});  // a group the reader opened or shut
  const [openTalk, setOpenTalk] = useState<string | null>(null);
  const search = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  useSlashFocus(search);
  const view = listView(p.rules, query.trim(), toggled);
  const keys = listKeyHandlers(listRef, search, p.onPick, view.firstResult, setQuery);
  const list: ListContext = { ...p, view, openTalk, setOpenTalk, setToggled, onItemKey: keys.onItemKey };
  return { list, listRef, search, query, setQuery, onSearchKey: keys.onSearchKey };
}

/** The groups as shown: all of them, or while searching only those with a match, open, holding only the matches. */
function listView(rules: RulesResponse, q: string, toggled: Record<string, boolean>) {
  const searching = q !== "";
  const isOpen = (g: RuleGroup) => searching || (toggled[groupKey(g)] ?? !g.collapsed);
  const shown: ShownGroup[] = rules.groups.map((g) => ({ g, open: isOpen(g), list: searching ? g.rules.filter((r) => matchesRule(r, q)) : g.rules }));
  const groups = shown.filter((x) => !searching || x.list.length > 0);
  return {
    q, searching, groups,
    firstResult: searching ? shown.flatMap((x) => x.list)[0] : undefined,
    folded: searching ? shown.filter((x) => x.list.length === 0).map((x) => x.g.label) : [],
    properties: rules.groups.filter((g) => g.kind === "property").reduce((n, g) => n + g.rules.length, 0),
    allRules: rules.groups.reduce((n, g) => n + g.rules.length, 0),
    /** the first rule shown carries the tour's marks */
    tourRule: groups.find((x) => x.open && x.list.length > 0)?.list[0]?.rule_id,
  };
}

/** "/" focuses the search from anywhere (not from inside a field). */
function useSlashFocus(search: RefObject<HTMLInputElement>): void {
  useEffect(() => {
    const on = (e: globalThis.KeyboardEvent) => {
      if (e.key !== "/" || isField(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      e.preventDefault();
      search.current?.focus();
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [search]);
}

/** Esc clears the search, ↓ moves into the rules, Enter opens the first result; ↑ ↓ move between rules. */
function listKeyHandlers(listRef: RefObject<HTMLDivElement>, search: RefObject<HTMLInputElement>, onPick: (id: string) => void,
  firstResult: RuleSummaryX | undefined, setQuery: (q: string) => void) {
  const items = () => [...(listRef.current?.querySelectorAll<HTMLElement>(".rule-item[data-rule]") ?? [])];
  const onSearchKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") { e.stopPropagation(); setQuery(""); }
    else if (e.key === "ArrowDown") { e.preventDefault(); items()[0]?.focus(); }
    else if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); if (firstResult) onPick(firstResult.rule_id); }
  };
  return { onSearchKey, onItemKey: itemKeyHandler(items, onPick, search) };
}

function itemKeyHandler(items: () => HTMLElement[], onPick: (id: string) => void, search: RefObject<HTMLInputElement>) {
  return (e: KeyboardEvent<HTMLDivElement>, id: string) => {
    if (e.key === "Enter") { onPick(id); return; }
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    focusNeighbour(items(), e.currentTarget, e.key === "ArrowDown", search);
  };
}

function focusNeighbour(all: HTMLElement[], from: HTMLElement, down: boolean, search: RefObject<HTMLInputElement>): void {
  const next = all[all.indexOf(from) + (down ? 1 : -1)];
  if (next) next.focus();
  else if (!down) search.current?.focus();
}

function RuleSearch({ search, query, setQuery, onKey, view, heads }: {
  search: RefObject<HTMLInputElement>; query: string; setQuery: (q: string) => void;
  onKey: (e: KeyboardEvent<HTMLInputElement>) => void; view: ListView; heads?: Record<string, ClassHead> | null;
}) {
  return (
    <div className="rule-search-box">
      <input ref={search} className="rule-search" type="search" value={query} aria-label="Search the rules"
        placeholder={heads ? `Search ${view.properties} properties in ${Object.keys(heads).length} classes` : `Search ${view.properties} properties`}
        onChange={(e) => setQuery(e.target.value)} onKeyDown={onKey} />
    </div>
  );
}

function RuleGroupBlock({ x, previous, list }: { x: ShownGroup; previous: ShownGroup | undefined; list: ListContext }) {
  const { g, open } = x;
  const head = list.heads && g.cls && list.heads[g.cls];
  return (
    <div className="rule-group" data-group={g.id} data-class={g.cls}>
      {head && previous?.g.cls !== g.cls && (
        <div className="cls-h" data-testid="class-heading">{head.name}<span>{head.sub}</span></div>)}
      <GroupHeader x={x} list={list} />
      {open && x.list.map((r) => <RuleEntry key={r.rule_id} r={r} list={list} />)}
    </div>
  );
}

function GroupHeader({ x: { g, open, list: matches }, list }: { x: ShownGroup; list: ListContext }) {
  const searching = list.view.searching;
  return (
    <button type="button" className="group-h" aria-expanded={open} disabled={searching}
      onClick={() => list.setToggled((t) => ({ ...t, [groupKey(g)]: !open }))}>
      <Ico name="chevron" className={`grp-car${open ? " open" : ""}`} />
      <span className="panel-title">{g.label}</span>
      <span className="sub">{searching ? `${matches.length} of ${g.rules.length} match` : groupSub(g)}</span>
    </button>
  );
}

/** A rule's line, and under it its thread when open. */
function RuleEntry({ r, list }: { r: RuleSummaryX; list: ListContext }) {
  return (
    <div>
    <RuleItem r={r} list={list} />
    {list.talk && list.onTalk && list.openTalk === r.rule_id && <RuleTalk r={r} talk={list.talk} onTalk={list.onTalk} />}
    </div>
  );
}

function RuleItem({ r, list }: { r: RuleSummaryX; list: ListContext }) {
  const tour = r.rule_id === list.view.tourRule;
  const { counts } = list;
  return (
    <div className={`rule-item${r.rule_id === list.active ? " on" : ""}${counts && !counts[r.rule_id] ? " dim" : ""}`} role="button" tabIndex={0}
      data-rule={r.rule_id} onClick={() => list.onPick(r.rule_id)} onKeyDown={(e) => list.onItemKey(e, r.rule_id)}>
      <div className="ico" title={r.status} data-tour={tour ? "rule-status" : undefined}><Ico name={r.status} /></div>
      <RuleName r={r} q={list.view.q} />
      <RuleMeta r={r} tour={tour} list={list} />
    </div>
  );
}

function RuleName({ r, q }: { r: RuleSummaryX; q: string }) {
  const child = r.subtitle.startsWith("part of ");  // a child: its parent's name, no path (#8)
  return (
    <div style={{ minWidth: 0 }}>
      <div className="nm">{marked(r.title, q)}{r.record_key && <span className="rl-tag">record key</span>}</div>
      <div className={`id${r.kind === "property" && !child ? "" : " plain"}`} title={r.subtitle}>
        {marked(r.subtitle, q)}{r.list && <span className="rl-tag">list</span>}</div>
    </div>
  );
}

function RuleMeta({ r, tour, list }: { r: RuleSummaryX; tour: boolean; list: ListContext }) {
  const notes = r.comments + (r.page_questions ?? 0);
  return (
    <div className="meta">
      {list.counts ? <FilterCount n={list.counts[r.rule_id]} countTip={list.countTip} /> : <ReviewedCount r={r} tour={tour} />}
      {notes > 0 && <span className="stat open" title="comments and questions for the institution"><Ico name="bubble" />{notes}</span>}
      {list.aiStat?.(r)}
      {(list.onImprove || (list.talk && list.onTalk)) && <RuleActs r={r} list={list} />}
    </div>
  );
}

/** With the "Annotated by" filter on: how many of the rule's rows pass it. */
function FilterCount({ n, countTip }: { n: number | undefined; countTip?: (n: number) => string }) {
  if (!n) return <span className="rev match none">—</span>;
  return <Tip delay={1000} width={260} tip={countTip?.(n)}>
    <span className="rev match">{fmt(n)}</span></Tip>;
}

function ReviewedCount({ r, tour }: { r: RuleSummaryX; tour: boolean }) {
  return <span className={`rev${r.reviewed ? "" : " none"}`} title={`${recordNoun(r.rule_id && classOfRule(r.rule_id) || undefined)[1]} with a verdict / all ${recordNoun(classOfRule(r.rule_id) || undefined)[1]}`}
    data-tour={tour ? "reviewed-count" : undefined}>{fmt(r.reviewed)} / {fmt(r.total)} reviewed</span>;
}

function RuleActs({ r, list }: { r: RuleSummaryX; list: ListContext }) {
  return (
    <span className="rule-acts">
      {list.onImprove && <ImproveButton r={r} allRules={list.view.allRules} onImprove={list.onImprove} />}
      {list.talk && list.onTalk && <TalkToggle r={r} talk={list.talk} openTalk={list.openTalk} setOpenTalk={list.setOpenTalk} />}
    </span>
  );
}

function ImproveButton({ r, allRules, onImprove }: { r: RuleSummaryX; allRules: number; onImprove: (r: RuleSummaryX) => void }) {
  return (
    <Tip width={320} tip={<><span className="hd">Improve {r.title} with AI</span>Claude may make small changes to
      other rules if this one needs it. Every check covers all {fmt(allRules)} rules.</>}>
      <button className="cb rule-act" aria-label={`Improve ${r.title} with AI`}
        onClick={(e) => { e.stopPropagation(); onImprove(r); }}><Ico name="spark" /></button>
    </Tip>
  );
}

function TalkToggle({ r, talk, openTalk, setOpenTalk }: {
  r: RuleSummaryX; talk: Discussion; openTalk: string | null; setOpenTalk: (id: string | null) => void;
}) {
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
}

function RuleTalk({ r, talk, onTalk }: { r: RuleSummaryX; talk: Discussion; onTalk: PostTalk }) {
  return (
    <div className="rule-talk" data-testid="rule-talk">
      <Thread items={talk.rules[r.rule_id] ?? []} />
      <Composer placeholder={`A thought about ${r.title} as a whole…`} question
        onPost={(note, topic) => onTalk({ kind: "rule", rule_id: r.rule_id }, note, topic)} />
    </div>
  );
}

/** The search's match in a name or a term, marked (the rest as it is). */
function marked(text: string, query: string): ReactNode {
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
const joinNames = (names: string[]) => (names.length < 2 ? names.join("")
  : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`);
