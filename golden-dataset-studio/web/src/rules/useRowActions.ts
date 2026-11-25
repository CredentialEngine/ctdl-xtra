// What the Rules tab saves: a row's verdict (✓, ✗ with its answer, a comment), a page's courses at once, a missed
// course or page, a list's items and objects, and approving or resetting the rule. Each save is one annotation event.
import { useCallback, useMemo } from "react";
import { api } from "../api/client";
import type { AnnotateResponse, EventBrief, NewEvent, RowItem, RuleSummary } from "../api/types";
import type { CapturedSelection } from "../pagepane";
import { fmt, toast } from "../shell/ui";
import type { RowX } from "./api";
import { fieldBarActions } from "./answerBar";
import { addComplete, correctionEvent, emptyAdd, labelField, objectEvent, takeBackEvent, type ObjectAdd } from "./claims";
import { applyEvent, applyItem, applyMissingItem, applyReview, briefOf, canConfirm, groupOf, itemEvent, missingEvent,
  missingItemEvent, moveIn, newDraft, pinnedComment, rowTarget, shortTitle, subjectOf, verdictEvent, type Draft, type PageGroup } from "./logic";
import type { Pick3 } from "./RowCard";
import { followScore, replaceSummary, rowName, updateRow, versionName } from "./rulesData";
import type { Paned } from "./usePageArea";

export function useRowActions(t: Paned) {
  const { send, post } = usePosting(t);
  const verdicts = useRowVerdicts(t, post);
  const items = useListItemActions(t, post);
  const objects = useObjectActions(t, post);
  const approval = useRuleApproval(t, send);
  return { ...verdicts, ...items, ...objects, ...approval };
}

type Post = (ev: NewEvent) => Promise<EventBrief | null>;
type Send = (ev: NewEvent) => Promise<AnnotateResponse | null>;
type RowAnswer = { verdict: "correct" } | { draft: Draft };

// --- posting -----------------------------------------------------------------------------------------------------
function usePosting({ cat, setBusy, setRules, setDetail }: Paned) {
  const send = useCallback((ev: NewEvent) => sendEvent({ cat, setBusy, setRules, setDetail }, ev), [cat, setBusy, setRules, setDetail]);
  const post = useCallback(async (ev: NewEvent): Promise<EventBrief | null> => {
    const r = await send(ev);
    return r ? briefOf(r.event as Parameters<typeof briefOf>[0]) : null;
  }, [send]);
  return { send, post };
}

async function sendEvent(c: Pick<Paned, "cat" | "setBusy" | "setRules" | "setDetail">, ev: NewEvent): Promise<AnnotateResponse | null> {
  c.setBusy(true);
  try {
    const r = await api.annotate(c.cat, ev);
    if (r.rule) applySummary(c, r.rule);
    return r;
  } catch (e) {
    toast(`Not saved: ${String(e instanceof Error ? e.message : e)}`);
    return null;
  } finally { c.setBusy(false); }
}

/** The rule's new counts and status, in the list and in the header. */
function applySummary(c: Pick<Paned, "setRules" | "setDetail">, s: RuleSummary) {
  c.setRules((rs) => (rs ? replaceSummary(rs, s) : rs));
  c.setDetail((d) => (d && d.rule_id === s.rule_id ? { ...d, ...s } : d));
}

/** Posts one event per thing in turn, stopping at the first that fails; how many were saved. */
async function postEach<T>(things: T[], post: Post, eventOf: (x: T) => NewEvent | null, onSaved: (x: T, brief: EventBrief) => void): Promise<number> {
  let n = 0;
  for (const x of things) {
    const ev = eventOf(x);
    if (!ev) continue;
    const brief = await post(ev);
    if (!brief) break;
    n++;
    onSaved(x, brief);
  }
  return n;
}

// --- a row's verdict ---------------------------------------------------------------------------------------------
function useRowVerdicts(t: Paned, post: Post) {
  const saveRow = useSaveRow(t, post);
  return { saveRow, acceptPage: useAcceptPage(t, post), saveMissed: useSaveMissed(t, post), pick: usePick(t, saveRow),
    startMissed: useStartMissed(t) };
}

