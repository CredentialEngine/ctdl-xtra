// The Records tab (spec §7.3, screen 07): find a course, see every property as a card, with the same
// verdict controls as the Rules tab (the same `verdict` events, targeting (property rule, occurrence)) and the same
// page pane with numbered highlights for each property. "Annotated by" (?by=…, Evals spec §6.8) lists only the courses a
// person annotated; on a course, their properties come first and the rest fold into one line.
import { Skel, SkelCards, SkelList } from "../shell/Skeleton";
import type { ReactNode } from "react";
import type { CourseDetail } from "../api/types";
import { PagePane } from "../pagepane";
import { AnnotatedBy, PersonLine, ReviewLine } from "../rules/AnnotatedBy";
import type { CourseHitX } from "../rules/api";
import { addCapture, canConfirm, isSettled, shortTitle } from "../rules/logic";
import { Controls, Expansion, HistoryLine } from "../rules/parts";
import { statusWords } from "../rules/claims";
import "../rules/rules.css";
import { Ico } from "../shell/icons";
import { go, href, type ClassSlug } from "../shell/router";
import type { TabProps } from "../shell/tabProps";
import { fmt, termUrl } from "../shell/ui";
import { foldLine, recordHeading, valueKey, type Card, type CardValue } from "./logic";
import { apiClass, NOUN } from "../shell/klass";
import { useRecordsPage, type RecordsPage } from "./useRecordsPage";
import "./records.css";

type PageProps = { page: RecordsPage };

export default function RecordsTab({ catalog, route }: TabProps) {
  const page = useRecordsPage(catalog, route);
  return (
    <div className="rec-layout w4-records">
      <RecordFinder page={page} />
      <RecordCards page={page} />
      <section className="col pane"><RecordPane page={page} /></section>
    </div>
  );
}

function RecordFinder({ page }: PageProps) {
  const { address, list, me } = page;
  return (
    <aside className="col">
      <input className="search" placeholder={address.allCls ? "Find a course or a program" : `Find a ${address.noun[0]} by name or identifier`}
        value={list.q} onChange={(e) => list.setQ(e.target.value)} aria-label={`Find a ${address.noun[0]}`} />
      <div className="records-filter">
        <AnnotatedBy people={list.people} by={address.by} me={me} onPick={(x) => go(href(address.cat, "records", null, { by: x }))} />
      </div>
      <RecordList page={page} />
    </aside>
  );
}

function RecordList({ page }: PageProps) {
  const { address, list } = page;
  const classes = address.allCls ? list.ruled.map((c) => c.slug) : [null];
  return (
    <div className="course-list" ref={list.listRef}>
      {list.listLoading && <SkelList label={`Loading ${address.noun[1]}`} heads={false} />}
      {!list.listLoading && classes.map((cls) => <ClassRecords key={cls ?? "one"} page={page} cls={cls} />)}
      {!list.listLoading && list.hits && list.hits.length === 0 && <div className="faint" style={{ padding: 10 }}>{list.q
        ? <>No {address.noun[0]} matches “{list.q}”.</> : `No ${address.noun[0]} passes the Annotated by filter.`}</div>}
    </div>
  );
}

function ClassRecords({ page, cls }: PageProps & { cls: ClassSlug | null }) {
  const hits = (page.list.hits ?? []).filter((h) => !cls || h.cls === cls);
  const isShut = isClassShut(page, cls);
  return (
    <div className="cls-list">
      {cls && <ClassHeading page={page} cls={cls} isShut={isShut} />}
      {!isShut && hits.map((h) => <RecordLink key={`${h.cls ?? ""}:${h.record_external_identifier}`} page={page} hit={h} cls={cls} />)}
    </div>
  );
}

