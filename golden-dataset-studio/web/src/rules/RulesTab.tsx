// The Rules tab (spec §7.2, screens 03–06, 12): rules by kind on the left, one rule's rows in the middle
// (sorted by the server with the likeliest problems first), the saved page on the right.
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { EventBrief, NewEvent, Overlay, RuleDetail, RulesResponse, RuleSummary, SampleInfo, Spread,
  UnclassifiedPage } from "../api/types";
import { PagePane, prefetchPages, type Highlight } from "../pagepane";
import { Ico } from "../shell/icons";
import { useReviewer } from "../shell/reviewer";
import { SampleDrawer, samplePrefs, sampleQuery, StrataTags, type SamplePrefs } from "../shell/Sample";
import { go, href } from "../shell/router";
import type { TabProps } from "../shell/tabProps";
import { fmt, toast, useKeyHints } from "../shell/ui";
import { apiX, type RowX } from "./api";
import {
  applyEvent, briefOf, isField, isSettled, keyAction, missingEvent, newDraft, pushRecent, paneTabs, rowTarget,
  scrollWithin, shortTitle, unitWord, verdictEvent, type Draft, type TabRef,
} from "./logic";
import { MissedCourse, MissedPage, type MissedState } from "./MissedPanel";
import { Controls, Expansion, HistoryLine, Value } from "./parts";
import { RuleHead } from "./RuleHead";
import { RuleList } from "./RuleList";
import "./rules.css";

const FIRST_PAGE = 100;
const MORE = 200;
const PREFETCH = 4;