function useSaveRow({ rows, detail, me, role, advance, setRows, setDraft, setSaved }: Paned, post: Post) {
  return useCallback((i: number, what: RowAnswer) => saveRowVerdict({ rows, detail, me, role, post, advance, setRows, setDraft, setSaved }, i, what),
    [rows, detail, me, role, post, advance, setRows, setDraft, setSaved]);
}

type SaveRowContext = Pick<Paned, "rows" | "detail" | "me" | "role" | "advance" | "setRows" | "setDraft" | "setSaved"> & { post: Post };

async function saveRowVerdict(c: SaveRowContext, i: number, what: RowAnswer) {
  const r = c.rows[i];
  if (!r || !c.detail) return;
  const confirming = "verdict" in what && canConfirm(r, c.role);
  if ("verdict" in what && r.state === "correct" && !confirming) { toast(`Already correct · ${rowName(r)}`); c.advance(i); return; }
  const target = rowTarget(c.detail.kind, c.detail.rule_id, r);
  const ev = verdictEvent(c.me, target, r.verdict, what, r.value);
  if (!(await postWithPin(c, i, ev, "draft" in what ? pinnedComment(c.me, target, what.draft) : null))) return;
  c.setDraft(null);
  c.setSaved((n) => n + 1);
  toast(`${verdictWord(ev, confirming)} · ${rowName(r)}`);
  if (ev.type === "verdict" && ev.verdict !== "question") c.advance(i);
}

/** The verdict, then the comment pinned to text that goes with a ✗; false when the verdict wasn't saved. */
async function postWithPin(c: SaveRowContext, i: number, ev: NewEvent, pin: NewEvent | null): Promise<boolean> {
  const brief = await c.post(ev);
  if (!brief) return false;
  c.setRows((rs) => updateRow(rs, i, (x) => applyReview(applyEvent(x, brief), brief, c.role)));
  const pinBrief = pin ? await c.post(pin) : null;
  if (pinBrief) c.setRows((rs) => updateRow(rs, i, (x) => applyEvent(x, pinBrief)));
  return true;
}

function verdictWord(ev: NewEvent, confirming: boolean): string {
  return ev.type === "comment" ? "Comment saved" : ev.verdict === "question" ? "Question for the institution saved"
    : confirming ? "Confirmed: human-reviewed" : ev.verdict === "correct" ? "Correct" : "Wrong";
}

/** ✓ on a page row: every course on the page not yet correct is marked correct, then on to the next page. */
function useAcceptPage({ groups, detail, rows, me, role, selectRow, setRows, setSaved }: Paned, post: Post) {
  return useCallback(async (start: number) => {
    const g = groupOf(groups, start);
    if (!g || !detail) return;
    const n = await postEach(range(g.start, g.end), post,
      (i) => (!rows[i] || rows[i].state === "correct" ? null : verdictEvent(me, rowTarget(detail.kind, detail.rule_id, rows[i]), rows[i].verdict, { verdict: "correct" })),
      (i, brief) => setRows((rs) => updateRow(rs, i, (x) => applyReview(applyEvent(x, brief), brief, role))));
    if (n) setSaved((k) => k + 1);
    toast(n ? `${n} ${n === 1 ? "course" : "courses"} correct · ${pageName(rows, g)}` : "Every course on this page is already correct");
    selectRow(moveIn(groups, g.start, "page", "next").sel, "page");
  }, [groups, detail, rows, me, role, post, selectRow, setRows, setSaved]);
}

/** A page of courses as a toast names it: their subject ("INTD"), else the page's title. */
const pageName = (rows: RowX[], g: PageGroup) =>
  subjectOf(rows.slice(g.start, g.end).map((r) => r.record_external_identifier)) || shortTitle(rows[g.start]?.page_title, 40);

const range = (start: number, end: number) => Array.from({ length: Math.max(0, end - start) }, (_, k) => start + k);

function useSaveMissed({ missed, detail, row, active, me, setMissing, setMissed, setExtraTab }: Paned, post: Post) {
  return useCallback(async () => {
    if (!missed || !detail || !row) return;
    const stem = detail.kind === "locator" ? (active ?? row.page_stem) : missed.stem;
    if (!stem || (detail.kind === "locator" && !missed.capture)) return;
    const brief = await post(missingEvent(me, detail.kind, detail.rule_id, stem, missed.capture, missed.note));
    if (!brief) return;
    setMissing((m) => [...m, { ...brief, page_stem: stem }]);
    setMissed(null); setExtraTab(null);
    toast(detail.kind === "locator" ? "Missed course saved" : "Missed page saved");
  }, [missed, detail, row, active, me, post, setMissing, setMissed, setExtraTab]);
}

