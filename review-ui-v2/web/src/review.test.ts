import { describe, expect, it } from "vitest";
import {
  cardState,
  flagTotals,
  foldDecision,
  foldFlag,
  foldNote,
  goldenMessage,
  pageFlagKey,
  pageFlags,
  pageProgress,
} from "./review";
import type { Decision, Flag, Note, PageSummary } from "./types";

const decision = (key: string, status: Decision["status"]): Decision => ({
  key,
  kind: "field",
  status,
  canonical_label: "x",
  source_url: "u",
  reasons: [],
  author: "Seth",
  at: "t",
});

const page = { keys: ["a", "b", "c"] } as PageSummary;

describe("review helpers", () => {
  it("treats a missing decision as pending and anything but accepted as rejected", () => {
    expect(cardState(undefined)).toBe("pending");
    expect(cardState(decision("a", "accepted"))).toBe("accepted");
    expect(cardState(decision("a", "rejected"))).toBe("rejected");
  });

  it("counts decided and rejected items per page", () => {
    const progress = pageProgress(page, {
      a: decision("a", "accepted"),
      b: decision("b", "rejected"),
      zzz: decision("zzz", "accepted"),
    });
    expect(progress).toEqual({ decided: 2, total: 3, rejected: 1 });
  });

  it("removes a decision when it is set back to pending", () => {
    const start = { a: decision("a", "accepted") };
    expect(foldDecision(start, { key: "a", status: "pending" })).toEqual({});
  });

  it("replaces a note by id and deletes it when the text is emptied", () => {
    const note = { id: "n1", scope: "general", target: null, text: "old" } as Note;
    const edited = foldNote([note], { ...note, text: "new" });
    expect(edited[0].text).toBe("new");
    expect(foldNote(edited, { ...note, text: "  " })).toEqual([]);
  });
});

describe("flags", () => {
  const flag = (stem: string, scope: Flag["scope"], target: string): Flag => ({
    target,
    scope,
    stem,
    source_url: "u",
    note: "",
    author: "Jared",
    at: "t",
  });

  it("adds a flag and removes it when flagged is false", () => {
    const added = foldFlag({}, { ...flag("p1", "field", "k"), flagged: true });
    expect(Object.keys(added)).toEqual(["k"]);
    expect(foldFlag(added, { target: "k", flagged: false })).toEqual({});
  });

  it("reports a page as flagged for a page flag or for any flagged item on it", () => {
    const flags = {
      [pageFlagKey("p1")]: flag("p1", "page", pageFlagKey("p1")),
      a: flag("p2", "field", "a"),
      b: flag("p2", "label", "b"),
    };
    expect(pageFlags("p1", flags)).toEqual({ page: true, items: 0, any: true });
    expect(pageFlags("p2", flags)).toEqual({ page: false, items: 2, any: true });
    expect(pageFlags("p3", flags)).toEqual({ page: false, items: 0, any: false });
  });

  it("totals pages and items separately", () => {
    const flags = {
      p: flag("p1", "page", "page::p1"),
      a: flag("p1", "field", "a"),
      b: flag("p1", "field", "b"),
    };
    expect(flagTotals(flags)).toEqual({ pages: 1, items: 2 });
  });
});

describe("goldenMessage", () => {
  const base = { key: "k", location: "l", values: 11, records: 3, datasets: 1 };

  it("reports a clean save", () => {
    expect(goldenMessage({ ...base, left_out: {} })).toEqual({
      text: "Saved 11 values in 3 records.",
      incomplete: false,
    });
  });

  it("uses singular forms", () => {
    expect(goldenMessage({ ...base, values: 1, records: 1, left_out: {} }).text).toBe(
      "Saved 1 value in 1 record.",
    );
  });

  it("says what was left out and why, and marks the page as incomplete", () => {
    const result = goldenMessage({
      ...base,
      left_out: { not_reviewed: 5, flagged: 2, rejected_without_correction: 1, no_ctdl_property: 3, absent: 4 },
    });
    expect(result.text).toBe(
      "Saved 11 values in 3 records. Left out: 5 not reviewed yet (2 flagged for an expert), " +
        "1 rejected without a correction, 4 accepted as absent, 3 with no CTDL property.",
    );
    expect(result.incomplete).toBe(true);
  });

  it("is not incomplete when only values with nothing to save were skipped", () => {
    expect(goldenMessage({ ...base, left_out: { absent: 2, no_ctdl_property: 1 } }).incomplete).toBe(false);
  });
});
