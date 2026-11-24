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
import { CLASS_NAME, CLASS_SLUGS, currentClass, type ClassSlug } from "../shell/router";
import { fmt, toast } from "../shell/ui";
import { agentApi2, type Picker, type PickerRule } from "./api";
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

export function RunDialog({ catalog, initial, onClose }: {
  catalog: string; initial: string[] | null; onClose: () => void;
}) {
  const me = useReviewer();
  const { refresh } = useAgent();
  const sel = currentClass();
  const [parts, setParts] = useState<Part[] | null>(null);
  const [ticked, setTicked] = useState<Set<string>>(new Set());  // `<class>:<rule>`
  const [busy, setBusy] = useState(false);
  const [opened, setOpened] = useState<Set<ClassSlug>>(new Set());  // All classes: the classes showing every rule

  useEffect(() => {
    let on = true;
    const one = (cls: ClassSlug) => inClass(cls, () => agentApi2.picker(catalog))
      .catch(() => inClass(cls, () => api.rules(catalog)).then(pickerFromRules))
      .then((p) => ({ cls, picker: p }), () => ({ cls, picker: { rules: [] } as Picker }));
    const load = sel === "all"
      ? inClass("course", () => api.catalog(catalog)).then((c) => Promise.all(
          (c.classes ?? []).filter((x) => x.ruleset_version).map((x) => one(x.slug))))
      : one(sel).then((p) => [p]);
    load.then((ps) => {
      if (!on) return;
      setParts(ps);
      const free = (r: PickerRule) => !r.held_by;
      setTicked(new Set(ps.flatMap(({ cls, picker }) => picker.rules
        .filter((r) => free(r) && (initial ? initial.includes(r.rule) : r.ticked)).map((r) => `${cls}:${r.rule}`))));
    }, () => { if (on) setParts([]); });
    return () => { on = false; };
  }, [catalog, initial, sel]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);

  const n = ticked.size;
  const classesTicked = new Set([...ticked].map((k) => k.split(":")[0]));
  const toggle = (id: string) => setTicked((t) => { const x = new Set(t); if (x.has(id)) x.delete(id); else x.add(id); return x; });

  const start = async () => {
    setBusy(true);
    // one run per class with a ticked rule: each class has its own lock (approved item 15)
    const results = [];
    for (const { cls, picker } of parts ?? []) {
      const ids = picker.rules.filter((r) => ticked.has(`${cls}:${r.rule}`)).map((r) => r.rule);
      if (ids.length) results.push(await inClass(cls, () => agentApi2.start(catalog, ids, me)));
    }
    setBusy(false);
    refresh();
    const bad = results.find((r) => !r.ok);
    if (!bad && results.length) {
      onClose();
      const late = results.some((r) => r.ok && r.queue && r.queue.start_in_min > 0);
      toast(late ? "Your run is in line. The bar above says when it should start." : "Your run starts in a moment. Watch it in the bar above.");
    } else if (bad && !bad.ok) {
      if (bad.kind === "fallback") { onClose(); openPrompt(bad.reason || "no answer"); }
      else if (bad.kind === "held") {
        toast(`${bad.rule_name} is already being improved${bad.run ? ` in ${bad.run.started_by}'s run` : ""}. Untick it to run on the others.`);
      } else toast(bad.kind === "busy" ? bad.detail || "Another run is in the way." : bad.detail);
    }
  };

  const item = (cls: ClassSlug) => (r: PickerRule) => {
    const held = r.held_by;
    const k = `${cls}:${r.rule}`;
    return (
      <label key={k} className={`run-pick${held ? " held" : ""}`}>
        <input type="checkbox" checked={ticked.has(k)} disabled={!!held} onChange={() => toggle(k)}
          aria-label={r.name} />
        <div className={`rule-item${held ? " dim" : ""}`} data-rule={r.rule}>
          <div className="ico" title={r.status}><Ico name={r.status} /></div>
          <div style={{ minWidth: 0 }}>
            <div className="nm">{r.name}</div>
            <div className="id plain">{r.why}</div>
          </div>
          <div className="meta"><span className={`rev${r.reviewed ? "" : " none"}`}>{fmt(r.reviewed)} / {fmt(r.total)} reviewed</span></div>
        </div>
      </label>
    );
  };
  const firstOf = (p: Picker) => p.rules.filter((r) => r.ticked || initial?.includes(r.rule));
  const restOf = (p: Picker) => p.rules.filter((r) => !(r.ticked || initial?.includes(r.rule)));
  // All classes: each class lists what needs work and what someone reviewed; the rest waits behind "N more rules"
  const quiet = (cls: ClassSlug, p: Picker) => restOf(p).filter((r) => !r.reviewed && !ticked.has(`${cls}:${r.rule}`)).length;
  const needWork = (p: Picker) => p.rules.filter((r) => r.ticked).length;
  const one = sel !== "all" ? parts?.[0] : null;
  const total = one ? one.picker.total_rules ?? one.picker.rules.length : 0;
  const name = sel !== "all" ? CLASS_NAME[sel] : "";
  const others = CLASS_SLUGS.filter((c) => c !== sel).map((c) => CLASS_NAME[c]).join(" and ");
  const note = parts?.find((p) => p.picker.note)?.picker.note ?? null;
  return (
    <div className="ac-back" onClick={onClose}>
      <div className="ac run-ask run-pick-ask" role="dialog" aria-modal="true" aria-labelledby="run-ask-h" onClick={(e) => e.stopPropagation()}>
        <div className="ac-head"><h2 id="run-ask-h">{sel === "all" ? "Run with Claude?" : `Run with Claude on ${name} rules?`}</h2>
          <button className="ac-x" aria-label="Close" onClick={onClose}>×</button></div>
        <div className="ac-body">
          {sel === "all"
            ? <p>Tick the rules you want improved, in any class. Claude may also make small changes to other rules of the same
                class when that helps, and every check covers the whole class. Classes with nothing ticked stay as they are.</p>
            : <p>Tick the rules you want improved. Claude may also make small changes to other {name} rules when that helps,
                and every check covers all {fmt(total)} of them.{others ? ` ${others} rules stay as they are.` : ""}</p>}
          {!parts ? <p className="faint">Loading the rules…</p> : sel === "all" ? (
            <div className="rule-list run-pick-list all" data-testid="run-picker">
              {parts.map(({ cls, picker }) => (
                <div key={cls} data-class={cls}>
                  <div className="cls-h">{CLASS_NAME[cls]}<span>{fmt(picker.total_rules ?? picker.rules.length)} rules, {
                    needWork(picker) === 1 ? "1 needs work" : `${needWork(picker)} need work`}</span></div>
                  {firstOf(picker).map(item(cls))}
                  {restOf(picker).filter((r) => opened.has(cls) || r.reviewed > 0 || ticked.has(`${cls}:${r.rule}`)).map(item(cls))}
                  {!opened.has(cls) && quiet(cls, picker) > 0 && (
                    <button type="button" className="run-pick-more" onClick={() => setOpened((o) => new Set([...o, cls]))}>
                      {quiet(cls, picker) === 1 ? "1 more rule" : `${fmt(quiet(cls, picker))} more rules`} with nothing reviewed</button>)}
                </div>
              ))}
            </div>
          ) : one && (
            <div className="rule-list run-pick-list" data-testid="run-picker">
              {firstOf(one.picker).length > 0 && <><div className="group-h"><span className="panel-title">Need work</span></div>
                {firstOf(one.picker).map(item(one.cls))}</>}
              {restOf(one.picker).length > 0 && <><div className="group-h"><span className="panel-title">Nothing open</span></div>
                {restOf(one.picker).map(item(one.cls))}</>}
            </div>
          )}
          {note && <p className="run-note">{note}</p>}
        </div>
        <div className="ac-foot">
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" onClick={start} disabled={busy || n === 0} autoFocus>
            <Ico name="spark" />Run on {n} rule{n === 1 ? "" : "s"}{classesTicked.size > 1 ? ` in ${classesTicked.size} classes` : ""}</button>
        </div>
      </div>
    </div>
  );
}
