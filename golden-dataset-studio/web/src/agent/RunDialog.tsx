// "Run with Claude?" with a rule picker (one-rule-runs spec §1.2): the rules to improve, each as its sidebar row with
// a checkbox. Opened from "Improve rules with AI…" (the fix bar), ✦ Improve on a sidebar row (that rule ticked), and
// ✦ Run again in a report (the run's rules ticked). A rule another live run is improving can't be ticked. The note line
// says where the run would stand in the queue (§1.7). When runs are off, the prompt opens instead, as today.
// One class (LearningProgram spec, item 15; mockup w2-run-one-class): the dialog names it, with no switch. All classes
// (w2-run-all-classes): one list with a heading per class, and one run per class with a ticked rule (its own lock).
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { RulesResponse } from "../api/types";
import { openPrompt } from "../prompt/PromptModal";
import { Ico } from "../shell/icons";
import { useReviewer } from "../shell/reviewer";
import { inClass } from "../shell/klass";
import { CLASS_NAME, CLASS_SLUGS, currentClass, type ClassSel, type ClassSlug } from "../shell/router";
import { fmt, toast } from "../shell/ui";
import { agentApi2, type Picker, type PickerRule, type StartResult2 } from "./api";
import { useAgent } from "./state";
import "./agent.css";

export const OPEN_RUN_DIALOG = "studio-run-dialog";
/** Open "Run with Claude?" from anywhere (RunDialogHost listens); `rules`: the ones ticked (default: the picker's). */
export function openRunDialog(rules?: string[]): void {
  window.dispatchEvent(new CustomEvent(OPEN_RUN_DIALOG, { detail: { rules: rules ?? null } }));
}

/** When the server has no picker route: the rules from /rules, ticked when they have open wrong or missing verdicts. */
export function pickerFromRules(rules: RulesResponse): Picker {
  const all = rules.groups.flatMap((g) => g.rules);
  return {
    total_rules: all.length,
    rules: all.map((r) => {
      const open = r.open_wrong + r.open_missing;
      const parts = [open && `${fmt(open)} open`, r.comments && `${fmt(r.comments)} comment${r.comments === 1 ? "" : "s"}`].filter(Boolean);
      return { rule: r.rule_id, name: r.title, status: r.status, reviewed: r.reviewed, total: r.total, ticked: open > 0,
               why: parts.length ? parts.join(", ") : "Nothing open", held_by: null };
    }),
  };
}

export function RunDialogHost({ catalog }: { catalog: string }) {
  const { config } = useAgent();
  const [open, setOpen] = useState<{ rules: string[] | null } | null>(null);
  useEffect(() => {
    const on = (e: Event) => {
      const d = (e as CustomEvent<{ rules: string[] | null }>).detail;
      if (config && !config.enabled) { openPrompt(); return; }
      setOpen({ rules: d?.rules ?? null });
    };
    window.addEventListener(OPEN_RUN_DIALOG, on);
    return () => window.removeEventListener(OPEN_RUN_DIALOG, on);
  }, [config]);
  if (!open) return null;
  return <RunDialog catalog={catalog} initial={open.rules} onClose={() => setOpen(null)} />;
}

/** One class's part of the picker (with All classes, one per class that has rules). */
interface Part { cls: ClassSlug; picker: Picker }
/** The ticked rules, as `<class>:<rule>`, and the rules the dialog was opened on. */
interface Picks { ticked: Set<string>; toggle: (key: string) => void; initial: string[] | null }

interface RunDialogProps { catalog: string; initial: string[] | null; onClose: () => void }

export function RunDialog({ catalog, initial, onClose }: RunDialogProps) {
  const sel = currentClass();
  const { parts, picks } = usePicker(catalog, initial, sel);
  const { busy, start } = useStartRuns(catalog, parts, picks.ticked, onClose);
  useCloseOnEscape(onClose);
  return (
    <div className="ac-back" onClick={onClose}>
      <div className="ac run-ask run-pick-ask" role="dialog" aria-modal="true" aria-labelledby="run-ask-h" onClick={(e) => e.stopPropagation()}>
        <DialogHead sel={sel} onClose={onClose} />
        <DialogBody sel={sel} parts={parts} picks={picks} />
        <DialogFoot ticked={picks.ticked} busy={busy} onClose={onClose} onStart={start} />
      </div>
    </div>
  );
}

function usePicker(catalog: string, initial: string[] | null, sel: ClassSel): { parts: Part[] | null; picks: Picks } {
  const [parts, setParts] = useState<Part[] | null>(null);
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  useEffect(() => {
    let on = true;
    loadParts(catalog, sel).then((ps) => {
      if (!on) return;
      setParts(ps);
      setTicked(initialTicks(ps, initial));
    }, () => { if (on) setParts([]); });
    return () => { on = false; };
  }, [catalog, initial, sel]);
  const toggle = (key: string) => setTicked((t) => toggled(t, key));
  return { parts, picks: { ticked, toggle, initial } };
}

