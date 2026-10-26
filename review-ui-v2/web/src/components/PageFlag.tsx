import { useState } from "react";
import type { Flag } from "../types";

interface Props {
  flag?: Flag;
  onFlag: (on: boolean, note?: string) => void;
}

/** Flag the whole page: shown above the cards, with its note as a red banner. */
export default function PageFlag({ flag, onFlag }: Props) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");

  const openForm = () => {
    setText(flag?.note ?? "");
    setOpen(true);
  };
  const close = () => {
    setOpen(false);
    setText("");
  };

  return (
    <div className="page-flag">
      <button className={`act flag-btn ${flag ? "on" : ""}`} onClick={openForm} title="Flag this whole page for review">
        ⚑ {flag ? "Page flagged" : "Flag page"}
      </button>
      {flag && !open && (
        <div className="flag-note banner">
          ⚑ <strong>Flagged for review</strong> by {flag.author}
          {flag.carried_from ? " (carried over)" : ""}
          {flag.note ? `: ${flag.note}` : ""}
        </div>
      )}
      {open && (
        <div className="form">
          <p className="hint">
            Use this when you cannot tell what the labels or values on this page should be
            and need a subject matter expert. You can also flag single properties below.
          </p>
          <textarea
            autoFocus
            placeholder="What are you unsure about? (optional)"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="form-actions">
            <button
              className="primary flag-save"
              onClick={() => {
                onFlag(true, text.trim() || undefined);
                close();
              }}
            >
              ⚑ {flag ? "Update flag" : "Flag page for review"}
            </button>
            {flag && (
              <button
                onClick={() => {
                  onFlag(false);
                  close();
                }}
              >
                Remove flag
              </button>
            )}
            <button onClick={close}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}
