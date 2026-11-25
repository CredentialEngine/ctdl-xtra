import { useState, type Dispatch, type ReactNode, type SetStateAction } from "react";
import { nextZoom, ZOOM_STEPS } from "./view";
import type { CapturedSelection } from "./dom";
import type { Highlight } from "./paint";
import { SourceView } from "./SourceView";
import { HighlightBar, type BarAction, type BarAt } from "./HighlightBar";
import { usePagePane, type BarState, type PaneMode, type PaneState, type ViewSettings } from "./usePagePane";
import "./pagepane.css";

export { LAYOUT_WIDTH, prefetchPages, renderUrl } from "./pages";
export { barAt } from "./frameEvents";

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
  /** With actions, a text selection shows the highlight bar above it (sme-fixes §1) instead of calling `onSelection`. */
  barActions?: BarAction[] | null;
  /** With `barActions`: the selection is first handed to `onSelection` (it counts at once), then the bar offers to change
   * what it means. Without it, nothing is kept until a button of the bar is pressed. */
  captureFirst?: boolean;
  /** The × of a `removable` highlight was clicked. */
  onRemove?(id: string): void;
  pickBlock?: boolean;
  onPickBlock?(sel: CapturedSelection): void;
  legend?: ReactNode;
  /** Ruleset whose `pane_css` applies (default: the catalog's latest). Also makes the render URL cacheable longer. */
  ruleset?: number | null;
}

export function PagePane(props: PagePaneProps): JSX.Element {
  const pane = usePagePane(props);
  return (
    <div className="gpp-browser" data-testid="page-pane">
      <PaneTabs tabs={props.tabs} active={pane.active} onActivate={props.onActivate} />
      <AddressBar active={pane.active} mode={pane.mode} setMode={pane.setMode} />
      <ViewTools view={pane.view} scale={pane.scale} />
      {props.legend ? <div className="gpp-ctx sel">{props.legend}</div> : null}
      {props.banner ? <div className="gpp-ctx">{props.banner}</div> : null}
      <PaneBody props={props} pane={pane} />
    </div>
  );
}

const MAX_TABS = 3;

function PaneTabs({ tabs, active, onActivate }: { tabs: PageTab[]; active: PageTab | null; onActivate(stem: string): void }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const { shown, hidden } = splitTabs(tabs, active);
  return (
    <div className="gpp-tabs">
      <div className="gpp-dots" aria-hidden="true"><i /><i /><i /></div>
      <div className="gpp-tabs-in" role="tablist">
        {shown.map((t, i) => <PaneTab key={t.stem} tab={t} index={i} on={t.stem === active?.stem} onActivate={onActivate} />)}
        {hidden.length > 0 && <MoreTabs hidden={hidden} open={moreOpen} setOpen={setMoreOpen} onActivate={onActivate} />}
      </div>
    </div>
  );
}

/** The first tabs, with the active one always among them; the rest go under "+n". */
function splitTabs(tabs: PageTab[], active: PageTab | null): { shown: PageTab[]; hidden: PageTab[] } {
  const shown = tabs.slice(0, MAX_TABS);
  if (active && !shown.some((t) => t.stem === active.stem)) shown[shown.length - 1] = active;
  return { shown, hidden: tabs.filter((t) => !shown.includes(t)) };
}

function PaneTab({ tab, index, on, onActivate }: { tab: PageTab; index: number; on: boolean; onActivate(stem: string): void }) {
  return (
    <button role="tab" aria-selected={on} className={`gpp-tab${on ? " on" : ""}`} title={tab.title} onClick={() => onActivate(tab.stem)}>
      {tab.badge != null && <span className={`gpp-num${index ? " alt" : ""}`}>{tab.badge}</span>}
      <span className="gpp-tab-t">{tab.title || tab.stem}</span>
    </button>
  );
}

function MoreTabs({ hidden, open, setOpen, onActivate }: { hidden: PageTab[]; open: boolean;
  setOpen: Dispatch<SetStateAction<boolean>>; onActivate(stem: string): void }) {
  return (
    <div className="gpp-more">
      <button className="gpp-more-btn" onClick={() => setOpen((o) => !o)} aria-expanded={open}>+{hidden.length}</button>
      {open && <MoreMenu hidden={hidden} onPick={(stem) => { setOpen(false); onActivate(stem); }} />}
    </div>
  );
}

function MoreMenu({ hidden, onPick }: { hidden: PageTab[]; onPick(stem: string): void }) {
  return (
    <div className="gpp-more-menu" role="menu">
      {hidden.map((t) => (
        <button key={t.stem} role="menuitem" onClick={() => onPick(t.stem)}>
          {t.badge != null && <span className="gpp-num alt">{t.badge}</span>}
          <span className="gpp-tab-t">{t.title || t.stem}</span>
        </button>
      ))}
    </div>
  );
}

