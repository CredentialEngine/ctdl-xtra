// Approving publishes (Evals spec §6.6; property-rules spec §4.10, m6): approving a property's rule asks once. It publishes
// every value the rule found into its ruleset's silver dataset (also called the rule-matched dataset); the golden dataset,
// only the values an expert reviewed, doesn't change. "Approve rule and publish silver dataset" approves the rule; the
// server publishes the column and scores it.
import { useEffect } from "react";
import type { ApprovePreview } from "../api/types";
import { fmt } from "../shell/ui";

const vname = (id?: string) => (id ?? "").replace(/^ruleset-v/, "ruleset v");

export function ApproveDialog({ p, busy, onApprove, onClose }: {
  p: ApprovePreview; busy: boolean; onApprove: () => void; onClose: () => void;
}) {
  useEffect(() => {
    const on = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onClose]);
  const cols = (c?: string[]) => (c?.length ? c.join(", ") : <span className="muted">none yet</span>);
  return (
    <div className="apx-back" onClick={onClose}>
      <div className="apx" role="dialog" aria-modal="true" aria-labelledby="apx-h" onClick={(e) => e.stopPropagation()}>
        <h2 id="apx-h">Approve {p.property ?? p.column} and publish its silver dataset?</h2>
        <p className="apx-lead">Approving this rule publishes every value it found into {vname(p.golden)}'s{" "}
          <b>silver dataset</b> (also called the <b>rule-matched dataset</b>). The <b>golden dataset</b> holds only values an expert
          reviewed, and doesn't change.</p>
        <table className="apx-cols">
          <thead><tr><th>Silver dataset {vname(p.golden)}</th><th>Columns</th></tr></thead>
          <tbody>
            <tr><td>Now</td><td className="mono">{p.creates ? <span className="muted">not created yet</span> : cols(p.now)}</td></tr>
            <tr><td>After approving</td><td className="mono">{cols(p.after)}</td></tr>
          </tbody>
        </table>
        <p className="apx-count">
          <b>{fmt(p.values ?? 0)}</b> values to the silver dataset · <b>{fmt(p.human ?? 0)}</b> human-reviewed, already in the golden dataset.{" "}
          <span className="tipwrap apx-where" data-tip={`Written to ${p.where}silver/ and to the latest location. The Datasets tab shows every file.`}>
            Where it's written <span className="apx-i" aria-hidden="true">i</span></span></p>
        {p.path_shown && <div className="apx-path">CTDL path <code>{p.path_shown}</code></div>}
        {p.xtra_extracts === false && (
          <p className="apx-xtra"><b>xtra doesn't extract this property yet</b>, so it isn't scored. Evals keeps its column, marked “not
            scored”, and leaves it out of the exact-match rate until an extract output has the same path.</p>)}
        <div className="apx-foot">
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" onClick={onApprove} disabled={busy} autoFocus>{busy ? "Publishing…" : "Approve rule and publish silver dataset"}</button>
        </div>
      </div>
    </div>
  );
}
