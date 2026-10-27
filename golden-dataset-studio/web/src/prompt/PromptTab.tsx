// Prompt tab (spec §7.5, screen 09): turn annotations into a prompt for Claude Code.
// Scope: one rule (picker; "Improve this rule" on the Rules tab opens #/c/<catalog>/prompt?rule=<id>&from=rules)
// or all rules needing work (no ?rule). The text comes from the server (prompt.py), the same as
// `golden-datasets prompt`, so it is deterministic: the same annotations always give the same text.
import { Fragment, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { PromptResponse, RuleSummary } from "../api/types";
import { go, href } from "../shell/router";
import type { TabProps } from "../shell/tabProps";
import { fmt, Ico, toast, useKeyHints } from "../shell/ui";
import { downloadName, highlight } from "./highlight";
import "./prompt.css";

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

function download(text: string, name: string): void {
  const a = document.createElement("a");
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export default function PromptTab({ catalog, route }: TabProps) {
  const cat = route.catalog ?? catalog.short;
  const ruleParam = route.params.get("rule");
  const fromRules = route.params.get("from") === "rules";
  const needsWork = !ruleParam;
  const [rules, setRules] = useState<RuleSummary[] | null>(null);
  const [data, setData] = useState<PromptResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api.rules(catalog.catalog).then((r) => { if (live) setRules(r.groups.flatMap((g) => g.rules)); },
                                    (e) => { if (live) setError(String(e)); });
    return () => { live = false; };
  }, [catalog.catalog, catalog.extraction]);

  useEffect(() => {
    let live = true;
    setData(null);
    setError(null);
    api.prompt(catalog.catalog, needsWork ? { needs_work: true } : { rule: ruleParam ?? undefined })
      .then((d) => { if (live) setData(d); }, (e) => { if (live) setError(String(e)); });
    return () => { live = false; };
  }, [catalog.catalog, catalog.extraction, ruleParam, needsWork]);

  const needing = useMemo(() => (rules ?? []).filter((r) => r.status === "needs work"), [rules]);
  // The rule the "One rule" picker shows: the one in the route, else the first needing work, else the first.
  const oneRule = ruleParam ?? needing[0]?.rule_id ?? rules?.[0]?.rule_id ?? "";
  const lines = useMemo(() => (data ? highlight(data.text) : []), [data]);
  const scopeName = needsWork ? "needs-work" : ruleParam ?? "";

  useKeyHints(<span>Commands Claude uses: <span className="mono">golden-datasets rule show · rule annotations ·
    pages get · rule try · rule publish</span></span>, []);

  const pickRule = (rid: string) => go(href(cat, "prompt", null, { rule: rid }), true);
  const pickNeedsWork = () => go(href(cat, "prompt"), true);
  const onCopy = async () => {
    if (!data) return;
    toast((await copyText(data.text)) ? "Prompt copied" : "Couldn't copy: select the text and copy it");
  };

  return (
    <div className="prompt-layout">
      <aside className="prompt-side">
        <h1>Prompt for Claude Code</h1>
        {fromRules && ruleParam && (
          <div className="prompt-from">Opened from the Rules tab with <b>{ruleParam}</b> selected.</div>
        )}
        <div className="lead">Deterministic: the same annotations always give the same text. Paste it into Claude Code
          on the laptop that has the <span className="mono">golden-datasets</span> CLI.</div>

        <label className={"opt" + (!needsWork ? " on" : "")} data-testid="scope-one">
          <input type="radio" name="scope" checked={!needsWork} onChange={() => oneRule && pickRule(oneRule)} />
          <div className="t">One rule</div>
          <div className="d">Everything about one rule: definition, what/how/why, every annotation, signals.</div>
          <select aria-label="Rule" value={oneRule} onChange={(e) => pickRule(e.target.value)}>
            {(rules ?? []).map((r) => (
              <option key={r.rule_id} value={r.rule_id}>{r.rule_id} v{r.version} · {r.status}</option>
            ))}
          </select>
        </label>

        <label className={"opt" + (needsWork ? " on" : "")} data-testid="scope-needs-work">
          <input type="radio" name="scope" checked={needsWork} onChange={pickNeedsWork} />
          <div className="t">All rules needing work
            <span className="needs-pill"><Ico name="needs work" />{needing.length}</span></div>
          <div className="d">{needing.map((r) => r.rule_id).join(", ") || "none"}</div>
        </label>

        <dl className="facts">
          <dt>Characters</dt><dd>{data ? fmt(data.chars) : "…"}</dd>
          <dt>≈ tokens</dt><dd>{data ? fmt(data.tokens) : "…"}</dd>
          <dt>Raw HTML included</dt><dd>none</dd>
          <dt>Page references</dt><dd>{data ? fmt(data.page_refs) : "…"}</dd>
          <dt>Open annotations</dt><dd>{data ? fmt(data.annotations) : "…"}</dd>
        </dl>
        <div className="foot">Claude reads pages with <span className="mono">golden-datasets pages get</span> and tests
          drafts with <span className="mono">golden-datasets rule try</span> before <span className="mono">golden-datasets
          rule publish</span>. The new version appears in the Studio when the manifest changes.</div>
      </aside>

      <section className="prompt-main">
        <div className="prompt-bar">
          <span className="grow">Preview · <span className="mono">{scopeName}</span> · ruleset v{catalog.ruleset_version}</span>
          <button className="btn" disabled={!data} onClick={() => data && download(data.text, downloadName(catalog.short, scopeName))}>
            <Ico name="download" />Download .md</button>
          <button className="btn primary" disabled={!data} onClick={onCopy}><Ico name="copy" />Copy prompt</button>
        </div>
        {error && <div className="prompt-error">{error}</div>}
        <pre className={"prompt-pre" + (data ? "" : " loading")} data-testid="prompt-text">
          {data ? lines.map((segs, i) => (
            <Fragment key={i}>
              {segs.map((s, j) => (s.cls ? <span key={j} className={s.cls}>{s.text}</span> : <Fragment key={j}>{s.text}</Fragment>))}
              {"\n"}
            </Fragment>
          )) : error ? "" : "Building the prompt…"}
        </pre>
      </section>
    </div>
  );
}