function AddressBar({ active, mode, setMode }: { active: PageTab | null; mode: PaneMode; setMode(mode: PaneMode): void }) {
  return (
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
  );
}

function ViewTools({ view, scale }: { view: ViewSettings; scale: number }) {
  const { pageCss, toggleCss } = view;
  return (
    <div className="gpp-tools" role="toolbar" aria-label="Page view" data-tour="page-view-tools">
      <ZoomControls view={view} scale={scale} />
      <span className="gpp-tools-sep" />
      <label className={`gpp-check${pageCss ? "" : " off"}`}
        title="Turn the page's own styles off to see its plain content and structure (highlights stay)">
        <input type="checkbox" checked={pageCss} onChange={toggleCss} /> Page CSS
      </label>
      {!pageCss && <span className="gpp-tools-note">styles off</span>}
    </div>
  );
}

function ZoomControls({ view: { zoom, changeZoom }, scale }: { view: ViewSettings; scale: number }) {
  return (
    <>
      <button className="gpp-tool" onClick={() => changeZoom(nextZoom(zoom, -1))} disabled={zoom <= ZOOM_STEPS[0]}
        title="Zoom out" aria-label="Zoom out"><ZoomIcon plus={false} /></button>
      <button className="gpp-zoom" onClick={() => changeZoom(1)} title="Reset zoom (fit the page to the pane)">
        {Math.round(scale * 100)}%
      </button>
      <button className="gpp-tool" onClick={() => changeZoom(nextZoom(zoom, 1))}
        disabled={zoom >= ZOOM_STEPS[ZOOM_STEPS.length - 1]} title="Zoom in" aria-label="Zoom in"><ZoomIcon plus /></button>
    </>
  );
}

function PaneBody({ props, pane }: { props: PagePaneProps; pane: PaneState }) {
  const { src, loaded, mode, active } = pane;
  return (
    <div className={`gpp-body${props.pickBlock ? " picking" : ""}`} ref={pane.bodyRef}>
      {src ? <PageFrame key={props.catalog} src={src} pane={pane} /> : <div className="gpp-empty">No page to show.</div>}
      {src && !loaded && mode === "page" && <div className="gpp-loading">Loading saved page…</div>}
      <PaneBar bar={pane.bar} actions={props.barActions} mode={mode} scale={pane.scale} />
      {mode === "html" && active && (
        <SourceView catalog={props.catalog} stem={active.stem} target={pane.sourceTarget} />
      )}
    </div>
  );
}

function PageFrame({ src, pane }: { src: string; pane: PaneState }) {
  return (
    <iframe
      ref={pane.frameRef}
      src={src}
      title={pane.active?.title ?? "Saved page"}
      sandbox="allow-same-origin"
      referrerPolicy="no-referrer"
      onLoad={pane.onLoad}
      style={frameStyleOf(pane)}
    />
  );
}

function frameStyleOf({ layoutWidth, size, scale, mode }: PaneState) {
  return {
    width: layoutWidth,
    height: size.h > 0 ? size.h / scale : "100%",
    transform: `scale(${scale})`,
    visibility: mode === "page" ? ("visible" as const) : ("hidden" as const),
  };
}

function PaneBar({ bar, actions, mode, scale }: { bar: BarState; actions?: BarAction[] | null; mode: PaneMode; scale: number }) {
  const at = barWhereItsTextIs(bar.bar, bar.frameY, scale);
  if (!at || at.y < 0 || mode !== "page" || !actions?.length) return null;
  const onPointer = (on: boolean) => { if (!bar.barRef.current?.hover) return; if (on) bar.keepHover(); else bar.dropHover(); };
  return (
    <HighlightBar key={`${at.sel.css_path}|${at.sel.char_start}|${at.sel.char_end}`} at={at}
      actions={actions} onDone={bar.closeBar} onPointer={onPointer}
      onPin={() => bar.setBar((b) => (b ? { ...b, hover: undefined } : b))} />
  );
}

/** The bar where its text is now; out of sight (negative y) while its text is scrolled above the pane. */
function barWhereItsTextIs(bar: BarAt | null, frameY: number, scale: number): BarAt | null {
  return bar ? { ...bar, y: bar.y - (frameY - (bar.scrollY ?? frameY)) * scale } : null;
}

const ExtIcon = () => (
  <svg viewBox="0 0 16 16" width="15" height="15" fill="none" aria-hidden="true">
    <path d="M9 2.5h4.5V7M13.5 2.5 7.5 8.5M11.5 9.5v3.5a.5.5 0 0 1-.5.5H3a.5.5 0 0 1-.5-.5V5a.5.5 0 0 1 .5-.5h3.5"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

function ZoomIcon({ plus }: { plus: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
      <circle cx="7" cy="7" r="4.6" />
      <path d="m10.4 10.4 3.6 3.6M5 7h4" />
      {plus && <path d="M7 5v4" />}
    </svg>
  );
}
