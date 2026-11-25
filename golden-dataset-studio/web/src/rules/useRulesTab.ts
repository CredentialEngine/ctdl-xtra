// The Rules tab's state: the rule list and its filters, one rule's rows and the selected row, the page pane beside
// them, and what saving does. Each step adds to what the steps before it found; the tab renders the result.
import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { api, ApiError } from "../api/client";
import type { CatalogDetail, Discussion, EventBrief, RuleDetail, RulesResponse, SampleInfo, Topic, UnclassifiedPage,
  ApprovePreview, ResetPreview } from "../api/types";
import { useAiStat } from "../agent/AiStat";
import { prefetchPages } from "../pagepane";
import { useReviewer, useRole } from "../shell/reviewer";
import { sampleQuery, type SamplePrefs } from "../shell/Sample";
import { go, href, replaceParam, type ClassSlug, type Route } from "../shell/router";
import { classOfRule, inClass } from "../shell/klass";
import { toast, useKeyHints } from "../shell/ui";
import { apiX, type Annotators, type RowsX, type RowX } from "./api";
import { profileOf } from "./claims";
import { BY_ANYONE, moveIn, newDraft, pageGroups, pushRecent, scrollWithin, type Draft, type Level,
  type TabRef } from "./logic";
import type { ItemAdd } from "./ListItems";
import type { MissedState } from "./MissedPanel";
import type { Missing } from "./NotHere";
import type { ObjectAdd, ObjectFix } from "./claims";
import type { PostTalk } from "./RuleList";
import { usePageArea } from "./usePageArea";
import { useRowActions } from "./useRowActions";
import { useRuleKeys } from "./ruleKeys";
import { ANNOTATORS_SETTLE_MS, classHead, DEFAULT_PREFS, defaultRule, FIRST_PAGE, KEY_HINTS, mergeClasses, MORE,
  PAGE_KEY_HINTS, PREFETCH, replaceSummary } from "./rulesData";

export function useRulesTab(catalog: CatalogDetail, route: Route) {
  const base = useBase(catalog, route);
  const listed = { ...base, ...useRuleListData(base) };
  const loaded = { ...listed, ...useRuleRows(listed) };
  const paned = { ...loaded, ...usePageArea(loaded) };
  const tab = { ...paned, ...useRowActions(paned) };
  useRuleKeys(tab);
  return tab;
}

export type Base = ReturnType<typeof useBase>;
export type Listed = Base & ReturnType<typeof useRuleListData>;
export type Loaded = Listed & ReturnType<typeof useRuleRows>;
export type RulesTabState = ReturnType<typeof useRulesTab>;

function useBase(catalog: CatalogDetail, route: Route) {
  const who = { me: useReviewer(), role: useRole(), aiStat: useAiStat() };
  const refs = useTabRefs();
  const data = useRuleData();
  const selection = useSelection();
  const work = useWork();
  const status = useStatus();
  const params = useRouteParams(catalog, route, data.rules);
  return { catalog, route, ...who, ...refs, ...data, ...selection, ...work, ...status, ...params };
}

function useTabRefs() {
  const token = useRef(0);
  const loadingMore = useRef(false);
  const rowsRef = useRef<HTMLDivElement>(null);
  const paneRef = useRef<HTMLElement>(null);
  const centerNext = useRef(true);
  useTourAnchors(paneRef);
  return { token, loadingMore, rowsRef, paneRef, centerNext };
}

/** Tour anchors inside the page pane (its markup belongs to the page pane module). */
function useTourAnchors(ref: RefObject<HTMLElement>) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const mark = () => {
      el.querySelector(".gpp-seg")?.setAttribute("data-tour", "page-html-switch");
      el.querySelector(".gpp-ext")?.setAttribute("data-tour", "open-live");
    };
    mark();
    const mo = new MutationObserver(mark);
    mo.observe(el, { childList: true, subtree: true });
    return () => mo.disconnect();
  }, [ref]);
}

function useRuleData() {
  const [rules, setRules] = useState<RulesResponse | null>(null);
  const [detail, setDetail] = useState<RuleDetail | null>(null);
  const [rows, setRows] = useState<RowX[]>([]);
  const [total, setTotal] = useState(0);
  const [sample, setSample] = useState<SampleInfo | null>(null);
  const [missing, setMissing] = useState<EventBrief[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notHere, setNotHere] = useState<Missing | null>(null);  // a linked row (?row=) this ruleset doesn't show
  return { rules, setRules, detail, setDetail, rows, setRows, total, setTotal, sample, setSample, missing, setMissing,
    error, setError, notHere, setNotHere };
}

