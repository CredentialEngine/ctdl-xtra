import { describe, expect, it } from "vitest";

import { parseDomains, validateDomains } from "../../common/domains";

describe("domains", () => {
  it("parses comma-separated domains without splitting on letters", () => {
    expect(parseDomains("continue.weber.edu, catalog.weber.edu")).toEqual([
      "continue.weber.edu",
      "catalog.weber.edu",
    ]);
  });

  it("parses newline-separated domains", () => {
    expect(parseDomains("a.example.edu\nb.example.edu")).toEqual([
      "a.example.edu",
      "b.example.edu",
    ]);
  });

  it("normalizes scheme, path, and www", () => {
    expect(parseDomains("https://www.Example.edu/path")).toEqual(["example.edu"]);
  });

  it("returns invalid domains after normalization", () => {
    const { invalid } = validateDomains(["not a domain", "example.edu"]);
    expect(invalid).toEqual(["not a domain"]);
  });
});

