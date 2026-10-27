// "Reviewing as [name ▾]" (spec §7.1): names remembered in this browser, recorded as each event's author.
// No login and no profiles (out of scope).
import { useEffect, useState } from "react";

const KEY = "studio.reviewer";
const NAMES = "studio.reviewers";
const DEFAULT_NAMES = ["Jared", "Seth", "Eric"];

function read<T>(k: string, d: T): T {
  try { const v = localStorage.getItem(k); return v ? (JSON.parse(v) as T) : d; } catch { return d; }
}
function write(k: string, v: unknown) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } }

export function reviewerNames(): string[] {
  const names = read<string[]>(NAMES, DEFAULT_NAMES);
  const me = currentReviewer();
  return names.includes(me) ? names : [...names, me];
}
export function currentReviewer(): string { return read(KEY, "Jared"); }
export function setReviewer(name: string): void {
  const names = read<string[]>(NAMES, DEFAULT_NAMES);
  if (!names.includes(name)) write(NAMES, [...names, name]);
  write(KEY, name);
  window.dispatchEvent(new Event("studio-reviewer"));
}
export function useReviewer(): string {
  const [me, setMe] = useState(currentReviewer);
  useEffect(() => {
    const on = () => setMe(currentReviewer());
    window.addEventListener("studio-reviewer", on);
    return () => window.removeEventListener("studio-reviewer", on);
  }, []);
  return me;
}
