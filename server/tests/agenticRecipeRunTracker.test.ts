import { describe, expect, it } from "vitest";
import { AgenticRecipeRunTracker } from "../src/agentic/agenticRecipeRunTracker";

describe("AgenticRecipeRunTracker", () => {
  it("records give_up messages from xtra tool results", () => {
    const tracker = new AgenticRecipeRunTracker();

    tracker.handleEvent({
      type: "tool",
      message: JSON.stringify({
        xtraEvent: true,
        kind: "give_up",
        message: "Catalogue uses hash routing and is not recipe-compatible.",
      }),
    });

    expect(tracker.giveUpMessage).toBe(
      "Catalogue uses hash routing and is not recipe-compatible."
    );
  });

  it("ignores failed tool results", () => {
    const tracker = new AgenticRecipeRunTracker();
    tracker.handleEvent({
      type: "tool",
      isError: true,
      message: JSON.stringify({
        xtraEvent: true,
        kind: "give_up",
        message: "Should not count",
      }),
    });
    expect(tracker.giveUpMessage).toBeNull();
  });
});
