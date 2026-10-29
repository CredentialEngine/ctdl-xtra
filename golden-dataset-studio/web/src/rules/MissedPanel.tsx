// "Add a course this rule missed" (record locator) and "Add a page this rule missed" (page rule): spec §7.2,
// screen 12. Both record a `missing` verdict.
import { useEffect, useState } from "react";
import type { Overlay, UnclassifiedPage } from "../api/types";
import type { CapturedSelection } from "../pagepane";
import { Ico } from "../shell/icons";
import { apiX, type PageHit } from "./api";
import { clip, parseMark, shortTitle } from "./logic";

export interface MissedState { capture: CapturedSelection | null; note: string; stem: string | null; query: string }

export function MissedCourse({ pageTitle, marks, state, onChange, onSave, onCancel }: {
  pageTitle: string; marks: Overlay["marks"]; state: MissedState; onChange: (s: MissedState) => void;
  onSave: () => void; onCancel: () => void;
}) {
  const c = state.capture;
  return (
    <div className="missed-panel" data-testid="missed-course">
      <div className="mp-h"><Ico name="missing" /><b>A course this rule missed</b><span className="faint">on {shortTitle(pageTitle, 50)}</span></div>
      {marks.length > 0 && <>
        <div className="mp-sub">Marked on this page — confirm one:</div>
        <div className="mp-list">{marks.map((m, k) => {
          const { code, line } = parseMark(m.detail);
          const on = !!c && c.css_path === m.css_path;
          return (
            <div key={k} className={`mp-item unc${on ? " on" : ""}`} onClick={() => onChange({ ...state,
              capture: { text: line, css_path: m.css_path, char_start: 0, char_end: line.length, prefix: "", suffix: "" } })}>
              <span><span className="sw-unc sm">{code}</span>{line}</span><span className="pickit">{on ? "selected" : "Confirm"}</span>
            </div>
          );
        })}</div>
      </>}
      {c ? <blockquote className="sel-quote">{clip(c.text, 220)}</blockquote>
         : <div className="pick"><Ico name="highlight" /><span>{marks.length ? "…or click any other course block on the page →" : "Click the course's block on the page →"}</span></div>}
      <input className="note" placeholder="Note (optional)" value={state.note} onChange={(e) => onChange({ ...state, note: e.target.value })} />
      <div className="ex-btns">
        <button className="btn primary save" disabled={!c} onClick={onSave}>Save · missing</button>
        <button className="btn cancel" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

export function MissedPage({ catalog, ruleId, unclassified, state, onChange, onOpen, onSave, onCancel }: {
  catalog: string; ruleId: string; unclassified: UnclassifiedPage[] | null; state: MissedState;
  onChange: (s: MissedState) => void; onOpen: (p: { page_stem: string; url: string; title: string | null }) => void;
  onSave: () => void; onCancel: () => void;
}) {
  const [hits, setHits] = useState<PageHit[] | null>(null);
  useEffect(() => {
    if (!state.query.trim()) { setHits(null); return; }
    let live = true;
    const t = window.setTimeout(() => apiX.pageSearch(catalog, state.query, ruleId).then((h) => { if (live) setHits(h); }), 150);
    return () => { live = false; window.clearTimeout(t); };
  }, [catalog, ruleId, state.query]);
  const list = hits ?? (unclassified ?? []).map((u) => ({ ...u, matched: false, detail: u.detail }));
  return (
    <div className="missed-panel" data-testid="missed-page">
      <div className="mp-h"><Ico name="missing" /><b>A page this rule missed</b></div>
      <input className="search-p" placeholder="Find a saved page by title or address" value={state.query}
        onChange={(e) => onChange({ ...state, query: e.target.value })} />
      {!hits && <div className="mp-sub">Pages no page rule recognised although they name many course codes:</div>}
      <div className="mp-list">{list.map((x) => (
        <div key={x.page_stem} className={`mp-item${x.page_stem === state.stem ? " on" : ""}`}
          onClick={() => { onChange({ ...state, stem: x.page_stem }); onOpen(x); }}>
          <span>{shortTitle(x.title) || x.page_stem}</span>
          <span className="faint">{x.url.replace(/^https?:\/\/[^/]+/, "")}{x.matched ? " · already recognised" : ""}</span>
        </div>
      ))}{list.length === 0 && <div className="mp-item faint">No pages.</div>}</div>
      <input className="note" placeholder="Note (optional): why does this page belong?" value={state.note}
        onChange={(e) => onChange({ ...state, note: e.target.value })} />
      <div className="ex-btns">
        <button className="btn primary save" disabled={!state.stem} onClick={onSave}>Save · missing</button>
        <button className="btn cancel" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}
