// Where these come from: the extract output, the golden side and the score, with the command that scored them.
import { useEffect } from "react";
import type { ScoreBasis, ScoreDoc } from "../api/types";
import { Ico, toast } from "../shell/ui";
import { fmtDayTime } from "../valuediff/diff";
import { multiline } from "./commands";
import { goldenName, HUMAN } from "./score";

interface InfoProps { doc: ScoreDoc; basis: ScoreBasis }

export function InfoModal({ doc, basis, onClose }: InfoProps & { onClose: () => void }) {
  useEscape(onClose);
  return (
    <div className="evx-back" onClick={onClose}>
      <div className="evx-modal" role="dialog" aria-label="Where these come from" onClick={(e) => e.stopPropagation()}>
        <div className="evx-modal-h"><h2>Where these come from</h2><button className="btn sm" onClick={onClose}>Close</button></div>
        <SourcesTable doc={doc} basis={basis} />
        <ScoreCommand doc={doc} basis={basis} />
      </div>
    </div>
  );
}

function useEscape(onClose: () => void) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);
}

function SourcesTable({ doc, basis }: InfoProps) {
  return (
    <table className="evx-where">
      <thead><tr><th>What</th><th>Where</th><th>Notes</th></tr></thead>
      <tbody>
        <tr><td>Extract output</td><td className="mono">{doc.output.path}/records/</td>
          <td className="muted">Written by engineers with <code>xtra catalog extract</code>. Each run overwrites it; the Studio keeps a copy of what it scored.</td></tr>
        <GoldenSource doc={doc} basis={basis} />
        <tr><td>Score</td><td>{fmtDayTime(doc.finished_at ?? doc.created_at)}</td>
          <td className="muted"><code>xtra score extraction match</code>{scorerVersion(doc)} · {doc.id}</td></tr>
      </tbody>
    </table>
  );
}

function ScoreCommand({ doc, basis }: InfoProps) {
  const cmd = doc.commands[basis === "human" ? 0 : 1];  // human-reviewed tree, then rule-matched (score.json)
  const text = cmd ? multiline(cmd) : "";
  return (
    <div className="evx-term">
      <pre>{text || "# a draft has no files for xtra score to read"}</pre>
      {text && <button className="evx-copy" onClick={() => navigator.clipboard.writeText(text).then(() => toast("Copied"))}><Ico name="copy" />Copy</button>}
    </div>
  );
}

function GoldenSource({ doc, basis }: InfoProps) {
  const draft = doc.golden.kind === "draft";
  return (
    <tr><td>{basis === "human" ? goldenName(HUMAN) : goldenName(doc.golden.id)}</td><td className="mono">{doc.golden.from}{draft ? "" : `/${basis === "human" ? "human-reviewed" : "rule-matched"}/`}</td>
      <td className="muted">{draft ? "A draft: an unpublished extraction, scored as if it were published." : "Published from this Studio."}
        {doc.golden.kind === "human-reviewed" || basis === "human" ? ` Read as of ${fmtDayTime(doc.golden.as_of)}.` : ""}</td></tr>
  );
}

function scorerVersion(doc: ScoreDoc): string {
  const commit = doc.scorer.xtra_cli_commit;
  return commit ? `, xtra-cli ${commit.slice(0, 7)}${commit.endsWith("+dirty") ? "+dirty" : ""}` : "";
}
