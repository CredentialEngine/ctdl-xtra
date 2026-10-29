import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { layoutFor, nextZoom, readSetting, setPageCss, writeSetting, ZOOM_STEPS } from "./view";
import type { ReactNode } from "react";
import { blockOf, captureElement, captureSelection, type CapturedSelection } from "./dom";
import { clear, hoverBox, paint, resolveAll, scrollToRect, type Highlight } from "./paint";
import { SourceView } from "./SourceView";
import "./pagepane.css";

export interface PageTab {
  stem: string;
  url: string;
  title: string;
  badge?: number;
}

export interface PagePaneProps {
  catalog: string;
  tabs: PageTab[];
  activeStem: string | null;
  onActivate(stem: string): void;
  highlights: Highlight[];
  focusId?: string | null;
  banner?: ReactNode;
  captureSelection?: boolean;
  onSelection?(sel: CapturedSelection): void;
  /** The × of a `removable` highlight was clicked. */
  onRemove?(id: string): void;
  pickBlock?: boolean;
  onPickBlock?(sel: CapturedSelection): void;
  legend?: ReactNode;
  /** Ruleset whose `pane_css` applies (default: the catalog's latest). Also makes the render URL cacheable longer. */
  ruleset?: number | null;
}

export const LAYOUT_WIDTH = 1400; // desktop width the page is laid out at, then scaled to fit
const MAX_TABS = 3;
const RESCROLL_MS = [250, 700, 1400];

export function renderUrl(catalog: string, stem: string, ruleset?: number | null): string {
  const q = ruleset != null ? `?ruleset=${ruleset}` : "";
  return `/api/catalogs/${encodeURIComponent(catalog)}/pages/${encodeURIComponent(stem)}/render${q}`;
}

const prefetched = new Set<string>();
const queue: string[] = [];
let inflight = 0;

function pump(): void {
  while (inflight < 2 && queue.length) {
    const url = queue.shift()!;
    inflight++;
    fetch(url, { credentials: "same-origin" })
      .then((r) => r.arrayBuffer())
      .catch(() => prefetched.delete(url))
      .finally(() => {
        inflight--;
        pump();
      });
  }
}

/** Warm the server's render cache and the browser's HTTP cache for pages about to be shown (next rows). */
export function prefetchPages(catalog: string, stems: string[], ruleset?: number | null): void {
  for (const stem of stems) {
    const url = renderUrl(catalog, stem, ruleset);
    if (prefetched.has(url)) continue;
    prefetched.add(url);
    queue.push(url);
  }
  pump();
}

