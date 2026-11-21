import { afterEach, describe, expect, it, vi } from "vitest";
import { actionOf, pageInfo, POLL, urlTemplate } from "./names";

describe("urlTemplate", () => {
  it.each([
    ["/api/catalogs", "/api/catalogs"],
    ["/api/catalogs/avc", "/api/catalogs/{catalog}"],
    ["/api/catalogs/avc/rules/course-description/rows", "/api/catalogs/{catalog}/rules/{rule_id}/rows"],
    ["/api/catalogs/avc/rules/picker", "/api/catalogs/{catalog}/rules/picker"],
    ["/api/catalogs/avc/pages/some-page/overlay", "/api/catalogs/{catalog}/pages/{stem}/overlay"],
    ["/api/catalogs/avc/golden/approve/course-title", "/api/catalogs/{catalog}/golden/approve/{rule_id}"],
    ["/api/catalogs/avc/golden/ruleset-v3/files/page/x-y.json", "/api/catalogs/{catalog}/golden/{vid}/files/page/{stem}.json"],
    ["/api/catalogs/avc/golden/ruleset-v3/files/lineage.parquet", "/api/catalogs/{catalog}/golden/{vid}/files/{table}.parquet"],
    ["/api/catalogs/avc/files/content", "/api/catalogs/{catalog}/files/content"],
    ["/api/catalogs/avc/agent-runs/current", "/api/catalogs/{catalog}/agent-runs/current"],
    ["/api/catalogs/avc/scores/sc-1/values", "/api/catalogs/{catalog}/scores/{sid}/values"],
    ["/api/crawls/some-crawl/add", "/api/crawls/{catalog}/add"],
  ])("%s", (path, template) => expect(urlTemplate(path)).toBe(template));
});

it("names pages and actions with few values", () => {
  expect(pageInfo(false, "avc", "rules", "x").page).toBe("sign-in");
  expect(pageInfo(true, null, "rules", null)).toEqual({ page: "catalogs", catalog: null, id: null, template: "#/" });
  expect(pageInfo(true, "avc", "rules", "course-title").template).toBe("#/c/{catalog}/rules/{id}");
  expect(actionOf("GET", "/api/catalogs/{catalog}")).toBeNull();
  expect(actionOf("POST", "/api/catalogs/{catalog}/annotations")).toBe("annotate");
  expect(actionOf("DELETE", "/api/crawls/{catalog}/add")).toBe("dismiss_catalog_add");
  expect(POLL.test("/api/catalogs/avc/agent-runs/current")).toBe(true);
});

describe("startTelemetry", () => {
  afterEach(() => { vi.resetModules(); document.getElementById("otel-config")?.remove(); });
  it("loads nothing and leaves fetch alone when the page has no config", async () => {
    const before = window.fetch;
    const { startTelemetry, pageView, readConfig } = await import("./index");
    expect(readConfig()).toBeNull();
    await startTelemetry();
    expect(window.fetch).toBe(before);
    pageView(pageInfo(true, "avc", "rules", null)); // a no-op
  });
  it("reads the config the server inlined", async () => {
    const el = document.createElement("script");
    el.id = "otel-config"; el.type = "application/json";
    el.textContent = JSON.stringify({ endpoint: "/otlp/v1/traces", sample_rate: 1, resource: {} });
    document.head.appendChild(el);
    const { readConfig } = await import("./index");
    expect(readConfig()?.endpoint).toBe("/otlp/v1/traces");
  });
});
