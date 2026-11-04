// Middle column header (spec §7.2; property-rules spec §4.2, §4.6, m1): the property's name, what it's part of and where it
// looks, its path with arrows (the leaf term linked to its definition), what the rule reads ("Input: …"), "Approve rule"
// (greyed out with the reason while a course is wrong or missing, or the property has no rule yet), and "How this rule
// works ›" (collapsed, a chevron icon; open for a property with no rule yet). The current version only.
import type { CatalogDetail, RuleDetail } from "../api/types";
import { Ico } from "../shell/icons";
import { fmt, termUrl } from "../shell/ui";
import { approveBlocked, whereWord } from "./logic";

// page rules by name; a record locator is titled from its definition by the server (`locator_title`, sme-fixes §3)
const PLAIN: Record<string, string> = {
  "course-page": "Course pages", "program-page": "Program pages",
  "program-page-with-courses": "Program pages that list courses",
};
const plain = (id: string) => PLAIN[id] ?? id;
const def = (d: Record<string, unknown>, k: string) => (d[k] as string | undefined) ?? null;

function DefRows({ rule }: { rule: RuleDetail }) {
  const d = rule.definition;
  const rows: [string, React.ReactNode][] = [];
  if (rule.kind === "page") {
    if (def(d, "url_regex")) rows.push(["Page address must match", <code>{def(d, "url_regex")}</code>]);
    if (def(d, "requires_selector")) rows.push(["Page must contain", <><code>{def(d, "requires_selector")}</code> (a CSS selector)</>]);
    if (def(d, "forbids_selector")) rows.push(["Page must not contain", <code>{def(d, "forbids_selector")}</code>]);
  } else if (rule.kind === "locator") {
    const pr = (d.page_rules as string[] | undefined) ?? [];
    if (pr.length) rows.push(["Used on", <>{pr.map((p, i) => <span key={p}>{i ? ", " : ""}{plain(p)} <span className="faint">(<code>{p}</code>)</span></span>)}</>]);
    rows.push(["One course is", def(d, "repeat") ? <>each <code>{def(d, "repeat")}</code> element</> : "the whole content area of the page"]);
    if (def(d, "scope")) rows.push(["Only inside", <code>{def(d, "scope")}</code>]);
    const f = d.repeat_filter as { selector?: string; regex?: string } | null | undefined;
    if (f?.regex || f?.selector) rows.push(["Kept only if", <>{f.selector ? <><code>{f.selector}</code> inside it</> : "its text"}
      {f.regex ? <> matches <code>{f.regex}</code></> : " is there"}</>]);
  } else {
    const loc = def(d, "locator");
    if (loc) rows.push(["Looks inside", <>{(rule.locator_title ?? plain(loc)).replace(/^\w/, (c) => c.toLowerCase())}{" "}
      <span className="faint">(record locator <code>{loc}</code>)</span></>]);
    const t = def(d, "rule_type");
    if (t === "constant") rows.push(["Value", <>always <code>{String(d.value)}</code>; nothing is read from the page</>]);
    else if (t === "source_url") rows.push(["Value", "the page's own address"]);
    else {
      if (def(d, "selector")) rows.push(["Element (CSS selector)", <code>{def(d, "selector")}</code>]);
      if (def(d, "regex")) rows.push(["Keeps the part matching", <><code>{def(d, "regex")}</code>{d.group ? ` (group ${String(d.group)})` : ""}</>]);
      const tr = (d.transforms as string[] | undefined) ?? [];
      if (tr.length) rows.push(["Then cleans up with", <>{tr.map((x) => <code key={x}>{x} </code>)}</>]);
    }
  }
  return <>{rows.map(([k, v]) => [<dt key={k + "t"}>{k}</dt>, <dd key={k + "d"}>{v}</dd>])}</>;
}