function useSelection() {
  const [sel, setSel] = useState(0);
  const [level, setLevel] = useState<Level>("page");  // a repeating locator's rows: on a page row, or on one of its courses
  const [recent, setRecent] = useState<TabRef[]>([]);
  const [activeStem, setActiveStem] = useState<string | null>(null);
  const [extraTab, setExtraTab] = useState<TabRef | null>(null);
  return { sel, setSel, level, setLevel, recent, setRecent, activeStem, setActiveStem, extraTab, setExtraTab };
}

function useWork() {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [missed, setMissed] = useState<MissedState | null>(null);
  const [itemAdd, setItemAdd] = useState<ItemAdd | null>(null);  // a missing item of a list property being selected
  const [objAdd, setObjAdd] = useState<ObjectAdd | null>(null);  // an object of a list-of-objects rule being labelled (§5.3)
  const [objFix, setObjFix] = useState<ObjectFix | null>(null);  // a found object being corrected (phase1-followups §3)
  return { draft, setDraft, missed, setMissed, itemAdd, setItemAdd, objAdd, setObjAdd, objFix, setObjFix };
}

function useStatus() {
  const [unclassified, setUnclassified] = useState<UnclassifiedPage[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState<ApprovePreview | null>(null);  // approve and publish? (a column's rule)
  const [resetting, setResetting] = useState<ResetPreview | null>(null);  // Reset rule? (phase1-followups §4.1)
  const [reloads, setReloads] = useState(0);  // the rows again after a change to many of them (Reset rule)
  return { unclassified, setUnclassified, busy, setBusy, asking, setAsking, resetting, setResetting, reloads, setReloads };
}

/** What the address says: the rule, the linked row, the extraction and the "Annotated by" filter. */
function useRouteParams(catalog: CatalogDetail, route: Route, rules: RulesResponse | null) {
  const cat = catalog.short;
  // the list in hand belongs to this catalog and class (a switch clears it; until the new one lands, no default rule:
  // the last class's first rule would be asked of this class and fail)
  const listKey = `${cat}|${route.cls}|${route.params.get("ext") ?? ""}`;
  const [rulesFor, setRulesFor] = useState<string | null>(null);
  const marked = useRef<string | null>(null);
  const byParam = route.params.get("by");
  return {
    cat, listKey, setRulesFor, marked, byParam, ruleId: route.id ?? (rulesFor === listKey ? defaultRule(rules) : null),
    focus: route.params.get("row"), ...filterParams(route, byParam),
  };
}

function filterParams(route: Route, byParam: string | null) {
  return {
    linkedNote: route.params.get("note"),  // a report's link to one annotation of the linked row (report-links §4)
    // an AI run's report sends ✕ here in a new browser tab (one-rule-runs §1.6): the linked row opens with ✕ pressed
    markWrong: route.params.get("mark") === "wrong",
    // the extraction being reviewed: ?ext=… picks an older ruleset's, none = the latest (catalog.extraction)
    ext: route.params.get("ext"),
    // "Annotated by": the URL's choice, else Anyone (sme-fixes §9); `?by=` is written only when a person is picked
    // (older links wrote "anyone")
    by: byParam === BY_ANYONE ? null : byParam,
    verdict: route.params.get("v"),
  };
}

// --- the rule list -----------------------------------------------------------------------------------------------
function useRuleListData(t: Base) {
  const people = usePeople(t);
  const sampling = useSampling(t);
  const classes = useRulesLoad(t);
  const talk = useTalk(t, classes);
  const { cat, ruleId, ext, by, verdict, notHere, error, rules, detail } = t;
  const setFilter = (o: { by?: string | null; v?: string | null }) => go(href(cat, "rules", ruleId, { ext, by, v: verdict, ...o }));
  // the rule in the address hasn't loaded yet (a class switch, another rule): placeholders, not the last rule's rows
  const loadingRule = !notHere && !error && (!rules || (!!ruleId && detail?.rule_id !== ruleId));
  return { ...people, ...sampling, ...classes, ...talk, setFilter, loadingRule };
}

/** "Annotated by": its people and counts, fetched again once the verdicts stop. */
function usePeople({ cat, by, verdict, ext }: Base) {
  const [people, setPeople] = useState<Annotators | null>(null);
  const [saved, setSaved] = useState(0);  // verdicts saved here: the rule list's counts and the experts' note follow
  // After a verdict the counts follow once the clicks stop (ANNOTATORS_SETTLE_MS), not once per click: each refetch
  // makes the server recount the catalog, and quick ✓s used to pile up those requests behind the next verdict.
  // A newer fetch cancels the older one, whose result never lands.
  const peopleFor = useRef<string | null>(null);
  useEffect(() => {
    const filter = JSON.stringify([cat, by, verdict, ext]);
    const settle = peopleFor.current === filter;  // only `saved` changed
    peopleFor.current = filter;
    return fetchAnnotators(cat, { by, verdict, ext }, settle ? ANNOTATORS_SETTLE_MS : 0, setPeople);
  }, [cat, by, verdict, ext, saved]);
  return { people, saved, setSaved };
}

function fetchAnnotators(cat: string, filter: { by: string | null; verdict: string | null; ext: string | null }, delay: number,
  setPeople: (p: Annotators | null) => void): () => void {
  const ac = new AbortController();
  const t = setTimeout(() => {
    apiX.annotators(cat, filter, ac.signal).then(
      (p) => { if (!ac.signal.aborted) setPeople(p); },
      () => { if (!ac.signal.aborted) setPeople(null); });
  }, delay);
  return () => { clearTimeout(t); ac.abort(); };
}

/** The Sample drawer's choices belong to one rule: another rule starts on Autostratify, unfiltered. */
function useSampling({ ruleId }: Base) {
  const [prefsOf, setPrefsOf] = useState<{ rule: string | null; p: SamplePrefs }>({ rule: null, p: DEFAULT_PREFS });
  const prefs = prefsOf.rule === ruleId ? prefsOf.p : DEFAULT_PREFS;
  const setPrefs = useCallback((p: SamplePrefs) => setPrefsOf({ rule: ruleId, p }), [ruleId]);
  const qKey = JSON.stringify(sampleQuery(prefs, "review"));
  const sq = useMemo(() => JSON.parse(qKey) as ReturnType<typeof sampleQuery>, [qKey]);
  return { prefs, setPrefs, sq, filtered: sq.f.length > 0 };
}

/** The rules of this class, or with All classes every class that has rules here, each in its own section of the
 * list (approved item 14). */
function useRulesLoad({ catalog, route, cat, ext, listKey, rules, setRules, setRulesFor, setError }: Base) {
  const all = route.cls === "all";
  const ruled = useMemo(() => (catalog.classes ?? []).filter((c) => c.ruleset_version), [catalog.classes]);
  const ruledKey = ruled.map((c) => c.slug).join(",");
  // a class or catalog switch clears the list at once (a loading preview shows), so the old class's rules never
  // linger looking current; a late answer for the previous class is dropped
  const rulesTok = useRef(0);
  useEffect(() => {
    const tok = ++rulesTok.current;
    const keep = (r: RulesResponse) => { if (tok === rulesTok.current) { setRules(r); setRulesFor(listKey); } };
    setRules(null); setError(null);
    fetchRules(cat, ext, all ? ruled : null, route.id).then(keep, (e) => setError(String(e)));
  }, [cat, ext, all, ruledKey, listKey]);  // eslint-disable-line react-hooks/exhaustive-deps
  const heads = useMemo(() => (all ? Object.fromEntries(ruled.map((c) => [c.slug, classHead(c, rules)])) : null),
                        [all, ruled, rules]);
  return { all, ruled, ruledKey, heads };
}

function fetchRules(cat: string, ext: string | null, ruled: CatalogDetail["classes"] | null, openRule: string | null): Promise<RulesResponse> {
  if (!ruled) return api.rules(cat, ext);
  const mine = classOfRule(openRule) ?? "course";
  return Promise.all(ruled.map((c) => inClass(c.slug, () => api.rules(cat, c.slug === mine ? ext : null)).then((r) => ({ c, r }))))
    .then((each) => mergeClasses(each.map(({ c, r }) => ({ cls: c.slug, rules: r })), mine, openRule));
}

/** Comments on whole rules and on the ruleset (the sidebar); with All classes, every class's. */
function useTalk({ cat, me, setRules }: Base, { all, ruled, ruledKey }: ReturnType<typeof useRulesLoad>) {
  const [talk, setTalk] = useState<Discussion | null>(null);
  const loadTalk = useCallback(() => fetchTalk(cat, all ? ruled : null).then(setTalk),
    [cat, all, ruledKey]);  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { void loadTalk(); }, [loadTalk]);
  const postTalk = useCallback<PostTalk>((target, note, topic) => saveTalk({ cat, me, setRules, loadTalk }, target, note, topic),
    [cat, me, setRules, loadTalk]);
  return { talk, postTalk };
}

