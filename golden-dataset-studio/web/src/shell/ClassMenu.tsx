// The class menu in the top bar, after the catalog chip (LearningProgram spec, item 11; mockup w4-class-menu): each
// class of the catalog with what it has here, then All classes. It sets the class for every tab to its right and for
// the AI button; the address bar carries it (#/c/<catalog>/<class>/<tab>).
import { useEffect, useRef, useState } from "react";
import type { CatalogDetail, ClassSummary } from "../api/types";
import { CLASS_NAME, go, href, type ClassSel, type Tab } from "./router";
import { fmt } from "./ui";

const caret = <svg viewBox="0 0 16 16" fill="none"><path d="m4 6 4 4 4-4" stroke="currentColor" strokeWidth="1.8"
  strokeLinecap="round" strokeLinejoin="round" /></svg>;
const tick = <svg viewBox="0 0 16 16" fill="none"><path d="m3.5 8.2 3 3 6-6.4" stroke="currentColor" strokeWidth="1.8"
  strokeLinecap="round" strokeLinejoin="round" /></svg>;

/** What a class has in this catalog: "43 rules, 22,023 courses", or its properties when it has no rules yet. */
export function classLine(c: ClassSummary): string {
  if (!c.ruleset_version) return `${fmt(c.properties)} properties, no rules yet`;
  const recs = c.records === null ? "" : `, ${fmt(c.records)} ${c.records === 1 ? c.noun[0] : c.noun[1]}`;
  return `${fmt(c.rules_total)} rules${recs}, ${fmt(c.rules_approved)} approved`;
}

export function ClassMenu({ catalog, cls, tab }: { catalog: CatalogDetail; cls: ClassSel; tab: Tab }) {
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
  const classes = catalog.classes ?? [];
  const pick = (c: ClassSel) => { setOpen(false); if (c !== cls) go(href(catalog.short, tab, null, {}, c)); };
  const names = classes.map((c) => c.name);
  return (
    <div className="class-menu" ref={ref}>
      <button type="button" className="chip crumb-cat crumb-class" aria-haspopup="menu" aria-expanded={open}
        data-testid="class-chip" onClick={() => setOpen((o) => !o)}
        title="The class whose rules, records, datasets and scores the tabs show">
        {CLASS_NAME[cls]}{caret}</button>
      {open && (
        <div className="menu" role="menu">
          {classes.map((c) => (
            <button key={c.slug} role="menuitem" className={c.slug === cls ? "on" : ""} onClick={() => pick(c.slug)}>
              {c.slug === cls ? tick : <i />}{c.name}<span>{classLine(c)}</span></button>
          ))}
          <div className="menu-sep" />
          <button role="menuitem" className={cls === "all" ? "on" : ""} onClick={() => pick("all")}>
            {cls === "all" ? tick : <i />}All classes
            <span>{names.length === 2 ? "Both classes'" : "Every class's"} rules in one list</span></button>
        </div>
      )}
    </div>
  );
}
