// The home page's menus (LearningProgram spec §2, mockups w2-home-classes-menu, w4-scores-props-menu): Catalogs (all,
// or one), Classes (any of them, ticked), Properties (listed under their class; ticking a class ticks all its
// properties). Each is a chip, "Classes  Course, LearningProgram ⌄", that opens a small panel. The address keeps
// what they pick (`homeState`).
import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { CLASS_NAME, CLASS_SLUGS, type ClassSlug } from "../shell/router";

const caret = <svg viewBox="0 0 16 16" fill="none" width="14" height="14"><path d="m4 6 4 4 4-4" stroke="currentColor"
  strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>;

type PropertyMenu = ReturnType<typeof propertyMenu>;

/** A chip that opens a panel below it; Escape or a click elsewhere closes it. */
export function Dropdown({ label, value, testid, children, wide }: {
  label: string; value: ReactNode; testid: string; children: (close: () => void) => ReactNode; wide?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useCloseWhenAway(open, ref, setOpen);
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
  const toggle = (c: ClassSlug) => {
    const next = toggleClass(picked, c);
    if (next.length) onChange(next);
  };
  return (
    <Dropdown label="Classes" value={classesLabel(picked)} testid="classes-menu">{() => <>
      {CLASS_SLUGS.map((c) => <ClassOption key={c} cls={c} info={info[c]} checked={picked.includes(c)} onToggle={() => toggle(c)} />)}
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
  const menu = propertyMenu(classes, options, picked, onChange);
  const words = q.trim().toLowerCase();
  return (
    <Dropdown label="Properties" value={propertiesLabel(menu, classes)} testid="properties-menu" wide>{() => <>
      <input className="hm-find" placeholder="Find a property" value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
      {classes.map((cls) => <PropertyGroup key={cls} cls={cls} menu={menu} words={words} expanded={more.has(cls)}
        onMore={() => setMore((m) => new Set([...m, cls]))} />)}
    </>}</Dropdown>
  );
}

function useCloseWhenAway(open: boolean, ref: RefObject<HTMLDivElement>, setOpen: (open: boolean) => void) {
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("mousedown", away);
    window.addEventListener("keydown", esc);
    return () => { window.removeEventListener("mousedown", away); window.removeEventListener("keydown", esc); };
  }, [open, ref, setOpen]);
}

function ClassOption({ cls, info: i, checked, onToggle }: { cls: ClassSlug; info: ClassInfo | undefined; checked: boolean; onToggle: () => void }) {
  return (
    <label className="hm-opt">
      <input type="checkbox" checked={checked} onChange={onToggle} />
      <span className="hm-n">{CLASS_NAME[cls]}</span>
      <span className="hm-s">{i ? `${i.properties} properties, ${i.catalogs} catalog${i.catalogs === 1 ? "" : "s"}` : ""}</span>
    </label>);
}

function PropertyGroup({ cls, menu, words, expanded, onMore }: {
  cls: ClassSlug; menu: PropertyMenu; words: string; expanded: boolean; onMore: () => void;
}) {
  const mine = menu.all.filter((o) => o.cls === cls);
  const shown = mine.filter((o) => !words || o.name.toLowerCase().includes(words));
  const cut = words || expanded ? shown : shown.slice(0, 4);
  return (
    <div className="hm-group" data-class={cls}>
      <ClassToggle cls={cls} mine={mine} menu={menu} />
      {cut.map((o) => <PropertyOption key={o.column} option={o} menu={menu} />)}
      {cut.length < shown.length && <button type="button" className="hm-more"
        onClick={onMore}>+ {shown.length - cut.length} more</button>}
    </div>
  );
}

function ClassToggle({ cls, mine, menu }: { cls: ClassSlug; mine: PropOption[]; menu: PropertyMenu }) {
  const n = mine.filter(menu.on).length;
  return (
    <label className="hm-opt head">
      <input type="checkbox" checked={n === mine.length} ref={(el) => { if (el) el.indeterminate = n > 0 && n < mine.length; }}
        onChange={() => toggleClassProperties(menu, mine, n === mine.length)} />
      <span className="hm-n">{CLASS_NAME[cls]}</span><span className="hm-s">{mine.length} properties</span>
    </label>
  );
}

function PropertyOption({ option: o, menu }: { option: PropOption; menu: PropertyMenu }) {
  return (
    <label className="hm-opt sub">
      <input type="checkbox" checked={menu.on(o)} onChange={() => toggleProperty(menu, o)} />
      <span className="hm-n mono">{o.name}</span>
    </label>
  );
}

function propertyMenu(classes: ClassSlug[], options: PropOption[], picked: Set<string> | null, onChange: (p: Set<string> | null) => void) {
  const all = options.filter((o) => classes.includes(o.cls));
  const on = (o: PropOption) => !picked || picked.has(keyOf(o));
  const ticked = all.filter(on);
  const set = (keys: Set<string>) => onChange(keys.size === all.length ? null : keys);
  return { all, on, ticked, set };
}

function toggleClassProperties(menu: PropertyMenu, mine: PropOption[], allTicked: boolean): void {
  const keys = keysOf(menu.ticked);
  for (const o of mine) { if (allTicked) keys.delete(keyOf(o)); else keys.add(keyOf(o)); }
  if (keys.size) menu.set(keys);
}

function toggleProperty(menu: PropertyMenu, o: PropOption): void {
  const keys = keysOf(menu.ticked), k = keyOf(o);
  if (keys.has(k)) keys.delete(k); else keys.add(k);
  if (keys.size) menu.set(keys);
}

function toggleClass(picked: ClassSlug[], c: ClassSlug): ClassSlug[] {
  return picked.includes(c) ? picked.filter((x) => x !== c) : CLASS_SLUGS.filter((x) => x === c || picked.includes(x));
}

function classesLabel(picked: ClassSlug[]): string {
  return picked.length === CLASS_SLUGS.length && picked.length > 2 ? "All classes" : picked.map((c) => CLASS_NAME[c]).join(", ");
}

function propertiesLabel({ all, ticked }: PropertyMenu, classes: ClassSlug[]): string {
  if (ticked.length === all.length) return "All properties";
  if (ticked.length === 1) return `${classes.length > 1 ? `${CLASS_NAME[ticked[0].cls]} › ` : ""}${ticked[0].name}`;
  return `${ticked.length} properties`;
}

function keyOf(o: PropOption): string {
  return `${o.cls}:${o.column}`;
}

function keysOf(options: PropOption[]): Set<string> {
  return new Set(options.map(keyOf));
}
