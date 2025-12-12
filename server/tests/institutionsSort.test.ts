import { describe, expect, it } from "vitest";

import { sortInstitutionsByUrlMatch } from "../src/data/institutions";

describe("sortInstitutionsByUrlMatch", () => {
  it("prioritizes exact and parent-domain matches", () => {
    const input = [
      { name: "Apex", domains: ["blabla.edu"] },
      { name: "Exact", domains: ["asdf.blabla.edu"] },
      { name: "FalseSuffix", domains: ["abla.edu"] },
      { name: "Unrelated", domains: ["example.edu"] },
    ];

    const sorted = sortInstitutionsByUrlMatch(
      input,
      "https://asdf.blabla.edu/catalog"
    );

    expect(sorted.map((i) => i.name)).toEqual([
      "Exact",
      "Apex",
      "FalseSuffix",
      "Unrelated",
    ]);
  });

  it("treats institution subdomains as close matches for an apex hostname", () => {
    const input = [
      { name: "Apex", domains: ["bergen.edu"] },
      { name: "CatalogSubdomain", domains: ["catalog.bergen.edu"] },
      { name: "Other", domains: ["example.edu"] },
    ];

    const sorted = sortInstitutionsByUrlMatch(input, "https://bergen.edu");

    expect(sorted.map((i) => i.name)).toEqual([
      "Apex",
      "CatalogSubdomain",
      "Other",
    ]);
  });
});
