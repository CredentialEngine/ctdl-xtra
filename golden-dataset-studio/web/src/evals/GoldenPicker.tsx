// Rule-matched: a searchable dropdown of silver datasets (one per ruleset version), the latest first with "(latest)"
// (older ones with their date); drafts (unpublished extractions) are tucked away under their own heading, never first.
import { useEffect, useRef, useState } from "react";
import type { GoldenChoice } from "../api/types";
import { Ico } from "../shell/ui";
import { fmtDayTime } from "../valuediff/diff";
import { goldenName } from "./score";

interface GoldenPickerProps { goldens: GoldenChoice[]; value: string; onPick: (id: string) => void }
type Picker = ReturnType<typeof usePicker>;

export function GoldenPicker({ goldens, value, onPick }: GoldenPickerProps) {
  const picker = usePicker();
  const cur = goldens.find((z) => z.id === value);
  const pick = (id: string) => { onPick(id); picker.setOpen(false); picker.setQuery(""); };
  return (
    <span className="evx-dd" ref={picker.box}>
      <button className="evx-gchip big dd" aria-haspopup="listbox" aria-expanded={picker.open} onClick={() => picker.setOpen(!picker.open)}>
        <PickedGolden cur={cur} value={value} />
        <Ico name="chevron" className="evx-caret" />
      </button>
      {picker.open && <GoldenMenu goldens={goldens} value={value} cur={cur} picker={picker} onPick={pick} />}
    </span>
  );
}

function usePicker() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [drafts, setDrafts] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const off = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", off);
    return () => document.removeEventListener("mousedown", off);
  }, [open]);
  return { open, setOpen, query, setQuery, drafts, setDrafts, box };
}

function PickedGolden({ cur, value }: { cur: GoldenChoice | undefined; value: string }) {
  return <>
    {cur ? goldenLabel(cur) : value ? goldenName(value) : "No silver dataset"}
    {cur && <span className="evx-gchip-d"> {cur.kind === "draft" ? "· unpublished" : cur.latest ? "(latest)" : `· ${fmtDayTime(cur.published_at)}`}</span>}
  </>;
}

function GoldenMenu({ goldens, value, cur, picker, onPick }: GoldenPickerProps & { cur: GoldenChoice | undefined; picker: Picker }) {
  const hit = (z: GoldenChoice) => matchesQuery(z, picker.query);
  const versions = goldens.filter((z) => z.kind === "version" && hit(z));
  const drafts = goldens.filter((z) => z.kind === "draft" && hit(z));
  const expanded = picker.drafts || (!!picker.query && drafts.length > 0) || cur?.kind === "draft";
  const item = (z: GoldenChoice) => <GoldenItem key={z.id} golden={z} on={z.id === value} onPick={onPick} />;
  return (
    <div className="evx-dd-m" role="listbox">
      <input className="evx-dd-q" placeholder="Find a silver dataset" value={picker.query} autoFocus onChange={(e) => picker.setQuery(e.target.value)} />
      {versions.map(item)}
      {!versions.length && !picker.query && <p className="muted evx-dd-none">No silver dataset published yet.</p>}
      {drafts.length > 0 && <DraftGoldens drafts={drafts} expanded={expanded} item={item} onExpand={() => picker.setDrafts(true)} />}
    </div>
  );
}

function DraftGoldens({ drafts, expanded, item, onExpand }: {
  drafts: GoldenChoice[]; expanded: boolean; item: (z: GoldenChoice) => JSX.Element; onExpand: () => void;
}) {
  return expanded
    ? <><div className="evx-dd-h">Drafts · unpublished extractions, scored as if published</div>{drafts.map(item)}</>
    : <button className="evx-dd-more" onClick={onExpand}>Drafts ({drafts.length}) <Ico name="chevron-right" /></button>;
}

function GoldenItem({ golden, on, onPick }: { golden: GoldenChoice; on: boolean; onPick: (id: string) => void }) {
  return (
    <button className={`evx-dd-i${on ? " on" : ""}${golden.kind === "draft" ? " draft" : ""}`} onClick={() => onPick(golden.id)}>
      <span>{goldenLabel(golden)}</span><span className="muted">{goldenWhen(golden)}</span>
    </button>
  );
}

function matchesQuery(z: GoldenChoice, query: string): boolean {
  return !query || `${goldenLabel(z)} ${z.id}`.toLowerCase().includes(query.toLowerCase());
}

function goldenLabel(z: GoldenChoice): string {
  return z.kind === "draft" ? `draft ${z.id}` : goldenName(z.id);
}

function goldenWhen(z: GoldenChoice): string {
  return z.kind === "draft" ? `ruleset v${z.ruleset_version}, unpublished` : z.latest ? "(latest)" : fmtDayTime(z.published_at);
}
