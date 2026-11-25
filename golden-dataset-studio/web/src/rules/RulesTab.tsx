// The Rules tab (spec §7.2, screens 03–06, 12): rules by kind on the left, one rule's rows in the middle
// (sorted by the server with the likeliest problems first), the saved page on the right. "Annotated by" and its verdict
// switch (?by=…&v=…, Evals spec §6.7) filter the rows of every rule, and the rule list counts the rows that pass.
import type { CatalogDetail, RulesResponse } from "../api/types";
import { FixBar } from "../agent/FixBar";
import { openRunDialog } from "../agent/RunDialog";
import { PagePane } from "../pagepane";
import { SampleDrawer } from "../shell/Sample";
import { SkelHead, SkelList } from "../shell/Skeleton";
import { go, href } from "../shell/router";
import { classOfRule } from "../shell/klass";
import type { TabProps } from "../shell/tabProps";
import { AnnotatedBy, VerdictSwitch, WaitingNote } from "./AnnotatedBy";
import { ApproveDialog } from "./ApproveDialog";
import { BY_WAITING, filterCountTip } from "./logic";
import { MissedCourse, MissedPage } from "./MissedPanel";
import { NotHere } from "./NotHere";
import { paneNotes } from "./paneNotes";
import { ResetDialog } from "./ResetDialog";
import { RowsColumn } from "./RuleRows";
import { RuleHead } from "./RuleHead";
import { RuleList } from "./RuleList";
import { useRulesTab, type RulesTabState } from "./useRulesTab";
import "./rules.css";

export { defaultRule } from "./rulesData";

export default function RulesTab({ catalog, route }: TabProps) {
  const t = useRulesTab(catalog, route);
  if (t.error && !t.rules) return <div className="placeholder muted" style={{ padding: 24 }}>{t.error}</div>;
  return (
    <div className="rules-layout w4-rules">
      <aside className="col">{!t.rules && <SkelList label="Loading rules" />}{t.rules && <RulesSidebar t={t} rules={t.rules} />}</aside>
      <RuleColumn t={t} />
      <PageColumn t={t} />
    </div>
  );
}

type Props = { t: RulesTabState };

function RulesSidebar({ t, rules }: Props & { rules: RulesResponse }) {
  const { cat, ext, verdict, byParam, ruleId, all } = t;
  return <RuleList rules={rules} active={ruleId} heads={t.heads}
    onPick={(id) => go(href(cat, "rules", id, { ext: all && classOfRule(id) !== classOfRule(ruleId) ? null : ext, by: byParam, v: verdict }))}
    talk={t.talk} onTalk={t.postTalk} counts={t.people?.rules} countTip={(n) => filterCountTip(n, t.by, verdict)}
    aiStat={t.aiStat} onImprove={ext ? undefined : (r) => openRunDialog([r.rule_id])}
    top={<RulesetPicker catalog={t.catalog} ext={ext} onPick={(x) => go(href(cat, "rules", ruleId, { ext: x, by: byParam, v: verdict }))} />}
    bottom={<SidebarFoot t={t} rules={rules} />} />;
}

function SidebarFoot({ t, rules }: Props & { rules: RulesResponse }) {
  const { by } = t;
  return (<>
    {t.role === "sme" && <WaitingNote n={t.people?.waiting ?? 0} on={by === BY_WAITING}
      onToggle={() => t.setFilter({ by: by === BY_WAITING ? null : BY_WAITING, v: null })} />}
    {!t.ext && <FixBar catalog={t.cat} name={t.catalog.name} rules={rules} />}</>);
}

/** Top of the sidebar: which ruleset's extraction the tab shows; the newest is "(latest)" and has no ?ext. */
function RulesetPicker({ catalog, ext, onPick }: { catalog: CatalogDetail; ext: string | null; onPick: (ext: string | null) => void }) {
  const items = [...catalog.extractions].sort((a, b) => b.ruleset_version - a.ruleset_version || b.extraction.localeCompare(a.extraction));
  const value = ext ?? catalog.extraction;
  return (
    <label className="ruleset-pick" data-testid="ruleset-pick">
      <span className="panel-title">Ruleset</span>
      <select value={value} onChange={(e) => onPick(e.target.value === catalog.extraction ? null : e.target.value)}>
        {items.map((x) => (
          <option key={x.extraction} value={x.extraction}>
            v{x.ruleset_version}{x.extraction === catalog.extraction ? " (latest)" : ""}
          </option>))}
      </select>
    </label>
  );
}

