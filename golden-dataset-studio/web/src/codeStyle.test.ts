// @vitest-environment node
/// <reference types="node" />
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// The ratchet: functions still over the CODE-STYLE limits are listed in eslint-suppressions.json, and the list may
// only shrink. It started at 195 (186 long functions, 9 deep blocks) and is now empty, so RATCHET_MAX is 0.
const RATCHET_MAX = 0;
const WEB = resolve(__dirname, "..");

function suppressedCount(): number {
  const suppressions = JSON.parse(readFileSync(resolve(WEB, "eslint-suppressions.json"), "utf8"));
  const rules = Object.values(suppressions) as Record<string, { count: number }>[];
  return rules.flatMap((byRule) => Object.values(byRule)).reduce((total, rule) => total + rule.count, 0);
}

function runEslint(): void {
  execFileSync(resolve(WEB, "node_modules/.bin/eslint"), ["src", "--quiet"], { cwd: WEB, stdio: "pipe" });
}

describe("code style", () => {
  it("adds no function over the limits and keeps no stale suppression", () => {
    expect(runEslint).not.toThrow();
  }, 60_000);

  it("never grows the list of functions allowed to exceed the limits", () => {
    expect(suppressedCount()).toBeLessThanOrEqual(RATCHET_MAX);
  });
});
