// Reset rule (phase1-followups spec §4.1, screens/b3-mock-reset-dialog.png): for when the right answer turns out to be
// different after examples were approved. Every ✓ and every answer given with ✕ on this property in this catalog goes
// back to "not reviewed", the rule's approval ends, and its column leaves the silver dataset (its values the golden
// one) until the rule is approved again. It says what it clears and keeps, and asks why: the log keeps the reason.
import { useEffect, useState } from "react";
import type { ResetPreview } from "../api/types";
import { fmt } from "../shell/ui";

const vname = (id?: string) => (id ?? "").replace(/^ruleset-v/, "ruleset v");
const plural = (n: number, one: string, many = `${one}s`) => `${fmt(n)} ${n === 1 ? one : many}`;

export function ResetDialog({ p, catalogName, busy, onReset, onClose }: {
  p: ResetPreview; catalogName: string; busy: boolean; onReset: (why: string) => void; onClose: () => void;
}) {
  const [why, setWhy] = useState("");
  useEffect(() => {
    const on = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onClose]);
  const authors = Object.entries(p.by_author).map(([a, n]) => `${a} ${fmt(n)}`).join(" · ");
  const k = p.kept;
  const kept = [k.wrong_no_answer && `${plural(k.wrong_no_answer, "✕")} with no answer`, k.questions && plural(k.questions, "question"),
                k.comments && plural(k.comments, "comment")].filter(Boolean).join(", ");
  return (
    <div className="apx-back" onClick={onClose}>
      <div className="apx" role="dialog" aria-modal="true" aria-labelledby="rsx-h" data-testid="reset-dialog" onClick={(e) => e.stopPropagation()}>
        <h2 id="rsx-h">Reset {p.property ?? p.rule_id} in {catalogName}?</h2>
        <p className="apx-lead">Every review of this property in {catalogName} goes back to <b>not reviewed</b>, so it can be reviewed again.</p>
        <table className="apx-cols">
          <thead><tr><th>What's reset</th><th /></tr></thead>
          <tbody>
            <tr><td><b>{fmt(p.counts.correct)}</b> marked correct (✓)</td><td className="mono">{authors || <span className="muted">—</span>}</td></tr>
            <tr><td><b>{fmt(p.counts.answered)}</b> answers given with ✕</td><td /></tr>
            <tr><td>The rule's approval</td>
              <td className="mono">{p.approval ? `${p.approval.by ?? ""} · ${(p.approval.at ?? "").slice(0, 10)}` : <span className="muted">not approved</span>}</td></tr>
          </tbody>
        </table>
        <p className="apx-count">{p.column
          ? <>The <b>{p.column.column}</b> column leaves {catalogName}'s <b>silver dataset</b> ({vname(p.column.golden)}), and these values leave
            the <b>golden dataset</b>, until the rule is approved again. Evals rescore.</>
          : <>These values leave the <b>golden dataset</b>. Evals rescore.</>}</p>
        <p className="apx-count">Kept: {kept || "nothing else"}.</p>
        <label className="rsx-why" htmlFor="rsx-why">Why? <span className="muted">(required)</span></label>
        <textarea id="rsx-why" className="rsx-text" value={why} onChange={(e) => setWhy(e.target.value)} autoFocus
          placeholder="What the right answer is now, so whoever re-reviews knows" />
        <div className="apx-foot">
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn danger" onClick={() => onReset(why.trim())} disabled={busy || !why.trim()}>{busy ? "Resetting…" : "Reset rule"}</button>
        </div>
      </div>
    </div>
  );
}
