// "Annotated by" (Evals spec §6.7, §6.8), shared by the Rules and Records tabs and kept in the URL (?by=…&v=…):
// a searchable dropdown of people grouped by role, each with the property values they annotated, plus "Not annotated
// yet", "Any subject matter expert", "Any engineer" and "Any engineer · waiting for an expert"; the verdict switch beside it (Rules tab); the line a row shows when
// an expert confirmed its value (human-reviewed) or only an engineer did (engineer-checked); the experts' note.
import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import type { ReviewMarks } from "../api/types";
import { Ico } from "../shell/icons";
import { fmt } from "../shell/ui";
import type { Annotators } from "./api";
import { BY_ENGINEERS, BY_EXPERTS, BY_NOBODY, BY_WAITING, byLabel, shortWhen } from "./logic";

const VERDICTS: { id: string | null; name: string }[] = [
  { id: null, name: "Any" }, { id: "correct", name: "✓ correct" }, { id: "wrong", name: "✕ wrong" }, { id: "note", name: "note" }];

export function AnnotatedBy({ people, by, me, onPick, bare }: AnnotatedByProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const box = useRef<HTMLDivElement>(null);
  useCloseOnClickAway(open, box, setOpen);
  const option = optionRenderer(by, me, query, (v) => { onPick(v); setOpen(false); setQuery(""); });
  return (
    <div className="ab" ref={box} data-testid="annotated-by">
      <PickerButton by={by} open={open} bare={bare} onToggle={() => setOpen(!open)} />
      {open && <AnnotatorMenu people={people} query={query} setQuery={setQuery} option={option} onClose={() => setOpen(false)} />}
    </div>
  );
}

export function VerdictSwitch({ verdict, onPick }: { verdict: string | null; onPick: (v: string | null) => void }) {
  return (
    <div className="seg ab-v" role="group" aria-label="Verdict">
      {VERDICTS.map((v) => <button key={v.name} className={verdict === v.id ? "on" : ""} onClick={() => onPick(v.id)}>{v.name}</button>)}
    </div>
  );
}

/** Under a value: "✓ human-reviewed · published  Jared Diener confirmed Eric Riddoch's check · just now", or
 * "✓ engineer-checked  Eric Riddoch [engineer] · 21 Oct · waiting for an expert". Nothing for other values. */
export function ReviewLine({ r }: { r: ReviewMarks }) {
  if (r.human_reviewed && r.human) return <HumanReviewedLine r={r} human={r.human} />;
  if (r.engineer_checked && r.checked) return <EngineerCheckedLine checked={r.checked} />;
  if (r.before_reset) return <BeforeResetLine before={r.before_reset} />;
  return null;
}

/** Foot of the rule list, for experts: the values an engineer checked, and a button that lists them. */
export function WaitingNote({ n, on, onToggle }: { n: number; on: boolean; onToggle: () => void }) {
  if (!n) return null;
  return (
    <div className="ab-note" data-testid="waiting-note">
      <p><b>{fmt(n)} value{n === 1 ? "" : "s"} an engineer checked</b> {n === 1 ? "is" : "are"} waiting for an expert.
        They aren't human-reviewed until you confirm them.</p>
      <button className="btn" onClick={onToggle}>{on ? "Clear filter" : "Show them"}</button>
    </div>
  );
}

const KIND_NAME: Record<string, string> = { correct: "✓ correct", wrong: "✕ wrong", note: "note" };

/** Records tab, filtered to a person: their verdict on a value and when, where no review line says it. */
export function PersonLine({ name, a }: { name: string; a: { kinds: string[]; at: string } }) {
  return (
    <div className="rv-line" data-testid="person-line">
      <b>{name}</b><span className="muted">{a.kinds.map((k) => ` · ${KIND_NAME[k] ?? k}`).join("")} · {shortWhen(a.at)}</span>
    </div>
  );
}

interface AnnotatedByProps {
  people: Annotators | null; by: string | null; me: string; onPick: (by: string | null) => void;
  /** Without its "Annotated by" label: the label sits beside it (the Rules tab's filter rows). */
  bare?: boolean;
}

type RenderOption = (id: string | null, name: string, extra?: ReactNode) => ReactNode;

function useCloseOnClickAway(open: boolean, box: RefObject<HTMLDivElement>, setOpen: (open: boolean) => void): void {
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open, box, setOpen]);
}

