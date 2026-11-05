// The Rules tab (spec §7.2, screens 03–06, 12): rules by kind on the left, one rule's rows in the middle
// (sorted by the server with the likeliest problems first), the saved page on the right. "Annotated by" and its verdict
// switch (?by=…&v=…, Evals spec §6.7) filter the rows of every rule, and the rule list counts the rows that pass.
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "../api/client";
import type { AnnotateResponse, ApprovePreview, CatalogDetail, Discussion, EventBrief, NewEvent, Overlay, RowItem, RuleDetail, RulesResponse,
  RuleSummary, SampleInfo, UnclassifiedPage } from "../api/types";
import { PagePane, prefetchPages, type BarAction, type CapturedSelection, type Highlight } from "../pagepane";
import { Ico } from "../shell/icons";
import { useReviewer, useRole } from "../shell/reviewer";
import { SampleDrawer, samplePrefs, sampleQuery, StrataTags, type SamplePrefs } from "../shell/Sample";
import { go, href, replaceParam } from "../shell/router";
import type { TabProps } from "../shell/tabProps";
import { fmt, toast, useKeyHints } from "../shell/ui";
import { AnnotatedBy, ReviewLine, VerdictSwitch, WaitingNote } from "./AnnotatedBy";
import { apiX, type Annotators, type RowX } from "./api";
import {
  addCapture, applyEvent, applyItem, applyMissingItem, applyReview, BY_ANYONE, BY_WAITING, briefOf, canConfirm, filterCountTip,
  groupOf, isField, isSettled, itemEvent, keyAction, markPiece, missingEvent, pinnedComment, missingItemEvent, moveIn, newDraft, pageGroups, pushRecent, paneTabs,
  rowTarget, scrollWithin, shortTitle, subjectOf, verdictEvent, type Draft, type Level, type Piece, type TabRef,
} from "./logic";
import { MissedCourse, MissedPage, type MissedState } from "./MissedPanel";
import { focusStem, NotHere, useFocusPage, type Missing } from "./NotHere";
import { Controls, Expansion, HistoryLine, Value } from "./parts";
import { ListItems, type ItemAdd } from "./ListItems";
import { ProfileItems } from "./ProfileItems";
import { addComplete, emptyAdd, fieldWord, labelField, objectEvent, profileOf, statusHint, statusWords, type ObjectAdd } from "./claims";
import { ApproveDialog } from "./ApproveDialog";
import { RuleHead } from "./RuleHead";
import { RuleList, type PostTalk } from "./RuleList";
import { FixBar } from "../agent/FixBar";
import "./rules.css";

const FIRST_PAGE = 100;
const MORE = 200;
const PREFETCH = 4;

export function defaultRule(rules: RulesResponse | null): string | null {
  if (!rules) return null;
  const all = rules.groups.flatMap((g) => g.rules);
  return (all.find((r) => r.rule_id === "course-description") ?? all.find((r) => r.kind === "property") ?? all[0])?.rule_id ?? null;
}

export function replaceSummary(rules: RulesResponse, s: RuleSummary): RulesResponse {
  return { ...rules, groups: rules.groups.map((g) => {
    if (!g.rules.some((r) => r.rule_id === s.rule_id)) return g;
    const items = g.rules.map((r) => (r.rule_id === s.rule_id ? { ...r, ...s } : r));
    return { ...g, rules: items, approved: items.filter((r) => r.status === "approved").length };
  }) };
}

export const KEY_HINTS = (
  <span className="key-hints">
    <kbd>Tab</kbd>next <kbd>1</kbd>correct <kbd>2</kbd>wrong <kbd>3</kbd>comment <kbd>H</kbd>select text{" "}
    <kbd>Enter</kbd>save <kbd>Esc</kbd>cancel
  </span>
);
/** A repeating record locator's rows: one per page, its courses inside (sme-fixes §3). */
export const PAGE_KEY_HINTS = (
  <span className="key-hints" data-testid="page-key-hints">
    <kbd>Tab</kbd>next course, then page <kbd>Enter</kbd>into a page <kbd>Esc</kbd>up to the page <kbd>1</kbd>correct
    (a page: all) <kbd>2</kbd>wrong <kbd>3</kbd>comment
  </span>
);

