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

export function ProfileItems(p: ProfileItemsProps) {
  const items = p.row.items ?? [];
  // an added object has a `missing` verdict; a correction (a found object's ✕ with its answer) shows under that object
  const added = (p.row.missing_items ?? []).filter((m) => m.verdict === "missing");
  return (
    <div className="items objects" data-testid="objects">
      <ObjectsHead items={items} />
      {items.map((it) => <FoundObject key={it.value_index} it={it} p={p} />)}
      {added.map((m) => <AddedObject key={m.annotation_id} m={m} p={p} />)}
      {p.on && !p.add && <button type="button" className="add-item" onClick={stopping(p.onStartAdd)}><Ico name="missing" />Add a {p.noun}</button>}
      {p.on && p.add && <AddObject add={p.add} p={p} />}
    </div>
  );
}

interface ProfileItemsProps {
  row: RowX; on: boolean; fields: string[]; keyField: string; noun: string; add: ObjectAdd | null; fix: ObjectFix | null;
  onVerdict: (it: RowItem, verdict: "correct" | "wrong") => void;
  onStartAdd: () => void; onLabel: (field: string) => void; onSaveAdd: () => void; onCancelAdd: () => void;
  onSelectItem: (it: RowItem) => void; onSaveFix: () => void; onCancelFix: () => void; onTakeBack: (added: EventBrief) => void;
}

function ObjectsHead({ items }: { items: RowItem[] }) {
  const wrong = items.filter((it) => it.state === "wrong").length;
  return (
    <div className="obj-head faint">
      <span>{items.length} found</span>
      {wrong > 0 && <span className="obj-wrong">{wrong} ✕ → row wrong</span>}
    </div>
  );
}

function FoundObject({ it, p }: { it: RowItem; p: ProfileItemsProps }) {
  const selected = p.on && p.fix?.valueIndex === it.value_index;
  const corrected = correctionOf(it);
  const o = objectOf(it);
  return (
    <div>
      <FoundObjectLine it={it} o={o} selected={selected} p={p} />
      {corrected && !selected && <CorrectedObject it={it} corrected={corrected} p={p} />}
      {selected && <ObjectFixDraft fix={p.fix!} o={o} p={p} />}
    </div>
  );
}

function FoundObjectLine({ it, o, selected, p }: { it: RowItem; o: Record<string, string>; selected: boolean; p: ProfileItemsProps }) {
  return (
    <div className={`item obj${it.state ? ` st-${it.state}` : ""}${selected ? " sel" : ""}${p.on ? " pickable" : ""}`} data-testid="object"
      aria-current={selected || undefined} title={p.on ? `Click to correct this ${p.noun} from the page` : undefined}
      onClick={p.on ? stopping(() => p.onSelectItem(it)) : undefined}>
      <span className="item-n" aria-hidden="true">{it.value_index}</span>
      <span className="obj-fields"><ObjectCells o={o} p={p} /></span>
      <span className="item-btns">
        {selected && <span className="obj-selected">selected</span>}
        <ObjectVerdictButtons it={it} p={p} />
      </span>
    </div>
  );
}

function ObjectVerdictButtons({ it, p }: { it: RowItem; p: ProfileItemsProps }) {
  return (<>
    <button type="button" className={`ibtn ok${it.state === "correct" ? " on" : ""}`} aria-label={`Correct ${it.value_index}`}
      title={`Correct: this ${p.noun} is right, every field`} onClick={stopping(() => p.onVerdict(it, "correct"))}><Ico name="correct" /></button>
    <button type="button" className={`ibtn no${it.state === "wrong" ? " on" : ""}`} aria-label={`Wrong ${it.value_index}`}
      title={`Wrong: this ${p.noun} shouldn't be here. To fix one part, select the ${p.noun} and pick the right text on the page.`}
      onClick={stopping(() => p.onVerdict(it, "wrong"))}><Ico name="wrong" /></button>
  </>);
}

function CorrectedObject({ it, corrected, p }: { it: RowItem; corrected: Record<string, string>; p: ProfileItemsProps }) {
  return (
    <div className="obj-corrected" data-testid="corrected-object" title={`Corrected by ${it.verdict?.author ?? ""}`}>
      <span className="faint">→ corrected</span><span className="obj-fields"><ObjectCells o={corrected} p={p} /></span>
      <span className="faint obj-by">{it.verdict?.author}</span>
    </div>
  );
}

