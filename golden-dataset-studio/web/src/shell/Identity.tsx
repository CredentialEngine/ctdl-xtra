// Sign-in: first the shared password (when the server has one and this browser isn't signed in), then "Who are
// you?", which profile you are. A new profile also gets a role; existing ones keep theirs. The profile is remembered in this browser and
// every annotation is recorded under that name.
import { useEffect, useState } from "react";
import { Ico } from "./icons";
import { currentReviewer, ROLE_LABEL, setIdentity, type Profile, type Role } from "./reviewer";
import { signIn } from "./session";
import "./identity.css";

const ADD = "__add";

type Inputs = ReturnType<typeof useInputs>;
type Form = ReturnType<typeof useIdentityForm>;
type FormState = Omit<Form, "submit">;

export function IdentityScreen({ needPassword }: { needPassword: boolean }) {
  const form = useIdentityForm(needPassword);
  return (
    <div className="idn-bg">
      <form className="idn" onSubmit={(e) => { e.preventDefault(); void form.submit(); }}>
        <IdentityBrand />
        <h1>{form.passwordOk ? "Who are you?" : "Sign in"}</h1>
        <IdentityFields form={form} />
        {form.error && <div className="idn-error">{form.error}</div>}
        <button type="submit" className="btn primary idn-go" disabled={!form.ready}>{form.busy ? (form.passwordOk ? "Saving…" : "Signing in…") : "Continue"}</button>
      </form>
    </div>
  );
}

function IdentityFields({ form }: { form: Form }) {
  return (<>
    {!form.passwordOk && <PasswordField form={form} />}
    {form.passwordOk && <ProfileField form={form} />}
    {form.adding && <NameField form={form} />}
    {form.askRole && <RoleField form={form} />}
  </>);
}

function IdentityBrand() {
  return (
    <div className="idn-brand">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M12 2.5 21 7l-9 4.5L3 7l9-4.5Z" fill="#c9a227" />
        <path d="m3 12 9 4.5 9-4.5" stroke="#8a6d12" strokeWidth="1.8" strokeLinejoin="round" />
        <path d="m3 16.5 9 4.5 9-4.5" stroke="#8a6d12" strokeWidth="1.8" strokeLinejoin="round" opacity=".55" />
      </svg>
      <span>Golden Dataset Studio</span>
    </div>
  );
}

function PasswordField({ form }: { form: Form }) {
  return (
    <label className="idn-field">
      <span>Password</span>
      <input type="password" value={form.password} onChange={(e) => form.setPassword(e.target.value)}
             autoComplete="current-password" autoFocus />
    </label>
  );
}

function ProfileField({ form }: { form: Form }) {
  return (
    <label className="idn-field">
      <span>Profile</span>
      <span className="idn-sel">
        <select value={form.pick} onChange={(e) => form.setPick(e.target.value)} disabled={!form.profiles} autoFocus>
          <option value="" disabled>{form.profiles ? "Choose your name…" : "Loading…"}</option>
          {form.profiles?.map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
          <option value={ADD}>+ Add a profile…</option>
        </select>
        <Ico name="chevron" className="idn-chev" />
      </span>
    </label>
  );
}

function NameField({ form }: { form: Form }) {
  return (
    <label className="idn-field">
      <span>Your name</span>
      <input value={form.newName} onChange={(e) => form.setNewName(e.target.value)} placeholder="First name" maxLength={60} autoFocus />
    </label>
  );
}

function RoleField({ form }: { form: Form }) {
  return (
    <fieldset className="idn-field">
      <legend>Role</legend>
      {(Object.keys(ROLE_LABEL) as Role[]).map((r) => (
        <label key={r} className={`idn-radio${form.newRole === r ? " on" : ""}`}>
          <input type="radio" name="role" value={r} checked={form.newRole === r} onChange={() => form.setNewRole(r)} />
          <span><b>{ROLE_LABEL[r]}</b></span>
        </label>
      ))}
    </fieldset>
  );
}

function useIdentityForm(needPassword: boolean) {
  const [passwordOk, setPasswordOk] = useState(!needPassword);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputs = useInputs();
  const profiles = useProfiles(passwordOk, inputs.setPick, setError);
  const choice = chooseIdentity(inputs, profiles, passwordOk, busy);
  const form = { ...inputs, ...choice, profiles, passwordOk, setPasswordOk, error, setError, busy, setBusy };
  return { ...form, submit: () => submitIdentity(form) };
}

function useInputs() {
  const [password, setPassword] = useState("");
  const [pick, setPick] = useState(currentReviewer());
  const [newName, setNewName] = useState("");
  const [newRole, setNewRole] = useState<Role | null>(null);
  return { password, setPassword, pick, setPick, newName, setNewName, newRole, setNewRole };
}

function useProfiles(passwordOk: boolean, setPick: (name: string) => void, setError: (e: string) => void): Profile[] | null {
  const [profiles, setProfiles] = useState<Profile[] | null>(null);
  useEffect(() => {
    if (!passwordOk) return;
    fetch("/api/profiles").then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then((d: { profiles: Profile[] }) => {
        setProfiles(d.profiles);
        if (!d.profiles.some((p) => p.name === currentReviewer())) setPick("");
      }, (e: Error) => setError(`Couldn't load the profiles (${e.message}).`));
  }, [passwordOk, setPick, setError]);
  return profiles;
}

function chooseIdentity({ pick, newName, newRole, password }: Inputs, profiles: Profile[] | null, passwordOk: boolean,
                        busy: boolean) {
  const adding = pick === ADD;
  const picked = adding ? null : profiles?.find((x) => x.name === pick) ?? null;
  const askRole = adding || (!!picked && !picked.role);  // a new profile, or an old one saved without a role
  const role = askRole ? newRole : picked?.role ?? null;
  const name = (adding ? newName : pick).trim().replace(/\s+/g, " ");
  const ready = !passwordOk ? !!password && !busy : !!name && !!role && !busy;
  return { adding, askRole, role, name, ready };
}

async function submitIdentity(form: FormState): Promise<void> {
  if (!form.ready) return;
  if (!form.passwordOk) return signInWithPassword(form);
  if (!form.role) return;
  if (!form.askRole) { setIdentity(form.name, form.role); return; }
  await saveNewProfile(form, form.role);
}

async function signInWithPassword(form: FormState): Promise<void> {
  form.setBusy(true);
  try {
    await signIn(form.password);  // a browser that already knows its profile goes straight in (App.tsx)
    form.setError(null);
    form.setPasswordOk(true);
  } catch (e) { form.setError(e instanceof Error ? e.message : String(e)); }
  form.setBusy(false);
}

async function saveNewProfile(form: FormState, role: Role): Promise<void> {
  form.setBusy(true);
  try {
    const r = await fetch("/api/profiles", { method: "POST", headers: { "Content-Type": "application/json" },
                                             body: JSON.stringify({ name: form.name, role }) });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? r.statusText);
    const d = await r.json() as { profile: Profile };
    setIdentity(d.profile.name, role);
  } catch (e) { form.setError(String(e)); form.setBusy(false); }
}