/** Tour anchors inside the page pane (its markup belongs to the page pane module). */
function useTourAnchors(ref: React.RefObject<HTMLElement>) {
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

const DEFAULT_PREFS = samplePrefs("auto");  // Autostratify (sme-fixes §9); the drawer stays shut until opened

const golden = (id?: string) => (id ?? "").replace(/^ruleset-v/, "ruleset v");

/** After an approval's publish: wait for its score, then say how it went. */
function followScore(cat: string, id: string, version: string, tries = 0): void {
  setTimeout(async () => {
    const d = await api.scoreDoc(cat, id).catch(() => null);
    if (!d) return;
    if (d.status === "running") { if (tries < 200) followScore(cat, id, version, tries + 1); return; }
    if (d.status !== "done") { toast(`xtra score of ${version} ${d.status}${d.error ? `: ${d.error}` : ""}`); return; }
    const basis = d.results.human ? "human" : "rule";
    const res = d.results[basis];
    if (res?.exact_match_rate == null) return;
    toast(`xtra score of ${version}: ${Math.round(100 * res.exact_match_rate)}% exact, ${basis === "human" ? "human-reviewed" : "rule-matched"}`
      + ` (${fmt(res.outcomes.match)} of ${fmt(res.values)})`, 5000);
  }, 3000);
}

export default function RulesTab({ catalog, route }: TabProps) {
  const cat = catalog.short;
  const me = useReviewer();
  const role = useRole();
  const [rules, setRules] = useState<RulesResponse | null>(null);
  const [detail, setDetail] = useState<RuleDetail | null>(null);
  const [rows, setRows] = useState<RowX[]>([]);
  const [total, setTotal] = useState(0);
  const [sample, setSample] = useState<SampleInfo | null>(null);
  // the Sample drawer's choices belong to one rule: another rule starts on Autostratify, unfiltered
  const [prefsOf, setPrefsOf] = useState<{ rule: string | null; p: SamplePrefs }>({ rule: null, p: DEFAULT_PREFS });
  const [missing, setMissing] = useState<EventBrief[]>([]);
  const [sel, setSel] = useState(0);
  const [level, setLevel] = useState<Level>("page");  // a repeating locator's rows: on a page row, or on one of its courses
  const [draft, setDraft] = useState<Draft | null>(null);
  const [missed, setMissed] = useState<MissedState | null>(null);
  const [itemAdd, setItemAdd] = useState<ItemAdd | null>(null);  // a missing item of a list property being selected
  const [objAdd, setObjAdd] = useState<ObjectAdd | null>(null);  // an object of a list-of-objects rule being labelled (§5.3)
  const [recent, setRecent] = useState<TabRef[]>([]);
  const [activeStem, setActiveStem] = useState<string | null>(null);
  const [extraTab, setExtraTab] = useState<TabRef | null>(null);
  const [overlay, setOverlay] = useState<{ key: string; data: Overlay } | null>(null);
  const [unclassified, setUnclassified] = useState<UnclassifiedPage[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notHere, setNotHere] = useState<Missing | null>(null);  // a linked row (?row=) this ruleset doesn't show
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState<ApprovePreview | null>(null);  // approve and publish? (a column's rule)
  const token = useRef(0);
  const loadingMore = useRef(false);
  const overlays = useRef(new Map<string, Overlay>());
  const rowsRef = useRef<HTMLDivElement>(null);
  const paneRef = useRef<HTMLElement>(null);
  const centerNext = useRef(true);
  useTourAnchors(paneRef);

  const ruleId = route.id ?? defaultRule(rules);
  const focus = route.params.get("row");
  const linkedNote = route.params.get("note");  // a report's link to one annotation of the linked row (report-links §4)
  // the extraction being reviewed: ?ext=… picks an older ruleset's, none = the latest (catalog.extraction)
  const ext = route.params.get("ext");
  const [people, setPeople] = useState<Annotators | null>(null);
  // "Annotated by": the URL's choice, else Anyone (sme-fixes §9); `?by=` is written only when a person is picked
  // (older links wrote "anyone")
  const byParam = route.params.get("by");
  const by = byParam === BY_ANYONE ? null : byParam;
  const verdict = route.params.get("v");
  const setFilter = (o: { by?: string | null; v?: string | null }) => go(href(cat, "rules", ruleId, { ext, by, v: verdict, ...o }));
  const [saved, setSaved] = useState(0);  // verdicts saved here: the rule list's counts and the experts' note follow
  useEffect(() => {
    apiX.annotators(cat, { by, verdict, ext }).then(setPeople, () => setPeople(null));
  }, [cat, by, verdict, ext, saved]);
  const prefs = prefsOf.rule === ruleId ? prefsOf.p : DEFAULT_PREFS;
  const setPrefs = useCallback((p: SamplePrefs) => setPrefsOf({ rule: ruleId, p }), [ruleId]);
  const qKey = JSON.stringify(sampleQuery(prefs, "review"));
  const sq = useMemo(() => JSON.parse(qKey) as ReturnType<typeof sampleQuery>, [qKey]);
  const filtered = sq.f.length > 0;

  useEffect(() => { api.rules(cat, ext).then(setRules, (e) => setError(String(e))); }, [cat, ext]);
  // comments on whole rules and on the ruleset (the sidebar)
  const [talk, setTalk] = useState<Discussion | null>(null);
  const loadTalk = useCallback(() => api.discussion(cat).then((d) => setTalk({ ruleset: d?.ruleset ?? [], rules: d?.rules ?? {} }),
                                                               () => setTalk({ ruleset: [], rules: {} })), [cat]);
  useEffect(() => { void loadTalk(); }, [loadTalk]);
  const postTalk = useCallback<PostTalk>(async (target, note, topic) => {
    try {
      const r = await api.annotate(cat, { type: "comment", author: me, target, note, topic });
      if (r.rule) setRules((rs) => (rs ? replaceSummary(rs, r.rule!) : rs));
      await loadTalk();
      toast(target.kind === "ruleset" ? "Comment on the ruleset saved" : "Comment on the rule saved");
      return true;
    } catch (e) {
      toast(`Couldn't save: ${String(e)}`);
      return false;
    }
  }, [cat, me, loadTalk]);

  useEffect(() => {
    if (!ruleId) return;
    const tok = ++token.current;
    setDraft(null); setMissed(null); setItemAdd(null); setObjAdd(null); setExtraTab(null); setActiveStem(null);
    Promise.all([api.rule(cat, ruleId, ext), apiX.rows(cat, ruleId, { limit: FIRST_PAGE, focus, ext, by, verdict, ...sq })]).then(([d, r]) => {
      if (tok !== token.current) return;
      const lost = !!focus && r.focus_index == null;  // the linked row isn't here: say so, show its page, select nothing
      setDetail(d); setRows(r.rows); setTotal(r.total); setSample(r.sample ?? null); setMissing(r.missing); setSel(lost ? -1 : r.focus_index ?? 0);
      // a link to one course of a page (?row=<occurrence key>) opens on that course; otherwise on its page row
      setLevel(focus && r.focus_index != null && r.rows[r.focus_index]?.key === focus ? "course" : "page");
      setNotHere(lost ? (by || verdict || sq.f.length ? "hidden" : "row") : null);
      centerNext.current = true; setError(null);
      if (rowsRef.current) rowsRef.current.scrollTop = 0;
    }, (e) => {
      if (tok !== token.current) return;
      if (focus && e instanceof ApiError && e.status === 404) {  // a rule this ruleset doesn't have (v3 dropped it)
        setDetail(null); setRows([]); setTotal(0); setSample(null); setMissing([]); setNotHere("rule"); setError(null);
      } else setError(String(e));
    });
  }, [cat, ruleId, focus, sq, ext, by, verdict]);

  const kind = detail?.kind ?? null;
  const row = detail && detail.rule_id === ruleId ? rows[sel] ?? null : null;
  const listRule = !!detail?.list;  // a list property: its rows have items, each with its own verdict (§4.4)
  const profile = useMemo(() => profileOf(detail?.definition), [detail]);  // a list of objects (sme-fixes §5)
  // a record locator that finds several courses per page: one row per page, its courses inside (sme-fixes §3)
  const perPage = kind === "locator" && !!detail?.definition.repeat;
  const groups = useMemo(() => (perPage ? pageGroups(rows) : []), [perPage, rows]);
  const onPage = perPage && level === "page";  // on a page row (not one of its courses)
  useKeyHints(perPage ? PAGE_KEY_HINTS : KEY_HINTS, [perPage]);

  const loadMore = useCallback(() => {
    if (!ruleId || loadingMore.current || rows.length >= total) return;
    loadingMore.current = true;
    const tok = token.current;
    apiX.rows(cat, ruleId, { offset: rows.length, limit: MORE, ext, by, verdict, ...sq }).then((r) => {
      if (tok === token.current) setRows((prev) => (prev.length === r.offset ? [...prev, ...r.rows] : prev));
    }).finally(() => { loadingMore.current = false; });
  }, [cat, ruleId, rows.length, total, sq, ext, by, verdict]);

  // the reader's own moves between rows (click, Tab, arrows): they close the Sample drawer
  const [moves, setMoves] = useState(0);
  // Selecting a row writes it to the address bar (?row=, replacing the entry: sme-fixes §2), so the URL links to it.
  const selectRow = useCallback((i: number, lvl: Level = level) => {
    const j = Math.max(0, Math.min(i, rows.length - 1));
    if (j === sel && lvl === level) return;
    setMoves((m) => m + 1);
    setLevel(lvl);
    const prev = rows[sel];
    if (prev && prev.page_stem !== rows[j]?.page_stem) setRecent((r) => pushRecent(r, { stem: prev.page_stem, url: prev.url, title: prev.page_title ?? prev.page_stem }));
    setSel(j); setDraft(null); setMissed(null); setItemAdd(null); setObjAdd(null); setExtraTab(null); setActiveStem(null);
    if (rows[j]) replaceParam("row", perPage && lvl === "page" ? rows[j].page_stem : rows[j].key);
    if (j >= rows.length - 5) loadMore();
  }, [rows, sel, level, perPage, loadMore]);
  /** After a verdict: the next row; inside a page, its next course, then the next page row. */
  const advance = useCallback((i: number) => {
    if (!perPage) { selectRow(i + 1); return; }
    const m = moveIn(groups, i, "course", "next");
    selectRow(m.sel, m.level);
  }, [perPage, groups, selectRow]);

  // keep the selected row visible; prefetch the next rows' pages (spec §10)
  useEffect(() => {
    const box = rowsRef.current;
    const el = box?.querySelector<HTMLElement>(onPage ? `[data-page-start="${sel}"]` : `[data-row-index="${sel}"]`);
    if (box && el) scrollWithin(box, el, centerNext.current);
    centerNext.current = false;
    prefetchPages(cat, [...new Set(rows.slice(sel + 1, sel + 1 + PREFETCH * 30).map((r) => r.page_stem))].slice(0, PREFETCH),
                  catalog.ruleset_version);
  }, [sel, rows, cat, catalog.ruleset_version, onPage]);

  // --- page pane --------------------------------------------------------------------------------------------
  const focusTab = useFocusPage(cat, notHere ? focusStem(focus) : null);
  const curTab: TabRef | null = row ? { stem: row.page_stem, url: row.url, title: row.page_title ?? row.page_stem } : focusTab;
  const tabs = useMemo(() => paneTabs(curTab,
    [...(extraTab ? [extraTab] : []), ...(row?.other_pages ?? []).map((p) => ({ stem: p.page_stem, url: p.url, title: p.title ?? p.page_stem }))],
    recent).map((t, i) => ({ ...t, title: shortTitle(t.title), badge: i + 1 })),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  [row?.key, extraTab, recent, focusTab]);
  const active = activeStem ?? row?.page_stem ?? curTab?.stem ?? null;

  useEffect(() => {
    if (!detail || detail.kind === "property" || !active) return;
    const key = `${detail.rule_id}|${active}|${ext ?? ""}`;
    const hit = overlays.current.get(key);
    if (hit) { setOverlay({ key, data: hit }); return; }
    api.overlay(cat, active, detail.rule_id, ext).then((data) => { overlays.current.set(key, data); setOverlay({ key, data }); }, () => {});
  }, [cat, detail, active, ext]);
  const ov = detail && active && overlay?.key === `${detail.rule_id}|${active}|${ext ?? ""}` ? overlay.data : null;

  const captures: Piece[] = draft?.captures.length ? draft.captures : missed?.capture ? [missed.capture] : itemAdd?.capture ? [itemAdd.capture] : [];
  // A property rule's row: selecting text on its page shows the highlight bar (sme-fixes §1): comment on it, ✓ it is
  // in the right answer, ✕ it is not (both open the ✗ draft with it). Once the ✗ draft is open, a selection is a piece
  // of the answer at once, as before the bar (Jared, 2026-11-05: answers dragged after ✗ were lost when the bar was
  // dismissed), and the bar only offers ✕ Not in answer. Only on the row's own page: the expected text is located there.
  const onRowPage = !!row && active === row.page_stem;
  // a list's row answers only while a missing item is being selected (its items have their own ✓ and ✕)
  const selectAnswer = listRule ? onRowPage && (!!itemAdd || !!objAdd)
    : kind === "property" ? onRowPage && !missed && draft?.mode !== "comment" : draft?.mode === "wrong";
  const onAnswer = useCallback((c: Piece) => {
    if (listRule && objAdd) { setObjAdd((a) => (a ? { ...a, pending: c } : a)); return; }  // then: which field is it?
    if (listRule && itemAdd) { setItemAdd({ capture: c }); return; }
    setMissed(null);
    // several drags add pieces of one answer; one over an existing piece replaces it
    // a comment already pinned with the bubble stays with the ✗: the comment goes with either answer
    setDraft((d) => (d && d.mode === "wrong" ? { ...d, captures: addCapture(d.captures, c) }
      : row ? { ...newDraft("wrong", row.verdict, row.state), captures: [c],
                ...(d?.mode === "comment" ? { anchor: d.anchor, note: d.note } : {}) } : d));
  }, [kind, draft, row, listRule, itemAdd, objAdd]);
  const captureFirst = kind === "property" && !listRule && draft?.mode === "wrong";
  const barActions = useMemo<BarAction[] | null>(() => {
    if (kind !== "property" || listRule || !onRowPage || missed || itemAdd || !row) return null;
    // after ✗ the drag is already a piece of the answer (captureFirst): ✓ keeps it in, ✕ marks it out
    const mark = (polarity: "in" | "out") => (c: CapturedSelection) => (captureFirst
      ? setDraft((d) => (d ? { ...d, captures: markPiece(d.captures, c, polarity) } : d))
      : onAnswer({ ...c, polarity }));
    return [
      { id: "comment", label: <Ico name="bubble" />, tone: "note", keepOpen: true,
        title: "Comment on this text: the comment is pinned to it on the page (a numbered bubble). Then ✓ or ✕ to say whether it is in the answer, or just save the comment.",
        run: (c: CapturedSelection) => { setMissed(null); setDraft((d) => ({ ...(d?.mode === "comment" || d?.mode === "wrong" ? d : newDraft("comment", row.verdict, row.state)), anchor: c })); } },
      { id: "in", label: "✓ In answer", tone: "in", title: "Mark this text as part of the right answer (outlined green). Several pieces can be combined; Enter saves the row as ✗ with this answer.",
        run: mark("in") },
      { id: "out", label: "✕ Not in answer", tone: "out", title: "Mark this text as not part of the right answer (red dashed). The row becomes ✗.",
        run: mark("out") },
    ];
  }, [kind, listRule, onRowPage, missed, itemAdd, row, onAnswer, captureFirst]);
  const removePiece = useCallback((id: string) => {
    const i = Number(id.replace(/^capture-/, ""));
    setDraft((d) => (d ? { ...d, captures: d.captures.filter((_, j) => j !== i) } : d));
  }, []);
  const { highlights, focusId } = useMemo(() => {
    const hs: Highlight[] = [];
    let fid: string | null = null;
    if (row && detail) {
      if (detail.kind === "property") {
        if (active === row.page_stem && row.css_path && row.status !== "absent") {
          hs.push({ id: "value", kind: "value", cssPath: row.css_path, charStart: row.char_start, charEnd: row.char_end, text: row.value, badge: 1 });
          fid = "value";
        }
        // a list's items, each where it is on the page; the items the rule missed, where they were selected
        if (listRule && active === row.page_stem) {
          for (const it of row.items ?? []) {
            if (it.fields) {  // an object: each field where it is (sme-fixes §5)
              for (const [f, x] of Object.entries(it.fields)) if (x.css_path) hs.push({ id: `item-${it.value_index}-${f}`, kind: "value",
                cssPath: x.css_path, charStart: x.char_start, charEnd: x.char_end, text: x.text });
            } else if (it.css_path) hs.push({ id: `item-${it.value_index}`, kind: "value", cssPath: it.css_path,
              charStart: it.char_start, charEnd: it.char_end, text: it.value });
          }
          for (const [f, c] of Object.entries(objAdd?.fields ?? {})) hs.push({ id: `obj-${f}`, kind: "expected", cssPath: c.css_path,
            charStart: c.char_start, charEnd: c.char_end, text: c.text });
          if (objAdd?.pending) hs.push({ id: "obj-pending", kind: "expected", cssPath: objAdd.pending.css_path,
            charStart: objAdd.pending.char_start, charEnd: objAdd.pending.char_end, text: objAdd.pending.text });
          (row.missing_items ?? []).forEach((m, i) => { const e = m.expected;
            if (e?.css_path) hs.push({ id: `missing-item-${i}`, kind: "expected", cssPath: e.css_path, charStart: e.char_start, charEnd: e.char_end, text: e.text }); });
        }
        if (row.status === "absent" && row.css_path && active === row.page_stem) {  // where the rule looked (§6)
          hs.push({ id: "looked", kind: "looked", cssPath: row.css_path });
          fid = "looked";
        }
        const exp = row.verdict?.expected;
        if (exp?.css_path && active === row.page_stem && (row.state === "wrong" || row.state === "still-wrong") && !draft) {
          // the saved answer: pieces in it outlined green, pieces marked not in it red dashed
          (exp.segments ?? [exp]).forEach((s, i) => hs.push({ id: `expected-${i}`, kind: "polarity" in s && s.polarity === "out" ? "excluded" : "expected",
            cssPath: s.css_path!, charStart: s.char_start, charEnd: s.char_end, text: s.text, badge: i === 0 ? 2 : undefined }));
        }
        // comments pinned to text: a numbered bubble at the text, in the order the row lists them
        if (active === row.page_stem) {
          const pinned = [...row.comments.map((c) => c.anchor), ...(draft?.anchor ? [draft.anchor] : [])];
          pinned.filter((a): a is NonNullable<typeof a> => !!a?.css_path).forEach((a, i) => hs.push({ id: `note-${i}`, kind: "note",
            cssPath: a.css_path, charStart: a.char_start, charEnd: a.char_end, text: a.text, badge: i + 1 }));
        }
      } else if (ov) {
        // course boxes: a border each, green / red once ✓ / ✗; only the current course is filled (none on a page row)
        const stateOf = new Map(rows.filter((r) => r.page_stem === active).map((r) => [r.occurrence_key, r.state]));
        for (const b of ov.blocks) {
          const s = stateOf.get(b.occurrence_key);
          hs.push({ id: b.occurrence_key, kind: "block", cssPath: b.css_path, badge: b.n,
                    state: s === "correct" ? "ok" : s === "wrong" || s === "still-wrong" ? "bad" : null });
        }
        if (detail.kind === "locator") ov.marks.forEach((m, i) => hs.push({ id: `mark${i}`, kind: "mark", cssPath: m.css_path, charStart: m.char_start, charEnd: m.char_end }));
        fid = onPage ? null : detail.kind === "locator" && active === row.page_stem ? row.occurrence_key : ov.blocks[0]?.occurrence_key ?? null;
      }
      if (detail.kind === "locator") {
        for (const m of missing) {
          const e = m.expected;
          if (e?.css_path && m.page_stem === active) hs.push({ id: `missing-${m.annotation_id}`, kind: "expected", cssPath: e.css_path, text: e.text });
        }
      }
      captures.forEach((c, i) => hs.push({ id: `capture-${i}`, kind: c.polarity === "out" ? "excluded" : "expected", cssPath: c.css_path,
        charStart: c.char_start, charEnd: c.char_end, text: c.text, removable: !!draft }));
      if (captures.length) fid = "capture-0";
    }
    return { highlights: hs, focusId: fid };
  }, [row, rows, detail, active, ov, captures, draft, missing, listRule, objAdd, onPage]);

  // --- saving ---------------------------------------------------------------------------------------------------
  const send = useCallback(async (ev: NewEvent): Promise<AnnotateResponse | null> => {
    setBusy(true);
    try {
      const r = await api.annotate(cat, ev);
      if (r.rule) {
        setRules((rs) => (rs ? replaceSummary(rs, r.rule!) : rs));
        setDetail((d) => (d && d.rule_id === r.rule!.rule_id ? { ...d, ...r.rule! } : d));
      }
      return r;
    } catch (e) {
      toast(`Not saved: ${String(e instanceof Error ? e.message : e)}`);
      return null;
    } finally { setBusy(false); }
  }, [cat]);
  const post = useCallback(async (ev: NewEvent): Promise<EventBrief | null> => {
    const r = await send(ev);
    return r ? briefOf(r.event as Parameters<typeof briefOf>[0]) : null;
  }, [send]);

  const saveRow = useCallback(async (i: number, what: { verdict: "correct" } | { draft: Draft }) => {
    const r = rows[i];
    if (!r || !detail) return;
    const confirming = "verdict" in what && canConfirm(r, role);
    if ("verdict" in what && r.state === "correct" && !confirming) { toast(`Already correct · ${r.course_key ?? shortTitle(r.page_title, 40)}`); advance(i); return; }
    const target = rowTarget(detail.kind, detail.rule_id, r);
    const ev = verdictEvent(me, target, r.verdict, what, r.value);
    const brief = await post(ev);
    if (!brief) return;
    setRows((rs) => rs.map((x, j) => (j === i ? applyReview(applyEvent(x, brief), brief, role) : x)));
    const pin = "draft" in what ? pinnedComment(me, target, what.draft) : null;  // a ✗ with a comment pinned to text
    const pinBrief = pin ? await post(pin) : null;
    if (pinBrief) setRows((rs) => rs.map((x, j) => (j === i ? applyEvent(x, pinBrief) : x)));
    setDraft(null);
    setSaved((n) => n + 1);
    const label = ev.type === "comment" ? "Comment saved" : ev.verdict === "question" ? "Question for the institution saved"
      : confirming ? "Confirmed: human-reviewed" : ev.verdict === "correct" ? "Correct" : "Wrong";
    toast(`${label} · ${r.course_key ?? shortTitle(r.page_title, 40)}`);
    if (ev.type === "verdict" && ev.verdict !== "question") advance(i);
  }, [rows, detail, me, role, post, advance]);

  /** ✓ on a page row: every course on the page not yet correct is marked correct, then on to the next page. */
  const acceptPage = useCallback(async (start: number) => {
    const g = groupOf(groups, start);
    if (!g || !detail) return;
    let n = 0;
    for (let i = g.start; i < g.end; i++) {
      const r = rows[i];
      if (!r || r.state === "correct") continue;
      const brief = await post(verdictEvent(me, rowTarget(detail.kind, detail.rule_id, r), r.verdict, { verdict: "correct" }));
      if (!brief) break;
      n++;
      setRows((rs) => rs.map((x, j) => (j === i ? applyReview(applyEvent(x, brief), brief, role) : x)));
    }
    if (n) setSaved((k) => k + 1);
    const first = rows[g.start];
    toast(n ? `${n} ${n === 1 ? "course" : "courses"} correct · ${subjectOf(rows.slice(g.start, g.end).map((r) => r.course_key)) || shortTitle(first?.page_title, 40)}`
      : "Every course on this page is already correct");
    const m = moveIn(groups, g.start, "page", "next");
    selectRow(m.sel, "page");
  }, [groups, detail, rows, me, role, post, selectRow]);

  const saveMissed = useCallback(async () => {
    if (!missed || !detail || !row) return;
    const stem = detail.kind === "locator" ? (active ?? row.page_stem) : missed.stem;
    if (!stem || (detail.kind === "locator" && !missed.capture)) return;
    const brief = await post(missingEvent(me, detail.kind, detail.rule_id, stem, missed.capture, missed.note));
    if (!brief) return;
    setMissing((m) => [...m, { ...brief, page_stem: stem }]);
    setMissed(null); setExtraTab(null);
    toast(detail.kind === "locator" ? "Missed course saved" : "Missed page saved");
  }, [missed, detail, row, active, me, post]);

  const pick = useCallback((i: number, v: "correct" | "wrong" | "comment") => {
    if (i !== sel || onPage) selectRow(i, "course");
    const r = rows[i];
    if (!r) return;
    if (v === "correct") { void saveRow(i, { verdict: "correct" }); return; }
    setMissed(null);
    setDraft(newDraft(v, r.verdict, r.state));
  }, [sel, onPage, rows, selectRow, saveRow]);

  // a list's item: ✓ or ✕ on its line (the row stays where it is); an item already ✓ isn't saved again
  const saveItem = useCallback(async (i: number, it: RowItem, verdict: "correct" | "wrong") => {
    const r = rows[i];
    if (!r || !detail) return;
    if (verdict === "correct" && it.state === "correct") { toast(`Already correct · ${r.course_key ?? ""}`); return; }
    const brief = await post(itemEvent(me, detail.rule_id, r, it.value_index, verdict, it.verdict?.annotation_id ?? null));
    if (!brief) return;
    setRows((rs) => rs.map((x, j) => (j === i ? applyItem(x, it.value_index, brief, role) : x)));
    setSaved((n) => n + 1);
    toast(`${verdict === "correct" ? "Correct" : "Wrong"} · ${r.course_key ?? shortTitle(r.page_title, 40)}`);
  }, [rows, detail, me, role, post]);

  const startAddItem = useCallback(() => { setDraft(null); setMissed(null); setItemAdd({ capture: null }); }, []);
  const saveAddItem = useCallback(async () => {
    const r = rows[sel];
    if (!itemAdd?.capture || !detail || !r) return;
    const brief = await post(missingItemEvent(me, detail.rule_id, r.occurrence_key, itemAdd.capture));
    if (!brief) return;
    setRows((rs) => rs.map((x, j) => (j === sel ? applyMissingItem(x, brief) : x)));
    setItemAdd(null);
    toast(`Missing item saved · ${r.course_key ?? ""}`);
  }, [itemAdd, detail, rows, sel, me, post]);

  // a list of objects (§5.3): select text, label it as a field; saved once every field is labelled (or by Save)
  const startAddObject = useCallback(() => { setDraft(null); setMissed(null); setItemAdd(null); setObjAdd(emptyAdd()); }, []);
  const saveObject = useCallback(async (a: ObjectAdd) => {
    const r = rows[sel];
    if (!detail || !r || !profile) return;
    const brief = await post(objectEvent(me, detail.rule_id, r.occurrence_key, a, profile.fields));
    if (!brief) return;
    setRows((rs) => rs.map((x, j) => (j === sel ? applyMissingItem(x, brief) : x)));
    setObjAdd(null);
    toast(`Added · ${r.course_key ?? ""}`);
  }, [detail, rows, sel, profile, me, post]);
  const labelObject = useCallback((field: string) => {
    if (!objAdd || !profile) return;
    const next = labelField(objAdd, field);
    setObjAdd(next);
    if (addComplete(next, profile.fields)) void saveObject(next);
  }, [objAdd, profile, saveObject]);
  // labelling an added object (§5.3): the highlight bar offers the object's field names instead of In / Not in
  const fieldBar = useMemo<BarAction[] | null>(() => {
    if (!listRule || !objAdd || !profile || !onRowPage) return null;
    return profile.fields.map((f) => ({
      id: `field-${f}`, label: fieldWord(f), tone: "in" as const,
      title: `Label this text as the ${fieldWord(f)} of the ${(detail?.property_label ?? "item").toLowerCase()} you're adding`,
      run: (c: CapturedSelection) => {
        const next = labelField({ ...objAdd, pending: c }, f);
        setObjAdd(next);
        if (addComplete(next, profile.fields)) void saveObject(next);
      },
    }));
  }, [listRule, objAdd, profile, onRowPage, detail, saveObject]);

  const startMissed = useCallback(() => {
    setDraft(null);
    setMissed({ capture: null, note: "", stem: null, query: "" });
    if (detail?.kind === "page" && !unclassified) api.unclassifiedPages(cat, ext).then(setUnclassified, () => setUnclassified([]));
  }, [detail, unclassified, cat, ext]);

  // Approving a column's rule publishes it and scores it (Evals spec §6.6): ask first, then follow the score.
  const approve = useCallback(async (type: "approve" | "reopen", confirmed = false) => {
    if (!detail) return;
    if (type === "approve" && !confirmed && detail.kind === "property") {
      const p = await api.approvePreview(cat, detail.rule_id).catch(() => null);
      if (p?.publishes) { setAsking(p); return; }
    }
    const r = await send({ type, author: me, target: { kind: "rule", rule_id: detail.rule_id },
                           note: type === "approve" ? "Approved in the Studio" : "Reopened in the Studio" });
    setAsking(null);
    if (!r) return;
    const pub = r.published;
    if (type === "reopen") toast(`Reopened: ${detail.title}`);
    else if (pub?.error) toast(`Approved: ${detail.title}, but not published: ${pub.error}`);
    else if (pub?.written) {
      toast(`Approved and published ${pub.column} to the silver dataset ${golden(pub.publication)}${r.score ? " · scoring xtra's latest extract output…" : ""}`, 3000);
      if (r.score) followScore(cat, r.score.id, golden(pub.publication));
    } else if (pub && !pub.written) toast(`Approved: ${detail.title}. It has no CTDL term, so it isn't written to the silver dataset files.`, 4000);
    else toast(`Approved: ${detail.title}`);
  }, [cat, detail, me, send]);

  // --- keyboard (spec §7.2) ----------------------------------------------------------------------------------
  const keys = useRef<(e: KeyboardEvent) => void>(() => {});
  keys.current = (e: KeyboardEvent) => {
    const a = keyAction(e, isField(e.target));
    if (!a || !row) return;
    if (a === "save") {
      if (missed) { e.preventDefault(); void saveMissed(); }
      else if (itemAdd?.capture) { e.preventDefault(); void saveAddItem(); }
      else if (objAdd && profile && objAdd.fields[profile.key]) { e.preventDefault(); void saveObject(objAdd); }
      else if (draft) { e.preventDefault(); void saveRow(sel, { draft }); }
      else if (onPage && !isField(e.target)) { e.preventDefault(); selectRow(sel, "course"); }  // into the page's courses
      return;
    }
    if (a === "cancel") {
      if (isField(e.target)) (e.target as HTMLElement).blur();
      // Esc on a course of a page, with nothing to cancel: back up to the page row (sme-fixes §3)
      if (perPage && level === "course" && !draft && !missed && !itemAdd) { const m = moveIn(groups, sel, level, "up"); selectRow(m.sel, m.level); }
      setDraft(null); setMissed(null); setExtraTab(null); setItemAdd(null); setObjAdd(null);
      return;
    }
    e.preventDefault();
    if (perPage && (a === "next" || a === "prev")) { const m = moveIn(groups, sel, level, a); selectRow(m.sel, m.level); }
    else if (onPage) { if (a === "correct") void acceptPage(sel); else if (a === "wrong" || a === "comment") pick(sel, a); }
    else if (a === "next") selectRow(sel + 1);
    else if (a === "prev") selectRow(sel - 1);
    else if (listRule) { if (a === "select") (profile ? startAddObject : startAddItem)(); else if (a === "comment") pick(sel, "comment"); }  // H: a missing item
    else if (a === "correct") pick(sel, "correct");
    else if (a === "wrong" || a === "select") pick(sel, "wrong");
    else if (a === "comment") pick(sel, "comment");
  };
  useEffect(() => {
    const on = (e: KeyboardEvent) => keys.current(e);
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, []);

  // --- render ----------------------------------------------------------------------------------------------------
  if (error && !rules) return <div className="placeholder muted" style={{ padding: 24 }}>{error}</div>;

  const legendLine = (
    <span className="legend grow" data-tour="locator-legend">
      <span className="sw-found">1</span>outlined = found by this rule <span className="sep">·</span>{" "}
      <span className="sw-unc">ABC 101</span>marked = looks like a course but wasn't found
    </span>
  );
  const addBtn = (label: string) => (
    <button className="missed-btn" data-tour="add-missed" onClick={startMissed}><Ico name="missing" />{label}</button>
  );
  let legend: ReactNode = null;
  let banner: ReactNode = null;
  if (detail && row) {
    const what = kind === "property" ? <><b>{detail.property_label ?? detail.title}</b> · {row.course_key ?? ""}</>
      : kind === "locator" ? <><b>Course</b> · {row.course_key ?? ""}</> : <b>{detail.title}</b>;
    if (objAdd && listRule) {
      legend = <><Ico name="highlight" /><span><b>{objAdd.pending ? "Which field is it?" : "Select a piece of the missing one"}</b> on the page for {what}
        {objAdd.pending ? ": pick its field under the row." : ", then label it."}</span></>;
    } else if (itemAdd && listRule) {
      legend = itemAdd.capture
        ? <><Ico name="highlight" /><span><b>Your missing item is outlined.</b> Save it under the row, or Esc to cancel.</span></>
        : <><Ico name="highlight" /><span><b>Select the missing item</b> on the page for {what}: drag across it.</span></>;
    } else if (draft?.mode === "wrong" && kind === "property" && !onRowPage) {
      legend = <><Ico name="highlight" /><span className="ctx-text"><b>Select the right text</b> for {what} on tab 1, the page this value is from.</span></>;
    } else if (draft?.mode === "wrong") {
      const n = draft.captures.length;
      legend = <><Ico name="highlight" /><span className="ctx-text"><b>{n ? `Your answer is outlined${n > 1 ? ` (${n} pieces)` : ""}` : "Select the right text"}</b> on the page for {what}:
        {n ? " drag across more text to add a piece, × to remove one, Enter to save." : " drag across it (more drags add more pieces). Zoom in (+) to select precisely."}</span></>;
    } else if (missed && kind === "locator") {
      legend = <>{legendLine}<span className="adding">Adding a missed course…</span></>;
    } else if (missed && kind === "page") {
      legend = <><Ico name="highlight" /><span><b>Add a missed page</b> · find the page below; it opens here so you can check it.</span></>;
    } else if (kind === "locator") {
      legend = <>{legendLine}{addBtn("Add a course this rule missed")}</>;
    } else if (kind === "page") {
      banner = <><span className="gds-num">1</span><span className="grow">{what} — the courses found on this page are outlined.</span>
        {addBtn("Add a page this rule missed")}</>;
    } else if (active === row.page_stem) {
      const found = listRule ? (row.items?.length ? "each item found is highlighted." : "this rule found nothing on this page.")
        : row.status === "found" && row.css_path ? "the value found is highlighted." : statusHint(row.status);
      const hint = listRule ? "Wrong item? Use its ✕. Missing one? Add it below."
        : row.status === "none" ? "Select the value the page shows to mark it."
        : row.css_path ? "Wrong? Drag across the right text to mark it." : "If the page shows it, drag across it to mark it.";
      banner = <><span className="gds-num">1</span><span className="grow">{what} — {found}
        {" "}<span className="answer-hint" data-testid="answer-hint">{hint}</span></span></>;
    } else {
      banner = <span className="grow">{what} — another page this course is on. The value is highlighted on tab 1.</span>;
    }
  }

  return (
    <div className="rules-layout w4-rules">
      <aside className="col">{rules && <RuleList rules={rules} active={ruleId} onPick={(id) => go(href(cat, "rules", id, { ext, by: byParam, v: verdict }))}
        talk={talk} onTalk={postTalk} counts={people?.rules} countTip={(n) => filterCountTip(n, by, verdict)}
        top={<RulesetPicker catalog={catalog} ext={ext} onPick={(x) => go(href(cat, "rules", ruleId, { ext: x, by: byParam, v: verdict }))} />}
        bottom={<>
          {role === "sme" && <WaitingNote n={people?.waiting ?? 0} on={by === BY_WAITING}
            onToggle={() => setFilter({ by: by === BY_WAITING ? null : BY_WAITING, v: null })} />}
          {!ext && <FixBar catalog={cat} name={catalog.name} rules={rules} />}</>} />}</aside>
      <section className="col mid">
        {detail && <RuleHead catalog={catalog} rule={detail} busy={busy} onApprove={() => approve("approve")} onReopen={() => approve("reopen")} />}
        {asking && <ApproveDialog p={asking} busy={busy} onApprove={() => approve("approve", true)} onClose={() => setAsking(null)} />}
        {detail && <SampleDrawer sample={sample} prefs={prefs} onPrefs={setPrefs} modes={["review", "auto", "shuffle", "manual"]}
          storageKey="studio.rules.sample" collapseOn={moves} filters={<>
            <span className="sm-k">Annotated by</span>
            <div className="sm-ctl">
              <AnnotatedBy people={people} by={by} me={me} bare onPick={(x) => setFilter({ by: x })} />
              <VerdictSwitch verdict={verdict} onPick={(x) => setFilter({ v: x })} />
            </div>
          </>} />}
        {notHere && focus && ruleId && <NotHere catalog={catalog} ruleId={ruleId} focus={focus} ext={ext} why={notHere}
          ruleName={detail?.property_label ?? detail?.title ?? ruleId} version={rules?.ruleset_version ?? catalog.ruleset_version}
          onAnyone={by || verdict ? () => setFilter({ by: null, v: null }) : undefined} />}
        <div className="rows" data-tour="rows" ref={rowsRef} onScroll={(e) => {
          const el = e.currentTarget;
          if (el.scrollTop + el.clientHeight > el.scrollHeight - 600) loadMore();
        }}>
          {missing.length > 0 && kind !== "property" && (
            <div className="missing-list">
              <div className="ml-h"><Ico name="missing" />{missing.length} marked missing: {kind === "locator" ? "courses" : "pages"} this rule didn't find</div>
              {missing.map((m) => (
                <div key={m.annotation_id} className="ml-item">
                  <span className="ml-t">{m.expected?.text ? shortTitle(m.expected.text, 90) : shortTitle(m.page_stem ?? "", 80)}</span>
                  <span className="faint">{m.author}{m.note ? `: “${m.note}”` : ""}</span>
                </div>
              ))}
            </div>
          )}
          {detail && (() => {
          const rowEl = (r: RowX, i: number) => {
            const on = i === sel && !onPage;
            // "Open in Records →" on the selected row (the same for every kind of row)
            const links = (x: RowX, selected: boolean) => selected && x.course_key && (
              <div className="row-links">
                <a className="xbtn" title="Open this course in the Records tab, with this property selected"
                  href={href(cat, "records", x.course_key, { prop: kind === "property" ? detail.property_label : null, occ: x.occurrence_key })}
                  onClick={(e) => e.stopPropagation()}>Open in Records →</a>
              </div>);
            const val = statusWords(r.status, r.value);
            const settled = isSettled(r.state);
            const cls = `row${on ? " on" : ""}${r.verdict && r.state !== "fixed" ? ` v-${r.verdict.verdict}` : ""}${settled && !(on && draft) ? " done" : ""}${kind === "page" ? " page-row" : ""}${perPage ? " in-page" : ""}`;
            return (
              <div key={r.key} className={cls} data-row-index={i} tabIndex={-1} onClick={() => selectRow(i, "course")}>
                {kind !== "page" && <div className="code">{r.course_key ?? "—"}</div>}
                <div className="body">
                  {kind === "page"
                    ? <><div className="val">{r.page_title ?? r.page_stem}</div><div className="pg">{r.url.replace(/^https?:\/\//, "")}</div></>
                    : listRule && r.items && profile ? <><ProfileItems row={r} on={on} fields={profile.fields} keyField={profile.key}
                        noun={(detail.property_label ?? "item").replace(/^Estimated /, "").toLowerCase()} add={on ? objAdd : null}
                        onVerdict={(it, v) => void saveItem(i, it, v)} onStartAdd={startAddObject} onLabel={labelObject}
                        onSaveAdd={() => objAdd && void saveObject(objAdd)} onCancelAdd={() => setObjAdd(null)} />
                        <div className="pg">{r.context}</div>{links(r, on)}</>
                    : listRule && r.items ? <><ListItems row={r} on={on} add={on ? itemAdd : null} onVerdict={(it, v) => void saveItem(i, it, v)}
                        onStartAdd={startAddItem} onSaveAdd={() => void saveAddItem()} onCancelAdd={() => setItemAdd(null)} />
                        <div className="pg">{r.context}</div>{links(r, on)}</>
                    : <><div className={`valbox${on ? " on" : ""}${r.status === "found" ? "" : " empty"}${r.status === "absent" ? " claim" : ""}`}>
                        {on && <span className="valbox-k">{kind === "property" ? detail.property_label : "Found"}</span>}
                        {on
                          // the selected row: the whole value, its paragraphs kept (as the Records tab shows a property)
                          ? <div className={`val full${r.status === "found" ? "" : " empty"}`} data-testid="row-full-value">{val}</div>
                          : <div className={`val${r.status === "found" ? "" : " empty"}`}><Value text={val} /></div>}
                        </div>
                        <div className="pg">{r.context}</div>
                        {links(r, on)}</>}
                  <ReviewLine r={r} />
                  <StrataTags tags={r.tags} />
                  <HistoryLine state={r.state} verdict={r.verdict} reattached={r.reattached} comments={r.comments} page_questions={r.page_questions}
                    linked={on ? linkedNote : null} />
                  {on && draft && <Expansion draft={draft} propertyRule={kind === "property"} emptyValue={r.status !== "found"}
                    onChange={setDraft} onSave={() => void saveRow(i, { draft })} onCancel={() => setDraft(null)} />}
                </div>
                <Controls state={r.state} verdict={r.verdict} comments={r.comments} draft={on ? draft : null}
                  onPick={(v) => pick(i, v)} tour={on} confirm={canConfirm(r, role)} marked={r.human_reviewed || r.engineer_checked}
                  commentOnly={listRule} />
              </div>
            );
          };
          if (!perPage) return rows.map(rowEl);
          // one row per page; the current page's courses inside it, each with its own ✓ ✕ (sme-fixes §3)
          const cur = groupOf(groups, sel);
          return groups.map((g) => {
            const rs = rows.slice(g.start, g.end);
            const open = g === cur;
            const n = rs[0]?.page_courses ?? rs.length;
            const all = rs.length === n && rs.every((r) => r.state === "correct");
            const subject = subjectOf(rs.map((r) => r.course_key));
            return (
              <div key={`${g.stem}@${g.start}`} className={`page-group${open ? " open" : ""}`}>
                <div className={`row page-head${open && onPage ? " on" : ""}${all ? " done" : ""}`} data-page-start={g.start}
                  data-testid="page-head" tabIndex={-1} onClick={() => selectRow(g.start, "page")}>
                  <div className="ph-t">
                    {subject && <b>{subject}</b>}{subject && " · "}{shortTitle(rs[0]?.page_title ?? g.stem, 70)}
                    <span className="faint"> · {fmt(n)} {n === 1 ? "course" : "courses"}</span>
                    {!open && <Ico name="chevron-right" className="ph-car" />}
                  </div>
                  <button className={`cb ok${all ? " on" : ""}`} aria-label="Accept every course on this page"
                    title={`Correct: accept all ${fmt(rs.length)} ${rs.length === 1 ? "course" : "courses"} of this page at once (1 on the page row)`}
                    onClick={(e) => { e.stopPropagation(); void acceptPage(g.start); }}><Ico name="correct" /></button>
                </div>
                {open && <>{rs.map((r, k) => rowEl(r, g.start + k))}
                  <button className="row add-course" onClick={(e) => { e.stopPropagation(); startMissed(); }}
                    title="A course on this page that no box outlines: click its block on the page to add it">+ Add a course this rule missed</button></>}
              </div>
            );
          });
          })()}
          {detail && rows.length < total && <div className="row more-rows" onClick={loadMore}>+ {fmt(total - rows.length)} more · scroll to load</div>}
          {detail && total === 0 && <div className="empty-state muted">{by || verdict
            ? "No row of this rule passes the Annotated by filter. Pick another rule, or Anyone above."
            : filtered ? "No row is in every stratum you picked. Remove a filter above." : "This rule found nothing in this extraction."}</div>}
        </div>
      </section>
      <section className="col pane" data-tour="page-pane" ref={paneRef}>
        <PagePane catalog={cat} tabs={tabs} activeStem={active} onActivate={(s) => setActiveStem(s)}
          highlights={highlights} focusId={focusId} banner={banner} legend={legend} ruleset={catalog.ruleset_version}
          captureSelection={selectAnswer} onSelection={onAnswer} onRemove={removePiece} barActions={barActions ?? fieldBar} captureFirst={captureFirst}
          pickBlock={!!missed && kind === "locator"}
          onPickBlock={(c) => setMissed((m) => (m ? { ...m, capture: c } : m))} />
        {missed && kind === "locator" && row && (
          <MissedCourse pageTitle={tabs.find((t) => t.stem === active)?.title ?? ""} marks={ov?.marks ?? []} state={missed}
            onChange={setMissed} onSave={() => void saveMissed()} onCancel={() => setMissed(null)} />
        )}
        {missed && kind === "page" && detail && (
          <MissedPage catalog={cat} ruleId={detail.rule_id} unclassified={unclassified} state={missed} onChange={setMissed}
            onOpen={(p) => { const t = { stem: p.page_stem, url: p.url, title: p.title ?? p.page_stem }; setExtraTab(t); setActiveStem(t.stem); }}
            onSave={() => void saveMissed()} onCancel={() => { setMissed(null); setExtraTab(null); setActiveStem(null); }} />
        )}
      </section>
    </div>
  );
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
