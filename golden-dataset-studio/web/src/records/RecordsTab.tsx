// The Records tab (spec §7.3, screen 07): find a course, see every in-scope field as a card, with the same
// verdict controls as the Rules tab (the same `verdict` events, targeting (field rule, occurrence)) and the same
// page pane with numbered highlights for each field.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { CourseDetail, EventBrief, NewEvent } from "../api/types";
import { PagePane, type Highlight } from "../pagepane";
import { apiX, type CourseHitX } from "../rules/api";
import {
  applyEvent, briefOf, isField, isSettled, keyAction, newDraft, scrollWithin, shortTitle, verdictEvent, type Draft,
} from "../rules/logic";
import { Controls, Expansion, HistoryLine } from "../rules/parts";
import "../rules/rules.css";
import { Ico } from "../shell/icons";
import { useReviewer } from "../shell/reviewer";
import { go, href } from "../shell/router";
import type { TabProps } from "../shell/tabProps";
import { termUrl, toast, useKeyHints } from "../shell/ui";
import { courseHeading, foundOn, groupCards, valueKey, type CardValue } from "./logic";
import "./records.css";

const HINTS = (
  <span className="key-hints"><kbd>A</kbd>correct <kbd>W</kbd>wrong <kbd>C</kbd>comment <kbd>Enter</kbd>save{" "}
    <kbd>Esc</kbd>cancel · same verdicts as the Rules tab</span>
);

