import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { Dispatch, MutableRefObject, RefObject, SetStateAction } from "react";
import { layoutFor, readSetting, setPageCss, writeSetting } from "./view";
import { clear, hoverBox, paint, resolveAll, scrollToRect, type Highlight, type Resolved } from "./paint";
import { listenToFrame, type FrameContext } from "./frameEvents";
import { LAYOUT_WIDTH, renderUrl } from "./pages";
import type { BarAt } from "./HighlightBar";
import type { PageTab, PagePaneProps } from "./PagePane";

export type PaneMode = "page" | "html";

export function usePagePane(props: PagePaneProps) {
  const [mode, setMode] = useState<PaneMode>("page");
  const frame = useFrameView();
  const active = activeTab(props.tabs, props.activeStem);
  const src = active ? renderUrl(props.catalog, active.stem, props.ruleset) : null;
  const bar = useHighlightBar(frame.doc, src, !!props.barActions?.length);
  const { onLoad, loaded } = usePaintedFrame(props, frame, bar, src);
  const sourceTarget = useSourceTarget(props.highlights, props.focusId);
  return { mode, setMode, ...frame, active, src, bar, onLoad, loaded, sourceTarget };
}

export type PaneState = ReturnType<typeof usePagePane>;

function useFrameView() {
  const { bodyRef, size } = useBodySize();
  const view = useViewSettings();
  const { width: layoutWidth, scale } = layoutFor(size.w, LAYOUT_WIDTH, view.zoom);
  const { frameRef, doc } = useFrame();
  return { bodyRef, size, view, layoutWidth, scale, frameRef, doc };
}

type FrameView = ReturnType<typeof useFrameView>;

function useBodySize() {
  const bodyRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  useLayoutEffect(() => {
    const body = bodyRef.current;
    if (!body) return;
    const fit = () => setSize({ w: body.clientWidth, h: body.clientHeight });
    fit();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(fit);
    ro.observe(body);
    return () => ro.disconnect();
  }, []);
  return { bodyRef, size };
}

/** Zoom and the page's own CSS, remembered in this browser. */
function useViewSettings() {
  const [zoom, setZoom] = useState<number>(() => readSetting("zoom", 1));
  const [pageCss, setPageCssOn] = useState<boolean>(() => readSetting("css", true));
  const changeZoom = useCallback((z: number) => { setZoom(z); writeSetting("zoom", z); }, []);
  const toggleCss = useCallback(() => {
    setPageCssOn((on) => { writeSetting("css", !on); return !on; });
  }, []);
  return { zoom, changeZoom, pageCss, toggleCss };
}

export type ViewSettings = ReturnType<typeof useViewSettings>;

function useFrame() {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const doc = useCallback((): Document | null => {
    try {
      return frameRef.current?.contentDocument ?? null;
    } catch {
      return null;
    }
  }, []);
  return { frameRef, doc };
}

function activeTab(tabs: PageTab[], activeStem: string | null): PageTab | null {
  return tabs.find((t) => t.stem === activeStem) ?? tabs[0] ?? null;
}

/** The highlight bar, over the selection it is about; `frameY` is the page's scroll while it is up, so it follows its text. */
function useHighlightBar(doc: () => Document | null, src: string | null, hasBar: boolean) {
  const [bar, setBar] = useState<BarAt | null>(null);
  const [frameY, setFrameY] = useState(0);
  const barRef = useLatest(bar);
  const { hideTimer, keepHover, dropHover } = useHoverGrace(setBar);
  const closeBar = useCallback(() => {
    window.clearTimeout(hideTimer.current);
    setBar(null);
    try { doc()?.getSelection()?.removeAllRanges(); } catch { /* the frame went away */ }
  }, [doc, hideTimer]);
  useEffect(() => { setBar(null); }, [src, hasBar]);
  useDismissBar(bar, closeBar);
  return { bar, setBar, frameY, setFrameY, barRef, keepHover, dropHover, closeBar };
}

export type BarState = ReturnType<typeof useHighlightBar>;

const HOVER_GRACE_MS = 350;  // a hover bar's time to reach it after leaving its text

/** A hover bar goes a moment after the pointer leaves its text, so the pointer can reach the bar. */
function useHoverGrace(setBar: Dispatch<SetStateAction<BarAt | null>>) {
  const hideTimer = useRef<number | undefined>(undefined);
  const keepHover = useCallback(() => window.clearTimeout(hideTimer.current), []);
  const dropHover = useCallback(() => {
    window.clearTimeout(hideTimer.current);
    hideTimer.current = window.setTimeout(() => setBar((b) => (b?.hover ? null : b)), HOVER_GRACE_MS);
  }, [setBar]);
  useEffect(() => () => window.clearTimeout(hideTimer.current), []);
  return { hideTimer, keepHover, dropHover };
}

/** Esc closes only the bar; a click anywhere else also clears the selection (one left on the page looks kept, but isn't). */
function useDismissBar(bar: BarAt | null, closeBar: () => void): void {
  useEffect(() => {
    if (!bar) return;
    const key = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.stopPropagation();  // capture phase: before the tab's own Esc
      closeBar();
    };
    const down = (e: MouseEvent) => { if (!(e.target as Element | null)?.closest?.(".gpp-hbar")) closeBar(); };
    window.addEventListener("keydown", key, true);
    window.addEventListener("mousedown", down, true);
    return () => { window.removeEventListener("keydown", key, true); window.removeEventListener("mousedown", down, true); };
  }, [bar, closeBar]);
}

