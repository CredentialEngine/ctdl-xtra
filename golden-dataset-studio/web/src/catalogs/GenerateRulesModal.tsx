// Generate rules (spec §7.1): a catalog added from the picker has no rules. This modal gives the prompt that has
// Claude Code write its first ruleset, starting from a catalog already in the Studio, and publish it as v1; the
// card then opens like the others. The text comes from the server (prompt.py), the same as
// `golden-datasets prompt --first-rules`.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CatalogCard, FirstRulesPrompt } from "../api/types";
import { Ico, toast } from "../shell/ui";
import { downloadName } from "../prompt/highlight";
import { Markdown } from "../prompt/markdown";
import { copyText, download } from "../prompt/PromptTab";
import "../prompt/prompt.css";

export function GenerateRulesModal({ card, onClose }: { card: CatalogCard; onClose: () => void }) {
  const [data, setData] = useState<FirstRulesPrompt | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.firstRulesPrompt(card.catalog).then(setData, (e) => setError(String(e.message ?? e)));
  }, [card.catalog]);
  useEffect(() => {
    const on = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onClose]);
  const onCopy = async () => {
    if (data) toast((await copyText(data.text)) ? "Prompt copied" : "Couldn't copy: select the text and copy it");
  };
  return (
    <div className="ac-back" onClick={onClose}>
      <div className="ac gr" role="dialog" aria-modal="true" aria-labelledby="gr-h" onClick={(e) => e.stopPropagation()}>
        <div className="ac-head">
          <h2 id="gr-h">Generate rules for {card.name}</h2>
          <button className="ac-x" aria-label="Close" onClick={onClose}>×</button>
        </div>
        <div className="ac-body">
          <p className="gr-lead">Run this prompt in Claude Code. It writes {card.name}'s first rules
            {data ? <>, starting from <b>{data.template_name}</b>'s</> : ""},
            and publishes them; the card then opens.</p>
          {data?.studio_root && data.studio_root !== data.root &&
            <div className="prompt-warn">This Studio serves another root than the Azure one Claude works on: what Claude
              publishes shows here only after a <span className="mono">golden-datasets sync</span>.</div>}
          {data?.warning && <div className="prompt-warn">{data.warning}</div>}
          {error ? <p className="prompt-error">{error}</p>
            : <div className={"prompt-pre prompt-md gr-text" + (data ? "" : " loading")} data-testid="first-rules-prompt">
                {data ? <Markdown text={data.text} /> : "Building the prompt…"}</div>}
        </div>
        <div className="ac-foot">
          <span className="ac-keys">{data ? `~${data.tokens.toLocaleString("en-US")} tokens` : ""}</span>
          <button className="btn" disabled={!data} onClick={() => data && download(data.text, downloadName(card.short, "first-rules"))}>
            <Ico name="download" />Download .md</button>
          <button className="btn primary" disabled={!data} onClick={onCopy}><Ico name="copy" />Copy prompt</button>
        </div>
      </div>
    </div>
  );
}
