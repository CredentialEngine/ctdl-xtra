// Top bar on every screen (spec §7): Studio name, catalog, crawl date, ruleset version, the five tabs,
// the reviewer's first name (picked once on the "Who are you?" screen; role on hover) and "Show the tour".
import type { CatalogDetail } from "../api/types";
import { ROLE_LABEL, useReviewer, useRole } from "./reviewer";
import { href, TAB_LABEL, TABS, type Tab } from "./router";
import { fmtDate } from "./ui";

export function TopBar({ catalog, tab, onTour }: { catalog: CatalogDetail | null; tab: Tab | null; onTour?: () => void }) {
  const me = useReviewer();
  const role = useRole();
  return (
    <header className="topbar">
      <a className="brand" href="#/">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M12 2.5 21 7l-9 4.5L3 7l9-4.5Z" fill="#c9a227" />
          <path d="m3 12 9 4.5 9-4.5" stroke="#8a6d12" strokeWidth="1.8" strokeLinejoin="round" />
          <path d="m3 16.5 9 4.5 9-4.5" stroke="#8a6d12" strokeWidth="1.8" strokeLinejoin="round" opacity=".55" />
        </svg>
        <span className="brand-name">Golden Dataset Studio</span>
      </a>
      <nav className="crumbs" data-tour="crumbs">
        {catalog && (
          <>
            <span className="sep">/</span>
            <a href="#/" className="chip crumb-cat" style={{ textDecoration: "none" }}
              title={`pages from ${fmtDate(catalog.crawl)} · latest ruleset v${catalog.ruleset_version}`}>
              {catalog.logo && <img src={catalog.logo} alt="" />}{catalog.name}
            </a>
          </>
        )}
      </nav>
      <nav className="tabs" data-tour="tabs">
        {catalog && TABS.map((t) => (
          <a key={t} href={href(catalog.short, t)} className={t === tab ? "on" : ""} data-tab={t}>
            {TAB_LABEL[t]}
          </a>
        ))}
      </nav>
      <div className="who">
        {me && <span className="who-l" title={role ? `${me} · ${ROLE_LABEL[role]}` : me}>
          <span className="who-name">{me.split(" ")[0]}</span></span>}
        {catalog && onTour && <button className="btn tour-btn" onClick={onTour} data-tour="tour-button">Show the tour</button>}
      </div>
    </header>
  );
}
