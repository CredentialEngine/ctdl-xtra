// The prompt for Claude Code, in a modal (spec §1): every rule that needs work, with every open verdict. It opens from
// a run button's "Open the prompt" (prompt users) and when the Remote AI rule generator can't be reached (then with a
// warning above it). The text comes from the server (prompt.py), the same as `golden-datasets prompt --needs-work`, so
// it is deterministic: the same annotations always give the same text. Claude always works on the shared Azure root.
import { Fragment, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { PromptResponse } from "../api/types";
import { K2Warning } from "../agent/K2Warning";
import { Ico, toast } from "../shell/ui";
import { downloadName, highlight, lineKinds, runs } from "./highlight";
import { Markdown } from "./markdown";
import "./prompt.css";
import "../agent/agent.css";

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Clipboard API unavailable (http over ngrok, old browser): fall back to a selected textarea.
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch { ok = false; }
    ta.remove();
    return ok;
  }
}

export function download(text: string, name: string): void {
  const a = document.createElement("a");
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

/** Open the prompt modal from anywhere (App listens); `warning`: why the Remote AI rule generator couldn't be reached. */
export const OPEN_PROMPT = "studio-open-prompt";
export function openPrompt(warning?: string): void {
  window.dispatchEvent(new CustomEvent(OPEN_PROMPT, { detail: { warning: warning ?? null } }));
}

export function PromptModal({ catalog, short, version, warning, onClose }: {
  catalog: string; short: string; version: number; warning: string | null; onClose: () => void;
}) {
  const [view, setView] = useState<"raw" | "rendered">(() => {
    try { return localStorage.getItem("studio.prompt.view") === "rendered" ? "rendered" : "raw"; } catch { return "raw"; }
  });
  const pickView = (v: "raw" | "rendered") => { setView(v); try { localStorage.setItem("studio.prompt.view", v); } catch { /* private */ } };
  const [data, setData] = useState<PromptResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api.prompt(catalog, { needs_work: true }).then((d) => { if (live) setData(d); }, (e) => { if (live) setError(String(e)); });
    return () => { live = false; };
  }, [catalog, version]);
  useEffect(() => {
    const on = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onClose]);
  const lines = useMemo(() => (data ? highlight(data.text) : []), [data]);
  const kinds = useMemo(() => (data ? lineKinds(data.text) : []), [data]);
  const bands = useMemo(() => (data ? runs(data.text) : []), [data]);
  const onCopy = async () => {
    if (data) toast((await copyText(data.text)) ? "Prompt copied" : "Couldn't copy: select the text and copy it");
  };
  const n = data?.rules.length ?? 0;
  return (
    <div className="ac-back" onClick={onClose}>
      <div className="ac prompt-modal" role="dialog" aria-modal="true" aria-labelledby="pm-h" onClick={(e) => e.stopPropagation()}>
        <div className="ac-head">
          <h2 id="pm-h">The prompt for Claude Code</h2>
          <span className="seg md-seg" role="group" aria-label="Preview">
            <button className={view === "raw" ? "on" : ""} onClick={() => pickView("raw")}>Raw</button>
            <button className={view === "rendered" ? "on" : ""} onClick={() => pickView("rendered")}>Rendered</button>
          </span>
          <button className="ac-x" aria-label="Close" onClick={onClose}>×</button>
        </div>
        <div className="ac-body pm-body">
          {warning !== null && <K2Warning reason={warning} />}
          <p className="pm-lead">{data ? (n ? `Every rule that needs work (${n}), with every open verdict. ` : "No rule needs work right now. ") : ""}
            Paste it into Claude Code: it installs the <span className="mono">golden-datasets</span> CLI, improves the rules
            and publishes a new ruleset version.</p>
          {data?.studio_root && data.studio_root !== data.root &&
            <div className="prompt-warn" data-testid="root-warn">This Studio serves another root than the Azure one Claude works
              on: what Claude publishes shows here only after a <span className="mono">golden-datasets sync</span>.</div>}
          {data?.warning && <div className="prompt-warn" data-testid="prompt-warn">{data.warning}</div>}
          {error && <div className="prompt-error">{error}</div>}
          {view === "rendered" && data ? <div className="prompt-pre prompt-md" data-testid="prompt-rendered">
            {bands.map((b, i) => <div key={i} className={"band " + b.kind}><Markdown text={b.text} /></div>)}</div> :
          <pre className={"prompt-pre" + (data ? "" : " loading")} data-testid="prompt-text">
            {data ? lines.map((segs, i) => (
              <span key={i} className={"ln " + kinds[i]}>
                {segs.map((s, j) => (s.cls ? <span key={j} className={s.cls}>{s.text}</span> : <Fragment key={j}>{s.text}</Fragment>))}
                {"\n"}
              </span>
            )) : error ? "" : "Building the prompt…"}
          </pre>}
        </div>
        <div className="ac-foot">
          <span className="ac-keys">{data ? `~${data.tokens.toLocaleString("en-US")} tokens · ruleset v${version}` : ""}</span>
          <button className="btn" disabled={!data} onClick={() => data && download(data.text, downloadName(short, "needs-work"))}>
            <Ico name="download" />Download .md</button>
          <button className="btn primary" disabled={!data} onClick={onCopy}><Ico name="copy" />Copy prompt</button>
        </div>
      </div>
    </div>
  );
}
