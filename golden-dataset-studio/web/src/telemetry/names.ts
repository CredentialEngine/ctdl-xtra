// Low-cardinality names for spans: which page a route is, and an API path with its ids replaced by placeholders
// (the same templates as the server's `http.route`), so spans group by page and by endpoint, not by catalog or rule.

/** What the browser is looking at; every span the web app makes carries it (`ce.page`, `ce.catalog`, `ce.rule.id`). */
export interface PageInfo {
  /** sign-in · catalogs · rules · records · compare · datasets · evals */
  page: string;
  catalog: string | null;
  /** the class in the top bar (course · learningprogram · all), null off a catalog's pages */
  cls: string | null;
  /** the selected rule (Rules tab) or record (Records tab): the route's id */
  id: string | null;
  /** the hash route without its query, ids replaced: `#/c/{catalog}/{class}/rules/{id}` */
  template: string;
}

export function pageInfo(signedIn: boolean, catalog: string | null, tab: string, id: string | null,
                         cls: string | null = null): PageInfo {
  if (!signedIn) return { page: "sign-in", catalog: null, cls: null, id: null, template: "#/" };
  if (!catalog) return { page: "catalogs", catalog: null, cls: null, id: null, template: "#/" };
  return { page: tab, catalog, cls, id, template: `#/c/{catalog}/{class}/${tab}${id ? "/{id}" : ""}` };
}

// /api/<segment>/<id>: the segment's next path part is an id, unless it's one of the literal sub-routes listed
const ID_AFTER: Record<string, string> = {
  catalogs: "{catalog}", crawls: "{catalog}", rules: "{rule_id}", pages: "{stem}", "agent-runs": "{run_id}",
  scores: "{sid}", golden: "{vid}", courses: "{record_external_identifier}", assets: "{sha256}", rulesets: "{version}",
  findings: "{finding_id}",
  approve: "{rule_id}",
};
const LITERAL = new Set(["picker", "config", "queue", "current", "approve", "files", "content", "page"]);

/** `/api/catalogs/avc/rules/course-description/rows` → `/api/catalogs/{catalog}/rules/{rule_id}/rows` */
export function urlTemplate(path: string): string {
  const parts = path.split("/");
  for (let i = 0; i < parts.length - 1; i++) {
    const id = ID_AFTER[parts[i]];
    if (id && parts[i + 1] && !LITERAL.has(parts[i + 1])) {
      parts[i + 1] = id;
      i++;
    }
  }
  // golden files: /files/page/<stem>.json, /files/<table>.parquet
  // a property's review, findings and threads: /properties/<class>/<column>/...
  const t = parts.join("/").replace(/\/api\/properties\/[^/]+\/[^/]+/, "/api/properties/{cls}/{column}");
  return t.replace(/\/files\/page\/[^/]+\.(json|html)$/, "/files/page/{stem}.$1")
    .replace(/\/files\/(?!content$)[^/]+\.(parquet|json)$/, "/files/{table}.$1");
}

/** What a request that changes something does, for `ce.action` (GETs have none). */
export function actionOf(method: string, template: string): string | null {
  if (method === "GET") return null;
  const last = template.split("/").filter((p) => p && !p.startsWith("{")).pop() ?? "";
  const named: Record<string, string> = {
    annotations: "annotate", login: "sign_in", logout: "sign_out", profiles: "save_profile", scores: "start_score",
    "agent-runs": "start_agent_run", cancel: "cancel_agent_run", end: "end_agent_run", revert: "revert_ruleset",
    add: method === "DELETE" ? "dismiss_catalog_add" : "add_catalog",
    // a property's review, across catalogs (LearningProgram, wave 4): its status, findings and discussion
    status: "set_property_status", findings: method === "PUT" ? "edit_finding" : "add_finding", threads: "comment_property",
  };
  return named[last] ?? `${method.toLowerCase()} ${template}`;
}

/** Requests the web app repeats on a timer: no span of their own (they'd be most of the spans), a count instead. */
export const POLL = /\/agent-runs\/(current|queue)$/;
