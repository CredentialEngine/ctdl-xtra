// Sign-in: first the shared password (when the server has one and this browser isn't signed in), then "Who are
// you?", which profile you are. A new profile also gets a role; existing ones keep theirs. The profile is remembered in this browser and
// every annotation is recorded under that name.
import { useEffect, useState } from "react";
import { Ico } from "./icons";
import { currentReviewer, ROLE_LABEL, setIdentity, type Profile, type Role } from "./reviewer";
import { signIn } from "./session";
import "./identity.css";

const ADD = "__add";

export function IdentityScreen({ needPassword }: { needPassword: boolean }) {
  const [password, setPassword] = useState("");
  const [passwordOk, setPasswordOk] = useState(!needPassword);
  const [profiles, setProfiles] = useState<Profile[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pick, setPick] = useState(currentReviewer());
  const [newName, setNewName] = useState("");
  const [newRole, setNewRole] = useState<Role | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!passwordOk) return;
    fetch("/api/profiles").then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then((d: { profiles: Profile[] }) => {
        setProfiles(d.profiles);
        if (!d.profiles.some((p) => p.name === currentReviewer())) setPick("");
      }, (e: Error) => setError(`Couldn't load the profiles (${e.message}).`));
  }, [passwordOk]);

  const adding = pick === ADD;
  const picked = adding ? null : profiles?.find((x) => x.name === pick) ?? null;
  const askRole = adding || (!!picked && !picked.role);  // a new profile, or an old one saved without a role
  const role = askRole ? newRole : picked?.role ?? null;
  const name = (adding ? newName : pick).trim().replace(/\s+/g, " ");
  const ready = !passwordOk ? !!password && !busy : !!name && !!role && !busy;

  const go = async () => {
    if (!ready) return;
    if (!passwordOk) {
      setBusy(true);
      try {
        await signIn(password);  // a browser that already knows its profile goes straight in (App.tsx)
        setError(null);
        setPasswordOk(true);
      } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
      setBusy(false);
      return;
    }
    if (!role) return;
    if (!askRole) { setIdentity(name, role); return; }
    setBusy(true);
    try {
      const r = await fetch("/api/profiles", { method: "POST", headers: { "Content-Type": "application/json" },
                                               body: JSON.stringify({ name, role }) });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? r.statusText);
      const d = await r.json() as { profile: Profile };
      setIdentity(d.profile.name, role);
    } catch (e) { setError(String(e)); setBusy(false); }
  };

  return (
    <div className="idn-bg">
      <form className="idn" onSubmit={(e) => { e.preventDefault(); void go(); }}>
        <div className="idn-brand">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M12 2.5 21 7l-9 4.5L3 7l9-4.5Z" fill="#c9a227" />
            <path d="m3 12 9 4.5 9-4.5" stroke="#8a6d12" strokeWidth="1.8" strokeLinejoin="round" />
            <path d="m3 16.5 9 4.5 9-4.5" stroke="#8a6d12" strokeWidth="1.8" strokeLinejoin="round" opacity=".55" />
          </svg>
          <span>Golden Rules Studio</span>
        </div>
        <h1>{passwordOk ? "Who are you?" : "Sign in"}</h1>

        {!passwordOk && (
          <label className="idn-field">
            <span>Password</span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                   autoComplete="current-password" autoFocus />
          </label>)}
        {passwordOk && <label className="idn-field">
          <span>Profile</span>
          <span className="idn-sel">
            <select value={pick} onChange={(e) => setPick(e.target.value)} disabled={!profiles} autoFocus>
              <option value="" disabled>{profiles ? "Choose your name…" : "Loading…"}</option>
              {profiles?.map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
              <option value={ADD}>+ Add a profile…</option>
            </select>
            <Ico name="chevron" className="idn-chev" />
          </span>
        </label>}
        {adding && (
          <label className="idn-field">
            <span>Your name</span>
            <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="First name" maxLength={60} autoFocus />
          </label>
        )}

        {askRole && (
          <fieldset className="idn-field">
            <legend>Role</legend>
            {(Object.keys(ROLE_LABEL) as Role[]).map((r) => (
              <label key={r} className={`idn-radio${newRole === r ? " on" : ""}`}>
                <input type="radio" name="role" value={r} checked={newRole === r} onChange={() => setNewRole(r)} />
                <span><b>{ROLE_LABEL[r]}</b></span>
              </label>
            ))}
          </fieldset>)}

        {error && <div className="idn-error">{error}</div>}
        <button type="submit" className="btn primary idn-go" disabled={!ready}>{busy ? (passwordOk ? "Saving…" : "Signing in…") : "Continue"}</button>
      </form>
    </div>
  );
}
