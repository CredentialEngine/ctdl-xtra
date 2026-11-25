// One value: the diff, the note box, the page.
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { ExtractOutputs, MatchRow, ScoreDoc, ScoreRow } from "../api/types";
import { addCapture, newDraft, verdictEvent, type Draft } from "../rules/logic";
import { href } from "../shell/router";
import { Ico, toast } from "../shell/ui";
import { fmtDay } from "../valuediff/diff";
import { comparedChip, MarkedWrong, NoteActions, RowNotes, useDiffMode, ValueDiff, ValuePage, WrongFlow } from "../valuediff/ValueDiff";

interface RowPanelProps {
  row: ScoreRow; doc: ScoreDoc; catalog: string; ruleset: number; goldenLabel: string; outputDay: string; idx: ExtractOutputs;
  me: string; onClose: () => void;
}
type RowValue = ReturnType<typeof useRowValue>;
interface RowSave {
  catalog: string; me: string; target: ReturnType<typeof matchTarget> | null;
  compared: { kind: "extract"; score: string; value: string | null }; reload: () => void;
}

export function RowPanel({ row, doc, catalog, ruleset, goldenLabel, outputDay, idx, me, onClose }: RowPanelProps) {
  const mode = useDiffMode();
  const value = useRowValue(catalog, row, doc, me);
  return (
    <section className="evx-panel" data-testid="row-panel">
      <RowPanelHeader row={row} catalog={catalog} onClose={onClose} />
      <ScrollingBody>
        <ValueDiff a={row.golden_value} b={row.extracted_value} aLabel={goldenLabel} bLabel={`extract output ${outputDay}`}
          mode={mode} bEmpty="nothing extracted" />
        <RowAnnotations row={row} value={value} idx={idx} />
        <RowPage row={row} catalog={catalog} ruleset={ruleset} value={value} />
      </ScrollingBody>
    </section>
  );
}

function useRowValue(catalog: string, row: ScoreRow, doc: ScoreDoc, me: string) {
  const { match, reload } = useMatch(catalog, row);
  const [draft, setDraft] = useState<Draft | null>(null);
  const target = match && matchTarget(match);
  const save: RowSave = { catalog, me, target, compared: { kind: "extract", score: doc.id, value: row.extracted_value }, reload };
  return { match, draft, setDraft, target,
    saveNote: (note: string) => saveNote(save, note),
    saveWrong: () => saveWrong(save, match, draft, () => setDraft(null)) };
}

function RowPanelHeader({ row, catalog, onClose }: { row: ScoreRow; catalog: string; onClose: () => void }) {
  return (
    <header className="evx-panel-h">
      <b>{row.golden_record_id}</b><span className="mono">{row.column}</span>
      <span className="evx-out"><i className={`sw o-${row.outcome}`} />{row.outcome}{row.similarity !== null && row.outcome !== "match" ? ` · ${row.similarity.toFixed(2)}` : ""}</span>
      <span className="grow" />
      {row.rule_id && <a className="muted small" href={href(catalog, "rules", row.rule_id, { row: row.occurrence_key })}>Open in Rules →</a>}
      <button className="evx-icon" onClick={onClose} title="Close" aria-label="Close">✕</button>
    </header>
  );
}

function ScrollingBody({ children }: { children: ReactNode }) {
  const [atEnd, setAtEnd] = useState(false);
  return <>
    <div className="evx-panel-b" onScroll={(e) => setAtEnd(scrolledToEnd(e.currentTarget))}>{children}</div>
    <div className={"evx-more" + (atEnd ? " gone" : "")} aria-hidden>Scroll for more <Ico name="chevron" /></div>
  </>;
}

function RowAnnotations({ row, value, idx }: { row: ScoreRow; value: RowValue; idx: ExtractOutputs }) {
  const outputOf = (score: string) => outputDayOf(idx, score);
  return <>
    <RowVerdict row={row} value={value} outputOf={outputOf} />
    {!row.rule_id && <p className="faint small">This value has no row in the Studio's latest extraction, so it can't be annotated here.</p>}
    {value.match && <RowNotes comments={value.match.comments} label={(c) => comparedChip(c.compared_with, outputOf)} />}
  </>;
}

