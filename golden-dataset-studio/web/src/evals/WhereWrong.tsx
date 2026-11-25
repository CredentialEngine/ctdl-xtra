// Where it's wrong (sme-fixes spec §8.4): every unit that isn't a match (under the picked column, or all), grouped by
// outcome × field × a key, biggest group first: each group's count, one example (golden → candidate), and its courses,
// each a link to its row in the Rules tab (anyone's annotations shown).
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { FindingLink, FindingX, PropertyReview, ScoreBasis, ScoreDoc, ThreadTarget, WrongGroups, WrongKey } from "../api/types";
import { FindingPanel } from "../findings/FindingPanel";
import { findingOf, groupThread, linkOf } from "../findings/logic";
import { useReview } from "../findings/Review";
import { BY_ANYONE } from "../rules/logic";
import { currentReviewer } from "../shell/reviewer";
import { href, type ClassSlug } from "../shell/router";
import { fmt, Ico, toast } from "../shell/ui";
import type { Nav } from "./query";
import { goldenTerm, OUTCOME_RULE, shown } from "./score";
import { Tip } from "./Tip";

const WRONG_KEYS: { key: WrongKey; label: string }[] = [
  { key: "auto", label: "the likely cause" }, { key: "label", label: "description label" }, { key: "shape", label: "value shape" },
  { key: "diff", label: "word diff" }, { key: "subject", label: "course subject" }];
const WRONG_SHOWN = 12;

interface WhereWrongProps { cat: string; cls: ClassSlug; doc: ScoreDoc; basis: ScoreBasis; col: string | null; wk: WrongKey; nav: Nav }
type WrongGroup = WrongGroups["groups"][number];
type CourseTarget = { rule_id: string | null; occurrence_key: string | null; golden_record_id?: string | null };
interface Discussion { target: ThreadTarget; title: string }
interface PanelState { finding: FindingX | null; link: FindingLink | null; thread?: Discussion }
type Findings = ReturnType<typeof useGroupFindings>;
interface RowProps { group: WrongGroup; where: WhereWrongProps; findings: Findings }

