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
  const me = useReviewer(), role = useRole();
  const s = review?.status ?? null;
  const set = async (status: "needs review" | "done") => {
    try { await api.setPropertyStatus(cls, col, status, me); reload(); } catch (e) { toast(`Not saved: ${e instanceof Error ? e.message : String(e)}`); }
  };
  const open = review?.findings.filter((f) => f.state === "open").length ?? 0;
  const fixed = (review?.findings.length ?? 0) - open;
  return (
    <div className="fd-status" data-testid="property-status">
      <b>{CLASS_NAME[cls]} › {termOfColumn(col)}</b>
      <span className="seg xs" role="group" aria-label="Status">
        <button className={s?.status === "needs review" ? "on" : ""} onClick={() => set("needs review")}>Needs review</button>
        <button className={s?.status === "done" ? "on" : ""} disabled={role !== "sme"} onClick={() => set("done")}
          title={role === "sme" ? "The team agrees: this property is done" : "Only a subject-matter expert sets Done"}>Done</button>
      </span>
      <span className="muted">{s ? `set by ${s.by.split(" ")[0]}, ${day(s.at)}` : "no status yet"}</span>
      <span className="grow" />
      <span className="muted">{review ? `${open} open finding${open === 1 ? "" : "s"}${fixed ? `, ${fixed} fixed` : ""}` : ""}</span>
    </div>
  );
}

const pair = (c: [number, number] | null) => (c ? `${fmt(c[0])} / ${fmt(c[1])}` : "–");

export function FindingsTable({ cls, col, review, reload, catalogName }: {
  cls: ClassSlug; col: string; review: PropertyReview | null; reload: () => void; catalogName: (short: string) => string;
}) {
  const [open, setOpen] = useState<FindingX | "new" | null>(null);
  if (!review) return null;
  const current = open && open !== "new" ? review.findings.find((f) => f.id === open.id) ?? open : null;
  return (
    <section className="fd-sec" data-testid="findings">
      <div className="sv-h"><h2>Findings</h2>
        <span className="muted">Kept per property, across catalogs. Counts are golden / silver units. Add one from Where it's wrong in a catalog's Evals tab.</span>
        <span className="grow" /><button className="btn sm" onClick={() => setOpen("new")}>+ Add finding</button></div>
      {review.findings.length === 0 ? <p className="muted">No findings yet.</p> : (
        <table className="fd-table">
          <thead><tr><th>Code</th><th>Kind</th><th>Finding</th>{COUNTED.map((o) => <th key={o} className="r">{o}</th>)}
            <th>Catalogs</th><th>Whose error</th><th>State</th><th /></tr></thead>
          <tbody>
            {review.findings.map((f) => {
              const c = countsOf(f);
              return (
                <tr key={f.id} data-finding={f.code} onClick={() => setOpen(f)}>
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
            })}
          </tbody>
        </table>)}
      {open && <FindingPanel key={open === "new" ? "new" : open.id} cls={cls} col={col} finding={open === "new" ? null : current}
        catalogName={catalogName} onClose={() => setOpen(null)} onSaved={reload} />}
    </section>
  );
}