function fetchTalk(cat: string, ruled: CatalogDetail["classes"] | null): Promise<Discussion> {
  const one = (slug?: string) => (slug ? inClass(slug as ClassSlug, () => api.discussion(cat)) : api.discussion(cat));
  const asks = ruled ? ruled.map((c) => one(c.slug)) : [one()];
  return Promise.all(asks).then((ds) => ({ ruleset: ds.flatMap((d) => d?.ruleset ?? []),
                                           rules: Object.assign({}, ...ds.map((d) => d?.rules ?? {})) }),
                                () => ({ ruleset: [], rules: {} }));
}

async function saveTalk(c: { cat: string; me: string; setRules: Base["setRules"]; loadTalk: () => Promise<void> },
  target: Parameters<PostTalk>[0], note: string, topic: Topic): Promise<boolean> {
  try {
    const r = await api.annotate(c.cat, { type: "comment", author: c.me, target, note, topic });
    if (r.rule) c.setRules((rs) => (rs ? replaceSummary(rs, r.rule!) : rs));
    await c.loadTalk();
    toast(target.kind === "ruleset" ? "Comment on the ruleset saved" : "Comment on the rule saved");
    return true;
  } catch (e) {
    toast(`Couldn't save: ${String(e)}`);
    return false;
  }
}

