// A property's review (learning-programs Phase 6; mockup w4-property-review), on the home page's one-property score
// view: its status at the top (Needs review: anyone; Done: the SME role), and its findings across catalogs below the
// score table, each opening its editor. The running notes' per-property section, made from data.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { FindingX, PropertyReview } from "../api/types";
import { useReviewer, useRole } from "../shell/reviewer";
import { CLASS_NAME, type ClassSlug } from "../shell/router";
import { Ico } from "../shell/icons";
import { fmt, toast } from "../shell/ui";
import { FindingPanel } from "./FindingPanel";
import { catalogsOf, COUNTED, countsOf, termOfColumn } from "./logic";
import "./findings.css";

const day = (iso: string) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

let names: Promise<Map<string, string>> | null = null;
/** A catalog's display name ("Marshall", "UARK") by its short name, asked for once. */
function useCatalogNames(): (short: string) => string {
  const [m, setM] = useState<Map<string, string> | null>(null);
  useEffect(() => {
    names ??= api.catalogs().then((cs) => new Map(cs.map((c) => [c.short, c.name])), () => new Map());
    let live = true; void names.then((x) => live && setM(x)); return () => { live = false; };
  }, []);
  return (short) => m?.get(short) ?? short.toUpperCase();
}

export function useReview(cls: ClassSlug, col: string | null) {
  const [review, setReview] = useState<PropertyReview | null>(null);
  const catalogName = useCatalogNames();
  const load = useCallback(() => {
    if (!col) { setReview(null); return; }
    api.propertyReview(cls, col).then(setReview, () => setReview(null));
  }, [cls, col]);
  useEffect(load, [load]);
  return { review, reload: load, catalogName };
}

/** "Course › ceterms:description  [Needs review | Done]  set by Jared, 18 Nov ··· 3 open findings, 2 fixed". */
export function StatusBar({ cls, col, review, reload }: { cls: ClassSlug; col: string; review: PropertyReview | null; reload: () => void }) {
  const s = review?.status ?? null;
  return (
    <div className="fd-status" data-testid="property-status">
      <b>{CLASS_NAME[cls]} › {termOfColumn(col)}</b>
      <StatusSwitch cls={cls} col={col} status={s?.status} reload={reload} />
      <span className="muted">{s ? `set by ${s.by.split(" ")[0]}, ${day(s.at)}` : "no status yet"}</span>
      <span className="grow" />
      <span className="muted">{review ? findingsSummary(review) : ""}</span>
    </div>
  );
}

type CatalogName = (short: string) => string;
type Opened = FindingX | "new" | null;

export function FindingsTable({ cls, col, review, reload, catalogName }: {
  cls: ClassSlug; col: string; review: PropertyReview | null; reload: () => void; catalogName: CatalogName;
}) {
  const [open, setOpen] = useState<Opened>(null);
  if (!review) return null;
  return (
    <section className="fd-sec" data-testid="findings">
      <FindingsHead onAdd={() => setOpen("new")} />
      {review.findings.length === 0 ? <p className="muted">No findings yet.</p>
        : <FindingsList findings={review.findings} catalogName={catalogName} onOpen={setOpen} />}
      {open && <FindingPanel key={open === "new" ? "new" : open.id} cls={cls} col={col} finding={openFinding(review, open)}
        catalogName={catalogName} onClose={() => setOpen(null)} onSaved={reload} />}
    </section>
  );
}

function StatusSwitch({ cls, col, status, reload }: { cls: ClassSlug; col: string; status: string | undefined; reload: () => void }) {
  const me = useReviewer(), role = useRole();
  const set = (next: "needs review" | "done") => saveStatus(cls, col, next, me, reload);
  return (
    <span className="seg xs" role="group" aria-label="Status">
      <button className={status === "needs review" ? "on" : ""} onClick={() => set("needs review")}>Needs review</button>
      <button className={status === "done" ? "on" : ""} disabled={role !== "sme"} onClick={() => set("done")}
        title={role === "sme" ? "The team agrees: this property is done" : "Only a subject-matter expert sets Done"}>Done</button>
    </span>
  );
}

function findingsSummary(review: PropertyReview): string {
  const open = review.findings.filter((f) => f.state === "open").length;
  const fixed = review.findings.length - open;
  return `${open} open finding${open === 1 ? "" : "s"}${fixed ? `, ${fixed} fixed` : ""}`;
}

function FindingsHead({ onAdd }: { onAdd: () => void }) {
  return <div className="sv-h"><h2>Findings</h2>
    <span className="muted">Kept per property, across catalogs. Counts are golden / silver units. Add one from Where it's wrong in a catalog's Evals tab.</span>
    <span className="grow" /><button className="btn sm" onClick={onAdd}>+ Add finding</button></div>;
}

function FindingsList({ findings, catalogName, onOpen }: { findings: FindingX[]; catalogName: CatalogName; onOpen: (f: FindingX) => void }) {
  return (
    <table className="fd-table">
      <thead><tr><th>Code</th><th>Kind</th><th>Finding</th>{COUNTED.map((o) => <th key={o} className="r">{o}</th>)}
        <th>Catalogs</th><th>Whose error</th><th>State</th><th /></tr></thead>
      <tbody>
        {findings.map((f) => <FindingRow key={f.id} finding={f} catalogName={catalogName} onOpen={() => onOpen(f)} />)}
      </tbody>
    </table>
  );
}

/** The finding as the store has it now (after a save), else as it was opened. */
function openFinding(review: PropertyReview, open: Exclude<Opened, null>): FindingX | null {
  return open === "new" ? null : review.findings.find((f) => f.id === open.id) ?? open;
}

async function saveStatus(cls: ClassSlug, col: string, status: "needs review" | "done", me: string, reload: () => void) {
  try { await api.setPropertyStatus(cls, col, status, me); reload(); } catch (e) { toast(`Not saved: ${e instanceof Error ? e.message : String(e)}`); }
}

function FindingRow({ finding: f, catalogName, onOpen }: { finding: FindingX; catalogName: CatalogName; onOpen: () => void }) {
  const c = countsOf(f);
  return (
    <tr data-finding={f.code} onClick={onOpen}>
      <td className="mono b">{f.code}</td>
      <td><span className={`fd-kind ${f.kind}`}>{f.kind}</span></td>
      <td className="fd-t">{f.title}</td>
      {COUNTED.map((o) => <td key={o} className="r num">{pair(c[o])}</td>)}
      <td className="muted">{catalogsOf(f, catalogName)}</td>
      <td className="muted">{f.whose ?? "–"}</td>
      <td className={`fd-state ${f.state}`}>{f.state}</td>
      <td className="muted fd-n" title="comments"><Ico name="open" />{f.comments}</td>
    </tr>
  );
}

function pair(c: [number, number] | null): string {
  return c ? `${fmt(c[0])} / ${fmt(c[1])}` : "–";
}