function ClassHeading({ page, cls, isShut }: PageProps & { cls: ClassSlug; isShut: boolean }) {
  const summary = page.list.ruled.find((c) => c.slug === cls);
  if (!summary) return null;
  return (
    <button type="button" className={`cls-h${isShut ? " shut" : ""}`} aria-expanded={!isShut}
      onClick={() => page.list.setShut((s) => ({ ...s, [cls]: !isShut }))}>
      <Ico name="chevron" />{summary.name}<span>{summary.records === null ? "" : `${fmt(summary.records)} ${NOUN[cls][1]}`}</span>
    </button>
  );
}

function RecordLink({ page, hit: h, cls }: PageProps & { hit: CourseHitX; cls: ClassSlug | null }) {
  const { cat, by, recordKey, openCls } = page.address;
  const isOpen = h.record_external_identifier === recordKey && (!cls || cls === openCls);
  return (
    <a title={h.line ?? undefined} className={`course-item named${isOpen ? " on" : ""}`}
      href={href(cat, "records", h.record_external_identifier, { by, in: cls })}>
      <span className="t">{h.name ?? (h.line ?? "").replace(/^[^-]*-\s*/, "")}{h.annotated && <span className="dot" title="has verdicts" />}</span>
      <span className={`c${isGeneratedKey(h, openCls) ? " gen" : ""}`}>
        {h.record_external_identifier}</span>
    </a>
  );
}

function RecordCards({ page }: PageProps) {
  const { list, cards, record, address } = page;
  return (
    <section className="col mid">
      {list.error && <div className="placeholder muted" style={{ padding: 18 }}>{list.error}</div>}
      {cards.recordLoading && <><div className="rec-head"><Skel w="34%" h={22} /></div><SkelCards label={`Loading this ${address.noun[0]}`} /></>}
      {record.course && !cards.recordLoading && <RecordBody page={page} course={record.course} />}
    </section>
  );
}

function RecordBody({ page, course }: PageProps & { course: CourseDetail }) {
  const { cards, address: { by }, selection } = page;
  return (<>
    <div className="rec-head"><h1>{recordHeading(cards.all, course.record_external_identifier, apiClass())}</h1>
      {cards.pages > 1 && <div className="sub">Values from {cards.pages} pages</div>}</div>
    <div className="cards" ref={page.cardsRef}>
      {cards.cards.map((c) => <PropertyCard key={c.property} page={page} card={c} />)}
      {by && cards.folded.length > 0 && !selection.showAll && (
        <div className="rec-fold" data-testid="fold">{foldLine(cards.folded.length, by)} · <button className="linkish" onClick={() => selection.setShowAll(true)}>show</button></div>)}
    </div>
  </>);
}

function PropertyCard({ page, card: c }: PageProps & { card: Card }) {
  const url = termUrl(c.ctdl_property);
  return (
    <div className="card" data-card={c.n}>
      <div className="card-h"><span className="bn">{c.n}</span>
        {url ? <a className="term sm" href={url} target="_blank" rel="noopener noreferrer">{c.ctdl_property?.replace(/>/g, " → ")}<Ico name="ext" /></a>
             : <span className="term sm plain">no CTDL term</span>}
        <span className="lbl">{c.property}</span></div>
      <div className="vals">{c.values.map((v) => <ValueRow key={valueKey(v)} page={page} v={v} />)}</div>
    </div>
  );
}

function ValueRow({ page, v }: PageProps & { v: CardValue }) {
  const { cards, selection: { draft, select }, actions, role } = page;
  const on = cards.cur?.v === v;
  const settled = isSettled(v.state);
  return (
    <div className={`v${on ? " on" : ""}${v.verdict ? ` v-${v.verdict.verdict}` : ""}${settled && !(on && draft) ? " done" : ""}`}
      onClick={() => { if (!on) select(valueKey(v)); }}>
      <ValueDetails page={page} v={v} on={on} />
      <Controls state={v.state} verdict={v.verdict} comments={v.comments} draft={on ? draft : null} onPick={(k) => actions.pick(v, k)}
        confirm={canConfirm(v, role)} marked={v.human_reviewed || v.engineer_checked} />
    </div>
  );
}

