import { useEffect, useRef, useState } from "react";
import App from "./App";
import { getCatalogs, setCatalog } from "./api";
import Landing from "./components/Landing";
import { buildHash, parseHash } from "./route";
import type { CatalogList } from "./types";

/** Landing page when the URL names no catalog, otherwise the review of that catalog. */
export default function Root() {
  const [route, setRoute] = useState(() => parseHash(location.hash));
  const [list, setList] = useState<CatalogList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const firstLoad = useRef(true);

  useEffect(() => {
    const onChange = () => setRoute(parseHash(location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  // Fetch the list on first load and again whenever we come back to the landing page,
  // so its progress is current.
  useEffect(() => {
    if (route.cid) {
      firstLoad.current = false;
      return;
    }
    getCatalogs()
      .then((l) => {
        setList(l);
        setError(null);
        // `serve --run X` goes straight to X, but only on the first load: "Change
        // ruleset" must be able to reach the landing page afterwards.
        if (firstLoad.current && l.default) location.hash = buildHash(l.default);
        firstLoad.current = false;
      })
      .catch((e) => setError(String(e)));
  }, [route.cid]);

  if (route.cid) {
    setCatalog(route.cid);
    return <App key={route.cid} cid={route.cid} />;
  }
  return <Landing list={list} error={error} onOpen={(cid) => (location.hash = buildHash(cid))} />;
}
