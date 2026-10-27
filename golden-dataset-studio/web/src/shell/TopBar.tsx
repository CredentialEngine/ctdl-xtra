// Top bar on every screen (spec §7): Studio name, catalog, crawl date, ruleset version, the five tabs,
// "Reviewing as [name ▾]" and "Show the tour".
import type { CatalogDetail } from "../api/types";
import { reviewerNames, setReviewer, useReviewer } from "./reviewer";
import { href, TABS, type Tab } from "./router";
import { fmtDate } from "./ui";

export function TopBar({ catalog, tab, onTour }: { catalog: CatalogDetail | null; tab: Tab | null; onTour?: () => void }) {
  const me = useReviewer();
  const names = reviewerNames();
  return (
    <header className="topbar">
      <a className="brand" href="#/">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M12 2.5 21 7l-9 4.5L3 7l9-4.5Z" fill="#c9a227" />
          <path d="m3 12 9 4.5 9-4.5" stroke="#8a6d12" strokeWidth="1.8" strokeLinejoin="round" />
          <path d="m3 16.5 9 4.5 9-4.5" stroke="#8a6d12" strokeWidth="1.8" strokeLinejoin="round" opacity=".55" />
        </svg>
        <span className="brand-name">Golden Dataset Studio</span><span className="brand-tag">CTDL</span>
      </a>
      <nav className="crumbs" data-tour="crumbs">
        {catalog && (
          <>
            <span className="sep">/</span>
            <a href="#/" className="chip crumb-cat" style={{ textDecoration: "none" }}>
              {catalog.logo && <img src={catalog.logo} alt="" />}{catalog.name}
            </a>
            <span className="muted">pages saved {fmtDate(catalog.crawl)}</span>
            <span className="muted" title={`extraction ${catalog.extraction}`}>· ruleset v{catalog.ruleset_version}</span>
          </>
        )}
      </nav>
      <nav className="tabs" data-tour="tabs">
        {catalog && TABS.map((t) => (
          <a key={t} href={href(catalog.short, t)} className={t === tab ? "on" : ""} data-tab={t}>
            {t[0].toUpperCase() + t.slice(1)}
          </a>
        ))}
      </nav>
      <div className="who">
        <label className="who-l">Reviewing as{" "}
          <select value={me} onChange={(e) => {
            if (e.target.value === "__add") {
              const n = (window.prompt("Name of the reviewer") || "").trim();
              if (n) setReviewer(n);
            } else setReviewer(e.target.value);
          }}>
            {names.map((n) => <option key={n} value={n}>{n}</option>)}
            <option value="__add">Add a name…</option>
          </select>
        </label>
        {catalog && onTour && <button className="btn tour-btn" onClick={onTour} data-tour="tour-button">Show the tour</button>}
      </div>
    </header>
  );
}