/** Paints the highlights whenever the page loads, they change, or the view moves them. */
function usePaintedFrame(props: PagePaneProps, frame: FrameView, bar: BarState, src: string | null) {
  const { doc, frameRef } = frame;
  const latest = useLatest(props);
  const painter = usePainter(doc, latest);
  const scaleRef = useLatest(frame.scale);
  const { onLoad, loadedSrc } = useFrameLoad(doc, frameRef, frameContextOf(latest, scaleRef, bar, painter));
  const loaded = src != null && loadedSrc === src;
  useRepaint(frame, props, loaded, painter.schedule);
  usePageCss(doc, frame.view.pageCss, loaded, painter.schedule);
  useFrameCleanup(doc, src, loaded, props.pickBlock);
  return { onLoad, loaded };
}

const RESCROLL_MS = [250, 700, 1400];

const HOVERABLE = new Set(["value", "expected", "excluded"]);

function usePainter(doc: () => Document | null, latest: MutableRefObject<PagePaneProps>) {
  const hoverables = useRef<Resolved[]>([]);
  const timers = useTimers();
  const apply = useCallback((scroll: boolean) => {
    const d = doc();
    if (!d || !d.documentElement || !d.body) return;
    hoverables.current = paintHighlights(d, latest.current, scroll);
  }, [doc, latest]);
  const schedule = useCallback((scroll: boolean) => {
    timers.current.forEach((t) => window.clearTimeout(t));
    apply(scroll);
    // re-apply while web fonts and late CSS settle (positions move); a newer call cancels these
    timers.current = RESCROLL_MS.map((ms) => window.setTimeout(() => apply(scroll), ms));
  }, [apply, timers]);
  return { apply, schedule, hoverables };
}

function useTimers(): MutableRefObject<number[]> {
  const timers = useRef<number[]>([]);
  useEffect(() => () => timers.current.forEach((t) => window.clearTimeout(t)), []);
  return timers;
}

type Painter = ReturnType<typeof usePainter>;

/** Paints the highlights; returns the painted text a hover shows the bar for: the value found and the pieces of an answer. */
function paintHighlights(d: Document, { highlights, focusId }: PagePaneProps, scroll: boolean): Resolved[] {
  const resolved = resolveAll(d, highlights);
  const hoverables = resolved.filter((r) => r.range && HOVERABLE.has(r.h.kind));
  const focus = paint(d, resolved, focusId);
  if (scroll && focus && d.defaultView) scrollToRect(d.defaultView, focus);
  return hoverables;
}

/** `context` holds stable callbacks and refs only, so the frame's listeners stay valid for the page's whole life. */
function useFrameLoad(doc: () => Document | null, frameRef: RefObject<HTMLIFrameElement>, context: Omit<FrameContext, "d">) {
  const [loadedSrc, setLoadedSrc] = useState<string | null>(null);
  const contextRef = useLatest(context);
  const onLoad = useCallback(() => {
    const d = doc();
    const frame = frameRef.current;
    if (!d || !frame) return;
    const loadedPath = framePath(frame);
    if (!loadedPath || loadedPath === "blank" || loadedPath.startsWith("about:")) return;
    listenToFrame({ d, ...contextRef.current });
    setLoadedSrc(loadedPath); // compared with `src`: a late load of an older page never counts as loaded
  }, [doc, frameRef, contextRef]);
  return { onLoad, loadedSrc };
}

function frameContextOf(latest: MutableRefObject<PagePaneProps>, scaleRef: MutableRefObject<number>, bar: BarState,
  painter: Painter): Omit<FrameContext, "d"> {
  const { barRef, setBar, setFrameY, keepHover, dropHover } = bar;
  return { latest, scaleRef, barRef, setBar, setFrameY, keepHover, dropHover, apply: painter.apply, hoverables: painter.hoverables };
}

// The iframe's current URL tells us which page finished loading.
function framePath(frame: HTMLIFrameElement): string | null {
  try {
    const loc = frame.contentWindow?.location;
    return loc ? loc.pathname + loc.search : null;
  } catch {
    return null;
  }
}

function useRepaint(frame: FrameView, props: PagePaneProps, loaded: boolean, schedule: (scroll: boolean) => void): void {
  const { highlights, focusId } = props;
  const { scale, layoutWidth, size } = frame;
  useEffect(() => {
    if (loaded) schedule(true);
  }, [loaded, highlights, focusId, schedule]);
  useEffect(() => {
    if (loaded) schedule(false);
  }, [scale, layoutWidth, size.w, loaded, schedule]);
}

function usePageCss(doc: () => Document | null, pageCss: boolean, loaded: boolean, schedule: (scroll: boolean) => void): void {
  useEffect(() => {
    const d = doc();
    if (d && loaded) {
      setPageCss(d, pageCss);
      schedule(true); // positions move when the styles change: bring the value back into view
    }
  }, [pageCss, loaded, doc, schedule]);
}

function useFrameCleanup(doc: () => Document | null, src: string | null, loaded: boolean, pickBlock?: boolean): void {
  // clear stale paint when picking mode turns off
  useEffect(() => {
    const d = doc();
    if (d && loaded && !pickBlock) hoverBox(d, null);
  }, [pickBlock, loaded, doc]);
  useEffect(() => {
    const d = doc();
    return () => {
      if (d) clear(d);
    };
  }, [src, doc]);
}

function useSourceTarget(highlights: Highlight[], focusId?: string | null): Highlight | null {
  return useMemo(() => {
    const byFocus = highlights.find((h) => h.id === focusId);
    return byFocus ?? highlights.find((h) => h.kind === "value" || h.kind === "expected") ?? highlights[0] ?? null;
  }, [highlights, focusId]);
}

function useLatest<T>(value: T): MutableRefObject<T> {
  const ref = useRef(value);
  ref.current = value;
  return ref;
}
