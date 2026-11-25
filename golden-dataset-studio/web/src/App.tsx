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
import { useRoute, type ClassSlug, type Route } from "./shell/router";
import { apiClass } from "./shell/klass";
import { IdentityScreen } from "./shell/Identity";
import { useHasIdentity } from "./shell/reviewer";
import { useSession, type Session } from "./shell/session";
import { TopBar } from "./shell/TopBar";
import { ThemeButton } from "./shell/theme";
import { StorageFiles } from "./files/StorageFiles";
import { Ico, KeysContext, useWindowEvent } from "./shell/ui";
import { Tour, useTour } from "./tour";
import { AgentProvider } from "./agent/state";
import { RunBar } from "./agent/RunBar";
import { RunsPanel } from "./agent/RunsPanel";
import { CATALOG_CHANGED, OPEN_RUNS, type OpenRuns } from "./agent/api";
import { RunDialogHost } from "./agent/RunDialog";
import { pageInfo, pageView } from "./telemetry";
import "./styles.css";
import "./shell/dark.css";

type RunsRule = { id: string; name: string | null };
type RunsPanelState = ReturnType<typeof useRunsPanel>;
type PromptModalState = ReturnType<typeof usePromptModal>;
interface StudioProps {
  route: Route; catalog: CatalogDetail | null; error: string | null; reload: () => void;
  tour: ReturnType<typeof useTour>; runs: RunsPanelState; prompt: PromptModalState;
}

export default function App() {
  const route = useRoute();
  const session = useSession();
  const signedIn = !!session?.signed_in;
  const { catalog, error, reload } = useOpenCatalog(route, signedIn);
  const tour = useTour(catalog);
  const runs = useRunsPanel(route.params);
  const prompt = usePromptModal(route.params);
  const known = useHasIdentity();
  useRecordPageView(session, signedIn, known, route);
  if (!session) return null;
  if (!known || !signedIn) return <IdentityScreen needPassword={!signedIn} />;
  return <Studio route={route} catalog={catalog} error={error} reload={reload} tour={tour} runs={runs} prompt={prompt} />;
}

function Studio(props: StudioProps) {
  const { route, catalog } = props;
  const [keys, setKeys] = useState<ReactNode>(null);
  const [files, setFiles] = useState(false);
  return (
    <KeysContext.Provider value={setKeys}>
    <AgentProvider catalog={route.catalog && catalog ? catalog.short : null} classes={agentClasses(route, catalog)}>
      <Header {...props} />
      <main id="app"><TabBody {...props} /></main>
      <Footer keys={keys} catalog={catalog} onFiles={() => setFiles(true)} onRuns={props.runs.showList} />
      {catalog && <Overlays {...props} catalog={catalog} files={files} onCloseFiles={() => setFiles(false)} />}
    </AgentProvider>
    </KeysContext.Provider>
  );
}

function Header({ route, catalog, tour }: StudioProps) {
  return (<>
    <TopBar catalog={route.catalog ? catalog : null} tab={route.catalog ? route.tab : null} cls={route.cls} onTour={tour.open} />
    {route.catalog && catalog && <RunBar catalog={catalog.short} />}
  </>);
}

function TabBody({ route, catalog, error, reload }: StudioProps): ReactNode {
  if (!route.catalog) return <CatalogPicker />;
  if (error) return <div className="placeholder muted" style={{ padding: 24 }}>{error}</div>;
  if (!catalog || catalog.short !== route.catalog && catalog.catalog !== route.catalog) return null;
  if (!catalog.extraction && route.cls !== "all") return <EmptyClass catalog={catalog} />;
  if (route.cls === "all" && route.tab === "compare") return <CompareOneClass />;
  const props = { catalog, route, reload };
  return { rules: <RulesTab {...props} />, records: <RecordsTab {...props} />, compare: <CompareTab {...props} />,
           datasets: <GoldenTab {...props} />, evals: <EvalsTab {...props} /> }[route.tab];
}

function Footer({ keys, catalog, onFiles, onRuns }: {
  keys: ReactNode; catalog: CatalogDetail | null; onFiles: () => void; onRuns: () => void;
}) {
  return (
    <footer className="keys"><span className="keys-hints">{keys}</span>
      {catalog && <button className="files-btn" onClick={onFiles}
        title="Browse the files the Studio keeps for this catalog on its storage root (read-only, for debugging)">
        <Ico name="folder" />Storage files</button>}
      {catalog && <button className="files-btn" onClick={onRuns} data-testid="past-runs"
        title="Every run of Claude on this catalog: outcome, Claude's report, progress notes and the prompt it was given">
        <Ico name="spark" />Past AI runs</button>}
      <ThemeButton /></footer>
  );
}

function Overlays({ catalog, tour, runs, prompt, files, onCloseFiles }: StudioProps & {
  catalog: CatalogDetail; files: boolean; onCloseFiles: () => void;
}) {
  return (<>
    <Tour {...tour} catalog={catalog} />
    {files && <StorageFiles catalog={catalog.short} onClose={onCloseFiles} />}
    {runs.open !== undefined && <RunsPanel key={`${runs.rule?.id ?? ""}|${runs.open ?? ""}`} catalog={catalog.short} initial={runs.open}
      rule={runs.rule?.id ?? null} ruleName={runs.rule?.name ?? null} onClose={runs.close} />}
    <RunDialogHost catalog={catalog.short} />
    {prompt.warning !== undefined && <PromptModal catalog={catalog.catalog} short={catalog.short}
      version={catalog.ruleset_version} warning={prompt.warning} onClose={prompt.close} />}
  </>);
}

