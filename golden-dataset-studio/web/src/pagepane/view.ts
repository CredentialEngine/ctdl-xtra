// View settings of the page pane: zoom and "page CSS off". Neither changes the page's DOM structure, so css
// paths, highlights and selection capture keep working.

/** Zoom steps, like a browser's. 1 = fit the 1400 px desktop layout to the pane's width. */
export const ZOOM_STEPS = [0.5, 0.67, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3];
const ZOOM_KEY = "studio.pane.zoom";
const CSS_KEY = "studio.pane.css";

export function nextZoom(z: number, dir: 1 | -1): number {
  if (dir > 0) return ZOOM_STEPS.find((s) => s > z + 1e-6) ?? z;
  return [...ZOOM_STEPS].reverse().find((s) => s < z - 1e-6) ?? z;
}

/** Zoom works like browser zoom: the page is laid out at a narrower width and scaled up, so it reflows instead
 * of overflowing. Returns the layout width and the scale for a pane `paneWidth` px wide. */
export function layoutFor(paneWidth: number, desktop: number, zoom: number): { width: number; scale: number } {
  const fit = paneWidth > 0 ? Math.min(1, paneWidth / desktop) : 1;
  const scale = fit * zoom;
  return { width: Math.max(320, Math.round(paneWidth > 0 ? paneWidth / scale : desktop / zoom)), scale };
}

export function readSetting<T>(key: "zoom" | "css", fallback: T): T {
  try {
    const v = localStorage.getItem(key === "zoom" ? ZOOM_KEY : CSS_KEY);
    return v == null ? fallback : (JSON.parse(v) as T);
  } catch {
    return fallback;
  }
}

export function writeSetting(key: "zoom" | "css", value: unknown): void {
  try {
    localStorage.setItem(key === "zoom" ? ZOOM_KEY : CSS_KEY, JSON.stringify(value));
  } catch {
    /* private mode: the setting lasts for this page only */
  }
}

// Sheets the Studio itself adds (highlights, the overlay's fallback); they stay on when the page's CSS is off.
const KEEP_IDS = new Set(["gds-highlight-css", "gds-plain-css"]);
// With the page's styles off, keep images and icons at a readable size and the text in a readable column.
const PLAIN_CSS = `img,video,canvas,iframe{max-width:min(100%,480px)!important;max-height:240px!important;height:auto!important}
svg{max-width:1.5em!important;max-height:1.5em!important}
body{font:16px/1.5 Georgia,serif;margin:16px 24px;max-width:72em}`;

function isStudioSheet(node: Node | null): boolean {
  if (!node || !(node instanceof Element || (node as Element).nodeType === 1)) return false;
  const el = node as Element;
  return KEEP_IDS.has(el.id) || !!el.closest?.("#gds-overlay");
}

/** Turn the page's own stylesheets, `<style>` elements and `style=""` attributes off or back on. */
export function setPageCss(doc: Document, on: boolean): void {
  for (const sheet of Array.from(doc.styleSheets)) {
    if (isStudioSheet(sheet.ownerNode)) continue;
    sheet.disabled = !on;
  }
  let plain = doc.getElementById("gds-plain-css");
  if (!on && !plain && doc.head) {
    plain = doc.createElement("style");
    plain.id = "gds-plain-css";
    plain.textContent = PLAIN_CSS;
    doc.head.appendChild(plain); // in <head>: no body element's css path changes
  } else if (on && plain) {
    plain.remove();
  }
  if (on) {
    for (const el of Array.from(doc.querySelectorAll("[data-gds-style]"))) {
      el.setAttribute("style", el.getAttribute("data-gds-style") ?? "");
      el.removeAttribute("data-gds-style");
    }
  } else {
    for (const el of Array.from(doc.querySelectorAll("body [style]"))) {
      if (el.closest("#gds-overlay")) continue;
      el.setAttribute("data-gds-style", el.getAttribute("style") ?? "");
      el.removeAttribute("style");
    }
  }
}
