// Who is reviewing (spec §7.1): a profile picked on the "Who are you?" screen and remembered in this browser.
// No login: a profile is a name and a role, shared by everyone on the root (routes_profiles.py); the name is
// recorded as each event's author.
import { useEffect, useState } from "react";

export type Role = "sme" | "engineer";
export interface Profile { name: string; role: Role | null }
export const ROLE_LABEL: Record<Role, string> = { sme: "Subject matter expert", engineer: "Engineer" };

const KEY = "studio.reviewer";
const ROLE = "studio.role";

// Where localStorage is unavailable (private mode, tests), the choice lasts until the page is reloaded.
const memory = new Map<string, string>();

function read<T>(k: string, d: T): T {
  let v: string | null | undefined;
  try { v = localStorage.getItem(k); } catch { v = memory.get(k); }
  try { return v ? (JSON.parse(v) as T) : d; } catch { return d; }
}
function write(k: string, v: unknown) {
  const text = v === null ? null : JSON.stringify(v);
  try {
    if (text === null) localStorage.removeItem(k); else localStorage.setItem(k, text);
  } catch {
    if (text === null) memory.delete(k); else memory.set(k, text);
  }
}

export function currentReviewer(): string { return read(KEY, ""); }
export function currentRole(): Role | null { return read<Role | null>(ROLE, null); }
/** True once this browser has picked a profile and a role. */
export function hasIdentity(): boolean { return !!currentReviewer() && !!currentRole(); }

export function setIdentity(name: string, role: Role): void {
  write(KEY, name);
  write(ROLE, role);
  window.dispatchEvent(new Event("studio-reviewer"));
}
function useIdentityEvent<T>(get: () => T): T {
  const [v, setV] = useState(get);
  useEffect(() => {
    const on = () => setV(get());
    window.addEventListener("studio-reviewer", on);
    return () => window.removeEventListener("studio-reviewer", on);
  }, [get]);
  return v;
}
export function useReviewer(): string { return useIdentityEvent(currentReviewer); }
export function useRole(): Role | null { return useIdentityEvent(currentRole); }
export function useHasIdentity(): boolean { return useIdentityEvent(hasIdentity); }