function RuleColumn({ t }: Props) {
  return (
    <section className="col mid">
      {t.loadingRule && <SkelHead />}
      {t.detail && !t.loadingRule && <RuleHead catalog={t.catalog} rule={t.detail} busy={t.busy} onApprove={() => t.approve("approve")}
        onReopen={() => t.approve("reopen")} onReset={() => void t.openReset()} />}
      <RuleDialogs t={t} />
      {t.detail && <RowSample t={t} />}
      {t.notHere && t.focus && t.ruleId && <LinkedRowNote t={t} why={t.notHere} focus={t.focus} ruleId={t.ruleId} />}
      <RowsColumn t={t} />
    </section>
  );
}

function RuleDialogs({ t }: Props) {
  return (<>
    {t.resetting && <ResetDialog p={t.resetting} catalogName={t.catalog.name} busy={t.busy} onReset={(why) => void t.reset(why)}
      onClose={() => t.setResetting(null)} />}
    {t.asking && <ApproveDialog p={t.asking} busy={t.busy} onApprove={() => t.approve("approve", true)} onClose={() => t.setAsking(null)} />}
  </>);
}

function RowSample({ t }: Props) {
  return <SampleDrawer sample={t.sample} prefs={t.prefs} onPrefs={t.setPrefs} modes={["review", "auto", "shuffle", "manual"]}
    storageKey="studio.rules.sample" collapseOn={t.moves} filters={<AnnotatedByFilters t={t} />} />;
}

function AnnotatedByFilters({ t }: Props) {
  return (<>
    <span className="sm-k">Annotated by</span>
    <div className="sm-ctl">
      <AnnotatedBy people={t.people} by={t.by} me={t.me} bare onPick={(x) => t.setFilter({ by: x })} />
      <VerdictSwitch verdict={t.verdict} onPick={(x) => t.setFilter({ v: x })} />
    </div>
  </>);
}

/** A link to one row (?row=) this ruleset doesn't show: why, and its saved page on the right. */
function LinkedRowNote({ t, why, focus, ruleId }: Props & { why: NonNullable<RulesTabState["notHere"]>; focus: string; ruleId: string }) {
  return <NotHere catalog={t.catalog} ruleId={ruleId} focus={focus} ext={t.ext} why={why}
    ruleName={t.detail?.property_label ?? t.detail?.title ?? ruleId} version={t.rules?.ruleset_version ?? t.catalog.ruleset_version}
    onAnyone={t.by || t.verdict ? () => t.setFilter({ by: null, v: null }) : undefined} />;
}

function PageColumn({ t }: Props) {
  const { legend, banner } = paneNotes(t);
  return (
    <section className="col pane" data-tour="page-pane" ref={t.paneRef}>
      <PagePane catalog={t.cat} tabs={t.tabs} activeStem={t.active} onActivate={(s) => t.setActiveStem(s)}
        highlights={t.highlights} focusId={t.focusId} banner={banner} legend={legend} ruleset={t.catalog.ruleset_version}
        captureSelection={t.selectAnswer} onSelection={t.onAnswer} onRemove={t.removePiece} barActions={t.barActions ?? t.fieldBar} captureFirst={t.captureFirst}
        pickBlock={!!t.missed && t.kind === "locator"}
        onPickBlock={(c) => t.setMissed((m) => (m ? { ...m, capture: c } : m))} />
      {t.missed && t.kind === "locator" && t.row && <MissedCoursePanel t={t} />}
      {t.missed && t.kind === "page" && t.detail && <MissedPagePanel t={t} ruleId={t.detail.rule_id} />}
    </section>
  );
}

function MissedCoursePanel({ t }: Props) {
  return <MissedCourse pageTitle={t.tabs.find((x) => x.stem === t.active)?.title ?? ""} marks={t.ov?.marks ?? []} state={t.missed!}
    onChange={t.setMissed} onSave={() => void t.saveMissed()} onCancel={() => t.setMissed(null)} />;
}

function MissedPagePanel({ t, ruleId }: Props & { ruleId: string }) {
  const open = (p: { page_stem: string; url: string; title: string | null }) => {
    const tab = { stem: p.page_stem, url: p.url, title: p.title ?? p.page_stem };
    t.setExtraTab(tab); t.setActiveStem(tab.stem);
  };
  return <MissedPage catalog={t.cat} ruleId={ruleId} unclassified={t.unclassified} state={t.missed!} onChange={t.setMissed}
    onOpen={open} onSave={() => void t.saveMissed()} onCancel={() => { t.setMissed(null); t.setExtraTab(null); t.setActiveStem(null); }} />;
}