// --- one rule's rows ---------------------------------------------------------------------------------------------
function useRuleRows(t: Listed) {
  useRowsLoad(t);
  const shape = useRuleShape(t);
  const navigation = useRowNavigation({ ...t, ...shape });
  return { ...shape, ...navigation };
}

function useRowsLoad(t: Listed) {
  const { cat, ruleId, focus, sq, ext, by, verdict, markWrong, reloads, token } = t;
  useEffect(() => {
    if (!ruleId) return;
    const tok = ++token.current;
    clearWork(t);
    Promise.all([api.rule(cat, ruleId, ext), apiX.rows(cat, ruleId, { limit: FIRST_PAGE, focus, ext, by, verdict, ...sq })]).then(
      ([d, r]) => { if (tok === token.current) showRows(t, d, r); },
      (e) => { if (tok === token.current) showRowsError(t, e); });
  }, [cat, ruleId, focus, sq, ext, by, verdict, markWrong, reloads]);  // eslint-disable-line react-hooks/exhaustive-deps
}

/** Drop what was under way on the row: a draft, an add, a correction, an extra page tab. */
export function clearWork(t: Pick<Base, "setDraft" | "setMissed" | "setItemAdd" | "setObjAdd" | "setObjFix" | "setExtraTab" | "setActiveStem">) {
  t.setDraft(null); t.setMissed(null); t.setItemAdd(null); t.setObjAdd(null); t.setObjFix(null); t.setExtraTab(null); t.setActiveStem(null);
}

function showRows(t: Listed, d: RuleDetail, r: RowsX) {
  const lost = !!t.focus && r.focus_index == null;  // the linked row isn't here: say so, show its page, select nothing
  t.setDetail(d); t.setRows(r.rows); t.setTotal(r.total); t.setSample(r.sample ?? null); t.setMissing(r.missing); t.setSel(lost ? -1 : r.focus_index ?? 0);
  // a link to one course of a page (?row=<occurrence key>) opens on that course; otherwise on its page row
  t.setLevel(t.focus && r.focus_index != null && r.rows[r.focus_index]?.key === t.focus ? "course" : "page");
  t.setNotHere(lost ? (t.by || t.verdict || t.sq.f.length ? "hidden" : "row") : null);
  pressWrongOnce(t, d, r);
  t.centerNext.current = true; t.setError(null);
  if (t.rowsRef.current) t.rowsRef.current.scrollTop = 0;
}

/** An AI run's report links here with ✕ pressed on the linked row. */
function pressWrongOnce(t: Listed, d: RuleDetail, r: RowsX) {
  const linked = t.focus && r.focus_index != null ? r.rows[r.focus_index] : null;
  if (!t.markWrong || !linked || d.list || t.marked.current === t.focus) return;
  t.marked.current = t.focus;
  t.setDraft(newDraft("wrong", linked.verdict, linked.state));
  replaceParam("mark", null);  // done once: a reload or a later row doesn't press ✕ again
}

function showRowsError(t: Listed, e: unknown) {
  if (t.focus && e instanceof ApiError && e.status === 404) {  // a rule this ruleset doesn't have (v3 dropped it)
    t.setDetail(null); t.setRows([]); t.setTotal(0); t.setSample(null); t.setMissing([]); t.setNotHere("rule"); t.setError(null);
  } else t.setError(String(e));
}

