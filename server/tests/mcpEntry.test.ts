import path from "path";
import { describe, expect, it } from "vitest";
import {
  agentMcpPrefersCompiledEntry,
  compiledCommonTypesPath,
  monorepoCommonTypesPath,
  resolveAgentMcpCommand,
} from "../src/agentic/mcpEntry";
import { serverPackageRoot } from "../src/agentic/paths";
import { xtraMcpCommand } from "../src/agentic/xtraMcp";

describe("agentMcpPrefersCompiledEntry", () => {
  it("is false in the monorepo dev layout", () => {
    const root = serverPackageRoot();
    expect(agentMcpPrefersCompiledEntry(root)).toBe(false);
  });
});

describe("resolveAgentMcpCommand", () => {
  it("uses tsx source in monorepo dev layout", () => {
    const root = serverPackageRoot();
    const compiledDir = path.join(root, "src", "agentic");
    const cmd = resolveAgentMcpCommand("xtraMcpServer", compiledDir);
    expect(cmd.args.some((arg) => arg.endsWith("xtraMcpServer.ts"))).toBe(true);
    expect(cmd.args.some((arg) => arg.includes("tsx"))).toBe(true);
  });

  it("uses compiled entry in Docker-like layout", () => {
    const root = serverPackageRoot();
    if (!agentMcpPrefersCompiledEntry(root)) {
      expect(monorepoCommonTypesPath(root)).toBeTruthy();
      expect(compiledCommonTypesPath(root)).toBeTruthy();
    }
    const compiledDir = path.join(root, "dist", "server", "src", "agentic");
    const cmd = resolveAgentMcpCommand("xtraMcpServer", compiledDir);
    if (agentMcpPrefersCompiledEntry(root)) {
      expect(cmd.args).toEqual([
        path.join(compiledDir, "xtraMcpServer.js"),
      ]);
    }
  });
});

describe("xtraMcpCommand", () => {
  it("returns a node command with xtraMcpServer entry", () => {
    const cmd = xtraMcpCommand();
    expect(cmd.command).toBe(process.execPath);
    expect(
      cmd.args.some((arg) => arg.includes("xtraMcpServer"))
    ).toBe(true);
  });
});