function usePick({ sel, onPage, rows, selectRow, setMissed, setDraft }: Paned, saveRow: (i: number, what: RowAnswer) => Promise<void>) {
  return useCallback((i: number, v: Pick3) => {
    if (i !== sel || onPage) selectRow(i, "course");
    const r = rows[i];
    if (!r) return;
    if (v === "correct") { void saveRow(i, { verdict: "correct" }); return; }
    setMissed(null);
    setDraft(newDraft(v, r.verdict, r.state));
  }, [sel, onPage, rows, selectRow, saveRow, setMissed, setDraft]);
}

function useStartMissed({ detail, unclassified, cat, ext, setDraft, setMissed, setUnclassified }: Paned) {
  return useCallback(() => {
    setDraft(null);
    setMissed({ capture: null, note: "", stem: null, query: "" });
    if (detail?.kind === "page" && !unclassified) api.unclassifiedPages(cat, ext).then(setUnclassified, () => setUnclassified([]));
  }, [detail, unclassified, cat, ext, setDraft, setMissed, setUnclassified]);
}

// --- a list's items (property-rules spec §4.4) -------------------------------------------------------------------
function useListItemActions(t: Paned, post: Post) {
  const { setDraft, setMissed, setItemAdd } = t;
  const startAddItem = useCallback(() => { setDraft(null); setMissed(null); setItemAdd({ capture: null }); }, [setDraft, setMissed, setItemAdd]);
  return { saveItem: useSaveItem(t, post), startAddItem, saveAddItem: useSaveAddItem(t, post), markAll: useMarkAll(t, post) };
}

/** A list's item: ✓ or ✕ on its line (the row stays where it is); an item already ✓ isn't saved again. */
function useSaveItem({ rows, detail, me, role, setRows, setSaved }: Paned, post: Post) {
  return useCallback(async (i: number, it: RowItem, verdict: "correct" | "wrong") => {
    const r = rows[i];
    if (!r || !detail) return;
    if (verdict === "correct" && it.state === "correct") { toast(`Already correct · ${r.record_external_identifier ?? ""}`); return; }
    const brief = await post(itemEvent(me, detail.rule_id, r, it.value_index, verdict, it.verdict?.annotation_id ?? null));
    if (!brief) return;
    setRows((rs) => updateRow(rs, i, (x) => applyItem(x, it.value_index, brief, role)));
    setSaved((n) => n + 1);
    toast(`${verdict === "correct" ? "Correct" : "Wrong"} · ${rowName(r)}`);
  }, [rows, detail, me, role, post, setRows, setSaved]);
}

function useSaveAddItem({ itemAdd, detail, rows, sel, me, setRows, setItemAdd }: Paned, post: Post) {
  return useCallback(async () => {
    const r = rows[sel];
    if (!itemAdd?.capture || !detail || !r) return;
    const brief = await post(missingItemEvent(me, detail.rule_id, r.occurrence_key, itemAdd.capture));
    if (!brief) return;
    setRows((rs) => updateRow(rs, sel, (x) => applyMissingItem(x, brief)));
    setItemAdd(null);
    toast(`Missing item saved · ${r.record_external_identifier ?? ""}`);
  }, [itemAdd, detail, rows, sel, me, post, setRows, setItemAdd]);
}

/** 1 / 2 on a list's row: every item ✓ or ✕ (no answer), one event each; an item that already says so is skipped. */
function useMarkAll({ rows, sel, detail, me, role, noun, setRows, setSaved }: Paned, post: Post) {
  return useCallback(async (verdict: "correct" | "wrong") => {
    const r = rows[sel];
    if (!r || !detail) return;
    const n = await postEach(r.items ?? [], post,
      (it) => (it.state === verdict ? null : itemEvent(me, detail.rule_id, r, it.value_index, verdict, it.verdict?.annotation_id ?? null)),
      (it, brief) => setRows((rs) => updateRow(rs, sel, (x) => applyItem(x, it.value_index, brief, role))));
    if (n) setSaved((k) => k + 1);
    const word = verdict === "correct" ? "correct" : "wrong";
    toast(n ? `${n} ${n === 1 ? noun : `${noun}s`} ${word} · ${r.record_external_identifier ?? ""}` : `Every ${noun} is already ${word}`);
  }, [rows, sel, detail, me, role, post, noun, setRows, setSaved]);
}

