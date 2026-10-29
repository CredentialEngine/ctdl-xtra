// Approving publishes (Evals spec §6.6, m4): approving a column's rule asks once, showing the golden dataset's columns
// now and after and how many of the column's values are human-reviewed and how many its rule labels. "Approve and
// publish" approves the rule; the server publishes the column into its ruleset's golden dataset and scores it.
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
  const g = <b>{vname(p.golden)}</b>;
  const cols = (c?: string[]) => (c?.length ? c.join(", ") : <span className="muted">none yet</span>);
  const others = (p.after ?? []).filter((c) => c !== p.column && !(p.now ?? []).includes(c));
  return (
    <div className="apx-back" onClick={onClose}>
      <div className="apx" role="dialog" aria-modal="true" aria-labelledby="apx-h" onClick={(e) => e.stopPropagation()}>
        <h2 id="apx-h">Approve <code>{p.column}</code> and publish it?</h2>
        <p className="apx-lead">Approving a column's rule publishes it.{" "}
          {p.creates ? <>Golden dataset {g} is created with this column{others.length ? <> and the other approved ones</> : null}</>
            : <>Golden dataset {g} gets this column{others.length ? <> and the other approved ones</> : null}</>}, then xtra's
          latest extract output is scored against it.</p>
        <table className="apx-cols">
          <thead><tr><th>Golden dataset {vname(p.golden)}</th><th>Columns</th></tr></thead>
          <tbody>
            <tr><td>Now</td><td className="mono">{p.creates ? <span className="muted">not created yet</span> : cols(p.now)}</td></tr>
            <tr><td>After approving</td><td className="mono">{cols(p.after)}</td></tr>
          </tbody>
        </table>
        <p className="apx-count">{fmt(p.values ?? 0)} {p.column} values: {fmt(p.human ?? 0)} human-reviewed,{" "}
          {fmt(p.rule ?? 0)} labelled by the rule.{" "}
          <span className="tipwrap apx-where" data-tip={`Written to ${p.where}rule-matched/ and human-reviewed/, and to the latest location. The Golden datasets tab shows every file.`}>
            Where it's written <span className="apx-i" aria-hidden="true">i</span></span></p>
        <div className="apx-foot">
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" onClick={onApprove} disabled={busy} autoFocus>{busy ? "Publishing…" : "Approve and publish"}</button>
        </div>
      </div>
    </div>
  );
}
