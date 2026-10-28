// Catalog picker (spec §7.1, screen 01): one card per catalog, logo, name, pages saved, approved-rules bar, and
// + Add a catalog (a crawl xtra-cli has already made). A catalog being added shows its progress until it's ready.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { CatalogCard } from "../api/types";
import { href } from "../shell/router";
import { fmt } from "../shell/ui";
import { AddCatalogModal } from "./AddCatalogModal";
import { GenerateRulesModal } from "./GenerateRulesModal";
import { LoopModal, shouldShowLoop } from "./LoopModal";

const STEP: Record<string, string> = {
  starting: "Starting…", copying: "Copying pages…", indexing: "Indexing pages…", assets: "Saving page styles…",
  done: "Finishing…",
};

function addingText(c: CatalogCard): string {
  const a = c.adding;
  if (!a) return "";
  if (c.status === "failed") return "Couldn't add it";
  return a.step === "copying" && a.total ? `Copying pages… ${Math.floor((100 * a.done) / a.total)}%` : STEP[a.step] ?? "Adding…";
}

export default function CatalogPicker() {
  const [cats, setCats] = useState<CatalogCard[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loop, setLoop] = useState(shouldShowLoop);
  const [adding, setAdding] = useState(false);
  const [generate, setGenerate] = useState<CatalogCard | null>(null);
  const load = useCallback(() => api.catalogs().then(setCats, (e) => setError(String(e))), []);
  useEffect(() => { load(); }, [load]);
  // while a catalog is being added, follow its progress
  const busy = !!cats?.some((c) => c.status === "adding");
  useEffect(() => {
    if (!busy) return;
    const t = window.setInterval(load, 2000);
    return () => window.clearInterval(t);
  }, [busy, load]);

  const modal = (loop && <LoopModal onClose={() => setLoop(false)} />)
    || (adding && <AddCatalogModal onClose={() => setAdding(false)} onAdded={load} />)
    || (generate && <GenerateRulesModal card={generate} onClose={() => { setGenerate(null); load(); }} />);
  const head = (
    <div className="picker-head">
      <h1>Choose a catalog</h1>
      <button className="btn primary" onClick={() => setAdding(true)}>+ Add a catalog</button>
    </div>
  );
  if (error) return <div className="picker"><div className="picker-in">{head}<p className="muted">{error}</p></div>{modal}</div>;
  if (!cats) return <div className="picker"><div className="picker-in">{head}</div>{modal}</div>;
  return (
    <div className="picker">
      <div className="picker-in">
        {head}
        <div className="cat-grid">
          {cats.map((c) => {
            const ready = c.status === "ready";
            const inFlight = c.status === "adding" || c.status === "failed";
            const pct = ready && c.rules_total ? Math.round((100 * c.rules_approved) / c.rules_total)
              : c.adding?.step === "copying" && c.adding.total ? Math.round((100 * c.adding.done) / c.adding.total) : 0;
            const sliding = c.status === "adding" && c.adding?.step !== "copying";
            const body = (
              <>
                <div className="cat-logo">{c.logo && <img src={c.logo} alt={`${c.name} logo`} />}</div>
                <div className="cat-main">
                  <div className="cat-row1"><span className="nm">{c.name}</span>
                    <span className="pages">{c.pages != null ? `${fmt(c.pages)} pages saved` : "pages not indexed"}</span></div>
                  <div className="cat-row2"><div className={`bar ${sliding ? "sliding" : ""}`}><i style={{ width: sliding ? undefined : `${pct}%` }} /></div>
                    <span className="bar-t" title={c.adding?.error ?? undefined}>
                      {inFlight ? addingText(c) : ready ? `${c.rules_approved} of ${c.rules_total} rules approved` : "rules not run yet"}
                    </span></div>
                </div>
                <span className="open">{ready ? "Open →" : c.status === "failed"
                  ? <button className="dismiss" onClick={() => api.dismissAdd(c.catalog).then(load)}>Dismiss</button>
                  : c.status === "not imported" && c.pages
                    ? <button className="btn gen" onClick={() => setGenerate(c)}>Generate rules</button> : ""}</span>
              </>
            );
            return ready
              ? <a key={c.catalog} className="cat ready" href={href(c.short, "rules")}>{body}</a>
              : <div key={c.catalog} className={`cat off ${inFlight ? c.status : ""}`}>{body}</div>;
          })}
        </div>
        <button className="loop-again" onClick={() => setLoop(true)}>How the Studio works</button>
      </div>
      {modal}
    </div>
  );
}