// --- a list of objects (sme-fixes §5.3; phase1-followups §3) ----------------------------------------------------
function useObjectActions(t: Paned, post: Post) {
  const saveObject = useSaveObject(t, post);
  return { startAddObject: useStartAddObject(t), saveObject, labelObject: useLabelObject(t, saveObject),
    fieldBar: useFieldBar(t, saveObject), selectObject: useSelectObject(t), saveFix: useSaveFix(t, post), takeBack: useTakeBack(t, post) };
}

/** Select text, label it as a field; saved once every field is labelled (or by Save). */
function useStartAddObject({ setDraft, setMissed, setItemAdd, setObjFix, setObjAdd }: Paned) {
  return useCallback(() => { setDraft(null); setMissed(null); setItemAdd(null); setObjFix(null); setObjAdd(emptyAdd()); },
    [setDraft, setMissed, setItemAdd, setObjFix, setObjAdd]);
}

function useSaveObject({ detail, rows, sel, profile, me, setRows, setObjAdd }: Paned, post: Post) {
  return useCallback(async (a: ObjectAdd) => {
    const r = rows[sel];
    if (!detail || !r || !profile) return;
    const brief = await post(objectEvent(me, detail.rule_id, r.occurrence_key, a, profile.fields));
    if (!brief) return;
    setRows((rs) => updateRow(rs, sel, (x) => applyMissingItem(x, brief)));
    setObjAdd(null);
    toast(`Added · ${r.record_external_identifier ?? ""}`);
  }, [detail, rows, sel, profile, me, post, setRows, setObjAdd]);
}

function useLabelObject({ objAdd, profile, setObjAdd }: Paned, saveObject: (a: ObjectAdd) => Promise<void>) {
  return useCallback((field: string) => {
    if (!objAdd || !profile) return;
    const next = labelField(objAdd, field);
    setObjAdd(next);
    if (addComplete(next, profile.fields)) void saveObject(next);
  }, [objAdd, profile, saveObject, setObjAdd]);
}

/** A list of objects' highlight bar: the object's field names while one is being added or corrected. */
function useFieldBar(t: Paned, saveObject: (a: ObjectAdd) => Promise<void>) {
  const { listRule, objAdd, objFix, profile, onRowPage, row, noun, setObjFix, setObjAdd, setMissed, setDraft } = t;
  return useMemo(() => {
    if (!listRule || !profile || !onRowPage || !row) return null;
    const onField = (f: string, c: CapturedSelection) => {
      if (objFix) { setObjFix((x) => (x ? { ...x, fields: { ...x.fields, [f]: c } } : x)); return; }
      if (!objAdd) return;
      const next = labelField({ ...objAdd, pending: c }, f);
      setObjAdd(next);
      if (addComplete(next, profile.fields)) void saveObject(next);
    };
    return fieldBarActions({ row, noun, fields: profile.fields, objectUnderWay: !!objAdd || !!objFix, fixing: !!objFix, onField, setMissed, setDraft });
  }, [listRule, objAdd, objFix, profile, onRowPage, row, noun, saveObject]);  // eslint-disable-line react-hooks/exhaustive-deps
}

/** Correcting a found object (phase1-followups §3.2): one ✕ on it, carrying the corrected object. */
function useSelectObject({ setDraft, setMissed, setObjAdd, setObjFix }: Paned) {
  return useCallback((it: RowItem) => {
    setDraft(null); setMissed(null); setObjAdd(null);
    setObjFix((x) => (x?.valueIndex === it.value_index ? null : { valueIndex: it.value_index, fields: {} }));
  }, [setDraft, setMissed, setObjAdd, setObjFix]);
}

