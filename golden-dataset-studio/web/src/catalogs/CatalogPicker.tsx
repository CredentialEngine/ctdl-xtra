// Catalog picker (spec §7.1, screen 01): one card per catalog, logo, name, pages saved, approved-rules bar.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CatalogCard } from "../api/types";
import { href } from "../shell/router";
import { fmt } from "../shell/ui";
import { LoopModal, shouldShowLoop } from "./LoopModal";

export default function CatalogPicker() {
  const [cats, setCats] = useState<CatalogCard[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loop, setLoop] = useState(shouldShowLoop);
  useEffect(() => { api.catalogs().then(setCats, (e) => setError(String(e))); }, []);
  const modal = loop && <LoopModal onClose={() => setLoop(false)} />;
  if (error) return <div className="picker"><div className="picker-in"><p className="muted">{error}</p></div>{modal}</div>;
  if (!cats) return <div className="picker"><div className="picker-in"><h1>Choose a catalog</h1></div>{modal}</div>;
  return (
    <div className="picker">
      <div className="picker-in">
        <h1>Choose a catalog</h1>
        <div className="cat-grid">
          {cats.map((c) => {
            const ready = c.status === "ready";
            const pct = ready && c.rules_total ? Math.round((100 * c.rules_approved) / c.rules_total) : 0;
            const body = (
              <>
                <div className="cat-logo">{c.logo && <img src={c.logo} alt={`${c.name} logo`} />}</div>
                <div className="cat-main">
                  <div className="cat-row1"><span className="nm">{c.name}</span>
                    <span className="pages">{c.pages != null ? `${fmt(c.pages)} pages saved` : "pages not indexed"}</span></div>
                  <div className="cat-row2"><div className="bar"><i style={{ width: `${pct}%` }} /></div>
                    <span className="bar-t">{ready ? `${c.rules_approved} of ${c.rules_total} rules approved` : "rules not run yet"}</span></div>
                </div>
                <span className="open">{ready ? "Open →" : ""}</span>
              </>
            );
            return ready
              ? <a key={c.catalog} className="cat ready" href={href(c.short, "rules")}>{body}</a>
              : <div key={c.catalog} className="cat off">{body}</div>;
          })}
        </div>
        <button className="loop-again" onClick={() => setLoop(true)}>How the Studio works</button>
      </div>
      {modal}
    </div>
  );
}