const ExtIcon = () => (
  <svg viewBox="0 0 16 16" width="15" height="15" fill="none" aria-hidden="true">
    <path d="M9 2.5h4.5V7M13.5 2.5 7.5 8.5M11.5 9.5v3.5a.5.5 0 0 1-.5.5H3a.5.5 0 0 1-.5-.5V5a.5.5 0 0 1 .5-.5h3.5"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export function PagePane(props: PagePaneProps): JSX.Element {
  const { catalog, tabs, activeStem, onActivate, highlights, focusId, banner, legend, ruleset } = props;
  const [mode, setMode] = useState<"page" | "html">("page");
  const [loadedSrc, setLoadedSrc] = useState<string | null>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [zoom, setZoom] = useState<number>(() => readSetting("zoom", 1));
  const [pageCss, setPageCssOn] = useState<boolean>(() => readSetting("css", true));
  const { width: layoutWidth, scale } = layoutFor(size.w, LAYOUT_WIDTH, zoom);
  const [moreOpen, setMoreOpen] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<HTMLIFrameElement>(null);
  const timers = useRef<number[]>([]);
  const latest = useRef(props);
  latest.current = props;

  const active = tabs.find((t) => t.stem === activeStem) ?? tabs[0] ?? null;
  const src = active ? renderUrl(catalog, active.stem, ruleset) : null;
  const loaded = src != null && loadedSrc === src;

  // --- scale to fit -------------------------------------------------------------------------------
  useLayoutEffect(() => {
    const body = bodyRef.current;
    if (!body) return;
    const fit = () => {
      const w = body.clientWidth;
      const h = body.clientHeight;
      setSize({ w, h });
    };
    fit();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(fit);
    ro.observe(body);
    return () => ro.disconnect();
  }, []);

  const doc = useCallback((): Document | null => {
    try {
      return frameRef.current?.contentDocument ?? null;
    } catch {
      return null;
    }
  }, []);

  // --- highlights ----------------------------------------------------------------------------------
  const apply = useCallback(
    (scroll: boolean) => {
      const d = doc();
      if (!d || !d.documentElement || !d.body) return;
      const { highlights: hs, focusId: fid } = latest.current;
      const resolved = resolveAll(d, hs);
      const focus = paint(d, resolved, fid);
      if (scroll && focus && d.defaultView) scrollToRect(d.defaultView, focus);
    },
    [doc],
  );

  const schedule = useCallback(
    (scroll: boolean) => {
      timers.current.forEach((t) => window.clearTimeout(t));
      apply(scroll);
      // re-apply while web fonts and late CSS settle (positions move); a newer call cancels these
      timers.current = RESCROLL_MS.map((ms) => window.setTimeout(() => apply(scroll), ms));
    },
    [apply],
  );

  useEffect(() => () => timers.current.forEach((t) => window.clearTimeout(t)), []);

  useEffect(() => {
    if (loaded) schedule(true);
  }, [loaded, highlights, focusId, schedule]);

  useEffect(() => {
    if (loaded) schedule(false);
  }, [scale, layoutWidth, size.w, loaded, schedule]);

  // --- view settings: zoom and the page's own CSS (remembered in this browser) ----------------------
  const changeZoom = useCallback((z: number) => { setZoom(z); writeSetting("zoom", z); }, []);
  const toggleCss = useCallback(() => {
    setPageCssOn((on) => { writeSetting("css", !on); return !on; });
  }, []);
  useEffect(() => {
    const d = doc();
    if (d && loaded) {
      setPageCss(d, pageCss);
      schedule(true); // positions move when the styles change: bring the value back into view
    }
  }, [pageCss, loaded, doc, schedule]);

  // --- events inside the frame (the page's own scripts never run; these are the parent's listeners) -------
  const onLoad = useCallback(() => {
    const d = doc();
    const frame = frameRef.current;
    if (!d || !frame) return;
    // the iframe's current URL tells us which page finished loading
    const loadedPath = (() => {
      try {
        const loc = frame.contentWindow?.location;
        return loc ? loc.pathname + loc.search : null;
      } catch {
        return null;
      }
    })();
    if (!loadedPath || loadedPath === "blank" || loadedPath.startsWith("about:")) return;
    d.addEventListener(
      "click",
      (e) => {
        const t = e.target as Element | null;
        const p = latest.current;
        const x = t && typeof t.closest === "function" ? t.closest(".gds-x") : null;
        if (x) {
          e.preventDefault();
          e.stopPropagation();
          p.onRemove?.(x.getAttribute("data-id") ?? "");
          return;
        }
        const a = t && typeof t.closest === "function" ? t.closest("a, area, form, button, input[type=submit]") : null;
        if (a) e.preventDefault();
        if (p.pickBlock && p.onPickBlock && t) {
          const sel = d.getSelection();
          if (sel && !sel.isCollapsed) return; // a drag-selection is handled on mouseup
          const block = blockOf(t, d.defaultView);
          if (block) {
            e.preventDefault();
            p.onPickBlock(captureElement(block));
          }
        }
      },
      true,
    );
    d.addEventListener("mouseup", () => {
      const p = latest.current;
      const sel = d.getSelection();
      const cap = captureSelection(sel);
      if (!cap) return;
      if (p.captureSelection && p.onSelection) {
        p.onSelection(cap);
        sel?.removeAllRanges();
      } else if (p.pickBlock && p.onPickBlock) {
        p.onPickBlock(cap);
        sel?.removeAllRanges();
      }
    });
    d.addEventListener("mousemove", (e) => {
      const p = latest.current;
      if (!p.pickBlock) return;
      const t = e.target as Element | null;
      hoverBox(d, t ? blockOf(t, d.defaultView) : null);
    });
    d.addEventListener("mouseleave", () => hoverBox(d, null));
    d.defaultView?.addEventListener("resize", () => apply(false));
    setLoadedSrc(loadedPath); // compared with `src`: a late load of an older page never counts as loaded
  }, [apply, doc]);

  // clear stale paint when picking mode turns off
  useEffect(() => {
    const d = doc();
    if (d && loaded && !props.pickBlock) hoverBox(d, null);
  }, [props.pickBlock, loaded, doc]);

  useEffect(() => {
    const d = doc();
    return () => {
      if (d) clear(d);
    };
  }, [src, doc]);

  // --- tabs -----------------------------------------------------------------------------------------
  const shown = tabs.slice(0, MAX_TABS);
  if (active && !shown.some((t) => t.stem === active.stem)) shown[shown.length - 1] = active;
  const hidden = tabs.filter((t) => !shown.includes(t));

  const sourceTarget = useMemo(() => {
    const byFocus = highlights.find((h) => h.id === focusId);
    return byFocus ?? highlights.find((h) => h.kind === "value" || h.kind === "expected") ?? highlights[0] ?? null;
  }, [highlights, focusId]);

  const frameStyle = {
    width: layoutWidth,
    height: size.h > 0 ? size.h / scale : "100%",
    transform: `scale(${scale})`,
    visibility: mode === "page" ? ("visible" as const) : ("hidden" as const),
  };

  return (
    <div className="gpp-browser" data-testid="page-pane">
      <div className="gpp-tabs">
        <div className="gpp-dots" aria-hidden="true"><i /><i /><i /></div>
        <div className="gpp-tabs-in" role="tablist">
          {shown.map((t, i) => (
            <button
              key={t.stem}
              role="tab"
              aria-selected={t.stem === active?.stem}
              className={`gpp-tab${t.stem === active?.stem ? " on" : ""}`}
              title={t.title}
              onClick={() => onActivate(t.stem)}
            >
              {t.badge != null && <span className={`gpp-num${i ? " alt" : ""}`}>{t.badge}</span>}
              <span className="gpp-tab-t">{t.title || t.stem}</span>
            </button>
          ))}
          {hidden.length > 0 && (
            <div className="gpp-more">
              <button className="gpp-more-btn" onClick={() => setMoreOpen((o) => !o)} aria-expanded={moreOpen}>
                +{hidden.length}
              </button>
              {moreOpen && (
                <div className="gpp-more-menu" role="menu">
                  {hidden.map((t) => (
                    <button key={t.stem} role="menuitem" onClick={() => { setMoreOpen(false); onActivate(t.stem); }}>
                      {t.badge != null && <span className="gpp-num alt">{t.badge}</span>}
                      <span className="gpp-tab-t">{t.title || t.stem}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      <div className="gpp-url">
        <div className="gpp-addr" title={active?.url}>{active?.url ?? ""}</div>
        <div className="gpp-seg" role="group" aria-label="View" data-tour="page-html-switch">
          <button className={mode === "page" ? "on" : ""} onClick={() => setMode("page")}>Page</button>
          <button className={mode === "html" ? "on" : ""} onClick={() => setMode("html")}>HTML</button>
        </div>
        <a className="gpp-ext" data-tour="open-live" href={active?.url ?? undefined} target="_blank" rel="noopener noreferrer"
          title="Open the live page">
          <ExtIcon />
        </a>
      </div>
      <div className="gpp-tools" role="toolbar" aria-label="Page view" data-tour="page-view-tools">
        <button className="gpp-tool" onClick={() => changeZoom(nextZoom(zoom, -1))} disabled={zoom <= ZOOM_STEPS[0]}
          title="Zoom out" aria-label="Zoom out"><ZoomIcon plus={false} /></button>
        <button className="gpp-zoom" onClick={() => changeZoom(1)} title="Reset zoom (fit the page to the pane)">
          {Math.round(scale * 100)}%
        </button>
        <button className="gpp-tool" onClick={() => changeZoom(nextZoom(zoom, 1))}
          disabled={zoom >= ZOOM_STEPS[ZOOM_STEPS.length - 1]} title="Zoom in" aria-label="Zoom in"><ZoomIcon plus /></button>
        <span className="gpp-tools-sep" />
        <label className={`gpp-check${pageCss ? "" : " off"}`}
          title="Turn the page's own styles off to see its plain content and structure (highlights stay)">
          <input type="checkbox" checked={pageCss} onChange={toggleCss} /> Page CSS
        </label>
        {!pageCss && <span className="gpp-tools-note">styles off</span>}
      </div>
      {legend ? <div className="gpp-ctx sel">{legend}</div> : null}
      {banner ? <div className="gpp-ctx">{banner}</div> : null}
      <div className={`gpp-body${props.pickBlock ? " picking" : ""}`} ref={bodyRef}>
        {src ? (
          <iframe
            ref={frameRef}
            key={catalog}
            src={src}
            title={active?.title ?? "Saved page"}
            sandbox="allow-same-origin"
            referrerPolicy="no-referrer"
            onLoad={onLoad}
            style={frameStyle}
          />
        ) : (
          <div className="gpp-empty">No page to show.</div>
        )}
        {src && !loaded && mode === "page" && <div className="gpp-loading">Loading saved page…</div>}
        {mode === "html" && active && (
          <SourceView catalog={catalog} stem={active.stem} target={sourceTarget} />
        )}
      </div>
    </div>
  );
}

function ZoomIcon({ plus }: { plus: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
      <circle cx="7" cy="7" r="4.6" />
      <path d="m10.4 10.4 3.6 3.6M5 7h4" />
      {plus && <path d="M7 5v4" />}
    </svg>
  );
}
