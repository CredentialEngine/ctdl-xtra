// "Who are you?": looks like a sign-in screen, but it only asks which profile you are and your role. There is no
// password; the choice is remembered in this browser and every annotation is recorded under that name.
import { useEffect, useState } from "react";
import { currentReviewer, currentRole, ROLE_LABEL, setIdentity, type Profile, type Role } from "./reviewer";
import "./identity.css";

const ADD = "__add";

export function IdentityScreen() {
  const [profiles, setProfiles] = useState<Profile[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pick, setPick] = useState(currentReviewer());
  const [newName, setNewName] = useState("");
  const [role, setRole] = useState<Role | null>(currentRole());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch("/api/profiles").then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then((d: { profiles: Profile[] }) => {
        setProfiles(d.profiles);
        if (!d.profiles.some((p) => p.name === currentReviewer())) setPick("");
      }, (e: Error) => setError(`Couldn't load the profiles (${e.message}).`));
  }, []);

  const choose = (name: string) => {
    setPick(name);
    const p = profiles?.find((x) => x.name === name);
    if (p?.role) setRole(p.role);
  };
  const adding = pick === ADD;
  const name = (adding ? newName : pick).trim().replace(/\s+/g, " ");
  const ready = !!name && !!role && !busy;

  const go = async () => {
    if (!ready || !role) return;
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
        <h1>Who are you?</h1>
        <p className="idn-lead">Your name goes on every verdict and comment you leave, so teammates know who to ask.
          This browser remembers it.</p>

        <label className="idn-field">
          <span>Profile</span>
          <select value={pick} onChange={(e) => choose(e.target.value)} disabled={!profiles} autoFocus>
            <option value="" disabled>{profiles ? "Choose your name…" : "Loading…"}</option>
            {profiles?.map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
            <option value={ADD}>+ Add a profile…</option>
          </select>
        </label>
        {adding && (
          <label className="idn-field">
            <span>Your name</span>
            <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="First name" maxLength={60} autoFocus />
          </label>
        )}

        <fieldset className="idn-field">
          <legend>Your role</legend>
          {(Object.keys(ROLE_LABEL) as Role[]).map((r) => (
            <label key={r} className={`idn-radio${role === r ? " on" : ""}`}>
              <input type="radio" name="role" value={r} checked={role === r} onChange={() => setRole(r)} />
              <span><b>{ROLE_LABEL[r]}</b>
                <small>{r === "sme" ? "You know what the catalog means: you judge whether values are right."
                                    : "You build the rules: you fix them when values are wrong."}</small></span>
            </label>
          ))}
        </fieldset>

        {error && <div className="idn-error">{error}</div>}
        <button type="submit" className="btn primary idn-go" disabled={!ready}>{busy ? "Saving…" : "Continue"}</button>
        <p className="idn-foot">No password: anyone can pick any profile. Switch later from the top bar.</p>
      </form>
    </div>
  );
}