/** One choice of the dropdown, hidden when the search doesn't match its name. */
function optionRenderer(by: string | null, me: string, query: string, pick: (id: string | null) => void): RenderOption {
  const q = query.trim().toLowerCase();
  return (id, name, extra) => (!q || name.toLowerCase().includes(q)) && (
    <button key={id ?? ""} role="option" aria-selected={by === id} className={"ab-item" + (by === id ? " on" : "")}
      onClick={() => pick(id)}><span>{name}{id === me && <span className="faint"> (you)</span>}</span>{extra}</button>);
}

function PickerButton({ by, open, bare, onToggle }: { by: string | null; open: boolean; bare?: boolean; onToggle: () => void }) {
  return (
    <button className={"ab-btn" + (open ? " open" : "") + (by ? " set" : "")} aria-haspopup="listbox" aria-expanded={open}
      onClick={onToggle}>{!bare && <><span className="ab-k">Annotated by</span> </>}<b>{byLabel(by)}</b><Ico name="chevron" className="ab-car" /></button>
  );
}

function AnnotatorMenu({ people, query, setQuery, option, onClose }: {
  people: Annotators | null; query: string; setQuery: (q: string) => void; option: RenderOption; onClose: () => void;
}) {
  return (
    <div className="ab-pop" role="listbox">
      <input className="ab-q" placeholder="Search people" value={query} autoFocus onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Escape") onClose(); }} />
      {option(null, "Anyone")}
      {option(BY_NOBODY, "Not annotated yet")}
      <ExpertOptions people={people} option={option} />
      <EngineerOptions people={people} option={option} />
    </div>
  );
}

function ExpertOptions({ people, option }: { people: Annotators | null; option: RenderOption }) {
  return (<>
    <div className="ab-h">Subject matter experts · human-reviewed</div>
    {option(BY_EXPERTS, "Any subject matter expert", people?.experts !== undefined && <ValueCount n={people.experts} />)}
    {personOptions(people, "sme", option)}
  </>);
}

function EngineerOptions({ people, option }: { people: Annotators | null; option: RenderOption }) {
  return (<>
    <div className="ab-h">Engineers · waiting for an expert</div>
    {option(BY_ENGINEERS, "Any engineer", people?.engineers !== undefined && <ValueCount n={people.engineers} />)}
    {option(BY_WAITING, "Any engineer · waiting for an expert", people && <ValueCount n={people.waiting} />)}
    {personOptions(people, "engineer", option)}
  </>);
}

function personOptions(people: Annotators | null, role: "sme" | "engineer", option: RenderOption): ReactNode[] {
  return (people?.people ?? []).filter((p) => p.role === role).map((p) => option(p.name, p.name, <ValueCount n={p.values} />));
}

function ValueCount({ n }: { n: number }) {
  return <span className="ab-n">{n ? `${fmt(n)} value${n === 1 ? "" : "s"}` : "none yet"}</span>;
}

function HumanReviewedLine({ r, human }: { r: ReviewMarks; human: NonNullable<ReviewMarks["human"]> }) {
  const confirmed = r.checked && r.checked.at <= human.at ? r.checked : null;
  return (
    <div className="rv-line" data-testid="review-line">
      <span className="rv-chip human">✓ human-reviewed · published</span>
      <b>{human.author}</b>{confirmed && <span className="muted">confirmed {confirmed.author}'s check</span>}
      <span className="muted">· {shortWhen(human.at)}</span>
    </div>
  );
}

function EngineerCheckedLine({ checked }: { checked: NonNullable<ReviewMarks["checked"]> }) {
  return (
    <div className="rv-line" data-testid="review-line">
      <span className="rv-chip eng">✓ engineer-checked</span>
      <b>{checked.author}</b><span className="rv-role">engineer</span>
      <span className="muted">· {shortWhen(checked.at)} · waiting for an expert</span>
    </div>
  );
}

/** What was said before Reset rule: a hint for the re-review, counted nowhere. */
function BeforeResetLine({ before }: { before: NonNullable<ReviewMarks["before_reset"]> }) {
  const mark = before.verdict === "correct" ? "✓" : "✕";
  return (
    <div className="rv-line before-reset" data-testid="before-reset" title={before.expected?.text ? `Their answer: ${before.expected.text}` : undefined}>
      <span className="muted">{mark} {before.author} · {shortWhen(before.at)}, before the reset</span>
    </div>
  );
}
