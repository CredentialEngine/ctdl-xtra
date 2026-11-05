// A list-of-objects row (sme-fixes §5.2, §5.3, picture img/mock-p3-q10-list.png): one sub-row per object, its fields
// side by side with their names small, a ✓ and ✕ each (one ✕ makes the row wrong); the objects reviewers added, each
// with a ✕ to take it back; and "+ Add a duration": select a piece of text on the page, then say which field it is.
// When every field is labelled the object is saved (Save works once the key field and one more are).
// Correcting a found object (phase1-followups §3): click it to select it, select the right text on the page and pick
// its field; the draft shows under it until Save correction.
import type { EventBrief, RowItem } from "../api/types";
import { Ico } from "../shell/icons";
import type { RowX } from "./api";
import { addedObject, addSavable, correctionOf, fieldWord, objectOf, type ObjectAdd, type ObjectFix } from "./claims";
import { clip } from "./logic";
import "./claims.css";

export function ProfileItems({ row, on, fields, keyField, noun, add, fix, onVerdict, onStartAdd, onLabel, onSaveAdd, onCancelAdd,
  onSelectItem, onSaveFix, onCancelFix, onTakeBack }: {
  row: RowX; on: boolean; fields: string[]; keyField: string; noun: string; add: ObjectAdd | null; fix: ObjectFix | null;
  onVerdict: (it: RowItem, verdict: "correct" | "wrong") => void;
  onStartAdd: () => void; onLabel: (field: string) => void; onSaveAdd: () => void; onCancelAdd: () => void;
  onSelectItem: (it: RowItem) => void; onSaveFix: () => void; onCancelFix: () => void; onTakeBack: (added: EventBrief) => void;
}) {
  const items = row.items ?? [];
  const wrong = items.filter((it) => it.state === "wrong").length;
  const stop = (f: () => void) => (e: React.MouseEvent) => { e.stopPropagation(); f(); };
  const cells = (o: Record<string, string>) => fields.map((f) => (
    <span key={f} className={`obj-f${f === keyField ? " key" : ""}`}>
      <span className="obj-v">{o[f] ?? "—"}</span> <span className="obj-k">{fieldWord(f)}</span>
    </span>));
  // an added object has a `missing` verdict; a correction (a found object's ✕ with its answer) shows under that object
  const added = (row.missing_items ?? []).filter((m) => m.verdict === "missing");
  return (
    <div className="items objects" data-testid="objects">
      <div className="obj-head faint">
        <span>{items.length} found</span>
        {wrong > 0 && <span className="obj-wrong">{wrong} ✕ → row wrong</span>}
      </div>
      {items.map((it) => {
        const selected = on && fix?.valueIndex === it.value_index;
        const corrected = correctionOf(it);
        const o = objectOf(it);
        return (
          <div key={it.value_index}>
            <div className={`item obj${it.state ? ` st-${it.state}` : ""}${selected ? " sel" : ""}${on ? " pickable" : ""}`} data-testid="object"
              aria-current={selected || undefined} title={on ? `Click to correct this ${noun} from the page` : undefined}
              onClick={on ? stop(() => onSelectItem(it)) : undefined}>
              <span className="item-n" aria-hidden="true">{it.value_index}</span>
              <span className="obj-fields">{cells(o)}</span>
              <span className="item-btns">
                {selected && <span className="obj-selected">selected</span>}
                <button type="button" className={`ibtn ok${it.state === "correct" ? " on" : ""}`} aria-label={`Correct ${it.value_index}`}
                  title={`Correct: this ${noun} is right, every field`} onClick={stop(() => onVerdict(it, "correct"))}><Ico name="correct" /></button>
                <button type="button" className={`ibtn no${it.state === "wrong" ? " on" : ""}`} aria-label={`Wrong ${it.value_index}`}
                  title={`Wrong: this ${noun} shouldn't be here. To fix one part, select the ${noun} and pick the right text on the page.`}
                  onClick={stop(() => onVerdict(it, "wrong"))}><Ico name="wrong" /></button>
              </span>
            </div>
            {corrected && !selected && (
              <div className="obj-corrected" data-testid="corrected-object" title={`Corrected by ${it.verdict?.author ?? ""}`}>
                <span className="faint">→ corrected</span><span className="obj-fields">{cells(corrected)}</span>
                <span className="faint obj-by">{it.verdict?.author}</span>
              </div>)}
            {selected && (
              <div className="obj-fix" data-testid="object-fix" onClick={(e) => e.stopPropagation()}>
                {Object.keys(fix.fields).length === 0
                  ? <div className="faint">Select the right text on the page, then pick which field it is.</div>
                  : <div className="obj-fix-lines">{fields.filter((f) => fix.fields[f]).map((f) => (
                      <div key={f}><b>Correcting</b> · <span className="obj-k">{fieldWord(f)}</span>{" "}
                        <s className="faint">{clip(o[f] ?? "—", 60)}</s> → <b>{clip(fix.fields[f].text.trim(), 80)}</b></div>))}</div>}
                <div className="ex-btns">
                  <button type="button" className="btn primary save" disabled={!Object.keys(fix.fields).length} onClick={onSaveFix}>
                    Save correction <kbd className="kb-inv">Enter</kbd></button>
                  <button type="button" className="btn cancel" onClick={onCancelFix}>Cancel</button>
                </div>
              </div>)}
          </div>);
      })}
      {added.map((m) => (
        <div key={m.annotation_id} className="item obj added" data-testid="added-object" title={`Added by ${m.author}: the rule missed it`}>
          <span className="item-n" aria-hidden="true">+</span>
          <span className="obj-fields">{cells(addedObject(m))}</span>
          <span className="faint obj-by">{m.author}</span>
          {on && <span className="item-btns">
            <button type="button" className="ibtn no" aria-label={`Remove the added ${noun}`} title={`Remove this ${noun}: take the add back`}
              onClick={stop(() => onTakeBack(m))}><Ico name="wrong" /></button></span>}
        </div>
      ))}
      {on && !add && <button type="button" className="add-item" onClick={stop(onStartAdd)}><Ico name="missing" />Add a {noun}</button>}
      {on && add && (
        <div className="add-obj" data-testid="add-object" onClick={(e) => e.stopPropagation()}>
          <div className="faint">Adding a {noun}: select each piece on the page, then say which field it is.</div>
          <div className="obj-labelled">{fields.map((f) => (
            <span key={f} className={`obj-slot${add.fields[f] ? " done" : ""}`}>
              <span className="obj-k">{fieldWord(f)}</span> {add.fields[f] ? clip(add.fields[f].text, 80) : "—"}
            </span>))}</div>
          {add.pending && (
            <div className="label-bar" role="toolbar" aria-label="Which field is this?">
              <blockquote className="sel-quote">{clip(add.pending.text, 120)}</blockquote>
              {fields.map((f) => (
                <button key={f} type="button" className="btn lbl" title={`This text is the ${fieldWord(f)} of the ${noun} being added`}
                  onClick={() => onLabel(f)}>{fieldWord(f)}</button>))}
            </div>)}
          <div className="ex-btns">
            <button type="button" className="btn primary save" disabled={!addSavable(add, keyField)} onClick={onSaveAdd}
              title={`Save the ${noun} (needs its ${fieldWord(keyField)} and one more field)`}>Save {noun} <kbd className="kb-inv">Enter</kbd></button>
            <button type="button" className="btn cancel" onClick={onCancelAdd}>Cancel</button>
          </div>
        </div>)}
    </div>
  );
}