export function defaultRule(rules: RulesResponse | null): string | null {
  if (!rules) return null;
  const all = rules.groups.flatMap((g) => g.rules);
  return (all.find((r) => r.rule_id === "course-description") ?? all.find((r) => r.kind === "field") ?? all[0])?.rule_id ?? null;
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

const DEFAULT_PREFS = samplePrefs("review");

export default function RulesTab({ catalog, route }: TabProps) {
  const cat = catalog.short;
  const me = useReviewer();
  const [rules, setRules] = useState<RulesResponse | null>(null);
  const [detail, setDetail] = useState<RuleDetail | null>(null);
  const [rows, setRows] = useState<RowX[]>([]);
  const [total, setTotal] = useState(0);
  const [spread, setSpread] = useState<Spread | null>(null);
  const [sample, setSample] = useState<SampleInfo | null>(null);
  // the Sample drawer's choices belong to one rule: another rule starts in review order, unfiltered
  const [prefsOf, setPrefsOf] = useState<{ rule: string | null; p: SamplePrefs }>({ rule: null, p: DEFAULT_PREFS });
  const [missing, setMissing] = useState<EventBrief[]>([]);
  const [sel, setSel] = useState(0);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [missed, setMissed] = useState<MissedState | null>(null);
  const [recent, setRecent] = useState<TabRef[]>([]);
  const [activeStem, setActiveStem] = useState<string | null>(null);
  const [extraTab, setExtraTab] = useState<TabRef | null>(null);
  const [overlay, setOverlay] = useState<{ key: string; data: Overlay } | null>(null);
  const [unclassified, setUnclassified] = useState<UnclassifiedPage[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const token = useRef(0);
  const loadingMore = useRef(false);
  const overlays = useRef(new Map<string, Overlay>());
  const rowsRef = useRef<HTMLDivElement>(null);
  const paneRef = useRef<HTMLElement>(null);
  const centerNext = useRef(true);
  useTourAnchors(paneRef);
  useKeyHints(KEY_HINTS, []);

  const ruleId = route.id ?? defaultRule(rules);
  const focus = route.params.get("row");
  const prefs = prefsOf.rule === ruleId ? prefsOf.p : DEFAULT_PREFS;
  const setPrefs = useCallback((p: SamplePrefs) => setPrefsOf({ rule: ruleId, p }), [ruleId]);
  const qKey = JSON.stringify(sampleQuery(prefs, "review"));
  const sq = useMemo(() => JSON.parse(qKey) as ReturnType<typeof sampleQuery>, [qKey]);
  const filtered = sq.f.length > 0;

  useEffect(() => { api.rules(cat).then(setRules, (e) => setError(String(e))); }, [cat]);

  useEffect(() => {
    if (!ruleId) return;
    const tok = ++token.current;
    setDraft(null); setMissed(null); setExtraTab(null); setActiveStem(null);
    Promise.all([api.rule(cat, ruleId), apiX.rows(cat, ruleId, { limit: FIRST_PAGE, focus, ...sq })]).then(([d, r]) => {
      if (tok !== token.current) return;
      setDetail(d); setRows(r.rows); setTotal(r.total); setSpread(r.spread); setSample(r.sample ?? null); setMissing(r.missing); setSel(r.focus_index ?? 0);
      centerNext.current = true; setError(null);
      if (rowsRef.current) rowsRef.current.scrollTop = 0;
    }, (e) => setError(String(e)));
  }, [cat, ruleId, focus, sq]);

  const kind = detail?.kind ?? null;
  const row = detail && detail.rule_id === ruleId ? rows[sel] ?? null : null;

  const loadMore = useCallback(() => {
    if (!ruleId || loadingMore.current || rows.length >= total) return;
    loadingMore.current = true;
    const tok = token.current;
    apiX.rows(cat, ruleId, { offset: rows.length, limit: MORE, ...sq }).then((r) => {
      if (tok === token.current) setRows((prev) => (prev.length === r.offset ? [...prev, ...r.rows] : prev));
    }).finally(() => { loadingMore.current = false; });
  }, [cat, ruleId, rows.length, total, sq]);

  const selectRow = useCallback((i: number) => {
    const j = Math.max(0, Math.min(i, rows.length - 1));
    if (j === sel) return;
    const prev = rows[sel];
    if (prev) setRecent((r) => pushRecent(r, { stem: prev.page_stem, url: prev.url, title: prev.page_title ?? prev.page_stem }));
    setSel(j); setDraft(null); setMissed(null); setExtraTab(null); setActiveStem(null);
    if (j >= rows.length - 5) loadMore();
  }, [rows, sel, loadMore]);

  // keep the selected row visible; prefetch the next rows' pages (spec §10)
  useEffect(() => {
    const box = rowsRef.current;
    const el = box?.querySelector<HTMLElement>(`[data-row-index="${sel}"]`);
    if (box && el) scrollWithin(box, el, centerNext.current);
    centerNext.current = false;
    prefetchPages(cat, rows.slice(sel + 1, sel + 1 + PREFETCH).map((r) => r.page_stem), catalog.ruleset_version);
  }, [sel, rows, cat, catalog.ruleset_version]);

  // --- page pane --------------------------------------------------------------------------------------------
  const curTab: TabRef | null = row ? { stem: row.page_stem, url: row.url, title: row.page_title ?? row.page_stem } : null;
  const tabs = useMemo(() => paneTabs(curTab,
    [...(extraTab ? [extraTab] : []), ...(row?.other_pages ?? []).map((p) => ({ stem: p.page_stem, url: p.url, title: p.title ?? p.page_stem }))],
    recent).map((t, i) => ({ ...t, title: shortTitle(t.title), badge: i + 1 })),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  [row?.key, extraTab, recent]);
  const active = activeStem ?? row?.page_stem ?? null;

  useEffect(() => {
    if (!detail || detail.kind === "field" || !active) return;
    const key = `${detail.rule_id}|${active}`;
    const hit = overlays.current.get(key);
    if (hit) { setOverlay({ key, data: hit }); return; }
    api.overlay(cat, active, detail.rule_id).then((data) => { overlays.current.set(key, data); setOverlay({ key, data }); }, () => {});
  }, [cat, detail, active]);
  const ov = detail && active && overlay?.key === `${detail.rule_id}|${active}` ? overlay.data : null;

  const capture = draft?.capture ?? missed?.capture ?? null;
  const { highlights, focusId } = useMemo(() => {
    const hs: Highlight[] = [];
    let fid: string | null = null;
    if (row && detail) {
      if (detail.kind === "field") {
        if (active === row.page_stem && row.css_path) {
          hs.push({ id: "value", kind: "value", cssPath: row.css_path, charStart: row.char_start, charEnd: row.char_end, text: row.value, badge: 1 });
          fid = "value";
        }
        const exp = row.verdict?.expected;
        if (exp?.css_path && active === row.page_stem && (row.state === "wrong" || row.state === "still-wrong") && !draft) {
          hs.push({ id: "expected", kind: "expected", cssPath: exp.css_path, charStart: exp.char_start, charEnd: exp.char_end, text: exp.text, badge: 2 });
        }
      } else if (ov) {
        for (const b of ov.blocks) hs.push({ id: b.occurrence_key, kind: "block", cssPath: b.css_path, badge: b.n });
        if (detail.kind === "locator") ov.marks.forEach((m, i) => hs.push({ id: `mark${i}`, kind: "mark", cssPath: m.css_path, charStart: m.char_start, charEnd: m.char_end }));
        fid = detail.kind === "locator" && active === row.page_stem ? row.occurrence_key : ov.blocks[0]?.occurrence_key ?? null;
      }
      if (detail.kind === "locator") {
        for (const m of missing) {
          const e = m.expected;
          if (e?.css_path && m.page_stem === active) hs.push({ id: `missing-${m.annotation_id}`, kind: "expected", cssPath: e.css_path, text: e.text });
        }
      }
      if (capture) { hs.push({ id: "capture", kind: "expected", cssPath: capture.css_path, charStart: capture.char_start, charEnd: capture.char_end, text: capture.text }); fid = "capture"; }
    }
    return { highlights: hs, focusId: fid };
  }, [row, detail, active, ov, capture, draft, missing]);

  // --- saving ---------------------------------------------------------------------------------------------------
  const post = useCallback(async (ev: NewEvent): Promise<EventBrief | null> => {
    setBusy(true);
    try {
      const r = await api.annotate(cat, ev);
      if (r.rule) {
        setRules((rs) => (rs ? replaceSummary(rs, r.rule!) : rs));
        setDetail((d) => (d && d.rule_id === r.rule!.rule_id ? { ...d, ...r.rule! } : d));
      }
      return briefOf(r.event as Parameters<typeof briefOf>[0]);
    } catch (e) {
      toast(`Not saved: ${String(e instanceof Error ? e.message : e)}`);
      return null;
    } finally { setBusy(false); }
  }, [cat]);

  const saveRow = useCallback(async (i: number, what: { verdict: "correct" } | { draft: Draft }) => {
    const r = rows[i];
    if (!r || !detail) return;
    if ("verdict" in what && r.state === "correct") { toast(`Already correct · ${r.course_key ?? shortTitle(r.page_title, 40)}`); selectRow(i + 1); return; }
    const ev = verdictEvent(me, rowTarget(detail.kind, detail.rule_id, r), r.verdict, what);
    const brief = await post(ev);
    if (!brief) return;
    setRows((rs) => rs.map((x, j) => (j === i ? applyEvent(x, brief) : x)));
    setDraft(null);
    const label = ev.type === "comment" ? "Comment saved" : ev.verdict === "question" ? "Question for the institution saved"
      : ev.verdict === "correct" ? "Correct" : "Wrong";
    toast(`${label} · ${r.course_key ?? shortTitle(r.page_title, 40)}`);
    if (ev.type === "verdict" && ev.verdict !== "question") selectRow(i + 1);
  }, [rows, detail, me, post, selectRow]);

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
    if (i !== sel) selectRow(i);
    const r = rows[i];
    if (!r) return;
    if (v === "correct") { void saveRow(i, { verdict: "correct" }); return; }
    setMissed(null);
    setDraft(newDraft(v, r.verdict, r.state));
  }, [sel, rows, selectRow, saveRow]);

  const startMissed = useCallback(() => {
    setDraft(null);
    setMissed({ capture: null, note: "", stem: null, query: "" });
    if (detail?.kind === "page" && !unclassified) api.unclassifiedPages(cat).then(setUnclassified, () => setUnclassified([]));
  }, [detail, unclassified, cat]);

  const approve = useCallback(async (type: "approve" | "reopen") => {
    if (!detail) return;
    const brief = await post({ type, author: me, target: { kind: "rule", rule_id: detail.rule_id },
                               note: type === "approve" ? "Approved in the Studio" : "Reopened in the Studio" });
    if (brief) toast(`${type === "approve" ? "Approved" : "Reopened"}: ${detail.title}`);
  }, [detail, me, post]);

  // --- keyboard (spec §7.2) ----------------------------------------------------------------------------------
  const keys = useRef<(e: KeyboardEvent) => void>(() => {});
  keys.current = (e: KeyboardEvent) => {
    const a = keyAction(e, isField(e.target));
    if (!a || !row) return;
    if (a === "save") {
      if (missed) { e.preventDefault(); void saveMissed(); }
      else if (draft) { e.preventDefault(); void saveRow(sel, { draft }); }
      return;
    }
    if (a === "cancel") {
      if (isField(e.target)) (e.target as HTMLElement).blur();
      setDraft(null); setMissed(null); setExtraTab(null);
      return;
    }
    e.preventDefault();
    if (a === "next") selectRow(sel + 1);
    else if (a === "prev") selectRow(sel - 1);
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
    const what = kind === "field" ? <><b>{detail.property_label ?? detail.title}</b> · {row.course_key ?? ""}</>
      : kind === "locator" ? <><b>Course</b> · {row.course_key ?? ""}</> : <b>{detail.title}</b>;
    if (draft?.mode === "wrong") {
      legend = <><Ico name="highlight" /><span><b>Select the right text</b> on the page for {what}: drag across it.</span></>;
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
      banner = <><span className="gds-num">1</span><span className="grow">{what} — {row.css_path ? "the value found is highlighted." : "this value isn't read from the page."}</span></>;
    } else {
      banner = <span className="grow">{what} — another page this course is on. The value is highlighted on tab 1.</span>;
    }
  }

  return (
    <div className="rules-layout w4-rules">
      <aside className="col">{rules && <RuleList rules={rules} active={ruleId} onPick={(id) => go(href(cat, "rules", id))} />}</aside>
      <section className="col mid">
        {detail && <RuleHead catalog={catalog} rule={detail} busy={busy} onApprove={() => approve("approve")} onReopen={() => approve("reopen")} />}
        {detail && <div className="rows-bar"><span><b>{fmt(total)}</b> {unitWord(detail.kind, detail.locator)}{filtered && <> · <b>filtered</b> by strata</>}{prefs.prior && <> · reviewed in other fields first</>} · {
          sq.order === "auto" ? "autostratified: 3 of each combination, rarest first"
          : sq.order === "shuffle" ? "shuffled"
          : <>discussed first, then the likeliest problems{spread && spread.groups.length > 1 && !filtered && <>, with every 5th row from a <SpreadNote spread={spread} /></>}</>}</span></div>}
        {detail && <SampleDrawer sample={sample} prefs={prefs} onPrefs={setPrefs} modes={["review", "auto", "shuffle", "manual"]}
          storageKey="studio.rules.sample" />}
        <div className="rows" data-tour="rows" ref={rowsRef} onScroll={(e) => {
          const el = e.currentTarget;
          if (el.scrollTop + el.clientHeight > el.scrollHeight - 600) loadMore();
        }}>
          {missing.length > 0 && kind !== "field" && (
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
          {detail && rows.map((r, i) => {
            const on = i === sel;
            const val = r.status === "found" ? r.value ?? "" : r.status === "no_match" ? "nothing found" : "empty";
            const settled = isSettled(r.state);
            const cls = `row${on ? " on" : ""}${r.verdict && r.state !== "fixed" ? ` v-${r.verdict.verdict}` : ""}${settled && !(on && draft) ? " done" : ""}${kind === "page" ? " page-row" : ""}`;
            return (
              <div key={r.key} className={cls} data-row-index={i} tabIndex={-1} onClick={() => selectRow(i)}>
                {kind !== "page" && <div className="code">{r.course_key ?? "—"}</div>}
                <div className="body">
                  {kind === "page"
                    ? <><div className="val">{r.page_title ?? r.page_stem}</div><div className="pg">{r.url.replace(/^https?:\/\//, "")}</div></>
                    : <>{on
                          // the selected row: the whole value, its paragraphs kept (as the Records tab shows a field)
                          ? <div className={`val full${r.status === "found" ? "" : " empty"}`} data-testid="row-full-value">{val}</div>
                          : <div className={`val${r.status === "found" ? "" : " empty"}`}><Value text={val} /></div>}
                        <div className="pg">{r.context}</div>
                        {on && r.course_key && (
                          <div className="row-links">
                            <a className="xbtn" title="Open this course in the Records tab, with this field selected"
                              href={href(cat, "records", r.course_key,
                                { prop: kind === "field" ? detail.property_label : null, occ: r.occurrence_key })}
                              onClick={(e) => e.stopPropagation()}>Open in Records →</a>
                          </div>)}</>}
                  <StrataTags tags={r.tags} />
                  <HistoryLine state={r.state} verdict={r.verdict} reattached={r.reattached} comments={r.comments} page_questions={r.page_questions} />
                  {on && draft && <Expansion draft={draft} fieldRule={kind === "field"} emptyValue={r.status !== "found"}
                    onChange={setDraft} onSave={() => void saveRow(i, { draft })} onCancel={() => setDraft(null)} />}
                </div>
                <Controls state={r.state} verdict={r.verdict} comments={r.comments} draft={on ? draft : null}
                  onPick={(v) => pick(i, v)} tour={on} />
              </div>
            );
          })}
          {detail && rows.length < total && <div className="row more-rows" onClick={loadMore}>+ {fmt(total - rows.length)} more · scroll to load</div>}
          {detail && total === 0 && <div className="empty-state muted">{filtered
            ? "No row is in every stratum you picked. Remove a filter above." : "This rule found nothing in this extraction."}</div>}
        </div>
      </section>
      <section className="col pane" data-tour="page-pane" ref={paneRef}>
        <PagePane catalog={cat} tabs={tabs} activeStem={active} onActivate={(s) => setActiveStem(s)}
          highlights={highlights} focusId={focusId} banner={banner} legend={legend} ruleset={catalog.ruleset_version}
          captureSelection={draft?.mode === "wrong"}
          onSelection={(c) => setDraft((d) => (d && d.mode === "wrong" ? { ...d, capture: c } : d))}
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

/** "spread sample by length", with every group and its size on hover (strata.py). */
function SpreadNote({ spread }: { spread: Spread }) {
  const what = spread.by.split(":")[0];
  const tip = `Rows without signals are grouped by ${spread.by}, and one row from each group is dealt in turn, ` +
    `so you see every kind of value early.\n\n${spread.groups.map((g) => `${fmt(g.rows).padStart(6)}  ${g.label}`).join("\n")}`;
  return <span className="spread-note" title={tip}>spread sample by {what} ({spread.groups.length} groups)</span>;
}
