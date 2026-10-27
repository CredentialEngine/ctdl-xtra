import type { CatalogDetail } from "../api/types";
import type { Route } from "./router";

/** What App passes to every tab. `reload()` re-fetches the catalog (e.g. after a publish or an approval). */
export interface TabProps { catalog: CatalogDetail; route: Route; reload: () => void }
