// The shared password (server/auth.py): whether this browser is signed in. Any 401 from the API (an expired
// cookie, a changed password) signs it out, which brings back the "Who are you?" screen.
import { useEffect, useState } from "react";

export interface Session { password_required: boolean; signed_in: boolean }

let current: Session | null = null;

function set(s: Session) {
  current = s;
  window.dispatchEvent(new Event("studio-session"));
}
export function signedOut(): void { if (current?.signed_in) set({ password_required: true, signed_in: false }); }

export async function signIn(password: string): Promise<void> {
  const r = await fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/json" },
                                        body: JSON.stringify({ password }) });
  if (!r.ok) throw new Error(r.status === 401 ? "Wrong password." : `Couldn't sign in (${r.status}).`);
  set({ password_required: true, signed_in: true });
}

/** The session, or null while it loads. */
export function useSession(): Session | null {
  const [s, setS] = useState(current);
  useEffect(() => {
    const on = () => setS(current);
    window.addEventListener("studio-session", on);
    if (!current) fetch("/api/session").then((r) => r.json()).then(set, () => set({ password_required: false, signed_in: true }));
    return () => window.removeEventListener("studio-session", on);
  }, []);
  return s;
}
