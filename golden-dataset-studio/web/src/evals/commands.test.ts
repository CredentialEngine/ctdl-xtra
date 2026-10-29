import { describe, expect, it } from "vitest";
import { multiline } from "./commands";

describe("multiline", () => {
  it("puts each option and its value on its own line", () => {
    expect(multiline("xtra catalog extract --with-template --source-uri '/a b' --catalog-id avc --only-golden-sample"))
      .toBe("xtra catalog extract \\\n  --with-template \\\n  --source-uri '/a b' \\\n  --catalog-id avc \\\n  --only-golden-sample");
  });
  it("leaves a command that is already multi-line alone", () => {
    const c = "xtra score extraction match \\\n  --exactly";
    expect(multiline(c)).toBe(c);
  });
});