function loadParts(catalog: string, sel: ClassSel): Promise<Part[]> {
  if (sel !== "all") return loadPart(catalog, sel).then((p) => [p]);
  return inClass("course", () => api.catalog(catalog)).then((c) => Promise.all(
    (c.classes ?? []).filter((x) => x.ruleset_version).map((x) => loadPart(catalog, x.slug))));
}

function loadPart(catalog: string, cls: ClassSlug): Promise<Part> {
  return inClass(cls, () => agentApi2.picker(catalog))
    .catch(() => inClass(cls, () => api.rules(catalog)).then(pickerFromRules))
    .then((p) => ({ cls, picker: p }), () => ({ cls, picker: { rules: [] } as Picker }));
}

function initialTicks(parts: Part[], initial: string[] | null): Set<string> {
  const free = (r: PickerRule) => !r.held_by;
  return new Set(parts.flatMap(({ cls, picker }) => picker.rules
    .filter((r) => free(r) && (initial ? initial.includes(r.rule) : r.ticked)).map((r) => pickKey(cls, r))));
}

function toggled(ticked: Set<string>, key: string): Set<string> {
  const x = new Set(ticked);
  if (x.has(key)) x.delete(key); else x.add(key);
  return x;
}

function useStartRuns(catalog: string, parts: Part[] | null, ticked: Set<string>, onClose: () => void) {
  const me = useReviewer();
  const { refresh } = useAgent();
  const [busy, setBusy] = useState(false);
  const start = async () => {
    setBusy(true);
    const results = await startEachClass(catalog, parts ?? [], ticked, me);
    setBusy(false);
    refresh();
    announceRuns(results, onClose);
  };
  return { busy, start };
}

/** One run per class with a ticked rule: each class has its own lock (approved item 15). */
async function startEachClass(catalog: string, parts: Part[], ticked: Set<string>, me: string): Promise<StartResult2[]> {
  const results: StartResult2[] = [];
  for (const { cls, picker } of parts) {
    const ids = picker.rules.filter((r) => ticked.has(pickKey(cls, r))).map((r) => r.rule);
    if (ids.length) results.push(await inClass(cls, () => agentApi2.start(catalog, ids, me)));
  }
  return results;
}

function announceRuns(results: StartResult2[], onClose: () => void): void {
  const bad = results.find((r) => !r.ok);
  if (!bad && results.length) {
    onClose();
    const late = results.some((r) => r.ok && r.queue && r.queue.start_in_min > 0);
    toast(late ? "Your run is in line. The bar above says when it should start." : "Your run starts in a moment. Watch it in the bar above.");
  } else if (bad && !bad.ok) announceRefusal(bad, onClose);
}