export function WhereWrong(where: WhereWrongProps) {
  const findings = useGroupFindings(where.cls, where.col);
  const [all, setAll] = useState(false);
  const wrong = useWrongGroups(where);
  if (!wrong) return null;
  return (
    <section className="evx-wrong" data-testid="where-wrong">
      <WrongHeader where={where} />
      {wrong.groups.length === 0 ? <p className="muted small">Nothing: every unit matched.</p>
        : <WrongTable groups={all ? wrong.groups : wrong.groups.slice(0, WRONG_SHOWN)} where={where} findings={findings} />}
      {wrong.groups.length > WRONG_SHOWN && <button className="btn sm" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${fmt(wrong.groups.length)} groups`}</button>}
      {findings.panel && where.col && <GroupFindingPanel cls={where.cls} col={where.col} panel={findings.panel} findings={findings} />}
    </section>
  );
}

/** Findings are per property (learning-programs Phase 6): with a column picked, each group's finding and discussion. */
function useGroupFindings(cls: ClassSlug, col: string | null) {
  const { review, reload, catalogName } = useReview(cls, col);
  const [panel, setPanel] = useState<PanelState | null>(null);
  return { review, reload, catalogName, panel, setPanel };
}

function useWrongGroups({ cat, doc, basis, col, wk }: WhereWrongProps): WrongGroups | null {
  const [wrong, setWrong] = useState<WrongGroups | null>(null);
  useEffect(() => {
    let live = true;
    api.scoreWrong(cat, doc.id, { basis, column: col, key: wk }).then((r) => live && setWrong(r), () => live && setWrong(null));
    return () => { live = false; };
  }, [cat, doc.id, basis, col, wk]);
  return wrong;
}

function WrongHeader({ where: { col, wk, nav } }: { where: WhereWrongProps }) {
  return (
    <header className="evx-wrong-h">
      <h3>Where it's wrong</h3>
      <span className="muted small">{col ? <span className="mono">{col}</span> : "every column"} · every unit that isn't an exact match, grouped by reason, biggest group first</span>
      <span className="grow" />
      <label className="evx-group">Group by
        <select value={wk} aria-label="Where it's wrong: group by" onChange={(e) => nav({ wk: e.target.value === "auto" ? null : e.target.value })}>
          {WRONG_KEYS.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
        </select>
      </label>
    </header>
  );
}

function WrongTable({ groups, where, findings }: { groups: WrongGroup[]; where: WhereWrongProps; findings: Findings }) {
  const term = goldenTerm(where.basis).toLowerCase().replace(/s$/, "");
  return (
    <table className="evx-wrong-t">
      <thead><tr><th className="r">Units</th><th>Reason (outcome · field · how it differs)</th><th>Grouped by</th><th>Example ({term} → candidate)</th><th>Courses</th>
        {where.col && <th>Finding</th>}</tr></thead>
      <tbody>
        {groups.map((g) => <WrongRow key={`${g.outcome}|${g.field}|${g.column}|${g.by}|${g.key}`} group={g} where={where} findings={findings} />)}
      </tbody>
    </table>
  );
}

function GroupFindingPanel({ cls, col, panel, findings: { review, reload, catalogName, setPanel } }: {
  cls: ClassSlug; col: string; panel: PanelState; findings: Findings }) {
  return <FindingPanel key={panel.finding?.id ?? panel.thread?.title ?? "new"} cls={cls} col={col}
    finding={panel.finding ? review?.findings.find((f) => f.id === panel.finding!.id) ?? panel.finding : null}
    link={panel.link} thread={panel.thread ?? null} catalogName={catalogName}
    onClose={() => setPanel(null)} onSaved={reload} />;
}

function WrongRow({ group: g, where, findings }: RowProps) {
  return (
    <tr data-testid="wrong-group">
      <td className="r"><button className="evx-link" title="Show these values" onClick={() => where.nav({ col: g.column, o: g.outcome, off: null })}>{fmt(g.units)}</button></td>
      <WrongReason group={g} col={where.col} />
      <td className="muted">{g.by} <span className="mono">{g.key}</span></td>
      <WrongExample group={g} cat={where.cat} />
      <WrongCourses group={g} cat={where.cat} />
      {where.col && <GroupFindingCell group={g} where={where} findings={findings} col={where.col} />}
    </tr>
  );
}

function WrongReason({ group: g, col }: { group: WrongGroup; col: string | null }) {
  return (
    <td>
      <Tip tip={OUTCOME_RULE[g.outcome]} width={260}><span className={`evx-ob o-${g.outcome}`} tabIndex={0}>{g.outcome}</span></Tip>
      {!col && <span className="mono"> {g.column}</span>}
      {g.field && <span className="mono"> {g.field}</span>}
      {g.reason && <span> {g.reason}</span>}
    </td>
  );
}

function WrongExample({ group: g, cat }: { group: WrongGroup; cat: string }) {
  const example = rulesLink(cat, g.example);
  return (
    <td className="evx-wrong-ex">
      <ClampedValue value={g.example.golden_value} />
      <span className="muted"> → </span>
      <ClampedValue value={g.example.extracted_value} />
      {example && <a className="small" href={example}> {g.example.golden_record_id ?? "open"} in Rules →</a>}
    </td>
  );
}

function WrongCourses({ group: g, cat }: { group: WrongGroup; cat: string }) {
  return (
    <td className="evx-wrong-c">
      <span className="muted">{fmt(g.courses)}</span>{" "}
      {g.targets.map((t, i) => <CourseLink key={i} cat={cat} target={t} />)}
      {g.courses > g.targets.length && <span className="muted small"> +{fmt(g.courses - g.targets.length)}</span>}
    </td>
  );
}

function GroupFindingCell({ group, where: { cat, cls, wk }, findings, col }: RowProps & { col: string }) {
  const me = currentReviewer();
  return <FindingCell review={findings.review} link={linkOf(cat, group, wk)}
    onOpen={(finding, link) => findings.setPanel({ finding, link })}
    onLink={(f, link) => void addToFinding(cls, col, me, f, link, findings.reload)}
    onDiscuss={(link) => findings.setPanel({ finding: null, link, thread: groupDiscussion(link, group) })} />;
}

function ClampedValue({ value }: { value: string | null }) {
  return <span className="evx-clamp" title={value ?? undefined}>{value === null ? <i className="muted">none</i> : shown(value)}</span>;
}

function CourseLink({ cat, target }: { cat: string; target: CourseTarget }) {
  const link = rulesLink(cat, target);
  return link ? <a className="evx-cc" href={link}>{target.golden_record_id ?? "?"}</a>
    : <span className="evx-cc muted">{target.golden_record_id ?? "?"}</span>;
}

async function addToFinding(cls: ClassSlug, col: string, me: string, f: FindingX, link: FindingLink, reload: () => void) {
  try { await api.saveFinding(cls, col, { author: me, links: [...f.links, link] }, f.id); toast(`Added to ${f.code}`); reload(); }
  catch (e) { toast(`Not saved: ${e instanceof Error ? e.message : String(e)}`); }
}

function groupDiscussion(link: FindingLink, g: WrongGroup): Discussion {
  return { target: { kind: "group", catalog: link.catalog, outcome: link.outcome, field: link.field, by: link.by, key: link.key },
    title: `${g.outcome}, ${g.key}` };
}

function rulesLink(cat: string, t: CourseTarget): string | null {
  return t.rule_id ? href(cat, "rules", t.rule_id, { row: t.occurrence_key, by: BY_ANYONE }) : null;
}

interface FindingCellProps {
  review: PropertyReview | null; link: FindingLink;
  onOpen: (f: FindingX | null, link: FindingLink) => void; onLink: (f: FindingX, link: FindingLink) => void; onDiscuss: (link: FindingLink) => void;
}

/** A group's finding (code, title, whose error) or + Add finding (a new one, or an existing finding of the property), and
 * its discussion with its comment count. */
function FindingCell({ review, link, onOpen, onLink, onDiscuss }: FindingCellProps) {
  const [menu, setMenu] = useState(false);
  const f = findingOf(review, link);
  const n = review?.threads[groupThread(link)] ?? 0;
  return (
    <td className="fd-cell" data-testid="finding-cell">
      {f ? <FindingChip finding={f} onOpen={() => onOpen(f, link)} />
        : <AddFinding review={review} link={link} menu={menu} setMenu={setMenu} onOpen={onOpen} onLink={onLink} />}
      <button className="fd-disc" onClick={() => onDiscuss(link)}><Ico name="open" />{n ? <><b>{n}</b> comment{n === 1 ? "" : "s"}</> : "Comment"}</button>
    </td>
  );
}

function FindingChip({ finding: f, onOpen }: { finding: FindingX; onOpen: () => void }) {
  return <button className="fd-chip" onClick={onOpen}><b className="mono">{f.code}</b><span>{f.title}</span>
    {f.whose && <span className="w">{f.whose}</span>}</button>;
}

function AddFinding({ review, link, menu, setMenu, onOpen, onLink }: Omit<FindingCellProps, "onDiscuss"> & {
  menu: boolean; setMenu: (open: boolean) => void }) {
  return (
    <div style={{ position: "relative" }}>
      <button className="fd-add" onClick={() => (review?.findings.length ? setMenu(!menu) : onOpen(null, link))}>+ Add finding</button>
      {menu && <div className="fd-menu" role="menu">
        <button role="menuitem" onClick={() => { setMenu(false); onOpen(null, link); }}>New finding…</button>
        {review!.findings.map((x) => <button key={x.id} role="menuitem" onClick={() => { setMenu(false); onLink(x, link); }}>
          Add to <b className="mono">{x.code}</b> {x.title}</button>)}
      </div>}
    </div>
  );
}
