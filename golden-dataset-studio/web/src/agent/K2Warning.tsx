// Shown above a prompt when a run button couldn't reach the remote agent (spec §1, "When K2 can't be reached").
import "./agent.css";

export function K2Warning({ reason }: { reason: string }) {
  return (
    <div className="k2-warn" role="alert" data-testid="k2-warning">
      <b>⚠ We couldn't connect to the Remote AI rule generator{reason ? ` (${reason})` : ""}.</b>
      Copy this prompt and ask an engineer to run it in their own Claude Code.
    </div>
  );
}
