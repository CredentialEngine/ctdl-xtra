import { describe, expect, it } from "vitest";
import type { EventBrief } from "../api/types";
import {
  addCapture, applyEvent, applyReview, approveBlocked, byLabel, canConfirm, shortWhen, clip, controlOn, expectedOf, historyItems, isSettled, keyAction, missingEvent, newDraft, paneTabs,
  parseMark, pushRecent, rowTarget, unitWord, verdictEvent, whereWord,
} from "./logic";

const ev = (o: Partial<EventBrief>): EventBrief => ({
  annotation_id: "an-1", type: "verdict", verdict: "wrong", author: "Jared", at: "2026-10-21T20:00:00Z", note: null,
  expected: null, rule_version_seen: 1, value_seen: null, ...o,
});
const cap = { text: "This course provides", css_path: "html > body:nth-of-type(1)", char_start: 3, char_end: 23, prefix: "a", suffix: "b" };

describe("wording", () => {
  it("names the rows and where a rule looks", () => {
    expect(unitWord("field", "locator-course-page")).toBe("courses");
    expect(unitWord("field", "locator-program-requirement")).toBe("course lines");
    expect(unitWord("locator", null)).toBe("courses found");
    expect(unitWord("page", null)).toBe("pages");
    expect(whereWord("locator-course-page")).toBe("course pages");
  });
  it("clips long selections at both ends", () => {
    const t = "x".repeat(300);
    expect(clip(t).length).toBeLessThan(260);
    expect(clip("short")).toBe("short");
  });
  it("parses the uncovered-code detail", () => {
    expect(parseMark("'CFE 201' in “CFE 201 fulfils CORE 8 Requirements” is outside every course"))
      .toEqual({ code: "CFE 201", line: "CFE 201 fulfils CORE 8 Requirements" });
  });
  it("says why approve is greyed out", () => {
    expect(approveBlocked({ open_wrong: 0, open_missing: 0 })).toBeNull();
    expect(approveBlocked({ open_wrong: 6, open_missing: 1 })).toMatch(/^Can't approve yet: 7 courses are marked wrong or missing/);
    expect(approveBlocked({ open_wrong: 1, open_missing: 0 })).toMatch(/1 course is/);
  });
});

describe("row state", () => {
  it("fades only verdicts that still apply", () => {
    expect(isSettled("correct")).toBe(true);
    expect(isSettled("question")).toBe(true);
    expect(isSettled("fixed")).toBe(false);
    expect(isSettled("changed-since-correct")).toBe(false);
    expect(isSettled(null)).toBe(false);
    expect(controlOn("still-wrong")).toBe("wrong");
    expect(controlOn("fixed")).toBeNull();
  });
  it("writes the history lines of spec §7.2", () => {
    const fixed = historyItems({ state: "fixed", verdict: ev({ note: "Prerequisite is separate." }), comments: [] });
    expect(fixed[0]).toEqual({ cls: "good", text: "Fixed: Jared marked the previous version wrong; this matches the text he selected." });
    expect(fixed).toHaveLength(1); // the old note isn't repeated on a fixed row
    expect(historyItems({ state: "still-wrong", verdict: ev({}), comments: [] })[0].cls).toBe("bad");
    expect(historyItems({ state: "changed-since-correct", verdict: ev({ verdict: "correct" }), comments: [] })[0].text)
      .toMatch(/^Changed: Jared marked the previous version correct/);
    expect(historyItems({ state: "correct", verdict: ev({ verdict: "correct" }), reattached: true, comments: [] })[0].text)
      .toMatch(/^Re-attached/);
    expect(historyItems({ state: "question", verdict: ev({ verdict: "question" }), comments: [] })[0].text)
      .toBe("Waiting for the institution's answer");
    expect(historyItems({ state: "wrong", verdict: ev({}), comments: [], page_questions: [ev({ verdict: "question" })] })
      .some((h) => h.text === "Question for the institution (no note yet)")).toBe(true);
    const c = historyItems({ state: null, verdict: null, comments: [ev({ type: "comment", verdict: null, note: "hm", author: "Seth" })] });
    expect(c).toEqual([{ cls: "comment", author: "Seth", text: "“hm”" }]);
  });
});

describe("events", () => {
  const t = rowTarget("field", "course-description", { occurrence_key: "p@x", page_stem: "p" });
  it("targets a match, an occurrence or a page", () => {
    expect(t).toEqual({ kind: "match", rule_id: "course-description", occurrence_key: "p@x", page_stem: "p" });
    expect(rowTarget("locator", "loc", { occurrence_key: "p@x", page_stem: "p" }).kind).toBe("occurrence");
    expect(rowTarget("page", "course-page", { occurrence_key: null, page_stem: "p" })).toEqual({ kind: "page", rule_id: "course-page", page_stem: "p" });
  });
  it("a changed verdict supersedes the previous one", () => {
    const e = verdictEvent("Jared", t, ev({ annotation_id: "an-old" }), { verdict: "correct" });
    expect(e).toMatchObject({ type: "verdict", verdict: "correct", supersedes: "an-old", author: "Jared" });
    expect(verdictEvent("Jared", t, null, { verdict: "correct" }).supersedes).toBeNull();
  });
  it("wrong carries the selection as expected; an empty value is wrong + text", () => {
    const d = { ...newDraft("wrong", null, null), captures: [cap], note: " drop it " };
    const e = verdictEvent("Jared", t, null, { draft: d });
    expect(e.verdict).toBe("wrong");
    expect(e.note).toBe("drop it");
    expect(e.expected).toMatchObject({ text: cap.text, css_path: cap.css_path, char_start: 3, char_end: 23,
                                       quote: { prefix: "a", exact: cap.text, suffix: "b" } });
  });
  it("one piece is expected as before; several are joined in page order, each located in segments", () => {
    expect(expectedOf([cap])).not.toHaveProperty("segments");
    expect(expectedOf([])).toBeNull();
    const b = { ...cap, text: " later ", css_path: "html > body > p:nth-of-type(9)", doc_start: 900, doc_end: 907 };
    const a = { ...cap, doc_start: 10, doc_end: 30 };
    const cs = addCapture(addCapture([], b), a);
    expect(cs.map((c) => c.doc_start)).toEqual([10, 900]);
    expect(expectedOf(cs)).toMatchObject({ text: `${cap.text.trim()}\nlater`, css_path: cap.css_path,
      segments: [{ css_path: cap.css_path }, { css_path: b.css_path, text: " later " }] });
    expect(addCapture(cs, { ...b, text: "replaced", doc_start: 905, doc_end: 950 }).map((c) => c.text)).toEqual([cap.text, "replaced"]);
  });
  it("a comment is a comment event, or a question verdict when ticked", () => {
    const d = newDraft("comment", null, null);
    expect(verdictEvent("J", t, ev({}), { draft: { ...d, note: "hi" } })).toMatchObject({ type: "comment", note: "hi" });
    expect(verdictEvent("J", t, ev({ annotation_id: "an-w" }), { draft: { ...d, note: "q?", question: true } }))
      .toMatchObject({ type: "verdict", verdict: "question", supersedes: "an-w", expected: null });
    const edit = newDraft("comment", ev({ verdict: "question", note: "old q" }), "question");
    expect(edit).toMatchObject({ note: "old q", question: true });
  });
  it("missing: a locator's course block or a page", () => {
    expect(missingEvent("J", "locator", "loc", "p", cap, "")).toMatchObject({
      verdict: "missing", target: { kind: "occurrence", rule_id: "loc", occurrence_key: null, page_stem: "p" },
      expected: { text: cap.text }, note: null });
    expect(missingEvent("J", "page", "course-page", "p", null, "why")).toMatchObject({
      verdict: "missing", target: { kind: "page", rule_id: "course-page", page_stem: "p" }, expected: null, note: "why" });
  });
  it("applies a stored event to a row", () => {
    const row = { state: "fixed" as const, verdict: ev({}), comments: [], reattached: true };
    expect(applyEvent(row, ev({ verdict: "correct", annotation_id: "an-2" }))).toMatchObject({ state: "correct", reattached: false });
    expect(applyEvent(row, ev({ type: "comment", verdict: null })).comments).toHaveLength(1);
  });
});

describe("keyboard", () => {
  it("maps the keys of spec §7.2", () => {
    expect(keyAction({ key: "Tab" }, false)).toBe("next");
    expect(keyAction({ key: "Tab", shiftKey: true }, false)).toBe("prev");
    expect(keyAction({ key: "a" }, false)).toBe("correct");
    expect(keyAction({ key: "W" }, false)).toBe("wrong");
    expect(keyAction({ key: "c" }, false)).toBe("comment");
    expect(keyAction({ key: "h" }, false)).toBe("select");
    expect([keyAction({ key: "1" }, false), keyAction({ key: "2" }, false), keyAction({ key: "3" }, false)])
      .toEqual(["correct", "wrong", "comment"]);
    expect(keyAction({ key: "1" }, true)).toBeNull(); // typing a note
    expect(keyAction({ key: "4" }, false)).toBeNull();
    expect(keyAction({ key: "Enter" }, true)).toBe("save");
    expect(keyAction({ key: "Escape" }, true)).toBe("cancel");
    expect(keyAction({ key: "a" }, true)).toBeNull();
    expect(keyAction({ key: "a", metaKey: true }, false)).toBeNull();
  });
});

describe("page tabs", () => {
  const T = (s: string) => ({ stem: s, url: `https://x/${s}`, title: s });
  it("current page, the course's other pages, then recent ones, without repeats", () => {
    expect(paneTabs(T("a"), [T("b"), T("a")], [T("c"), T("b")]).map((t) => t.stem)).toEqual(["a", "b", "c"]);
    expect(paneTabs(null, [], []).length).toBe(0);
  });
  it("keeps the last few pages viewed", () => {
    let r = [T("a"), T("b"), T("c")];
    r = pushRecent(r, T("d"));
    expect(r.map((t) => t.stem)).toEqual(["d", "a", "b"]);
    expect(pushRecent(r, T("b")).map((t) => t.stem)).toEqual(["b", "d", "a"]);
  });
});

describe("human-reviewed and engineer-checked (Evals spec §4.3)", () => {
  it("an expert's ✓ confirms; an engineer's ✓ waits, or leaves an expert's standing; other verdicts clear both", () => {
    const eric = ev({ verdict: "correct", author: "Eric Riddoch" });
    const jared = ev({ verdict: "correct", author: "Jared Diener", annotation_id: "an-2" });
    const waiting = applyReview({}, eric, "engineer");
    expect(waiting).toMatchObject({ engineer_checked: true, checked: eric });
    expect(canConfirm(waiting, "sme")).toBe(true);
    expect(canConfirm(waiting, "engineer")).toBe(false);
    const human = applyReview(waiting, jared, "sme");
    expect(human).toMatchObject({ human_reviewed: true, engineer_checked: false, human: jared, checked: eric });
    expect(applyReview(human, eric, "engineer")).toBe(human);
    expect(applyReview(human, ev({ verdict: "wrong" }), "engineer")).toMatchObject({ human_reviewed: false, engineer_checked: false });
    expect(applyReview(human, ev({ type: "comment", verdict: null }), "engineer")).toBe(human);
  });

  it("names the filter's choices and dates a check", () => {
    expect([null, "nobody", "waiting", "Jared Diener"].map(byLabel))
      .toEqual(["Anyone", "Not annotated yet", "Any engineer · waiting for an expert", "Jared Diener"]);
    const now = Date.parse("2026-10-28T12:00:00Z");
    expect(shortWhen("2026-10-28T11:59:30Z", now)).toBe("just now");
    expect(shortWhen("2026-10-21T10:00:00Z", now)).toBe("21 Oct");
  });
});