export function RuleHead({ catalog, rule, onApprove, onReopen, busy }: {
  catalog: CatalogDetail; rule: RuleDetail; onApprove: () => void; onReopen: () => void; busy: boolean;
}) {
  const isProperty = rule.kind === "property";
  const child = rule.subtitle.startsWith("part of ");
  // the path with arrows; its leaf term links to the definition (termUrl)
  const shown = (rule.path_shown ?? rule.ctdl_property?.replace(/>/g, " → ")) || "";
  const steps = shown.split(" → ");
  const leaf = steps.pop() ?? "";
  const path = !shown ? <span className="term plain">no CTDL term</span> : (
    <span className="rh-path">
      {steps.length > 0 && <>{steps.join(" → ")} → </>}
      <a className="term" href={termUrl(rule.ctdl_property) ?? undefined} target="_blank" rel="noopener noreferrer">{leaf}<Ico name="ext" /></a>
    </span>);
  const sub = isProperty
    ? [child ? `part of ${rule.parent_label ?? ""}` : null, whereWord(rule.locator)].filter(Boolean).join(" · ")
    : `${rule.subtitle} · ${rule.kind === "page" ? "page rule" : "record locator"}`;
  const blocked = approveBlocked(rule);
  const approved = rule.status === "approved";
  const fill = rule.fill;
  return (
    <div className="rule-head">
      <div className="rh-top">
        <div className="rh-title">
          <h1>{isProperty ? rule.property_label ?? rule.title : <span className="term plain">{rule.title}</span>}</h1>
          <span className="rh-sub">{sub}</span>
          {isProperty && <div className="rh-line">{path}{rule.list && <span className="rl-tag">list</span>}</div>}
          {isProperty && rule.input && <div className="rh-input">Input: <b>{rule.input}</b></div>}
        </div>
        <div className="rh-actions">
        {approved ? (
          <span className="approved-by" data-tour="approve">
            <span className="btn approve is-approved"><Ico name="correct" />Approved</span>
            <span className="ab-who">by {rule.approved_by}{rule.approved_at ? ` · ${rule.approved_at.slice(0, 10)}` : ""} ·{" "}
              <button className="linkish" onClick={onReopen} disabled={busy} title="Undo the approval (a reopen event)">Reopen</button></span>
          </span>
        ) : (
          <span className="tipwrap" data-tip={blocked ?? undefined} data-tour="approve">
            <button className="btn approve" disabled={!!blocked || busy} onClick={onApprove}
              aria-describedby={blocked ? "approve-why" : undefined}><Ico name="correct" />Approve rule</button>
            {blocked && <span id="approve-why" className="sr-only">{blocked}</span>}
          </span>
        )}
        </div>
      </div>
      {rule.no_rule && <p className="rh-norule" role="note">No rule yet. Nothing is extracted for this property. You can still mark the
        value a course shows: select it on the page, then ✗.</p>}
      <details className="how" data-tour="how-it-works" open={!!rule.no_rule}>
        <summary>How this rule works<Ico name="chevron-right" className="how-car" /></summary>
        <dl className="wwh">
          <dt>What it finds</dt><dd>{rule.what}</dd>
          <dt>How</dt><dd>{rule.how}</dd>
          <dt>Why</dt><dd className={rule.why ? "" : "empty"}>{rule.why ||
            "Nobody has changed this rule yet: it was carried over unchanged from the previous review tool (review-ui-v2)."}</dd>
        </dl>
        <dl className="tech">
          <DefRows rule={rule} />
          <dt>{isProperty ? "Filled" : "Found"}</dt>
          <dd>{isProperty ? `${fmt(fill.found)} of ${fmt(fill.rows)} courses have a value (${fill.rows ? Math.round(100 * fill.found / fill.rows) : 0}%)`
                       : `${fmt(fill.found)} ${rule.kind === "page" ? "pages" : "courses"}`}</dd>
          {rule.depends_on.length > 0 && <><dt>Depends on</dt><dd>{rule.depends_on.map((d, i) => (
            <span key={d}>{i ? ", " : ""}{plain(d)} <span className="faint">(<code>{d}</code>)</span></span>))}: if that rule changes, this one is run again.</dd></>}
          <dt>Version</dt><dd>Version {rule.version} of this rule{rule.version === 1 ? " (the first)" : ""}
            {rule.published_by ? `, published by ${rule.published_by}` : ""}. Earlier versions: see the Compare tab.</dd>
          <dt>Fingerprint</dt><dd><code>{rule.content_hash.slice(0, 23)}…</code> · changes whenever the rule's definition changes.</dd>
          <dt>These rows</dt><dd>Values from running ruleset version {catalog.ruleset_version} over the pages saved on{" "}
            {catalog.crawl.slice(0, 10)}; stored as extraction <code>{catalog.extraction}</code>.</dd>
        </dl>
      </details>
    </div>
  );
}
