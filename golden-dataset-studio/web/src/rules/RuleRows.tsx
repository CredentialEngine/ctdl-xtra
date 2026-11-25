// The middle column's rows: one card per row, or for a repeating record locator one row per page with its courses inside
// (sme-fixes §3); the courses or pages marked missing above them; "more" and the empty state below.
import type { EventBrief, RuleDetail } from "../api/types";
import { SkelCards } from "../shell/Skeleton";
import { Ico } from "../shell/icons";
import { href } from "../shell/router";
import { fmt } from "../shell/ui";
import type { RowX } from "./api";
import { ListItems } from "./ListItems";
import { canConfirm, groupOf, shortTitle, subjectOf, type Draft, type PageGroup } from "./logic";
import { Expansion } from "./parts";
import { ProfileItems } from "./ProfileItems";
import { RowCard } from "./RowCard";
import type { RulesTabState } from "./useRulesTab";

export function RowsColumn({ t }: { t: RulesTabState }) {
  const ready = !!t.detail && !t.loadingRule;
  return (
    <div className="rows" data-tour="rows" ref={t.rowsRef} onScroll={(e) => loadNearBottom(e.currentTarget, t.loadMore)}>
      {t.missing.length > 0 && t.kind !== "property" && <MissingList missing={t.missing} kind={t.kind} />}
      {t.loadingRule && <SkelCards label="Loading this rule's rows" />}
      {ready && <RuleRows t={t} detail={t.detail!} />}
      {ready && t.rows.length < t.total && <div className="row more-rows" onClick={t.loadMore}>+ {fmt(t.total - t.rows.length)} more · scroll to load</div>}
      {ready && t.total === 0 && <div className="empty-state muted">{emptyWords(t)}</div>}
    </div>
  );
}

function loadNearBottom(el: HTMLElement, loadMore: () => void) {
  if (el.scrollTop + el.clientHeight > el.scrollHeight - 600) loadMore();
}

function emptyWords({ by, verdict, filtered }: RulesTabState): string {
  if (by || verdict) return "No row of this rule passes the Annotated by filter. Pick another rule, or Anyone above.";
  return filtered ? "No row is in every stratum you picked. Remove a filter above." : "This rule found nothing in this extraction.";
}

function MissingList({ missing, kind }: { missing: EventBrief[]; kind: RulesTabState["kind"] }) {
  return (
    <div className="missing-list">
      <div className="ml-h"><Ico name="missing" />{missing.length} marked missing: {kind === "locator" ? "courses" : "pages"} this rule didn't find</div>
      {missing.map((m) => (
        <div key={m.annotation_id} className="ml-item">
          <span className="ml-t">{m.expected?.text ? shortTitle(m.expected.text, 90) : shortTitle(m.page_stem ?? "", 80)}</span>
          <span className="faint">{m.author}{m.note ? `: “${m.note}”` : ""}</span>
        </div>
      ))}
    </div>
  );
}

type RenderRow = (r: RowX, i: number) => JSX.Element;

function RuleRows({ t, detail }: { t: RulesTabState; detail: RuleDetail }) {
  const rowCard: RenderRow = (r, i) => <RuleRowCard key={r.key} t={t} detail={detail} r={r} i={i} />;
  if (!t.perPage) return <>{t.rows.map(rowCard)}</>;
  // one row per page; the current page's courses inside it, each with its own ✓ ✕ (sme-fixes §3)
  const cur = groupOf(t.groups, t.sel);
  return <>{t.groups.map((g) => <PageGroupBlock key={`${g.stem}@${g.start}`} t={t} g={g} open={g === cur} rowCard={rowCard} />)}</>;
}

function RuleRowCard({ t, detail, r, i }: { t: RulesTabState; detail: RuleDetail; r: RowX; i: number }) {
  const on = i === t.sel && !t.onPage;
  return (
    <RowCard row={r} kind={detail.kind} index={i} on={on} draft={on ? t.draft : null} perPage={t.perPage}
      label={t.kind === "property" ? detail.property_label : "Found"} onClick={() => t.selectRow(i, "course")}
      links={on && r.record_external_identifier ? <RecordsLink t={t} detail={detail} r={r} /> : null}
      items={t.listRule && r.items ? <RowItems t={t} r={r} i={i} on={on} /> : undefined}
      linked={on ? t.linkedNote : null}
      expansion={on && t.draft ? <RowExpansion t={t} draft={t.draft} r={r} i={i} /> : null}
      onPick={(v) => t.pick(i, v)} tour={on} confirm={canConfirm(r, t.role)} marked={r.human_reviewed || r.engineer_checked}
      commentOnly={t.listRule} />
  );
}