/** What kind of rule this is and the row selected in it. */
function useRuleShape({ detail, ruleId, rows, sel, level }: Listed) {
  const kind = detail?.kind ?? null;
  const row = detail && detail.rule_id === ruleId ? rows[sel] ?? null : null;
  const listRule = !!detail?.list;  // a list property: its rows have items, each with its own verdict (§4.4)
  const noun = (detail?.property_label ?? "item").replace(/^Estimated /, "").toLowerCase();  // "duration"
  const profile = useMemo(() => profileOf(detail?.definition), [detail]);  // a list of objects (sme-fixes §5)
  // a record locator that finds several courses per page: one row per page, its courses inside (sme-fixes §3)
  const perPage = kind === "locator" && !!detail?.definition.repeat;
  const groups = useMemo(() => (perPage ? pageGroups(rows) : []), [perPage, rows]);
  useKeyHints(perPage ? PAGE_KEY_HINTS : KEY_HINTS, [perPage]);
  return { kind, row, listRule, noun, profile, perPage, groups, onPage: perPage && level === "page" };
}

type Shaped = Listed & ReturnType<typeof useRuleShape>;

function useRowNavigation(t: Shaped) {
  const loadMore = useLoadMore(t);
  const [moves, setMoves] = useState(0);  // the reader's own moves between rows (click, Tab, arrows): they close the Sample drawer
  const selectRow = useSelectRow(t, loadMore, setMoves);
  const { perPage, groups } = t;
  /** After a verdict: the next row; inside a page, its next course, then the next page row. */
  const advance = useCallback((i: number) => {
    if (!perPage) { selectRow(i + 1); return; }
    const m = moveIn(groups, i, "course", "next");
    selectRow(m.sel, m.level);
  }, [perPage, groups, selectRow]);
  useKeepSelectedInView(t);
  return { loadMore, moves, selectRow, advance };
}

function useLoadMore({ cat, ruleId, rows, total, sq, ext, by, verdict, token, loadingMore, setRows }: Shaped) {
  return useCallback(() => {
    if (!ruleId || loadingMore.current || rows.length >= total) return;
    loadingMore.current = true;
    const tok = token.current;
    apiX.rows(cat, ruleId, { offset: rows.length, limit: MORE, ext, by, verdict, ...sq }).then((r) => {
      if (tok === token.current) setRows((prev) => (prev.length === r.offset ? [...prev, ...r.rows] : prev));
    }).finally(() => { loadingMore.current = false; });
  }, [cat, ruleId, rows.length, total, sq, ext, by, verdict]);  // eslint-disable-line react-hooks/exhaustive-deps
}

/** Selecting a row writes it to the address bar (?row=, replacing the entry: sme-fixes §2), so the URL links to it. */
function useSelectRow(t: Shaped, loadMore: () => void, setMoves: (f: (m: number) => number) => void) {
  const { rows, sel, level, perPage } = t;
  return useCallback((i: number, lvl: Level = level) => {
    const j = Math.max(0, Math.min(i, rows.length - 1));
    if (j === sel && lvl === level) return;
    setMoves((m) => m + 1);
    t.setLevel(lvl);
    rememberPage(t.setRecent, rows[sel], rows[j]);
    t.setSel(j); clearWork(t);
    if (rows[j]) replaceParam("row", perPage && lvl === "page" ? rows[j].page_stem : rows[j].key);
    if (j >= rows.length - 5) loadMore();
  }, [rows, sel, level, perPage, loadMore]);  // eslint-disable-line react-hooks/exhaustive-deps
}

/** Leaving a page for another: the page left joins the recent tabs. */
function rememberPage(setRecent: Base["setRecent"], prev: RowX | undefined, next: RowX | undefined) {
  if (prev && prev.page_stem !== next?.page_stem) setRecent((r) => pushRecent(r, { stem: prev.page_stem, url: prev.url, title: prev.page_title ?? prev.page_stem }));
}

/** Keep the selected row visible; prefetch the next rows' pages (spec §10). */
function useKeepSelectedInView({ sel, rows, cat, catalog, onPage, rowsRef, centerNext }: Shaped) {
  useEffect(() => {
    const box = rowsRef.current;
    const el = box?.querySelector<HTMLElement>(onPage ? `[data-page-start="${sel}"]` : `[data-row-index="${sel}"]`);
    if (box && el) scrollWithin(box, el, centerNext.current);
    centerNext.current = false;
    prefetchPages(cat, nextPageStems(rows, sel), catalog.ruleset_version);
  }, [sel, rows, cat, catalog.ruleset_version, onPage]);  // eslint-disable-line react-hooks/exhaustive-deps
}

const nextPageStems = (rows: RowX[], sel: number) =>
  [...new Set(rows.slice(sel + 1, sel + 1 + PREFETCH * 30).map((r) => r.page_stem))].slice(0, PREFETCH);