function announceRefusal(bad: Exclude<StartResult2, { ok: true }>, onClose: () => void): void {
  if (bad.kind === "fallback") { onClose(); openPrompt(bad.reason || "no answer"); }
  else if (bad.kind === "held") {
    toast(`${bad.rule_name} is already being improved${bad.run ? ` in ${bad.run.started_by}'s run` : ""}. Untick it to run on the others.`);
  } else toast(bad.kind === "busy" ? bad.detail || "Another run is in the way." : bad.detail);
}

function useCloseOnEscape(onClose: () => void): void {
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
}

function DialogHead({ sel, onClose }: { sel: ClassSel; onClose: () => void }) {
  return (
    <div className="ac-head"><h2 id="run-ask-h">{sel === "all" ? "Run with Claude?" : `Run with Claude on ${CLASS_NAME[sel]} rules?`}</h2>
      <button className="ac-x" aria-label="Close" onClick={onClose}>×</button></div>
  );
}

function DialogBody({ sel, parts, picks }: { sel: ClassSel; parts: Part[] | null; picks: Picks }) {
  const one = sel !== "all" ? parts?.[0] : null;
  const note = parts?.find((p) => p.picker.note)?.picker.note ?? null;
  return (
    <div className="ac-body">
      <PickerLead sel={sel} total={one ? one.picker.total_rules ?? one.picker.rules.length : 0} />
      {!parts ? <p className="faint">Loading the rules…</p> : sel === "all" ? <AllClassesList parts={parts} picks={picks} />
        : one && <OneClassList part={one} picks={picks} />}
      {note && <p className="run-note">{note}</p>}
    </div>
  );
}

function PickerLead({ sel, total }: { sel: ClassSel; total: number }) {
  if (sel === "all") {
    return <p>Tick the rules you want improved, in any class. Claude may also make small changes to other rules of the same
                class when that helps, and every check covers the whole class. Classes with nothing ticked stay as they are.</p>;
  }
  const name = CLASS_NAME[sel];
  const others = CLASS_SLUGS.filter((c) => c !== sel).map((c) => CLASS_NAME[c]).join(" and ");
  return <p>Tick the rules you want improved. Claude may also make small changes to other {name} rules when that helps,
                and every check covers all {fmt(total)} of them.{others ? ` ${others} rules stay as they are.` : ""}</p>;
}

/** All classes: each class lists what needs work and what someone reviewed; the rest waits behind "N more rules". */
function AllClassesList({ parts, picks }: { parts: Part[]; picks: Picks }) {
  const [opened, setOpened] = useState<Set<ClassSlug>>(new Set());
  return (
    <div className="rule-list run-pick-list all" data-testid="run-picker">
      {parts.map(({ cls, picker }) => (
        <ClassPicks key={cls} cls={cls} picker={picker} picks={picks} opened={opened.has(cls)}
          onOpen={() => setOpened((o) => new Set([...o, cls]))} />
      ))}
    </div>
  );
}

function ClassPicks({ cls, picker, picks, opened, onOpen }: { cls: ClassSlug; picker: Picker; picks: Picks; opened: boolean; onOpen: () => void }) {
  const rest = restOf(picker, picks.initial);
  const quiet = rest.filter((r) => !r.reviewed && !picks.ticked.has(pickKey(cls, r))).length;
  const needWork = picker.rules.filter((r) => r.ticked).length;
  const row = (r: PickerRule) => <PickRow key={pickKey(cls, r)} cls={cls} rule={r} picks={picks} />;
  return (
    <div data-class={cls}>
      <div className="cls-h">{CLASS_NAME[cls]}<span>{fmt(picker.total_rules ?? picker.rules.length)} rules, {
        needWork === 1 ? "1 needs work" : `${needWork} need work`}</span></div>
      {firstOf(picker, picks.initial).map(row)}
      {rest.filter((r) => opened || r.reviewed > 0 || picks.ticked.has(pickKey(cls, r))).map(row)}
      {!opened && quiet > 0 && <MoreRules count={quiet} onOpen={onOpen} />}
    </div>
  );
}

function MoreRules({ count, onOpen }: { count: number; onOpen: () => void }) {
  return (
    <button type="button" className="run-pick-more" onClick={onOpen}>
      {count === 1 ? "1 more rule" : `${fmt(count)} more rules`} with nothing reviewed</button>
  );
}

function OneClassList({ part: { cls, picker }, picks }: { part: Part; picks: Picks }) {
  const first = firstOf(picker, picks.initial);
  const rest = restOf(picker, picks.initial);
  const row = (r: PickerRule) => <PickRow key={pickKey(cls, r)} cls={cls} rule={r} picks={picks} />;
  return (
    <div className="rule-list run-pick-list" data-testid="run-picker">
      {first.length > 0 && <><div className="group-h"><span className="panel-title">Need work</span></div>
        {first.map(row)}</>}
      {rest.length > 0 && <><div className="group-h"><span className="panel-title">Nothing open</span></div>
        {rest.map(row)}</>}
    </div>
  );
}

function PickRow({ cls, rule: r, picks }: { cls: ClassSlug; rule: PickerRule; picks: Picks }) {
  const held = r.held_by;
  const k = pickKey(cls, r);
  return (
    <label className={`run-pick${held ? " held" : ""}`}>
      <input type="checkbox" checked={picks.ticked.has(k)} disabled={!!held} onChange={() => picks.toggle(k)}
        aria-label={r.name} />
      <PickedRule rule={r} held={!!held} />
    </label>
  );
}

/** The rule as its sidebar row. */
function PickedRule({ rule: r, held }: { rule: PickerRule; held: boolean }) {
  return (
    <div className={`rule-item${held ? " dim" : ""}`} data-rule={r.rule}>
      <div className="ico" title={r.status}><Ico name={r.status} /></div>
      <div style={{ minWidth: 0 }}>
        <div className="nm">{r.name}</div>
        <div className="id plain">{r.why}</div>
      </div>
      <div className="meta"><span className={`rev${r.reviewed ? "" : " none"}`}>{fmt(r.reviewed)} / {fmt(r.total)} reviewed</span></div>
    </div>
  );
}

function DialogFoot({ ticked, busy, onClose, onStart }: { ticked: Set<string>; busy: boolean; onClose: () => void; onStart: () => void }) {
  const n = ticked.size;
  const classesTicked = new Set([...ticked].map((k) => k.split(":")[0]));
  return (
    <div className="ac-foot">
      <button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn primary" onClick={onStart} disabled={busy || n === 0} autoFocus>
        <Ico name="spark" />Run on {n} rule{n === 1 ? "" : "s"}{classesTicked.size > 1 ? ` in ${classesTicked.size} classes` : ""}</button>
    </div>
  );
}

const pickKey = (cls: ClassSlug, r: PickerRule) => `${cls}:${r.rule}`;
const isFirst = (r: PickerRule, initial: string[] | null) => r.ticked || initial?.includes(r.rule);
const firstOf = (p: Picker, initial: string[] | null) => p.rules.filter((r) => isFirst(r, initial));
const restOf = (p: Picker, initial: string[] | null) => p.rules.filter((r) => !isFirst(r, initial));