/** "Open in Records →" on the selected row (the same for every kind of row). */
function RecordsLink({ t, detail, r }: { t: RulesTabState; detail: RuleDetail; r: RowX }) {
  return <a className="xbtn" title="Open this course in the Records tab, with this property selected"
    href={href(t.cat, "records", r.record_external_identifier, { prop: t.kind === "property" ? detail.property_label : null, occ: r.occurrence_key })}
    onClick={(e) => e.stopPropagation()}>Open in Records →</a>;
}

/** A list property's items: plain items, or a list of objects. */
function RowItems({ t, r, i, on }: { t: RulesTabState; r: RowX; i: number; on: boolean }) {
  if (!t.profile) {
    return <ListItems row={r} on={on} add={on ? t.itemAdd : null} onVerdict={(it, v) => void t.saveItem(i, it, v)}
      onStartAdd={t.startAddItem} onSaveAdd={() => void t.saveAddItem()} onCancelAdd={() => t.setItemAdd(null)} />;
  }
  return <ProfileItems row={r} on={on} fields={t.profile.fields} keyField={t.profile.key}
    noun={t.noun} add={on ? t.objAdd : null} fix={on ? t.objFix : null}
    onVerdict={(it, v) => void t.saveItem(i, it, v)} onStartAdd={t.startAddObject} onLabel={t.labelObject}
    onSaveAdd={() => t.objAdd && void t.saveObject(t.objAdd)} onCancelAdd={() => t.setObjAdd(null)}
    onSelectItem={t.selectObject} onSaveFix={() => void t.saveFix()} onCancelFix={() => t.setObjFix(null)} onTakeBack={(m) => void t.takeBack(m)} />;
}

function RowExpansion({ t, draft, r, i }: { t: RulesTabState; draft: Draft; r: RowX; i: number }) {
  return <Expansion draft={draft} propertyRule={t.kind === "property"} emptyValue={r.status !== "found"}
    onChange={t.setDraft} onSave={() => void t.saveRow(i, { draft })} onCancel={() => t.setDraft(null)} />;
}

function PageGroupBlock({ t, g, open, rowCard }: { t: RulesTabState; g: PageGroup; open: boolean; rowCard: RenderRow }) {
  const rs = t.rows.slice(g.start, g.end);
  return (
    <div className={`page-group${open ? " open" : ""}`}>
      <PageHead t={t} g={g} rs={rs} open={open} />
      {open && <>{rs.map((r, k) => rowCard(r, g.start + k))}
        <button className="row add-course" onClick={(e) => { e.stopPropagation(); t.startMissed(); }}
          title="A course on this page that no box outlines: click its block on the page to add it">+ Add a course this rule missed</button></>}
    </div>
  );
}

function PageHead({ t, g, rs, open }: { t: RulesTabState; g: PageGroup; rs: RowX[]; open: boolean }) {
  const n = rs[0]?.page_courses ?? rs.length;
  const all = rs.length === n && rs.every((r) => r.state === "correct");
  return (
    <div className={`row page-head${open && t.onPage ? " on" : ""}${all ? " done" : ""}`} data-page-start={g.start}
      data-testid="page-head" tabIndex={-1} onClick={() => t.selectRow(g.start, "page")}>
      <PageTitle g={g} rs={rs} n={n} open={open} />
      <button className={`cb ok${all ? " on" : ""}`} aria-label="Accept every course on this page"
        title={`Correct: accept all ${fmt(rs.length)} ${rs.length === 1 ? "course" : "courses"} of this page at once (1 on the page row)`}
        onClick={(e) => { e.stopPropagation(); void t.acceptPage(g.start); }}><Ico name="correct" /></button>
    </div>
  );
}

function PageTitle({ g, rs, n, open }: { g: PageGroup; rs: RowX[]; n: number; open: boolean }) {
  const subject = subjectOf(rs.map((r) => r.record_external_identifier));
  return (
    <div className="ph-t">
      {subject && <b>{subject}</b>}{subject && " · "}{shortTitle(rs[0]?.page_title ?? g.stem, 70)}
      <span className="faint"> · {fmt(n)} {n === 1 ? "course" : "courses"}</span>
      {!open && <Ico name="chevron-right" className="ph-car" />}
    </div>
  );
}
