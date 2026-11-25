// Who is reading and where: the attributes every span carries, and the baggage every API call sends the server.
import type { Attributes } from "@opentelemetry/api";
import { currentReviewer, currentRole } from "../shell/reviewer";
import type { PageInfo } from "./names";
import { state } from "./state";

type Baggage = Record<string, { value: string }>;

export function whoAndWhere(): Attributes {
  return { ...reader(), ...pageAttributes(state.page), ...viewAttributes() };
}

export function baggageEntries(): Baggage {
  const who = whoAndWhere();
  const entries: Baggage = {};
  for (const key of ["user.id", "ce.page", "ce.page_view.id"] as const) {
    if (who[key]) entries[key] = { value: String(who[key]) };
  }
  if (who["user.roles"]) entries["user.roles"] = { value: (who["user.roles"] as string[]).join("|") };
  const sessionId = state.sessions?.getSessionId();
  if (sessionId) entries["session.id"] = { value: sessionId };
  return entries;
}

function reader(): Attributes {
  const reviewer = currentReviewer();
  const role = currentRole();
  return { ...(reviewer ? { "user.id": reviewer } : {}), ...(role ? { "user.roles": [role] } : {}) };
}

function pageAttributes(page: PageInfo | null): Attributes {
  if (!page) return {};
  return {
    "ce.page": page.page, "ce.page.template": page.template,
    ...(page.catalog ? { "ce.catalog": page.catalog } : {}), ...(page.cls ? { "ce.class": page.cls } : {}),
    ...(page.id ? { [page.page === "records" ? "ce.record.external_identifier" : "ce.rule.id"]: page.id } : {}),
  };
}

function viewAttributes(): Attributes {
  return {
    ...(state.view ? { "ce.page_view.id": state.view.id } : {}),
    ...(state.entryPage ? { "ce.entry_page": state.entryPage } : {}),
  };
}