export default function RecordsTab({ catalog, route }: TabProps) {
  const cat = catalog.short;
  const me = useReviewer();
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<CourseHitX[] | null>(null);
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [activeStem, setActiveStem] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  useKeyHints(HINTS, []);

  const courseKey = route.id;
  const wantProp = route.params.get("prop") ?? "Description";

  useEffect(() => {
    let live = true;
    const t = window.setTimeout(() => apiX.courses(cat, q || undefined).then((h) => { if (live) setHits(h); }, (e) => setError(String(e))), q ? 120 : 0);
    return () => { live = false; window.clearTimeout(t); };
  }, [cat, q]);

  // no course in the address yet: open the first one in the list
  useEffect(() => {
    if (!courseKey && hits && hits.length && !q) go(href(cat, "records", hits[0].course_key), true);
  }, [courseKey, hits, q, cat]);

  useEffect(() => {
    if (!courseKey) return;
    let live = true;
    setDraft(null); setActiveStem(null);
    api.course(cat, courseKey).then((d) => { if (live) { setCourse(d); setError(null); } }, (e) => { if (live) { setCourse(null); setError(String(e)); } });
    return () => { live = false; };
  }, [cat, courseKey]);

  const cards = useMemo(() => (course ? groupCards(course) : []), [course]);
  useEffect(() => {
    if (!cards.length) return;
    const card = cards.find((c) => c.property === wantProp) ?? cards[0];
    setSel(valueKey(card.values[0]));
  }, [cards, wantProp]);

  useEffect(() => {
    const box = listRef.current;
    const el = box?.querySelector<HTMLElement>(".course-item.on");
    if (box && el) scrollWithin(box, el, false);
  }, [hits, courseKey]);

  const cardsRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const box = cardsRef.current;
    const el = box?.querySelector<HTMLElement>(".v.on")?.closest<HTMLElement>(".card");
    if (box && el) box.scrollTop = el.offsetTop - box.offsetTop - 8;
  }, [sel, course]);

  const flat = useMemo(() => cards.flatMap((c) => c.values.map((v) => ({ card: c, v }))), [cards]);
  const cur = flat.find((x) => valueKey(x.v) === sel) ?? flat[0] ?? null;

  // --- page pane ------------------------------------------------------------------------------------------
  const tabs = useMemo(() => {
    const seen = new Map<string, { stem: string; url: string; title: string; course: boolean }>();
    for (const o of course?.occurrences ?? []) {
      if (!seen.has(o.page_stem)) seen.set(o.page_stem, { stem: o.page_stem, url: o.url, title: shortTitle(o.page_title ?? o.page_stem), course: false });
      if (o.locator_rule_id === "locator-course-page") seen.get(o.page_stem)!.course = true;
    }
    return [...seen.values()].sort((a, b) => Number(b.course) - Number(a.course)).map((t, i) => ({ stem: t.stem, url: t.url, title: t.title, badge: i + 1 }));
  }, [course]);
  const active = activeStem ?? cur?.v.page_stem ?? tabs[0]?.stem ?? null;
  const highlights = useMemo(() => {
    const hs: Highlight[] = [];
    for (const { card, v } of flat) {
      if (v.page_stem !== active || !v.css_path) continue;
      hs.push({ id: valueKey(v), kind: "value", cssPath: v.css_path, charStart: v.char_start, charEnd: v.char_end, text: v.value, badge: card.n });
    }
    if (draft?.capture) hs.push({ id: "capture", kind: "expected", cssPath: draft.capture.css_path, charStart: draft.capture.char_start, charEnd: draft.capture.char_end, text: draft.capture.text });
    return hs;
  }, [flat, active, draft]);
  const focusId = draft?.capture ? "capture" : cur && cur.v.page_stem === active ? valueKey(cur.v) : null;

  // --- saving ---------------------------------------------------------------------------------------------
  const patch = useCallback((v: CardValue, ev: EventBrief) => {
    setCourse((d) => d && { ...d, occurrences: d.occurrences.map((o) => o.occurrence_key !== v.occurrence_key ? o
      : { ...o, fields: o.fields.map((f) => (f.rule_id === v.rule_id ? applyEvent(f, ev) : f)) }) });
  }, []);

  const save = useCallback(async (v: CardValue, what: { verdict: "correct" } | { draft: Draft }) => {
    if ("verdict" in what && v.state === "correct") { toast("Already correct"); return; }
    const target: NewEvent["target"] = { kind: "match", rule_id: v.rule_id, occurrence_key: v.occurrence_key, page_stem: v.page_stem };
    const ev = verdictEvent(me, target, v.verdict, what);
    try {
      const r = await api.annotate(cat, ev);
      patch(v, briefOf(r.event as Parameters<typeof briefOf>[0]));
      setDraft(null);
      toast(ev.type === "comment" ? "Comment saved" : ev.verdict === "question" ? "Question for the institution saved"
        : `${ev.verdict === "correct" ? "Correct" : "Wrong"} saved · ${v.property_label ?? v.rule_id}`);
    } catch (e) {
      toast(`Not saved: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [cat, me, patch]);

  const pick = useCallback((v: CardValue, k: "correct" | "wrong" | "comment") => {
    if (valueKey(v) !== sel) { setSel(valueKey(v)); setActiveStem(null); }
    if (k === "correct") { void save(v, { verdict: "correct" }); return; }
    setDraft(newDraft(k, v.verdict, v.state));
  }, [sel, save]);

  const keys = useRef<(e: KeyboardEvent) => void>(() => {});
  keys.current = (e) => {
    const a = keyAction(e, isField(e.target));
    if (!a || !cur) return;
    if (a === "save") { if (draft) { e.preventDefault(); void save(cur.v, { draft }); } return; }
    if (a === "cancel") { setDraft(null); return; }
    const i = flat.indexOf(cur);
    if (a === "next" || a === "prev") {
      e.preventDefault();
      const n = flat[Math.max(0, Math.min(flat.length - 1, i + (a === "next" ? 1 : -1)))];
      setSel(valueKey(n.v)); setDraft(null); setActiveStem(null);
      return;
    }
    e.preventDefault();
    pick(cur.v, a === "correct" ? "correct" : a === "comment" ? "comment" : "wrong");
  };
  useEffect(() => {
    const on = (e: KeyboardEvent) => keys.current(e);
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, []);

  const curCard = cur?.card;
  const banner = draft?.mode === "wrong"
    ? null
    : curCard ? <><span className="gds-num">{curCard.n}</span><span className="grow"><b>{curCard.property}</b> on {shortTitle(tabs.find((t) => t.stem === active)?.title, 50)} — numbers match the cards on the left.</span></> : null;
  const legend = draft?.mode === "wrong" && curCard
    ? <><Ico name="highlight" /><span><b>Select the right text</b> on the page for {curCard.property}: drag across it.</span></> : null;

  return (
    <div className="rec-layout w4-records">
      <aside className="col">
        <input className="search" placeholder="Find a course code" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Find a course" />
        <div className="course-list" ref={listRef}>
          {(hits ?? []).map((h) => (
            <a key={h.course_key} className={`course-item${h.course_key === courseKey ? " on" : ""}`} href={href(cat, "records", h.course_key)}>
              <span className="c">{h.course_key}{h.annotated && <span className="dot" title="has verdicts" />}</span>
              <span className="t">{(h.line ?? "").replace(/^[^-]*-\s*/, "")}</span>
            </a>
          ))}
          {hits && hits.length === 0 && <div className="faint" style={{ padding: 10 }}>No course matches “{q}”.</div>}
        </div>
      </aside>
      <section className="col mid">
        {error && <div className="placeholder muted" style={{ padding: 18 }}>{error}</div>}
        {course && <>
          <div className="rec-head"><h1>{courseHeading(cards, course.course_key)}</h1><div className="sub">{foundOn(course)}</div></div>
          <div className="cards" ref={cardsRef}>
            {cards.map((c) => {
              const url = termUrl(c.ctdl_property);
              return (
                <div key={c.property} className="card" data-card={c.n}>
                  <div className="card-h"><span className="bn">{c.n}</span>
                    {url ? <a className="term sm" href={url} target="_blank" rel="noopener noreferrer">{c.ctdl_property}<Ico name="ext" /></a>
                         : <span className="term sm plain">no CTDL term</span>}
                    <span className="lbl">{c.property}</span></div>
                  <div className="vals">{c.values.map((v) => {
                    const on = cur?.v === v;
                    const settled = isSettled(v.state);
                    return (
                      <div key={valueKey(v)} className={`v${on ? " on" : ""}${v.verdict ? ` v-${v.verdict.verdict}` : ""}${settled && !(on && draft) ? " done" : ""}`}
                        onClick={() => { if (!on) { setSel(valueKey(v)); setDraft(null); setActiveStem(null); } }}>
                        <div style={{ minWidth: 0 }}>
                          <div className="tx">{v.status === "found" ? v.value : "(nothing found)"}</div>
                          <div className="src"><span className="tag">{v.on_course_page ? "course page" : "program page"}</span><span>{shortTitle(v.page_title, 70)}</span></div>
                          <HistoryLine state={v.state} verdict={v.verdict} comments={v.comments} />
                          {on && draft && <Expansion draft={draft} fieldRule emptyValue={v.status !== "found"} onChange={setDraft}
                            onSave={() => void save(v, { draft })} onCancel={() => setDraft(null)} />}
                        </div>
                        <Controls state={v.state} verdict={v.verdict} comments={v.comments} draft={on ? draft : null} onPick={(k) => pick(v, k)} />
                      </div>
                    );
                  })}</div>
                </div>
              );
            })}
          </div>
        </>}
      </section>
      <section className="col pane">
        <PagePane catalog={cat} tabs={tabs} activeStem={active} onActivate={setActiveStem} highlights={highlights} focusId={focusId}
          banner={banner} legend={legend} ruleset={catalog.ruleset_version}
          captureSelection={draft?.mode === "wrong"} onSelection={(c) => setDraft((d) => (d && d.mode === "wrong" ? { ...d, capture: c } : d))} />
      </section>
    </div>
  );
}