function ValueDetails({ page, v, on }: PageProps & { v: CardValue; on: boolean }) {
  const { address, cards, selection: { draft, setDraft }, actions } = page;
  return (
    <div style={{ minWidth: 0 }}>
      <ValueBox v={v} on={on} />
      {cards.pages > 1 && <div className="src"><span className="tag">{v.on_course_page ? `${address.noun[0]} page` : "other page"}</span><span>{shortTitle(v.page_title, 70)}</span></div>}
      {on && <OpenInRules cat={address.cat} v={v} />}
      <WhoReviewed v={v} by={address.by} />
      <HistoryLine state={v.state} verdict={v.verdict} comments={v.comments} />
      {on && draft && <Expansion draft={draft} propertyRule emptyValue={v.status !== "found"} onChange={setDraft}
        onSave={() => void actions.save(v, { draft })} onCancel={() => setDraft(null)} />}
    </div>
  );
}

function ValueBox({ v, on }: { v: CardValue; on: boolean }) {
  return (
    <div className={`valbox${on ? " on" : ""}${v.status === "found" ? "" : " empty"}`}>
      {on && <span className="valbox-k">Value</span>}
      {v.items
        ? v.items.map((it) => <div key={it.value_index} className="item-line">{it.value}</div>)  // a list: one line per item
        : <div className="tx">{statusWords(v.status, v.value)}</div>}
    </div>
  );
}

function OpenInRules({ cat, v }: { cat: string; v: CardValue }) {
  return (
    <div className="row-links">
      <a className="xbtn" title="Open this property's rule in the Rules tab, with this course selected"
        href={href(cat, "rules", v.rule_id, { row: v.occurrence_key })}
        onClick={(e) => e.stopPropagation()}>Open in Rules →</a>
    </div>
  );
}

function WhoReviewed({ v, by }: { v: CardValue; by: string | null }) {
  if (v.human_reviewed || v.engineer_checked) return <ReviewLine r={v} />;
  return by && v.annotators?.[by] ? <PersonLine name={by} a={v.annotators[by]} /> : null;
}

function RecordPane({ page }: PageProps) {
  const { address, pane, selection: { draft, setDraft, setActiveStem }, catalog } = page;
  return (
    <PagePane catalog={address.cat} tabs={pane.tabs} activeStem={pane.active} onActivate={setActiveStem} highlights={pane.highlights} focusId={pane.focusId}
      banner={bannerOf(page)} legend={legendOf(page)} ruleset={catalog.ruleset_version}
      captureSelection={draft?.mode === "wrong"}
      onSelection={(c) => setDraft((d) => (d && d.mode === "wrong" ? { ...d, captures: addCapture(d.captures, c) } : d))}
      onRemove={(id) => setDraft((d) => (d ? { ...d, captures: d.captures.filter((_, j) => `capture-${j}` !== id) } : d))} />
  );
}

function bannerOf({ cards, pane, selection }: RecordsPage): ReactNode {
  const card = cards.cur?.card;
  if (selection.draft?.mode === "wrong" || !card) return null;
  return <><span className="gds-num">{card.n}</span><span className="grow"><b>{card.property}</b> on {shortTitle(pane.tabs.find((t) => t.stem === pane.active)?.title, 50)} — numbers match the cards on the left.</span></>;
}

function legendOf({ cards, selection }: RecordsPage): ReactNode {
  const card = cards.cur?.card;
  if (selection.draft?.mode !== "wrong" || !card) return null;
  return <><Ico name="highlight" /><span><b>Select the right text</b> on the page for {card.property}: drag across it.</span></>;
}

function isClassShut({ list, address }: RecordsPage, cls: ClassSlug | null): boolean {
  if (!cls) return false;
  return list.shut[cls] ?? (cls !== (address.openCls ?? list.ruled[list.ruled.length - 1]?.slug) && !list.q);
}

function isGeneratedKey(h: CourseHitX, openCls: ClassSlug | null): boolean {
  return h.record_external_identifier.startsWith(`${NOUN[(h.cls ?? openCls ?? "course") as ClassSlug][0]}-`);
}
