import { describe, expect, it } from "vitest";
import { parsePageLoadWaitTime } from "../src/agentic/xtraMcp";

describe("parsePageLoadWaitTime", () => {
  it("accepts non-negative numbers and numeric strings", () => {
    expect(parsePageLoadWaitTime(10)).toBe(10);
    expect(parsePageLoadWaitTime(0)).toBe(0);
    expect(parsePageLoadWaitTime("10")).toBe(10);
  });

  it("rejects missing or invalid values", () => {
    expect(parsePageLoadWaitTime(undefined)).toBeUndefined();
    expect(parsePageLoadWaitTime("")).toBeUndefined();
    expect(parsePageLoadWaitTime(-1)).toBeUndefined();
    expect(parsePageLoadWaitTime("nope")).toBeUndefined();
  });
});
