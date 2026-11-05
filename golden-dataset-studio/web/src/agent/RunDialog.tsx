// "Run with Claude?" with a rule picker (one-rule-runs spec §1.2): the rules to improve, each as its sidebar row with
// a checkbox. Opened from "Improve rules with AI…" (the fix bar), ✦ Improve on a sidebar row (that rule ticked), and
// ✦ Run again in a report (the run's rules ticked). A rule another live run is improving can't be ticked. The note line
// says where the run would stand in the queue (§1.7). When runs are off, the prompt opens instead, as today.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { RulesResponse } from "../api/types";
import { openPrompt } from "../prompt/PromptModal";
import { Ico } from "../shell/icons";
import { useReviewer } from "../shell/reviewer";
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

export function RunDialog({ catalog, initial, onClose }: {
  catalog: string; initial: string[] | null; onClose: () => void;
}) {
  const me = useReviewer();
  const { refresh } = useAgent();
  const [picker, setPicker] = useState<Picker | null>(null);
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let on = true;
    agentApi2.picker(catalog).catch(() => api.rules(catalog).then(pickerFromRules)).then((p) => {
      if (!on) return;
      setPicker(p);
      const free = (r: PickerRule) => !r.held_by;
      setTicked(new Set(p.rules.filter((r) => free(r) && (initial ? initial.includes(r.rule) : r.ticked)).map((r) => r.rule)));
    }, () => { if (on) setPicker({ rules: [] }); });
    return () => { on = false; };
  }, [catalog, initial]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);

  const all = picker?.rules ?? [];
  const total = picker?.total_rules ?? all.length;
  // rules with something to do first (and any rule asked for), then the rest
  const first = all.filter((r) => r.ticked || initial?.includes(r.rule));
  const rest = all.filter((r) => !first.includes(r));
  const n = ticked.size;
  const toggle = (id: string) => setTicked((t) => { const x = new Set(t); if (x.has(id)) x.delete(id); else x.add(id); return x; });

  const start = async () => {
    setBusy(true);
    const ids = all.filter((r) => ticked.has(r.rule)).map((r) => r.rule);
    const r = await agentApi2.start(catalog, ids, me);
    setBusy(false);
    refresh();
    if (r.ok) {
      onClose();
      toast(r.queue && r.queue.start_in_min > 0 ? "Your run is in line. The bar above says when it should start." : "Your run starts in a moment. Watch it in the bar above.");
    } else if (r.kind === "fallback") { onClose(); openPrompt(r.reason || "no answer"); }
    else if (r.kind === "held") {
      toast(`${r.rule_name} is already being improved${r.run ? ` in ${r.run.started_by}'s run` : ""}. Untick it to run on the others.`);
    } else toast(r.kind === "busy" ? r.detail || "Another run is in the way." : r.detail);
  };

  const item = (r: PickerRule) => {
    const held = r.held_by;
    return (
      <label key={r.rule} className={`run-pick${held ? " held" : ""}`}>
        <input type="checkbox" checked={ticked.has(r.rule)} disabled={!!held} onChange={() => toggle(r.rule)}
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
  const note = picker?.note ?? null;
  return (
    <div className="ac-back" onClick={onClose}>
      <div className="ac run-ask run-pick-ask" role="dialog" aria-modal="true" aria-labelledby="run-ask-h" onClick={(e) => e.stopPropagation()}>
        <div className="ac-head"><h2 id="run-ask-h">Run with Claude?</h2>
          <button className="ac-x" aria-label="Close" onClick={onClose}>×</button></div>
        <div className="ac-body">
          <p>Tick the rules you want improved. Claude may also make small changes to other rules when that helps, and every
            check covers all {fmt(total)} rules.</p>
          {!picker ? <p className="faint">Loading the rules…</p> : (
            <div className="rule-list run-pick-list" data-testid="run-picker">
              {first.length > 0 && <><div className="group-h"><span className="panel-title">Need work</span></div>{first.map(item)}</>}
              {rest.length > 0 && <><div className="group-h"><span className="panel-title">Nothing open</span></div>{rest.map(item)}</>}
            </div>
          )}
          {note && <p className="run-note">{note}</p>}
        </div>
        <div className="ac-foot">
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" onClick={start} disabled={busy || n === 0} autoFocus>
            <Ico name="spark" />Run on {n} rule{n === 1 ? "" : "s"}</button>
        </div>
      </div>
    </div>
  );
}
