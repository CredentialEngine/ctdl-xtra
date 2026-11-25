// A list property's row (property-rules spec §4.4, m2): one line per item, each with its own ✓ and ✕; the items the rule
// missed under it; and "＋ Select a missing item on the page" on the selected row, which adds one by a selection there.
import type { RowItem } from "../api/types";
import type { CapturedSelection } from "../pagepane";
import { Ico } from "../shell/icons";
import type { RowX } from "./api";
import { clip } from "./logic";

/** A missing item being added: the text selected on the page, once there is one. */
export interface ItemAdd { capture: CapturedSelection | null }

export function ListItems({ row, on, add, onVerdict, onStartAdd, onSaveAdd, onCancelAdd }: {
  row: RowX; on: boolean; add: ItemAdd | null; onVerdict: (it: RowItem, verdict: "correct" | "wrong") => void;
  onStartAdd: () => void; onSaveAdd: () => void; onCancelAdd: () => void;
}) {
  const items = row.items ?? [];
  return (
    <div className="items" data-testid="items">
      {items.map((it) => <ItemLine key={it.value_index} it={it} onVerdict={onVerdict} />)}
      <ItemsMeta items={items} canAdd={on && !add} onStartAdd={onStartAdd} />
      {on && add && <AddItem add={add} onSave={onSaveAdd} onCancel={onCancelAdd} />}
      <MissingItems missing={row.missing_items ?? []} />
    </div>
  );
}

function ItemLine({ it, onVerdict }: { it: RowItem; onVerdict: (it: RowItem, verdict: "correct" | "wrong") => void }) {
  return (
    <div className={`item${it.state ? ` st-${it.state}` : ""}`} data-testid="item">
      <span className="item-n" aria-hidden="true">{it.value_index}</span>
      <span className="item-v">{it.value}</span>
      <span className="item-btns">
        <button type="button" className={`ibtn ok${it.state === "correct" ? " on" : ""}`} aria-label={`Correct ${it.value}`}
          title="Correct: this item is right" onClick={stopping(() => onVerdict(it, "correct"))}><Ico name="correct" /></button>
        <button type="button" className={`ibtn no${it.state === "wrong" ? " on" : ""}`} aria-label={`Wrong ${it.value}`}
          title="Wrong: this item shouldn't be here" onClick={stopping(() => onVerdict(it, "wrong"))}><Ico name="wrong" /></button>
      </span>
    </div>
  );
}

function ItemsMeta({ items, canAdd, onStartAdd }: { items: RowItem[]; canAdd: boolean; onStartAdd: () => void }) {
  const ticked = items.filter((it) => it.state === "correct").length;
  return (
    <div className="items-meta">
      <span className="faint">{items.length} {items.length === 1 ? "item" : "items"} · {ticked} ✓</span>
      {canAdd && <button type="button" className="add-item" onClick={stopping(onStartAdd)}><Ico name="missing" />Select a missing item on the page</button>}
    </div>
  );
}

function AddItem({ add, onSave, onCancel }: { add: ItemAdd; onSave: () => void; onCancel: () => void }) {
  const cancel = <button type="button" className="btn cancel" onClick={stopping(onCancel)}>Cancel</button>;
  if (!add.capture) return <div className="add-item-q faint">Drag across the missing item on the page.{cancel}</div>;
  return (
    <div className="add-item-q" data-testid="add-item">
      <blockquote className="sel-quote">{clip(add.capture.text)}</blockquote>
      <button type="button" className="btn primary save" onClick={stopping(onSave)}>Save missing item <kbd className="kb-inv">Enter</kbd></button>
      {cancel}
    </div>
  );
}

function MissingItems({ missing }: { missing: NonNullable<RowX["missing_items"]> }) {
  if (!missing.length) return null;
  return (
    <div className="missing-items"><span className="faint">Missed by the rule:</span>{missing.map((m) => (
      <span key={m.annotation_id} className="mi">“{clip(m.expected?.text ?? "", 90)}”</span>))}</div>
  );
}

const stopping = (f: () => void) => (e: React.MouseEvent) => { e.stopPropagation(); f(); };
