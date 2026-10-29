import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api } from "./api/client";
import type { CatalogDetail } from "./api/types";
import CatalogPicker from "./catalogs/CatalogPicker";
import CompareTab from "./compare/CompareTab";
import EvalsTab from "./evals/EvalsTab";
import GoldenTab from "./golden/GoldenTab";
import { OPEN_PROMPT, PromptModal } from "./prompt/PromptModal";
import RecordsTab from "./records/RecordsTab";
import RulesTab from "./rules/RulesTab";
import { useRoute } from "./shell/router";
import { IdentityScreen } from "./shell/Identity";
import { useHasIdentity } from "./shell/reviewer";
import { useSession } from "./shell/session";
import { TopBar } from "./shell/TopBar";
import { ThemeButton } from "./shell/theme";
import { StorageFiles } from "./files/StorageFiles";
import { Ico, KeysContext } from "./shell/ui";
import { Tour, useTour } from "./tour";
import { AgentProvider } from "./agent/state";
import { RunBar } from "./agent/RunBar";
import { RunsPanel } from "./agent/RunsPanel";
import { OPEN_RUNS } from "./agent/api";
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
  const session = useSession();
  const signedIn = !!session?.signed_in;
  useEffect(() => { if (signedIn) load(); }, [load, signedIn]);
  const tour = useTour(catalog);
  const [files, setFiles] = useState(false);
  // Past AI runs: undefined = closed, null = the list, a run id = that run
  const [runsOpen, setRunsOpen] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    const on = (e: Event) => setRunsOpen((e as CustomEvent<string | null>).detail ?? null);
    window.addEventListener(OPEN_RUNS, on);
    return () => window.removeEventListener(OPEN_RUNS, on);
  }, []);
  // the prompt modal: undefined = closed, otherwise the "couldn't connect" warning (null = none)
  const [promptOpen, setPromptOpen] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    const on = (e: Event) => setPromptOpen((e as CustomEvent<{ warning: string | null }>).detail.warning);
    window.addEventListener(OPEN_PROMPT, on);
    return () => window.removeEventListener(OPEN_PROMPT, on);
  }, []);
  useEffect(() => {  // an old #/c/<catalog>/prompt link (or ?prompt=1): open the modal, then drop the parameter
    if (!route.params.get("prompt")) return;
    setPromptOpen(route.params.get("k2err"));
    const rest = new URLSearchParams(route.params);
    rest.delete("prompt");
    rest.delete("k2err");
    history.replaceState(null, "", location.hash.split("?")[0] + (rest.toString() ? `?${rest}` : ""));
  }, [route.params]);
  const known = useHasIdentity();
  if (!session) return null;
  if (!known || !signedIn) return <IdentityScreen needPassword={!signedIn} />;

  let body: ReactNode;
  if (!route.catalog) body = <CatalogPicker />;
  else if (error) body = <div className="placeholder muted" style={{ padding: 24 }}>{error}</div>;
  else if (!catalog || catalog.short !== route.catalog && catalog.catalog !== route.catalog) body = null;
  else {
    const props = { catalog, route, reload: load };
    body = { rules: <RulesTab {...props} />, records: <RecordsTab {...props} />, compare: <CompareTab {...props} />,
             golden: <GoldenTab {...props} />, evals: <EvalsTab {...props} /> }[route.tab];
  }
  return (
    <KeysContext.Provider value={setKeys}>
    <AgentProvider catalog={route.catalog && catalog ? catalog.short : null}>
      <TopBar catalog={route.catalog ? catalog : null} tab={route.catalog ? route.tab : null} onTour={tour.open} />
      {route.catalog && catalog && <RunBar catalog={catalog.short} />}
      <main id="app">{body}</main>
      <footer className="keys"><span className="keys-hints">{keys}</span>
        {catalog && <button className="files-btn" onClick={() => setFiles(true)}
          title="Browse the files the Studio keeps for this catalog on its storage root (read-only, for debugging)">
          <Ico name="folder" />Storage files</button>}
        {catalog && <button className="files-btn" onClick={() => setRunsOpen(null)} data-testid="past-runs"
          title="Every run of Claude on this catalog: outcome, Claude's report, progress notes and the prompt it was given">
          <Ico name="spark" />Past AI runs</button>}
        <ThemeButton /></footer>
      {catalog && <Tour {...tour} catalog={catalog} />}
      {catalog && files && <StorageFiles catalog={catalog.short} onClose={() => setFiles(false)} />}
      {catalog && runsOpen !== undefined && <RunsPanel catalog={catalog.short} initial={runsOpen} onClose={() => setRunsOpen(undefined)} />}
      {catalog && promptOpen !== undefined && <PromptModal catalog={catalog.catalog} short={catalog.short}
        version={catalog.ruleset_version} warning={promptOpen} onClose={() => setPromptOpen(undefined)} />}
    </AgentProvider>
    </KeysContext.Provider>
  );
}