function ObjectFixDraft({ fix, o, p }: { fix: ObjectFix; o: Record<string, string>; p: ProfileItemsProps }) {
  const empty = Object.keys(fix.fields).length === 0;
  return (
    <div className="obj-fix" data-testid="object-fix" onClick={(e) => e.stopPropagation()}>
      {empty
        ? <div className="faint">Select the right text on the page, then pick which field it is.</div>
        : <FixLines fix={fix} o={o} fields={p.fields} />}
      <div className="ex-btns">
        <button type="button" className="btn primary save" disabled={empty} onClick={p.onSaveFix}>
          Save correction <kbd className="kb-inv">Enter</kbd></button>
        <button type="button" className="btn cancel" onClick={p.onCancelFix}>Cancel</button>
      </div>
    </div>
  );
}

function FixLines({ fix, o, fields }: { fix: ObjectFix; o: Record<string, string>; fields: string[] }) {
  return (
    <div className="obj-fix-lines">{fields.filter((f) => fix.fields[f]).map((f) => (
      <div key={f}><b>Correcting</b> · <span className="obj-k">{fieldWord(f)}</span>{" "}
        <s className="faint">{clip(o[f] ?? "—", 60)}</s> → <b>{clip(fix.fields[f].text.trim(), 80)}</b></div>))}</div>
  );
}

function AddedObject({ m, p }: { m: EventBrief; p: ProfileItemsProps }) {
  return (
    <div className="item obj added" data-testid="added-object" title={`Added by ${m.author}: the rule missed it`}>
      <span className="item-n" aria-hidden="true">+</span>
      <span className="obj-fields"><ObjectCells o={addedObject(m)} p={p} /></span>
      <span className="faint obj-by">{m.author}</span>
      {p.on && <span className="item-btns">
        <button type="button" className="ibtn no" aria-label={`Remove the added ${p.noun}`} title={`Remove this ${p.noun}: take the add back`}
          onClick={stopping(() => p.onTakeBack(m))}><Ico name="wrong" /></button></span>}
    </div>
  );
}

function AddObject({ add, p }: { add: ObjectAdd; p: ProfileItemsProps }) {
  return (
    <div className="add-obj" data-testid="add-object" onClick={(e) => e.stopPropagation()}>
      <div className="faint">Adding a {p.noun}: select each piece on the page, then say which field it is.</div>
      <LabelledFields add={add} fields={p.fields} />
      {add.pending && <LabelBar pending={add.pending} p={p} />}
      <AddButtons add={add} p={p} />
    </div>
  );
}

function LabelledFields({ add, fields }: { add: ObjectAdd; fields: string[] }) {
  return (
    <div className="obj-labelled">{fields.map((f) => (
      <span key={f} className={`obj-slot${add.fields[f] ? " done" : ""}`}>
        <span className="obj-k">{fieldWord(f)}</span> {add.fields[f] ? clip(add.fields[f].text, 80) : "—"}
      </span>))}</div>
  );
}

function AddButtons({ add, p }: { add: ObjectAdd; p: ProfileItemsProps }) {
  return (
    <div className="ex-btns">
      <button type="button" className="btn primary save" disabled={!addSavable(add, p.keyField)} onClick={p.onSaveAdd}
        title={`Save the ${p.noun} (needs its ${fieldWord(p.keyField)} and one more field)`}>Save {p.noun} <kbd className="kb-inv">Enter</kbd></button>
      <button type="button" className="btn cancel" onClick={p.onCancelAdd}>Cancel</button>
    </div>
  );
}

/** "Which field is this?": the text just selected on the page, and a button per field. */
function LabelBar({ pending, p }: { pending: NonNullable<ObjectAdd["pending"]>; p: ProfileItemsProps }) {
  return (
    <div className="label-bar" role="toolbar" aria-label="Which field is this?">
      <blockquote className="sel-quote">{clip(pending.text, 120)}</blockquote>
      {p.fields.map((f) => (
        <button key={f} type="button" className="btn lbl" title={`This text is the ${fieldWord(f)} of the ${p.noun} being added`}
          onClick={() => p.onLabel(f)}>{fieldWord(f)}</button>))}
    </div>
  );
}

function ObjectCells({ o, p }: { o: Record<string, string>; p: ProfileItemsProps }) {
  return (<>{p.fields.map((f) => (
    <span key={f} className={`obj-f${f === p.keyField ? " key" : ""}`}>
      <span className="obj-v">{o[f] ?? "—"}</span> <span className="obj-k">{fieldWord(f)}</span>
    </span>))}</>);
}

const stopping = (f: () => void) => (e: React.MouseEvent) => { e.stopPropagation(); f(); };