/** A class with no rules in this catalog yet: what it would have, and how its first rules come. */
function EmptyClass({ catalog }: { catalog: CatalogDetail }) {
  const c = catalog.classes?.find((x) => x.slug === catalog.cls);
  const name = c?.name ?? catalog.cls ?? "This class";
  return (
    <div className="empty-class" data-testid="empty-class">
      <h2>No {name} rules for {catalog.name} yet</h2>
      <p className="muted">{c ? `${c.properties} properties are waiting for rules. ` : ""}The first rules come from an AI run,
        or from <code>golden-datasets rule publish --class {catalog.cls}</code>. The class menu above switches back.</p>
    </div>
  );
}

function CompareOneClass() {
  return (
    <div className="empty-class" data-testid="compare-one-class"><h2>Compare one class at a time</h2>
      <p className="muted">Ruleset versions belong to a class. Pick Course or LearningProgram in the class menu above.</p></div>);
}

function useOpenCatalog(route: Route, signedIn: boolean) {
  const { catalog, error, load } = useCatalogLoader(route);
  useEffect(() => { if (signedIn) load(); }, [load, signedIn]);
  // a revert from a report: re-fetch, so the ruleset picker shows the new latest version
  useWindowEvent(CATALOG_CHANGED, load);
  return { catalog, error, reload: load };
}

function useCatalogLoader(route: Route) {
  const [catalog, setCatalog] = useState<CatalogDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  // the class the tabs read now: the class menu's, or with All classes the one of the item on screen (klass.ts)
  const effCls = route.cls === "all" ? apiClass() : route.cls;
  const load = useCallback(() => {
    if (!route.catalog) { setCatalog(null); return; }
    api.catalog(route.catalog).then((c) => { setCatalog(c); setError(null); }, (e) => setError(String(e)));
  }, [route.catalog, effCls]);
  return { catalog, error, load };
}

// Past AI runs: open undefined = closed, null = the list, a run id = that run; `rule`: one rule's runs
function useRunsPanel(params: URLSearchParams) {
  const [open, setOpen] = useState<string | null | undefined>(undefined);
  const [rule, setRule] = useState<RunsRule | null>(null);
  const show = useCallback((run: string | null, runsRule: RunsRule | null) => { setRule(runsRule); setOpen(run); }, []);
  useWindowEvent(OPEN_RUNS, useCallback((e: Event) => showRequested(e, show), [show]));
  useEffect(() => {  // a link to a run's report (?run=<run id>, report-links spec §4): open it, then drop the parameter
    const id = params.get("run");
    if (!id) return;
    show(id, null);
    dropParams(params, ["run"]);
  }, [params, show]);
  return { open, rule, showList: () => show(null, null), close: () => setOpen(undefined) };
}

function showRequested(e: Event, show: (run: string | null, rule: RunsRule | null) => void): void {
  const detail = (e as CustomEvent<OpenRuns | string | null>).detail;
  const request: OpenRuns = typeof detail === "object" && detail ? detail : { run: detail ?? null };
  show(request.run ?? null, request.rule ? { id: request.rule, name: request.ruleName ?? null } : null);
}

// the prompt modal: warning undefined = closed, otherwise the "couldn't connect" warning (null = none)
function usePromptModal(params: URLSearchParams) {
  const [warning, setWarning] = useState<string | null | undefined>(undefined);
  useWindowEvent(OPEN_PROMPT, useCallback((e: Event) => setWarning((e as CustomEvent<{ warning: string | null }>).detail.warning), []));
  useEffect(() => {  // an old #/c/<catalog>/prompt link (or ?prompt=1): open the modal, then drop the parameter
    if (!params.get("prompt")) return;
    setWarning(params.get("k2err"));
    dropParams(params, ["prompt", "k2err"]);
  }, [params]);
  return { warning, close: () => setWarning(undefined) };
}

function useRecordPageView(session: Session | null, signedIn: boolean, known: boolean, route: Route) {
  useEffect(() => {  // one page view per route opened (a no-op unless telemetry is on)
    if (session) pageView(pageInfo(signedIn && known, route.catalog, route.tab, route.id, route.cls));
  }, [session, signedIn, known, route.catalog, route.tab, route.id]);
}

function agentClasses(route: Route, catalog: CatalogDetail | null): ClassSlug[] {
  return route.cls === "all" ? (catalog?.classes ?? []).filter((c) => c.ruleset_version).map((c) => c.slug) : [route.cls];
}

function dropParams(params: URLSearchParams, names: string[]): void {
  const rest = new URLSearchParams(params);
  names.forEach((name) => rest.delete(name));
  history.replaceState(null, "", location.hash.split("?")[0] + (rest.toString() ? `?${rest}` : ""));
}
