export const LAYOUT_WIDTH = 1400; // desktop width the page is laid out at, then scaled to fit

export function renderUrl(catalog: string, stem: string, ruleset?: number | null): string {
  const q = ruleset != null ? `?ruleset=${ruleset}` : "";
  return `/api/catalogs/${encodeURIComponent(catalog)}/pages/${encodeURIComponent(stem)}/render${q}`;
}

const prefetched = new Set<string>();
const queue: string[] = [];
let inflight = 0;

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
