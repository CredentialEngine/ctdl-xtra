// The highlight bar's buttons on the Rules tab (sme-fixes §1, §5.3; phase1-followups §3.1): for a value, 💬, ✓ In answer
// and ✕ Not in answer; for a list of objects, 💬 and the object's field names.
import type { Dispatch, SetStateAction } from "react";
import type { BarAction, CapturedSelection } from "../pagepane";
import { Ico } from "../shell/icons";
import type { RowX } from "./api";
import { fieldWord } from "./claims";
import { newDraft, type Draft, type DraftMode } from "./logic";
import type { MissedState } from "./MissedPanel";

type SetDraft = Dispatch<SetStateAction<Draft | null>>;
type SetMissed = Dispatch<SetStateAction<MissedState | null>>;
type Mark = (polarity: "in" | "out") => (c: CapturedSelection) => void;

export function answerBarActions(row: RowX, mark: Mark, setMissed: SetMissed, setDraft: SetDraft): BarAction[] {
  return [
    commentAction(row, ANSWER_COMMENT, ["comment", "wrong"], setMissed, setDraft),
    { id: "in", label: "✓ In answer", tone: "in", title: "Mark this text as part of the right answer (outlined green). Several pieces can be combined; Enter saves the row as ✗ with this answer.",
      run: mark("in") },
    { id: "out", label: "✕ Not in answer", tone: "out", title: "Mark this text as not part of the right answer (red dashed). The row becomes ✗.",
      run: mark("out") },
  ];
}

/** While adding or correcting an object, the object's field names instead of In / Not in, and 💬; with neither under
 * way, a note saying how to start (nothing is dropped silently). */
export function fieldBarActions(c: FieldBar): BarAction[] {
  const comment = commentAction(c.row, FIELD_COMMENT, ["comment"], c.setMissed, c.setDraft);
  if (!c.objectUnderWay) return [comment, { id: "pick-first", label: `Select a ${c.noun} first, or + Add a ${c.noun}`,
    title: `To correct a ${c.noun}, click it under the row first; to add one the rule missed, use + Add a ${c.noun}.`, run: () => {} }];
  return [comment, ...c.fields.map((f) => ({
    id: `field-${f}`, label: fieldWord(f), tone: "in" as const, run: (s: CapturedSelection) => c.onField(f, s),
    title: c.fixing ? `This text is the right ${fieldWord(f)} of the selected ${c.noun}` : `Label this text as the ${fieldWord(f)} of the ${c.noun} you're adding`,
  }))];
}

export interface FieldBar {
  row: RowX; noun: string; fields: string[]; objectUnderWay: boolean; fixing: boolean;
  onField: (field: string, s: CapturedSelection) => void; setMissed: SetMissed; setDraft: SetDraft;
}

const ANSWER_COMMENT = "Comment on this text: the comment is pinned to it on the page (a numbered bubble). Then ✓ or ✕ to say whether it is in the answer, or just save the comment.";
const FIELD_COMMENT = "Comment on this text: the comment is pinned to it on the page (a numbered bubble).";

/** 💬: a comment pinned to the selected text; a draft of one of the `keeps` modes keeps going with it. */
function commentAction(row: RowX, title: string, keeps: DraftMode[], setMissed: SetMissed, setDraft: SetDraft): BarAction {
  return { id: "comment", label: <Ico name="bubble" />, tone: "note", keepOpen: true, title,
    run: (c: CapturedSelection) => {
      setMissed(null);
      setDraft((d) => ({ ...(d && keeps.includes(d.mode) ? d : newDraft("comment", row.verdict, row.state)), anchor: c }));
    } };
}
