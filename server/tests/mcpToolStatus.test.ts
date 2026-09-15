import { describe, expect, it } from "vitest";
import { mcpToolDisplayName } from "../src/agentic/permissions";

describe("mcpToolDisplayName", () => {
  it("strips Claude MCP prefixes", () => {
    expect(
      mcpToolDisplayName("mcp__puppeteer__puppeteer_navigate")
    ).toBe("puppeteer_navigate");
    expect(mcpToolDisplayName("mcp__xtra__xtra_report_stage")).toBe(
      "xtra_report_stage"
    );
  });

  it("accepts unprefixed puppeteer and xtra tool names", () => {
    expect(mcpToolDisplayName("puppeteer_click")).toBe("puppeteer_click");
    expect(mcpToolDisplayName("xtra_verify_recipe_links")).toBe(
      "xtra_verify_recipe_links"
    );
  });

  it("ignores non-MCP tools", () => {
    expect(mcpToolDisplayName("ToolSearch")).toBeNull();
    expect(mcpToolDisplayName("Bash")).toBeNull();
  });
});
