import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api } from "./api/client";
import type { CatalogDetail } from "./api/types";
import CatalogPicker from "./catalogs/CatalogPicker";
import CompareTab from "./compare/CompareTab";
import GoldenTab from "./golden/GoldenTab";
import PromptTab from "./prompt/PromptTab";
import RecordsTab from "./records/RecordsTab";
import RulesTab from "./rules/RulesTab";
import { useRoute } from "./shell/router";
import { TopBar } from "./shell/TopBar";
import { ThemeButton } from "./shell/theme";
import { StorageFiles } from "./files/StorageFiles";
import { Ico, KeysContext } from "./shell/ui";
import { Tour, useTour } from "./tour";
import "./styles.css";
import "./shell/dark.css";

export default function App() {
  const route = useRoute();
  const [catalog, setCatalog] = useState<CatalogDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [keys, setKeys] = useState<ReactNode>(null);
  const load = useCallback(() => {
    if (!route.catalog) { setCatalog(null); return; }
    api.catalog(route.catalog).then((c) => { setCatalog(c); setError(null); }, (e) => setError(String(e)));
  }, [route.catalog]);
  useEffect(load, [load]);
  const tour = useTour(catalog);
  const [files, setFiles] = useState(false);

  let body: ReactNode;
  if (!route.catalog) body = <CatalogPicker />;
  else if (error) body = <div className="placeholder muted" style={{ padding: 24 }}>{error}</div>;
  else if (!catalog || catalog.short !== route.catalog && catalog.catalog !== route.catalog) body = null;
  else {
    const props = { catalog, route, reload: load };
    body = { rules: <RulesTab {...props} />, records: <RecordsTab {...props} />, compare: <CompareTab {...props} />,
             prompt: <PromptTab {...props} />, publish: <GoldenTab {...props} /> }[route.tab];
  }
  return (
    <KeysContext.Provider value={setKeys}>
      <TopBar catalog={route.catalog ? catalog : null} tab={route.catalog ? route.tab : null} onTour={tour.open} />
      <main id="app">{body}</main>
      <footer className="keys"><span className="keys-hints">{keys}</span>
        {catalog && <button className="files-btn" onClick={() => setFiles(true)}
          title="Browse the files the Studio keeps for this catalog on its storage root (read-only, for debugging)">
          <Ico name="folder" />Storage files</button>}
        <ThemeButton /></footer>
      {catalog && <Tour {...tour} catalog={catalog} />}
      {catalog && files && <StorageFiles catalog={catalog.short} onClose={() => setFiles(false)} />}
    </KeysContext.Provider>
  );
}