function useSaveFix({ objFix, detail, rows, sel, profile, me, role, setRows, setObjFix, setSaved }: Paned, post: Post) {
  return useCallback(async () => {
    const r = rows[sel];
    const it = r?.items?.find((x) => x.value_index === objFix?.valueIndex);
    if (!objFix || !detail || !r || !it || !profile || !Object.keys(objFix.fields).length) return;
    const brief = await post(correctionEvent(me, detail.rule_id, r.occurrence_key, it, objFix, profile.fields));
    if (!brief) return;
    setRows((rs) => updateRow(rs, sel, (x) => applyItem(x, it.value_index, brief, role)));
    setObjFix(null);
    setSaved((n) => n + 1);
    toast(`Corrected · ${r.record_external_identifier ?? ""}`);
  }, [objFix, detail, rows, sel, profile, me, role, post, setRows, setObjFix, setSaved]);
}

/** ✕ on an added object takes it back. */
function useTakeBack({ detail, rows, sel, me, setRows }: Paned, post: Post) {
  return useCallback(async (added: EventBrief) => {
    const r = rows[sel];
    if (!detail || !r) return;
    const brief = await post(takeBackEvent(me, detail.rule_id, r.occurrence_key, added));
    if (!brief) return;
    setRows((rs) => updateRow(rs, sel, (x) => ({ ...x, missing_items: (x.missing_items ?? []).filter((m) => m.annotation_id !== added.annotation_id) })));
    toast(`Removed · ${r.record_external_identifier ?? ""}`);
  }, [detail, rows, sel, me, post, setRows]);
}

// --- approving and resetting the rule ----------------------------------------------------------------------------
function useRuleApproval(t: Paned, send: Send) {
  return { approve: useApprove(t, send), openReset: useOpenReset(t), reset: useReset(t, send) };
}

/** Approving a column's rule publishes it and scores it (Evals spec §6.6): ask first, then follow the score. */
function useApprove({ cat, detail, me, setAsking }: Paned, send: Send) {
  return useCallback(async (type: "approve" | "reopen", confirmed = false) => {
    if (!detail) return;
    if (type === "approve" && !confirmed && detail.kind === "property") {
      const p = await api.approvePreview(cat, detail.rule_id).catch(() => null);
      if (p?.publishes) { setAsking(p); return; }
    }
    const r = await send({ type, author: me, target: { kind: "rule", rule_id: detail.rule_id },
                           note: type === "approve" ? "Approved in the Studio" : "Reopened in the Studio" });
    setAsking(null);
    if (r) announceApproval(cat, detail.title, type, r);
  }, [cat, detail, me, send, setAsking]);
}

function announceApproval(cat: string, title: string, type: "approve" | "reopen", r: AnnotateResponse): void {
  const pub = r.published;
  if (type === "reopen") toast(`Reopened: ${title}`);
  else if (pub?.error) toast(`Approved: ${title}, but not published: ${pub.error}`);
  else if (pub?.written) {
    toast(`Approved and published ${pub.column} to the silver dataset ${versionName(pub.publication)}${r.score ? " · scoring xtra's latest extract output…" : ""}`, 3000);
    if (r.score) followScore(cat, r.score.id, versionName(pub.publication));
  } else if (pub && !pub.written) toast(`Approved: ${title}. It has no CTDL term, so it isn't written to the silver dataset files.`, 4000);
  else toast(`Approved: ${title}`);
}

/** Reset rule (phase1-followups §4): what it clears and keeps first, then one `reset` event with the reason; the server
 * republishes without the column and rescores. The rows are fetched again: every reviewed row changed. */
function useOpenReset({ cat, detail, setResetting }: Paned) {
  return useCallback(async () => {
    if (!detail) return;
    const p = await api.resetPreview(cat, detail.rule_id).catch((e) => { toast(`Couldn't read what a reset clears: ${String(e)}`); return null; });
    if (p) setResetting(p);
  }, [cat, detail, setResetting]);
}

function useReset({ detail, resetting, me, setResetting, setReloads }: Paned, send: Send) {
  return useCallback(async (why: string) => {
    if (!detail || !resetting) return;
    const r = await send({ type: "reset", author: me, target: { kind: "rule", rule_id: detail.rule_id }, note: why });
    if (!r) return;
    const n = resetting.counts.correct + resetting.counts.answered;
    setResetting(null);
    setReloads((k) => k + 1);
    toast(r.published?.error ? `Reset ${detail.title}, but the datasets weren't rewritten: ${r.published.error}`
      : `Reset ${detail.title}: ${fmt(n)} ${n === 1 ? "value" : "values"} back to not reviewed`, 3000);
  }, [detail, resetting, me, send, setResetting, setReloads]);
}
