// One changed value in Compare (Evals spec §6.5): the shared value diff (Split by default), From on the left and To on
// the right, with Note… and "The new value is wrong…" (the ✗ flow: select the right text on the page, shown under the
// diff while it's open). Both write to the To side's match, with `compared_with: {kind: "ruleset", ruleset: From, value}`.
import { createContext, useContext, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { BriefRow, ComparedWith, EventBrief, Expected, MatchRow } from "../api/types";
import { addCapture, newDraft, verdictEvent, type Draft } from "../rules/logic";
import { toast } from "../shell/ui";
import { comparedChip, MarkedWrong, NoteActions, useDiffMode, ValueDiff, ValuePage, WrongFlow } from "../valuediff/ValueDiff";

/** What every row of one comparison shares. */
export interface CompareCtxValue { short: string; a: number; b: number; bExtraction: string; me: string }
export const CompareCtx = createContext<CompareCtxValue | null>(null);

interface CompareValueProps { r: BriefRow; ruleId: string; kind: string; column: string; head: ReactNode; foot?: ReactNode; children?: ReactNode }
interface ValueSave {
  cx: CompareCtxValue; r: BriefRow; compared: ComparedWith;
  target: { kind: "match"; rule_id: string; occurrence_key: string; page_stem: string };
}
type Annotations = ReturnType<typeof useValueAnnotations>;
type WrongEvent = { annotation_id: string; at: string; author: string; note: string | null; expected: Expected | null };

export function CompareValue({ r, ruleId, kind, column, head, foot, children }: CompareValueProps) {
  const cx = useContext(CompareCtx);
  const mode = useDiffMode();
  const notes = useValueAnnotations(cx, r, ruleId);
  const annotatable = kind === "property" && !!cx && r.b_value !== null;  // a value gone in To has no row there to annotate
  return (
    <div className="cval" data-testid="compare-value">
      <div className="cval-h">{head}<span className="grow" />{children}</div>
      <ValueDiff a={r.a_value} b={r.b_value} aLabel={cx ? `ruleset v${cx.a}` : "from"} bLabel={cx ? `ruleset v${cx.b}` : "to"} mode={mode} compact={!notes.draft} />
      {foot}
      {annotatable && <ValueActions cx={cx!} r={r} column={column} notes={notes} />}
    </div>
  );
}

function useValueAnnotations(cx: CompareCtxValue | null, r: BriefRow, ruleId: string) {
  const [match, setMatch] = useState<MatchRow | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [marked, setMarked] = useState<MatchRow["verdict"]>(null);
  const save = valueSave(cx, r, ruleId);
  const onMarked = (verdict: EventBrief) => { setMarked(verdict); setDraft(null); };
  return { draft, setDraft, marked,
    saveNote: (note: string) => saveNote(save, note),
    openWrong: () => openWrong(save, match, setMatch, setDraft),
    saveWrong: () => submitWrong(save, match, draft, onMarked) };
}

function ValueActions({ cx, r, column, notes }: { cx: CompareCtxValue; r: BriefRow; column: string; notes: Annotations }) {
  if (notes.marked) return <MarkedWrong verdict={notes.marked} what="the new value" column={column} compared={comparedChip(notes.marked.compared_with)} />;
  if (notes.draft) return <WrongDraft cx={cx} r={r} draft={notes.draft} notes={notes} />;
  return <NoteActions collapsed wrongLabel="The new value is wrong…" onSave={notes.saveNote} onWrong={() => void notes.openWrong()} />;
}

function valueSave(cx: CompareCtxValue | null, r: BriefRow, ruleId: string): ValueSave | null {
  if (!cx) return null;
  return { cx, r, compared: { kind: "ruleset", ruleset: cx.a, value: r.a_value },
    target: { kind: "match", rule_id: ruleId, occurrence_key: r.key, page_stem: r.page_stem } };
}

async function saveNote(save: ValueSave | null, note: string): Promise<boolean> {
  if (!save) return false;
  const { cx, target, compared } = save;
  try {
    await api.annotate(cx.short, { type: "comment", author: cx.me, target, note, compared_with: compared, extraction: cx.bExtraction });
    toast("Note saved");
    return true;
  } catch (e) { toast(`Couldn't save: ${String(e)}`); return false; }
}

async function openWrong(save: ValueSave | null, match: MatchRow | null, setMatch: (m: MatchRow) => void, setDraft: (d: Draft) => void) {
  const x = match ?? await loadMatch(save, setMatch);
  if (x) setDraft(newDraft("wrong", x.verdict, x.state));
}

async function submitWrong(save: ValueSave | null, match: MatchRow | null, draft: Draft | null, onMarked: (verdict: EventBrief) => void) {
  if (!save || !draft) return;
  if (!draft.captures.length) { toast("Select the right text on the page first"); return; }
  try {
    onMarked(await saveWrong(save, match?.verdict ?? null, draft));
    toast("Marked wrong");
  } catch (e) { toast(`Couldn't save: ${String(e)}`); }
}

function WrongDraft({ cx, r, draft, notes: { setDraft, saveWrong } }: { cx: CompareCtxValue; r: BriefRow; draft: Draft; notes: Annotations }) {
  return <>
    <WrongFlow draft={draft} onChange={setDraft} onSave={() => void saveWrong()} onCancel={() => setDraft(null)} />
    <div className="cval-page">
      <ValuePage catalog={cx.short} stem={r.page_stem} url="" title={r.record_external_identifier ?? r.page_stem}
        golden={{ cssPath: r.css_path, charStart: r.char_start, charEnd: r.char_end, text: r.b_value }} other={r.a_value}
        captures={draft.captures} capturing onCapture={(c) => setDraft((d) => (d ? { ...d, captures: addCapture(d.captures, c) } : d))}
        onRemove={(i) => setDraft((d) => (d ? { ...d, captures: d.captures.filter((_, j) => j !== i) } : d))}
        labels={{ golden: `ruleset v${cx.b} value`, other: `ruleset v${cx.a} value` }} ruleset={cx.b} />
    </div>
  </>;
}

async function loadMatch(save: ValueSave | null, setMatch: (m: MatchRow) => void): Promise<MatchRow | null> {
  if (!save) return null;
  try { const x = await api.match(save.cx.short, save.target.rule_id, save.r.key, save.cx.bExtraction); setMatch(x); return x; }
  catch (e) { toast(`Couldn't load this row: ${String(e)}`); return null; }
}

async function saveWrong({ cx, r, target, compared }: ValueSave, verdict: MatchRow["verdict"], draft: Draft): Promise<EventBrief> {
  const res = await api.annotate(cx.short, { ...verdictEvent(cx.me, target, verdict, { draft }), compared_with: compared,
                                             extraction: cx.bExtraction });
  return markedVerdict(res.event as WrongEvent, r, compared);
}

function markedVerdict(ev: WrongEvent, r: BriefRow, compared: ComparedWith): EventBrief {
  return { annotation_id: ev.annotation_id, type: "verdict", verdict: "wrong", author: ev.author, at: ev.at, note: ev.note,
           expected: ev.expected, rule_version_seen: null, value_seen: r.b_value, compared_with: compared };
}
