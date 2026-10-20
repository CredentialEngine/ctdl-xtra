// The URL hash is "#<catalog id>/<page stem>"; no hash means the landing page.
export interface Route {
  cid: string | null;
  stem: string | null;
}

export function parseHash(hash: string): Route {
  const raw = decodeURIComponent(hash.replace(/^#/, ""));
  if (!raw) return { cid: null, stem: null };
  const [cid, ...rest] = raw.split("/");
  return { cid: cid || null, stem: rest.join("/") || null };
}

export function buildHash(cid: string | null, stem?: string | null): string {
  if (!cid) return "";
  return stem ? `#${cid}/${stem}` : `#${cid}`;
}
