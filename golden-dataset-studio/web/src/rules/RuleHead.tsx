// Middle column header (spec §7.2): the CTDL term linked to its definition, the plain name under it,
// "Approve" (greyed out with the reason while a course is wrong or missing), and
// "How this rule works ▸" (collapsed). The current version only.
import type { CatalogDetail, RuleDetail } from "../api/types";
import { Ico } from "../shell/icons";
import { fmt, termUrl } from "../shell/ui";
import { approveBlocked, whereWord } from "./logic";

const PLAIN: Record<string, string> = {
  "course-page": "Course pages", "program-page": "Program pages",
  "program-page-with-courses": "Program pages that list courses",
  "locator-course-page": "One course per course page", "locator-program-requirement": "One course per requirement line",
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
    const f = d.repeat_filter as { regex?: string } | undefined;
    if (f?.regex) rows.push(["Kept only if its text matches", <code>{f.regex}</code>]);
  } else {
    const loc = def(d, "locator");
    if (loc) rows.push(["Looks inside", <>{plain(loc).toLowerCase()} <span className="faint">(record locator <code>{loc}</code>)</span></>]);
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
  const isField = rule.kind === "field";
  const url = termUrl(rule.ctdl_property);
  const title = isField
    ? (url ? <a className="term" href={url} target="_blank" rel="noopener noreferrer">{rule.ctdl_property}<Ico name="ext" /></a>
           : <span className="term plain">{rule.property_label ?? rule.title}</span>)
    : <span className="term plain">{rule.title}</span>;
  const sub = isField
    ? `${rule.property_label ?? rule.title}${rule.ctdl_property ? "" : " · no CTDL term"} · ${whereWord(rule.locator)}`
    : `${rule.subtitle} · ${rule.kind === "page" ? "page rule" : "record locator"}`;
  const blocked = approveBlocked(rule);
  const approved = rule.status === "approved";
  const fill = rule.fill;
  return (
    <div className="rule-head">
      <div className="rh-top">
        <div className="rh-title"><h1>{title}</h1><span className="rh-sub">{sub}</span></div>
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
              aria-describedby={blocked ? "approve-why" : undefined}><Ico name="correct" />Approve</button>
            {blocked && <span id="approve-why" className="sr-only">{blocked}</span>}
          </span>
        )}
        </div>
      </div>
      <details className="how" data-tour="how-it-works">
        <summary>How this rule works</summary>
        <dl className="wwh">
          <dt>What it finds</dt><dd>{rule.what}</dd>
          <dt>How</dt><dd>{rule.how}</dd>
          <dt>Why</dt><dd className={rule.why ? "" : "empty"}>{rule.why ||
            "Nobody has changed this rule yet: it was carried over unchanged from the previous review tool (review-ui-v2)."}</dd>
        </dl>
        <dl className="tech">
          <DefRows rule={rule} />
          <dt>{isField ? "Filled" : "Found"}</dt>
          <dd>{isField ? `${fmt(fill.found)} of ${fmt(fill.rows)} courses have a value (${fill.rows ? Math.round(100 * fill.found / fill.rows) : 0}%)`
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
