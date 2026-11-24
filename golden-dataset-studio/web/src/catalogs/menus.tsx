// The home page's menus (LearningProgram spec §2, mockups w2-home-classes-menu, w4-scores-props-menu): Catalogs (all,
// or one), Classes (any of them, ticked), Properties (listed under their class; ticking a class ticks all its
// properties). Each is a chip, "Classes  Course, LearningProgram ⌄", that opens a small panel. The address keeps
// what they pick (`homeState`).
import { useEffect, useRef, useState, type ReactNode } from "react";
import { CLASS_NAME, CLASS_SLUGS, type ClassSlug } from "../shell/router";

const caret = <svg viewBox="0 0 16 16" fill="none" width="14" height="14"><path d="m4 6 4 4 4-4" stroke="currentColor"
  strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>;

/** A chip that opens a panel below it; Escape or a click elsewhere closes it. */
export function Dropdown({ label, value, testid, children, wide }: {
  label: string; value: ReactNode; testid: string; children: (close: () => void) => ReactNode; wide?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("mousedown", away);
    window.addEventListener("keydown", esc);
    return () => { window.removeEventListener("mousedown", away); window.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div className="hm-dd" ref={ref}>
      <button type="button" className="hm-chip" aria-haspopup="menu" aria-expanded={open} data-testid={testid}
        onClick={() => setOpen((o) => !o)}><span className="hm-l">{label}</span><span className="hm-v">{value}</span>{caret}</button>
      {open && <div className={`hm-pop${wide ? " wide" : ""}`} role="menu">{children(() => setOpen(false))}</div>}
    </div>
  );
}

export interface ClassInfo { slug: ClassSlug; properties: number; catalogs: number }

/** Classes: any of them; at least one stays ticked. */
export function ClassesMenu({ picked, info, onChange, note }: {
  picked: ClassSlug[]; info: Partial<Record<ClassSlug, ClassInfo>>; onChange: (c: ClassSlug[]) => void; note: string;
}) {
  const value = picked.length === CLASS_SLUGS.length && picked.length > 2 ? "All classes" : picked.map((c) => CLASS_NAME[c]).join(", ");
  const toggle = (c: ClassSlug) => {
    const next = picked.includes(c) ? picked.filter((x) => x !== c) : CLASS_SLUGS.filter((x) => x === c || picked.includes(x));
    if (next.length) onChange(next);
  };
  return (
    <Dropdown label="Classes" value={value} testid="classes-menu">{() => <>
      {CLASS_SLUGS.map((c) => {
        const i = info[c];
        return (
          <label key={c} className="hm-opt">
            <input type="checkbox" checked={picked.includes(c)} onChange={() => toggle(c)} />
            <span className="hm-n">{CLASS_NAME[c]}</span>
            <span className="hm-s">{i ? `${i.properties} properties, ${i.catalogs} catalog${i.catalogs === 1 ? "" : "s"}` : ""}</span>
          </label>);
      })}
      <div className="hm-foot">{note}</div>
    </>}</Dropdown>
  );
}

/** Catalogs: all, or one. */
export function CatalogsMenu({ picked, catalogs, onChange }: {
  picked: string | null; catalogs: { short: string; name: string }[]; onChange: (c: string | null) => void;
}) {
  const name = catalogs.find((c) => c.short === picked)?.name;
  return (
    <Dropdown label="Catalogs" value={name ?? "All catalogs"} testid="catalogs-menu">{(close) => <>
      {[{ short: null as string | null, name: "All catalogs" }, ...catalogs].map((c) => (
        <button key={c.short ?? "all"} type="button" role="menuitemradio" aria-checked={c.short === picked}
          className={`hm-opt${c.short === picked ? " on" : ""}`} onClick={() => { close(); onChange(c.short); }}>
          <span className="hm-n">{c.name}</span></button>
      ))}
    </>}</Dropdown>
  );
}

export interface PropOption { cls: ClassSlug; column: string; name: string }

/** Properties: under their class, with a search; ticking a class ticks (or unticks) all its properties. `picked`
 * holds `class:column` keys, null for every property. */
export function PropertiesMenu({ classes, options, picked, onChange }: {
  classes: ClassSlug[]; options: PropOption[]; picked: Set<string> | null; onChange: (p: Set<string> | null) => void;
}) {
  const [q, setQ] = useState("");
  const [more, setMore] = useState<Set<ClassSlug>>(new Set());
  const all = options.filter((o) => classes.includes(o.cls));
  const on = (o: PropOption) => !picked || picked.has(`${o.cls}:${o.column}`);
  const ticked = all.filter(on);
  const set = (keys: Set<string>) => onChange(keys.size === all.length ? null : keys);
  const keysOf = (xs: PropOption[]) => new Set(xs.map((o) => `${o.cls}:${o.column}`));
  const value = ticked.length === all.length ? "All properties"
    : ticked.length === 1 ? `${classes.length > 1 ? `${CLASS_NAME[ticked[0].cls]} › ` : ""}${ticked[0].name}`
      : `${ticked.length} properties`;
  const words = q.trim().toLowerCase();
  return (
    <Dropdown label="Properties" value={value} testid="properties-menu" wide>{() => <>
      <input className="hm-find" placeholder="Find a property" value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
      {classes.map((cls) => {
        const mine = all.filter((o) => o.cls === cls);
        const shown = mine.filter((o) => !words || o.name.toLowerCase().includes(words));
        const n = mine.filter(on).length;
        const cut = words || more.has(cls) ? shown : shown.slice(0, 4);
        return (
          <div key={cls} className="hm-group" data-class={cls}>
            <label className="hm-opt head">
              <input type="checkbox" checked={n === mine.length} ref={(el) => { if (el) el.indeterminate = n > 0 && n < mine.length; }}
                onChange={() => {
                  const keys = keysOf(ticked);
                  for (const o of mine) { if (n === mine.length) keys.delete(`${o.cls}:${o.column}`); else keys.add(`${o.cls}:${o.column}`); }
                  if (keys.size) set(keys);
                }} />
              <span className="hm-n">{CLASS_NAME[cls]}</span><span className="hm-s">{mine.length} properties</span>
            </label>
            {cut.map((o) => (
              <label key={o.column} className="hm-opt sub">
                <input type="checkbox" checked={on(o)} onChange={() => {
                  const keys = keysOf(ticked), k = `${o.cls}:${o.column}`;
                  if (keys.has(k)) keys.delete(k); else keys.add(k);
                  if (keys.size) set(keys);
                }} />
                <span className="hm-n mono">{o.name}</span>
              </label>
            ))}
            {cut.length < shown.length && <button type="button" className="hm-more"
              onClick={() => setMore((m) => new Set([...m, cls]))}>+ {shown.length - cut.length} more</button>}
          </div>
        );
      })}
    </>}</Dropdown>
  );
}
