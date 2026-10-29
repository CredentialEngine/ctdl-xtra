// One changed value in Compare (Evals spec §6.5): the shared value diff (Split by default), From on the left and To on
// the right, with Note… and "The new value is wrong…" (the ✗ flow: select the right text on the page, shown under the
// diff while it's open). Both write to the To side's match, with `compared_with: {kind: "ruleset", ruleset: From, value}`.
import { createContext, useContext, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { BriefRow, ComparedWith, Expected, MatchRow } from "../api/types";
import type { CapturedSelection } from "../pagepane";
import { addCapture, newDraft, verdictEvent, type Draft } from "../rules/logic";
import { toast } from "../shell/ui";
import { comparedChip, DiffModeSwitch, MarkedWrong, NoteActions, useDiffMode, ValueDiff, ValuePage, WrongFlow } from "../valuediff/ValueDiff";

/** What every row of one comparison shares. */
export interface CompareCtxValue { short: string; a: number; b: number; bExtraction: string; me: string }
export const CompareCtx = createContext<CompareCtxValue | null>(null);

export function CompareValue({ r, ruleId, kind, column, head, foot, children }: {
  r: BriefRow; ruleId: string; kind: string; column: string; head: ReactNode; foot?: ReactNode; children?: ReactNode;
}) {
  const cx = useContext(CompareCtx);
  const [mode, setMode] = useDiffMode();
  const [m, setM] = useState<MatchRow | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [marked, setMarked] = useState<MatchRow["verdict"]>(null);
  const field = kind === "field" && !!cx && r.b_value !== null;  // a value gone in To has no row there to annotate
  const compared: ComparedWith | null = cx && { kind: "ruleset", ruleset: cx.a, value: r.a_value };
  const target = { kind: "match" as const, rule_id: ruleId, occurrence_key: r.key, page_stem: r.page_stem };
  const fetchMatch = async () => {
    if (!cx) return null;
    try { const x = await api.match(cx.short, ruleId, r.key, cx.bExtraction); setM(x); return x; }
    catch (e) { toast(`Couldn't load this row: ${String(e)}`); return null; }
  };
  const saveNote = async (note: string) => {
    if (!cx || !compared) return false;
    try {
      await api.annotate(cx.short, { type: "comment", author: cx.me, target, note, compared_with: compared, extraction: cx.bExtraction });
      toast("Note saved");
      return true;
    } catch (e) { toast(`Couldn't save: ${String(e)}`); return false; }
  };
  const openWrong = async () => {
    const x = m ?? await fetchMatch();
    if (x) setDraft(newDraft("wrong", x.verdict, x.state));
  };
  const saveWrong = async () => {
    if (!cx || !compared || !draft) return;
    if (!draft.captures.length) { toast("Select the right text on the page first"); return; }
    try {
      const res = await api.annotate(cx.short, { ...verdictEvent(cx.me, target, m?.verdict ?? null, { draft }), compared_with: compared,
                                                 extraction: cx.bExtraction });
      const ev = res.event as { annotation_id: string; at: string; author: string; note: string | null; expected: Expected | null };
      setMarked({ annotation_id: ev.annotation_id, type: "verdict", verdict: "wrong", author: ev.author, at: ev.at, note: ev.note,
                  expected: ev.expected, rule_version_seen: null, value_seen: r.b_value, compared_with: compared });
      setDraft(null);
      toast("Marked wrong");
    } catch (e) { toast(`Couldn't save: ${String(e)}`); }
  };
  const capture = (c: CapturedSelection) => setDraft((d) => (d ? { ...d, captures: addCapture(d.captures, c) } : d));
  return (
    <div className="cval" data-testid="compare-value">
      <div className="cval-h">{head}<span className="grow" /><DiffModeSwitch mode={mode} onMode={setMode} />{children}</div>
      <ValueDiff a={r.a_value} b={r.b_value} aLabel={cx ? `ruleset v${cx.a}` : "from"} bLabel={cx ? `ruleset v${cx.b}` : "to"} mode={mode} compact={!draft} />
      {foot}
      {field && (marked
        ? <MarkedWrong verdict={marked} what="the new value" column={column} compared={comparedChip(marked.compared_with)} />
        : draft
          ? <>
              <WrongFlow draft={draft} onChange={setDraft} onSave={() => void saveWrong()} onCancel={() => setDraft(null)} />
              <div className="cval-page">
                <ValuePage catalog={cx!.short} stem={r.page_stem} url="" title={r.course_key ?? r.page_stem}
                  golden={{ cssPath: r.css_path, charStart: r.char_start, charEnd: r.char_end, text: r.b_value }} other={r.a_value}
                  captures={draft.captures} capturing onCapture={capture}
                  onRemove={(i) => setDraft((d) => (d ? { ...d, captures: d.captures.filter((_, j) => j !== i) } : d))}
                  labels={{ golden: `ruleset v${cx!.b} value`, other: `ruleset v${cx!.a} value` }} ruleset={cx!.b} />
              </div>
            </>
          : <NoteActions collapsed wrongLabel="The new value is wrong…" onSave={saveNote} onWrong={() => void openWrong()} />)}
    </div>
  );
}
