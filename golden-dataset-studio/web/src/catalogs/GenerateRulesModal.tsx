// Generate rules (spec §7.1): a catalog added from the picker has no rules. With the Remote AI rule generator on
// (agent runs, docs/qrspi/k2-runs), this modal starts Claude writing and publishing its first ruleset and shows the
// run's progress; otherwise (or for prompt users who pick it, or when the generator can't be reached) it gives the
// prompt for Claude Code, starting from a catalog already in the Studio. The text comes from the server (prompt.py),
// the same as `golden-datasets prompt --first-rules`.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CatalogCard, FirstRulesPrompt } from "../api/types";
import { elapsed } from "../agent/api";
import { K2Warning } from "../agent/K2Warning";
import { RunButton } from "../agent/RunButton";
import { AgentProvider, isLive, useAgent } from "../agent/state";
import { Ico, toast } from "../shell/ui";
import { downloadName } from "../prompt/highlight";
import { Markdown } from "../prompt/markdown";
import { copyText, download } from "../prompt/PromptModal";
import "../prompt/prompt.css";

export function GenerateRulesModal({ card, onClose }: { card: CatalogCard; onClose: () => void }) {
  useEffect(() => {
    const on = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onClose]);
  return (
    <AgentProvider catalog={card.catalog}>
      <div className="ac-back" onClick={onClose}>
        <div className="ac gr" role="dialog" aria-modal="true" aria-labelledby="gr-h" onClick={(e) => e.stopPropagation()}>
          <div className="ac-head">
            <h2 id="gr-h">Generate rules for {card.name}</h2>
            <button className="ac-x" aria-label="Close" onClick={onClose}>×</button>
          </div>
          <Body card={card} />
        </div>
      </div>
    </AgentProvider>
  );
}

function Body({ card }: { card: CatalogCard }) {
  const { config, run, last, notes, now } = useAgent();
  const [prompt, setPrompt] = useState<{ warning?: string } | null>(null);
  if (!config) return <div className="ac-body"><p className="muted">Loading…</p></div>;
  if (!config.enabled || prompt) return <PromptView card={card} warning={prompt?.warning} />;
  const shown = isLive(run) ? run : last?.scope.kind === "first_rules" ? last : null;
  return (
    <>
      <div className="ac-body">
        {shown ? (
          <>
            <p className="gr-lead">{isLive(shown)
              ? <>Claude is writing {card.name}'s first rules on the {config.agent_name} · started by {shown.started_by} ·{" "}
                  {elapsed(shown.created_at, now)}. You can close this; the run keeps going, and the card opens when the
                  rules are published.</>
              : <>{shown.state === "finished" ? "Claude finished" : "The last run ended"}{shown.outcome ? `: ${shown.outcome}` : "."}</>}</p>
            <ol className="run-notes" aria-label="Progress">
              {notes.length === 0 && <li className="faint">No notes yet.</li>}
              {notes.map((n, i) => <li key={i} className={`rn-${n.kind}`}>
                <time dateTime={n.at}>{new Date(n.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time>
                <span>{n.text}</span></li>)}
            </ol>
          </>
        ) : (
          <p className="gr-lead">Claude writes {card.name}'s first rules on the {config.agent_name}, starting from a
            catalog already in the Studio, and publishes them; the card then opens. It works unattended, and you can
            watch its progress here.</p>
        )}
      </div>
      <div className="ac-foot">
        <RunButton catalog={card.catalog} scope={{ kind: "first_rules" }} label="Generate rules with Claude"
          onPrompt={(warning) => setPrompt({ warning })}
          confirm={`Have Claude write and publish ${card.name}'s first rules?`} />
      </div>
    </>
  );
}

function PromptView({ card, warning }: { card: CatalogCard; warning?: string }) {
  const [data, setData] = useState<FirstRulesPrompt | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.firstRulesPrompt(card.catalog).then(setData, (e) => setError(String(e.message ?? e)));
  }, [card.catalog]);
  const onCopy = async () => {
    if (data) toast((await copyText(data.text)) ? "Prompt copied" : "Couldn't copy: select the text and copy it");
  };
  return (
    <>
      <div className="ac-body">
        {warning !== undefined && <K2Warning reason={warning} />}
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
    </>
  );
}
