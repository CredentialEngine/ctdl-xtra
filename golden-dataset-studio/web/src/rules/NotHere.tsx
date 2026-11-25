// A link to one row (?row=, e.g. Compare's "See on page →") that this ruleset doesn't have: its rule isn't in the
// ruleset (v3 dropped the program-page rules), or the rule found no value for that record. The Rules tab then says so
// plainly above the rows and still shows the record's saved page, instead of a blank column and an empty pane.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CatalogDetail } from "../api/types";
import { href } from "../shell/router";
import type { TabRef } from "./logic";
import "./notHere.css";

/** Why the linked row isn't shown: `rule` (no such rule in this ruleset), `row` (no value for it in this ruleset's
 *  extraction) or `hidden` (a filter above hides it). */
export type Missing = "rule" | "row" | "hidden";

/** The page a row key (`<page stem>@<css path>`), occurrence key or page stem names; null for a course key. */
export function focusStem(focus: string | null): string | null {
  if (!focus) return null;
  const at = focus.indexOf("@");
  return at > 0 ? focus.slice(0, at) : /[a-z]/.test(focus) && focus.includes("-") ? focus : null;
}

/** The saved page of the linked row, as a pane tab (its URL and title from the page's meta). */
export function useFocusPage(catalog: string, stem: string | null): TabRef | null {
  const [tab, setTab] = useState<TabRef | null>(null);
  useEffect(() => {
    if (!stem) { setTab(null); return; }
    let live = true;
    setTab({ stem, url: "", title: stem });
    api.pageMeta(catalog, stem).then((m) => { if (live) setTab({ stem, url: m.url, title: m.title || stem }); }, () => {});
    return () => { live = false; };
  }, [catalog, stem]);
  return tab;
}

export function NotHere({ catalog, ruleId, ruleName, focus, ext, version, why, onAnyone }: NotHereProps) {
  const other = useRulesetWith(catalog, ruleId, ext, why === "rule");
  const record = focusStem(focus) ? "This record" : focus;
  const otherHref = other && href(catalog.short, "rules", ruleId,
    { row: focus, ext: other.extraction === catalog.extraction ? null : other.extraction });
  return (
    <div className="not-here" data-testid="not-here">
      {why === "rule" ? <NoSuchRule record={record} ruleId={ruleId} version={version} other={other} otherHref={otherHref} />
        : why === "row" ? <NoValue record={record} ruleName={ruleName} version={version} />
        : <FilteredOut record={record} onAnyone={onAnyone} />}
    </div>
  );
}

interface NotHereProps {
  catalog: CatalogDetail; ruleId: string; ruleName: string; focus: string; ext: string | null; version: number;
  why: Missing; onAnyone?: () => void;
}

type RulesetRef = { extraction: string; ruleset_version: number };

/** The newest other ruleset whose extraction has this rule (looked up only when this one doesn't). */
function useRulesetWith(catalog: CatalogDetail, ruleId: string, ext: string | null, on: boolean) {
  const [found, setFound] = useState<RulesetRef | null>(null);
  useEffect(() => {
    setFound(null);
    if (!on) return;
    let live = true;
    void findRulesetWith(catalog, ruleId, ext ?? catalog.extraction, (x) => { if (live) setFound(x); });
    return () => { live = false; };
  }, [catalog, ruleId, ext, on]);
  return found;
}

async function findRulesetWith(catalog: CatalogDetail, ruleId: string, here: string, onFound: (x: RulesetRef) => void) {
  const others = [...catalog.extractions].filter((x) => x.extraction !== here)
    .sort((a, b) => b.ruleset_version - a.ruleset_version);
  for (const x of others) {
    try { await api.rule(catalog.short, ruleId, x.extraction); onFound(x); return; } catch { /* not in it */ }
  }
}

function NoSuchRule({ record, ruleId, version, other, otherHref }: {
  record: string; ruleId: string; version: number; other: RulesetRef | null; otherHref: string | null;
}) {
  return (<>
    <b>{record} has no value in ruleset v{version}:</b> this ruleset has no rule <span className="mono">{ruleId}</span>.
    {" "}Its saved page is on the right.
    {otherHref && <> <a href={otherHref}>See it in ruleset v{other!.ruleset_version} →</a></>}
  </>);
}

function NoValue({ record, ruleName, version }: { record: string; ruleName: string; version: number }) {
  return (<>
    <b>{record} has no value for {ruleName} in ruleset v{version}:</b> the rule found nothing for it in this
    ruleset's extraction. Its saved page is on the right; the rows below are the rule's other values.
  </>);
}

function FilteredOut({ record, onAnyone }: { record: string; onAnyone?: () => void }) {
  return (<>
    <b>{record} isn't among the rows shown:</b> a filter above hides it. Its saved page is on the right.
    {onAnyone && <> <button className="linkbtn" onClick={onAnyone}>Show everyone's rows</button></>}
  </>);
}
