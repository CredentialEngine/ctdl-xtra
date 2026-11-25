// "Add a course this rule missed" (record locator) and "Add a page this rule missed" (page rule): spec §7.2,
// screen 12. Both record a `missing` verdict.
import { useEffect, useState } from "react";
import type { Overlay, UnclassifiedPage } from "../api/types";
import type { CapturedSelection } from "../pagepane";
import { Ico } from "../shell/icons";
import { apiX, type PageHit } from "./api";
import { clip, parseMark, shortTitle } from "./logic";

export interface MissedState { capture: CapturedSelection | null; note: string; stem: string | null; query: string }

export function MissedCourse({ pageTitle, marks, state, onChange, onSave, onCancel }: MissedCourseProps) {
  const c = state.capture;
  return (
    <div className="missed-panel" data-testid="missed-course">
      <div className="mp-h"><Ico name="missing" /><b>A course this rule missed</b><span className="faint">on {shortTitle(pageTitle, 50)}</span></div>
      {marks.length > 0 && <MarkedCourses marks={marks} state={state} onChange={onChange} />}
      {c ? <blockquote className="sel-quote">{clip(c.text, 220)}</blockquote>
         : <div className="pick"><Ico name="highlight" /><span>{marks.length ? "…or click any other course block on the page →" : "Click the course's block on the page →"}</span></div>}
      <input className="note" placeholder="Note (optional)" value={state.note} onChange={(e) => onChange({ ...state, note: e.target.value })} />
      <SaveButtons canSave={!!c} onSave={onSave} onCancel={onCancel} />
    </div>
  );
}

export function MissedPage({ catalog, ruleId, unclassified, state, onChange, onOpen, onSave, onCancel }: MissedPageProps) {
  const hits = usePageSearch(catalog, ruleId, state.query);
  const list = hits ?? (unclassified ?? []).map((u) => ({ ...u, matched: false, detail: u.detail }));
  return (
    <div className="missed-panel" data-testid="missed-page">
      <div className="mp-h"><Ico name="missing" /><b>A page this rule missed</b></div>
      <PageSearch state={state} onChange={onChange} searching={!!hits} />
      <PageChoices list={list} state={state} onChange={onChange} onOpen={onOpen} />
      <input className="note" placeholder="Note (optional): why does this page belong?" value={state.note}
        onChange={(e) => onChange({ ...state, note: e.target.value })} />
      <SaveButtons canSave={!!state.stem} onSave={onSave} onCancel={onCancel} />
    </div>
  );
}

interface MissedCourseProps {
  pageTitle: string; marks: Overlay["marks"]; state: MissedState; onChange: (s: MissedState) => void;
  onSave: () => void; onCancel: () => void;
}

type OpenPage = (p: { page_stem: string; url: string; title: string | null }) => void;

interface MissedPageProps {
  catalog: string; ruleId: string; unclassified: UnclassifiedPage[] | null; state: MissedState;
  onChange: (s: MissedState) => void; onOpen: OpenPage; onSave: () => void; onCancel: () => void;
}

/** The course blocks the uncovered-code signal marked on this page, each confirmable as the missed course. */
function MarkedCourses({ marks, state, onChange }: { marks: Overlay["marks"]; state: MissedState; onChange: (s: MissedState) => void }) {
  return (<>
    <div className="mp-sub">Marked on this page — confirm one:</div>
    <div className="mp-list">{marks.map((m, k) => <MarkedCourse key={k} mark={m} state={state} onChange={onChange} />)}</div>
  </>);
}

function MarkedCourse({ mark, state, onChange }: { mark: Overlay["marks"][number]; state: MissedState; onChange: (s: MissedState) => void }) {
  const { code, line } = parseMark(mark.detail);
  const on = !!state.capture && state.capture.css_path === mark.css_path;
  const confirm = () => onChange({ ...state,
    capture: { text: line, css_path: mark.css_path, char_start: 0, char_end: line.length, prefix: "", suffix: "" } });
  return (
    <div className={`mp-item unc${on ? " on" : ""}`} onClick={confirm}>
      <span><span className="sw-unc sm">{code}</span>{line}</span><span className="pickit">{on ? "selected" : "Confirm"}</span>
    </div>
  );
}

/** Saved pages matching the search, 150 ms after typing stops; null while there is no search. */
function usePageSearch(catalog: string, ruleId: string, query: string): PageHit[] | null {
  const [hits, setHits] = useState<PageHit[] | null>(null);
  useEffect(() => {
    if (!query.trim()) { setHits(null); return; }
    let live = true;
    const t = window.setTimeout(() => apiX.pageSearch(catalog, query, ruleId).then((h) => { if (live) setHits(h); }), 150);
    return () => { live = false; window.clearTimeout(t); };
  }, [catalog, ruleId, query]);
  return hits;
}

function PageSearch({ state, onChange, searching }: { state: MissedState; onChange: (s: MissedState) => void; searching: boolean }) {
  return (<>
    <input className="search-p" placeholder="Find a saved page by title or address" value={state.query}
      onChange={(e) => onChange({ ...state, query: e.target.value })} />
    {!searching && <div className="mp-sub">Pages no page rule recognised although they name many course codes:</div>}
  </>);
}

function PageChoices({ list, state, onChange, onOpen }: {
  list: (PageHit | (UnclassifiedPage & { matched: boolean }))[]; state: MissedState; onChange: (s: MissedState) => void; onOpen: OpenPage;
}) {
  return (
    <div className="mp-list">{list.map((x) => (
      <div key={x.page_stem} className={`mp-item${x.page_stem === state.stem ? " on" : ""}`}
        onClick={() => { onChange({ ...state, stem: x.page_stem }); onOpen(x); }}>
        <span>{shortTitle(x.title) || x.page_stem}</span>
        <span className="faint">{x.url.replace(/^https?:\/\/[^/]+/, "")}{x.matched ? " · already recognised" : ""}</span>
      </div>
    ))}{list.length === 0 && <div className="mp-item faint">No pages.</div>}</div>
  );
}

function SaveButtons({ canSave, onSave, onCancel }: { canSave: boolean; onSave: () => void; onCancel: () => void }) {
  return (
    <div className="ex-btns">
      <button className="btn primary save" disabled={!canSave} onClick={onSave}>Save · missing</button>
      <button className="btn cancel" onClick={onCancel}>Cancel</button>
    </div>
  );
}
