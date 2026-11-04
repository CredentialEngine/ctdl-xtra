// "Why wrong?" (sme-fixes §6, picture img/mock-p3-q12.png): after ✕, a small set of reason flags. Saved as
// `reasons` on the verdict; "Not on the page" makes the golden dataset say the property is absent.
import { REASONS } from "./claims";
import "./claims.css";

export function WhyWrong({ reasons, onChange }: { reasons: string[]; onChange: (r: string[]) => void }) {
  return (
    <div className="why-wrong" data-testid="why-wrong">
      <span className="why-h">Why wrong?</span>
      {REASONS.map((r) => (
        <label key={r.id} className="why-r" title={r.tip}>
          <input type="checkbox" checked={reasons.includes(r.id)}
            onChange={(e) => onChange(e.target.checked ? [...reasons, r.id] : reasons.filter((x) => x !== r.id))} />
          {r.label}
        </label>))}
    </div>
  );
}
