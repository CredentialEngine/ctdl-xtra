// Prompt tab (spec §7.5, screen 09): turn annotations into a prompt for Claude Code.
// Scope: one rule (picker; "Improve this rule" on the Rules tab opens #/c/<catalog>/prompt?rule=<id>&from=rules)
// or all rules needing work (no ?rule); for Claude working on this Studio's root (Local) or the shared Azure root
// (Azure, after a minimal `az login` setup). The text comes from the server (prompt.py), the same as
// `golden-datasets prompt`, so it is deterministic: the same annotations always give the same text.
import { Fragment, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { PromptResponse, PromptTarget, RuleGroup } from "../api/types";
import { go, href } from "../shell/router";
import type { TabProps } from "../shell/tabProps";
import { fmt, Ico, toast, useKeyHints } from "../shell/ui";
import { downloadName, highlight, lineKinds, runs } from "./highlight";
import { Markdown } from "./markdown";
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
  const [groups, setGroups] = useState<RuleGroup[] | null>(null);
  const rules = useMemo(() => (groups ? groups.flatMap((g) => g.rules) : null), [groups]);
  const [view, setView] = useState<"raw" | "rendered">(() => {
    try { return localStorage.getItem("studio.prompt.view") === "rendered" ? "rendered" : "raw"; } catch { return "raw"; }
  });
  const pickView = (v: "raw" | "rendered") => { setView(v); try { localStorage.setItem("studio.prompt.view", v); } catch { /* private */ } };
  const [target, setTarget] = useState<PromptTarget>(() => {
    try { return localStorage.getItem("studio.prompt.target") === "azure" ? "azure" : "local"; } catch { return "local"; }
  });
  const pickTarget = (t: PromptTarget) => { setTarget(t); try { localStorage.setItem("studio.prompt.target", t); } catch { /* private */ } };
  const [data, setData] = useState<PromptResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api.rules(catalog.catalog).then((r) => { if (live) setGroups(r.groups); },
                                    (e) => { if (live) setError(String(e)); });
    return () => { live = false; };
  }, [catalog.catalog, catalog.extraction]);

  useEffect(() => {
    let live = true;
    setData(null);
    setError(null);
    api.prompt(catalog.catalog, { ...(needsWork ? { needs_work: true } : { rule: ruleParam ?? undefined }), target })
      .then((d) => { if (live) setData(d); }, (e) => { if (live) setError(String(e)); });
    return () => { live = false; };
  }, [catalog.catalog, catalog.extraction, ruleParam, needsWork, target]);

  const needing = useMemo(() => (rules ?? []).filter((r) => r.status === "needs work"), [rules]);
  // The rule the "One rule" picker shows: the one in the route, else the first needing work, else the first.
  const oneRule = ruleParam ?? needing[0]?.rule_id ?? rules?.[0]?.rule_id ?? "";
  const lines = useMemo(() => (data ? highlight(data.text) : []), [data]);
  const kinds = useMemo(() => (data ? lineKinds(data.text) : []), [data]);
  const bands = useMemo(() => (data ? runs(data.text) : []), [data]);
  // keep the selected rule visible in the list (e.g. after "Improve this rule")
  useEffect(() => {
    const el = document.querySelector<HTMLElement>(".rule-pick .rp-item.on");
    const box = el?.closest<HTMLElement>(".rule-pick");
    if (el && box) box.scrollTop = Math.max(0, el.offsetTop - box.offsetTop - box.clientHeight / 2 + el.clientHeight / 2);
  }, [groups, oneRule, needsWork]);
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
        <div className="lead">Deterministic: the same annotations always give the same text. Paste it into Claude Code:
          it installs the <span className="mono">golden-datasets</span> CLI from this branch and points it at the root.</div>

        <div className="prompt-k">Where Claude works</div>
        <div className="seg target-seg" role="group" aria-label="Where Claude works">
          <button className={target === "local" ? "on" : ""} onClick={() => pickTarget("local")}>Local</button>
          <button className={target === "azure" ? "on" : ""} onClick={() => pickTarget("azure")}>Azure</button>
        </div>
        <div className="target-d" data-testid="target-d">{target === "local"
          ? <>On this Studio's root, <span className="mono">{data?.root ?? "…"}</span>: run Claude Code on the machine
            that runs the Studio.</>
          : <>On the shared Azure root, <span className="mono">{data?.root ?? "…"}</span>, after <span className="mono">az
            login</span>: works from any machine.{data?.studio_root && data.studio_root !== data.root &&
            <div className="prompt-warn">This Studio serves another root: the rules and annotations in the prompt are this
              root's, and what Claude publishes to Azure shows here only after a <span className="mono">golden-datasets
              sync</span>. Serve the Studio from the Azure root to keep them the same.</div>}</>}
        </div>
        {data?.warning && <div className="prompt-warn" data-testid="prompt-warn">{data.warning}</div>}

        <div className="prompt-k">Scope</div>
        <label className={"opt" + (!needsWork ? " on" : "")} data-testid="scope-one">
          <input type="radio" name="scope" checked={!needsWork} onChange={() => oneRule && pickRule(oneRule)} />
          <div className="t">One rule{!needsWork && <span className="opt-pick mono">{oneRule}</span>}</div>
          <div className="d">Everything about one rule: definition, what/how/why, every annotation, signals.</div>
        </label>
        {!needsWork && (
          <div className="rule-pick" role="listbox" aria-label="Rule">
            {(groups ?? []).map((g) => (
              <div key={g.kind} className="rp-group">
                <div className="rp-h">{g.label}</div>
                {g.rules.map((r) => (
                  <button key={r.rule_id} role="option" aria-selected={r.rule_id === oneRule}
                    className={"rp-item" + (r.rule_id === oneRule ? " on" : "")}
                    onClick={() => pickRule(r.rule_id)} title={`${r.rule_id} · v${r.version} · ${r.status}`}>
                    <Ico name={r.status} />
                    <span className="rp-t">{r.title}<span className="rp-sub">{r.kind === "field" ? (r.ctdl_property ?? "no CTDL term") : r.rule_id}</span></span>
                    {r.open_wrong + r.open_missing > 0 && <span className="rp-n" title="open wrong / missing verdicts">{r.open_wrong + r.open_missing}</span>}
                  </button>
                ))}
              </div>
            ))}
          </div>
        )}

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
          <span className="grow">Preview · <span className="mono">{scopeName}</span> · {target === "azure" ? "Azure" : "Local"} · ruleset v{catalog.ruleset_version}</span>
          <div className="seg md-seg" role="group" aria-label="Preview">
            <button className={view === "raw" ? "on" : ""} onClick={() => pickView("raw")}>Raw</button>
            <button className={view === "rendered" ? "on" : ""} onClick={() => pickView("rendered")}>Rendered</button>
          </div>
          <button className="btn" disabled={!data} onClick={() => data && download(data.text, downloadName(catalog.short, scopeName + (target === "azure" ? "-azure" : "")))}>
            <Ico name="download" />Download .md</button>
          <button className="btn primary" disabled={!data} onClick={onCopy}><Ico name="copy" />Copy prompt</button>
        </div>
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
      </section>
    </div>
  );
}
