import { useState } from "react";
import { saveGolden } from "../api";
import { goldenMessage } from "../review";

interface Props {
  stem: string;
  saved: boolean;
  onSaved: (stem: string) => void;
}

/** Saves the page's verified values to the verified golden sets storage. */
export default function SaveGolden({ stem, saved, onSaved }: Props) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; kind: "ok" | "warn" | "error" } | null>(null);

  const save = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const result = await saveGolden(stem);
      const { text, incomplete } = goldenMessage(result);
      setMessage({ text: `${text} (${stem}/ with the page's HTML)`, kind: incomplete ? "warn" : "ok" });
      onSaved(stem);
    } catch (error) {
      setMessage({ text: error instanceof Error ? error.message : String(error), kind: "error" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="save-golden">
      <button
        className="act"
        onClick={save}
        disabled={busy}
        title="Save this page's accepted, corrected and added values to the verified golden sets storage"
      >
        {busy ? "Saving…" : saved ? "✓ Update golden dataset" : "Save golden dataset"}
      </button>
      {message && (
        <div className={`golden-msg ${message.kind}`} role={message.kind === "error" ? "alert" : "status"}>
          {message.text}
        </div>
      )}
    </div>
  );
}
