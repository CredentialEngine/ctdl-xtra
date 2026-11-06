import type {
  Boot,
  CatalogList,
  Counts,
  DecisionEvent,
  FlagEvent,
  GoldenResult,
  NoteEvent,
  PageView,
} from "./types";

async function check(response: Response) {
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status}: ${body}`);
  }
  return response;
}

// Each catalog has its own URL space, so a click can only reach the review it was made in.
let catalog = "";
export const setCatalog = (cid: string) => {
  catalog = cid;
};
export const apiBase = () => `/api/c/${catalog}`;

export const getCatalogs = async (): Promise<CatalogList> =>
  (await check(await fetch("/api/catalogs"))).json();

export const getBoot = async (): Promise<Boot> =>
  (await check(await fetch(`${apiBase()}/state`))).json();

export const getPage = async (stem: string): Promise<PageView> =>
  (await check(await fetch(`${apiBase()}/pages/${stem}`))).json();

export const getSource = async (stem: string): Promise<string> =>
  (await (await check(await fetch(`${apiBase()}/pages/${stem}/source`))).json()).html;

export const contentUrl = (stem: string) => `${apiBase()}/pages/${stem}/content`;

export async function postEvent(
  event: (DecisionEvent | NoteEvent | FlagEvent) & { author: string },
): Promise<{ event: Record<string, unknown>; counts: Counts }> {
  const response = await fetch(`${apiBase()}/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(event),
  });
  return (await check(response)).json();
}

export const startReview = async (): Promise<Boot> =>
  (await check(await fetch(`${apiBase()}/reviews`, { method: "POST" }))).json();

export const openReview = async (id: string): Promise<Boot> =>
  (await check(await fetch(`${apiBase()}/reviews/${id}/open`, { method: "POST" }))).json();

/** Save the page's verified values to the golden sets storage. A 422 carries the reason. */
export async function saveGolden(stem: string): Promise<GoldenResult> {
  const response = await fetch(`${apiBase()}/golden/${stem}`, { method: "POST" });
  if (!response.ok) {
    let detail = "";
    try {
      detail = (await response.json()).detail;
    } catch {
      /* not JSON */
    }
    throw new Error(detail || `Could not save (${response.status})`);
  }
  return response.json();
}