function RowPage({ row, catalog, ruleset, value: { draft, setDraft } }: { row: ScoreRow; catalog: string; ruleset: number; value: RowValue }) {
  return <ValuePage catalog={catalog} stem={row.page_stem} url={row.source_url ?? ""} title={row.golden_record_id ?? row.page_stem}
    golden={{ cssPath: row.golden_css_path, charStart: row.golden_char_start, charEnd: row.golden_char_end, text: row.golden_value }}
    other={row.outcome === "match" ? null : row.extracted_value} captures={draft?.captures ?? []} capturing={!!draft}
    onCapture={(c) => setDraft((d) => (d ? { ...d, captures: addCapture(d.captures, c) } : d))}
    onRemove={(i) => setDraft((d) => (d ? { ...d, captures: d.captures.filter((_, j) => j !== i) } : d))}
    labels={{ golden: "golden value", other: "extracted value" }} ruleset={ruleset} />;
}

function useMatch(catalog: string, row: ScoreRow) {
  const [match, setMatch] = useState<MatchRow | null>(null);
  const reload = useCallback(() => {
    if (!row.rule_id || !row.occurrence_key) return;
    api.match(catalog, row.rule_id, row.occurrence_key).then(setMatch, () => setMatch(null));
  }, [catalog, row.rule_id, row.occurrence_key]);
  useEffect(() => { reload(); }, [reload]);
  return { match, reload };
}

function matchTarget(m: MatchRow) {
  return { kind: "match" as const, rule_id: m.rule_id, occurrence_key: m.occurrence_key, page_stem: m.page_stem };
}

async function saveNote({ catalog, me, target, compared, reload }: RowSave, note: string): Promise<boolean> {
  if (!target) return false;
  try {
    await api.annotate(catalog, { type: "comment", author: me, target, note, compared_with: compared });
    toast("Note saved");
    reload();
    return true;
  } catch (e) { toast(`Couldn't save: ${String(e)}`); return false; }
}

async function saveWrong({ catalog, me, target, compared, reload }: RowSave, match: MatchRow | null, draft: Draft | null, clearDraft: () => void) {
  if (!target || !match || !draft) return;
  if (!draft.captures.length) { toast("Select the right text on the page first"); return; }
  try {
    await api.annotate(catalog, { ...verdictEvent(me, target, match.verdict, { draft }), compared_with: compared });
    toast("Marked wrong");
    clearDraft();
    reload();
  } catch (e) { toast(`Couldn't save: ${String(e)}`); }
}

function RowVerdict({ row, value, outputOf }: { row: ScoreRow; value: RowValue; outputOf: (score: string) => string | null }) {
  const { match, draft, setDraft, target } = value;
  const marked = match?.state === "wrong" && match.verdict?.verdict === "wrong" ? match.verdict : null;
  if (marked) return <MarkedWrong verdict={marked} what="the golden value" column={row.column} compared={comparedChip(marked.compared_with, outputOf)} />;
  if (draft) return <WrongFlow draft={draft} onChange={setDraft} onSave={() => void value.saveWrong()} onCancel={() => setDraft(null)} />;
  return <NoteActions wrongLabel="The golden value is wrong…" onSave={value.saveNote} disabled={!target}
    onWrong={() => match && setDraft(newDraft("wrong", match.verdict, match.state))} />;
}

function outputDayOf(idx: ExtractOutputs, score: string): string | null {
  const o = idx.outputs.find((x) => x.scores.some((s) => s.id === score));
  return o ? fmtDay(o.last_modified) : null;
}

function scrolledToEnd(el: HTMLElement): boolean {
  return el.scrollTop + el.clientHeight >= el.scrollHeight - 24;
}
