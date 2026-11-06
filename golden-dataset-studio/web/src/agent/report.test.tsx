// One-rule runs (docs/qrspi/one-rule-runs/03-spec.md §1.4, §1.6, §2.3–2.4; contract 05-api-contract.md §2.6, §3): the
// report rendered from a resolved report, its row cards' ✓ and ✕, Open in Rules in a new tab, refetch on focus, Run
// again, Revert, and no " · " anywhere in it.
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setIdentity } from "../shell/reviewer";
import { compareOf, type AgentRun, type ReportRow, type ReportRows, type ResolvedReport, type RunNote } from "./api";
import { Report } from "./Report";
import { OPEN_RUN_DIALOG } from "./RunDialog";
import { RunsPanel } from "./RunsPanel";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const RUN: AgentRun = {
  run_id: "20261106T153500Z-4f2a", catalog: "avc-x", catalog_short: "avc", scope: { kind: "rules", rules: ["course-credit-value"] },
  rule_names: { "course-credit-value": "Credit Value", "course-credit-value-credit-unit-type": "Credit Unit Type" },
  started_by: "Jared Diener", created_at: "2026-11-06T15:35:00Z", updated_at: "2026-11-06T15:41:00Z", deadline: "2026-11-06T17:05:00Z",
  state: "finished", sent_at: "2026-11-06T15:36:00Z", next_try_at: null, k2: { url: "https://k2.example", agent: "golden-rules", delivery_id: null },
  ruleset_before: 9, ruleset_after: 10, outcome: "Claude published Credit Value in ruleset v10.", ended_at: "2026-11-06T15:41:00Z",
  ended_by: null, fallback_reason: null, annotations_as_of: "2026-11-06T15:36:05Z", rulesets_published: [10],
  also_changed: ["course-credit-value-credit-unit-type"], report_version: 2,
};
const NOTES: RunNote[] = [{ at: "2026-11-06T15:37:00Z", kind: "note", text: "Drafted Credit Value", by: "golden-rules agent" }];

const JARED_WRONG = { annotation_id: "an-718755f023ce", type: "verdict" as const, verdict: "wrong" as const, author: "Jared Diener",
  author_role: "sme", at: "2026-11-04T16:20:00Z", expected: null, rule_version_seen: 2, value_seen: "1.0 - 8.0 Units",
  note: "There should be no values for this property.", run_id: null, ruleset_version: null };
const CLAUDE = { annotation_id: "an-c1a0de4b7f20", type: "comment" as const, verdict: null, author: "Claude", author_role: "ai",
  at: "2026-11-06T15:44:00Z", note: "Empty is the value Jared's note asks for.", expected: null, rule_version_seen: null, value_seen: null,
  run_id: RUN.run_id, ruleset_version: 10, run_at: "2026-11-06T15:35:00Z", after_run: false };
const JARED_OK = { annotation_id: "an-5d0c1e2f9a11", type: "verdict" as const, verdict: "correct" as const, author: "Jared Diener",
  author_role: "sme", at: "2026-11-07T17:04:00Z", note: null, expected: null, rule_version_seen: 3, value_seen: null,
  run_id: null, ruleset_version: null, after_run: true };

const row = (o: Partial<ReportRow> & Pick<ReportRow, "rule" | "course">): ReportRow => ({
  rule_name: o.rule, legend: o.rule, kind: "property", title: `${o.course} - A course`, page_stem: `p-${o.course.toLowerCase()}`,
  url: `https://avc.example/${o.course}`, key: `p-${o.course}@html`, occurrence_key: `p-${o.course}@html`, value: "x", status: "found",
  verdict: null, state: null, history: [], ...o,
  links: { rules: `#/c/avc/rules/${o.rule}?row=${o.course}&by=anyone&ext=rs-0010`,
           wrong: `#/c/avc/rules/${o.rule}?row=${o.course}&by=anyone&ext=rs-0010&mark=wrong`, ...o.links },
});
const ACCT_CV = row({ rule: "course-credit-value", course: "ACCT199", legend: "Credit Value", value: null, status: "absent",
  value_before: { version: 9, value: "1.0 - 8.0 Units" }, comment: CLAUDE.note, verdict: JARED_WRONG, state: "still-wrong",
  history: [JARED_WRONG, CLAUDE] });
const ACCT_UNIT = row({ rule: "course-credit-value-credit-unit-type", course: "ACCT199", legend: "Credit Unit Type", value: "Units" });
const BIOL = row({ rule: "course-description", course: "BIOL110", legend: "Description", value: "A comprehensive introduction.",
  inferred: { value: "A comprehensive introduction.", annotation: "an-biol-wrong", saves: "expected" },
  verdict: { ...JARED_WRONG, annotation_id: "an-biol-wrong", author: "Eric Riddoch", note: "Prerequisites are not part of it." },
  state: "wrong", left_out: [{ text: "Advisory: Completion of a general biology course is recommended." },
                             { text: "Prerequisite: Intermediate Algebra." }] });
const GEOG = row({ rule: "course-in-catalog", course: "GEOG222", legend: "In Catalog", value: "https://avc.example/geog222",
  inferred: { value: "https://avc.example/geog222", annotation: "an-geog", saves: "correct" },
  verdict: { ...JARED_WRONG, annotation_id: "an-geog" }, state: "wrong" });
const SUBJ = (c: string) => row({ rule: "course-subject-webpage", course: c, legend: "Subject Webpage", value: `https://avc.example/${c}` });
const todo = (ask: string, open = true) => ({ ask, open, about: [SUBJ("ACCT199")], options: [
  { answer: "yes", text: "If yes, mark the 13 courses Not on the page. The next run publishes both rules together." },
  { answer: "no", text: "If no, mark ACCT199 correct. The next run publishes In Catalog." }],
  evidence: [{ kind: "set" as const, label: "marked correct", rule: "course-subject-webpage", count: 3, rows: [SUBJ("GEOG222")],
               courses: [{ course: "AERO199", title: "AERO 199 - Flight", value: "https://avc.example/aero199", verdict: "correct" },
                         { course: "AJ912", title: "AJ 912 - Law", value: "https://avc.example/aj912", verdict: "correct" }] }] });

const REPORT: ResolvedReport = {
  version: 2, run_id: RUN.run_id, ending: "published", outcome: "Claude published Credit Value in ruleset v10.",
  ruleset: { started_on: 9, based_on: 9, published: [10], latest: 10, ext: "rs-0010", compare: { a: 9, b: 10 } },
  facts: [{ label: "Rules to improve", text: "Credit Value" }, { label: "Also changed", text: "Credit Unit Type" },
          { label: "Checked", text: "All 44 rules against 244 golden values. Nothing that was right got worse." }],
  inferred: [{ rule: "course-description", rule_name: "Description", course: "BIOL110", value: BIOL.inferred!.value, published: false, row: BIOL },
             { rule: "course-in-catalog", rule_name: "In Catalog", course: "GEOG222", value: GEOG.inferred!.value, published: true, row: GEOG }],
  to_do: [todo("Should Subject Webpage be empty for every course?"), todo("Second?"), todo("Third?"), todo("Fourth?")],
  rules: [{ rule: "course-credit-value", name: "Credit Value", goal: true, outcome: "published", now: "empty on every course", why: null,
            values_changed: { count: 1062, of: 1062, base: 9, published: 10, compare_url: "#/c/avc/compare?a=9&b=10&rule=course-credit-value",
                              text: "1,062 of 1,062 courses" }, rows: [ACCT_CV] }],
  also_changed: [{ rule: "course-credit-value-credit-unit-type", name: "Credit Unit Type", goal: false, outcome: "published",
                   why: "It took its unit word from Credit Value; it now reads the same line on the page.",
                   because: { reads: "course-credit-value", name: "Credit Value" },
                   values_changed: { count: 0, of: 1062, base: 9, published: 10, compare_url: null, text: "0 of 1,062 courses" }, rows: [ACCT_UNIT] }],
  notes: null,
  revert: { version: 10, text: "Revert v10? This publishes v11 with Credit Value and Credit Unit Type back to how they were in v9." },
};

let rows: ReportRows;
let rowsFetches = 0;
const posts: { url: string; body: Record<string, unknown> }[] = [];
const respond = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

beforeEach(() => {
  rowsFetches = 0;
  posts.length = 0;
  rows = { run_id: RUN.run_id, annotations_as_of: RUN.annotations_as_of!, new_feedback: 0,
    rules_touched: ["course-credit-value", "course-credit-value-credit-unit-type"],
    rows: [{ rule: "course-credit-value", course: "ACCT199", state: "correct", verdict: JARED_OK, history: [JARED_WRONG, CLAUDE, JARED_OK] },
           { rule: "course-credit-value-credit-unit-type", course: "ACCT199", state: null, verdict: null, history: [] }] };
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      const body = JSON.parse(String(init.body));
      posts.push({ url, body });
      if (url.endsWith("/annotations")) {
        const event = { ...body, annotation_id: "an-new", at: "2026-11-07T18:00:00Z", note: body.note ?? null,
          expected: body.expected ?? null, verdict: body.verdict ?? null, target: { ...body.target } };
        // the server's log: the row's history has it on the next refetch
        rows = { ...rows, rows: rows.rows.map((r) => (r.rule === body.target.rule_id && `p-${r.course}@html` === body.target.occurrence_key
          ? { ...r, history: [...r.history, { ...event, after_run: true }] } : r)) };
        return respond(200, { event, rule: null, elapsed_ms: 1 });
      }
      if (url.includes("/revert")) return respond(200, { version: 11, reverted: 10 });
      return respond(200, {});
    }
    if (url.endsWith("/rows")) { rowsFetches++; return respond(200, rows); }
    if (url.endsWith("/prompt")) return respond(200, { text: "# The prompt" });
    if (url.includes("/agent-runs?")) return respond(200, [RUN]);
    if (url.endsWith(`/agent-runs/${RUN.run_id}`)) return respond(200, { run: RUN, notes: NOTES, summary: "x", report: REPORT });
    if (url.endsWith("/agent-runs/old-run")) return respond(200, { run: { ...RUN, run_id: "old-run", report_version: null }, notes: [],
      summary: "## Decisions for Eric\n\nAdvisory text", report: null });
    if (url.endsWith("/agent-runs/queue")) return respond(200, { cap: 2, working: [], waiting: [], median_min: 6, from_runs: 0 });
    return respond(404, { detail: "no" });
  });
  setIdentity("Jared Diener", "sme");
  location.hash = "#/c/avc/rules";
});

let host: HTMLDivElement, root: Root;
beforeEach(() => { host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
const flush = () => act(async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); });

async function render(report = REPORT, run = RUN) {
  await act(async () => root.render(<Report catalog="avc" run={run} report={report} notes={NOTES} pastRuns={() => {}} />));
  await flush();
}
const cardOf = (rule: string, course: string) =>
  [...host.querySelectorAll<HTMLElement>("[data-testid=row-card]")].find((c) =>
    c.dataset.course === course && c.querySelector(`a.xbtn[href*="/rules/${rule}?"]`))!;
const histLines = (el: Element) => [...el.querySelectorAll(".hist.stacked > span")].map((s) => s.textContent);

describe("Report", () => {
  it("renders the band, the facts, a section per rule with Values changed and Compare, and row cards", async () => {
    await render();
    expect(host.querySelector(".run-done-t")!.textContent).toBe("Claude published Credit Value in ruleset v10.");
    expect(host.querySelector(".run-done a")!.getAttribute("href")).toBe("#/c/avc/compare?a=9&b=10");
    const facts = [...host.querySelectorAll("[data-testid=report-facts] dt")].map((d) => d.textContent);
    expect(facts).toEqual(["Rules to improve", "Also changed", "Checked", "Started", "Ran"]);
    const secs = [...host.querySelectorAll("[data-testid=rule-section]")];
    expect(secs.map((s) => s.querySelector("h3")!.textContent)).toEqual(["Credit Value", "Also changed: Credit Unit Type"]);
    const vc = secs[0].querySelector("[data-testid=values-changed]")!;
    expect(vc.textContent).toBe("1,062 of 1,062 courses. Compare v9 and v10");
    expect(vc.querySelector("a")!.getAttribute("href")).toBe("#/c/avc/compare?a=9&b=10&rule=course-credit-value");
    // an also-changed rule: its count, a Compare link made from the versions, and its one sentence
    expect(secs[1].querySelector("[data-testid=values-changed]")!.textContent).toBe("0 of 1,062 courses. Compare v9 and v10");
    expect(secs[1].querySelector("p")!.textContent).toContain("It took its unit word from Credit Value");
    expect(secs[0].querySelector("p")!.textContent).toBe("Now empty on every course.");
    // the course as its Rules tab row card: code, legend, the claim, the title, both link buttons
    const card = cardOf("course-credit-value", "ACCT199");
    expect(card.querySelector(".code")!.textContent).toBe("ACCT199");
    expect(card.querySelector(".valbox-k")!.textContent).toBe("Credit Value");
    expect(card.querySelector(".valbox")!.className).toContain("claim");
    expect([...card.querySelectorAll(".xbtn")].map((a) => a.textContent)).toEqual(["Open in Records →", "Open in Rules →"]);
    expect(card.getAttribute("tabindex")).toBeNull();  // not selectable in a report
  });

  it("shows each history item on its own line: the old value, the notes, Claude's comment with its run, later verdicts", async () => {
    await render();
    const card = cardOf("course-credit-value", "ACCT199");
    expect(card.querySelector(".hist")!.className).toContain("stacked");
    expect(card.querySelector(".h-sep")).toBeNull();
    const lines = histLines(card);
    expect(lines[0]).toBe("In v9: 1.0 - 8.0 Units");
    expect(lines[1]).toBe("Jared Diener: “There should be no values for this property.”");
    expect(lines[2]).toBe("Claude (v10, AI run Nov 6): Empty is the value Jared's note asks for.");
    expect(card.querySelector(".hist a")!.getAttribute("href")).toBe(`#/c/avc/rules?run=${RUN.run_id}`);
    expect(lines[3]).toMatch(/^Jared Diener marked it correct, \d{1,2}:\d\d [AP]M, after this run\.$/);
    // the row's controls show its current verdict (refetched), not the one at the run's end
    expect(card.querySelector(".cb.ok")!.className).toContain(" on");
    expect(card.querySelector(".byline")!.textContent).toBe("Jared Diener");
  });

  it("opens the first value Claude worked out and folds the rest; at most 3 decisions open", async () => {
    await render();
    const inf = host.querySelector("[data-testid=inferred]")!;
    expect(inf.querySelector("h3")!.textContent).toBe("Values Claude worked out");
    expect(inf.querySelectorAll(":scope > div [data-testid=row-card]").length).toBe(1);
    expect(inf.querySelector("details > summary")!.textContent).toBe("GEOG222: In Catalog");
    expect(inf.querySelector("p")!.textContent).toBe(
      "Eric Riddoch marked BIOL110 wrong without selecting the right text. Claude worked out the value below from the notes and the page.");
    // BIOL110's box holds the value Claude worked out; the lines it left out are struck through
    const biol = cardOf("course-description", "BIOL110");
    expect(biol.querySelector("[data-testid=row-full-value]")!.textContent).toBe("A comprehensive introduction.");
    expect([...biol.querySelectorAll(".sel-quote.out")].map((q) => q.textContent)).toEqual([
      "Advisory: Completion of a general biology course is recommended.", "Prerequisite: Intermediate Algebra."]);
    expect([...biol.querySelectorAll(".sel-pol")].map((q) => q.textContent)).toEqual(["✕ not in answer", "✕ not in answer"]);
    const todos = [...host.querySelectorAll("[data-testid=to-do]")];
    expect(todos.map((t) => t.tagName)).toEqual(["SECTION", "SECTION", "SECTION", "DETAILS"]);
    expect(todos[0].querySelector("h3")!.textContent).toBe("Should Subject Webpage be empty for every course?");
    expect(todos[0].querySelector("p")!.textContent).toBe("3 courses marked correct, like GEOG222:");
    expect(todos[0].querySelector(".report-others")!.textContent).toBe("The other 2: AERO199, AJ912.");
    expect(todos[0].querySelector(".report-option b")!.textContent).toBe("If yes,");
  });

  it("shows a course code's title, value and verdict in the app's Tip on hover", async () => {
    await render();
    const code = [...host.querySelectorAll<HTMLButtonElement>(".report-others .linkish")].find((b) => b.textContent === "AERO199")!;
    await act(async () => code.parentElement!.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })));
    const tip = document.querySelector(".evx-tip")!;
    expect(tip.textContent).toBe("AERO199: AERO 199 - Flighthttps://avc.example/aero199Marked correct.");
  });

  it("never shows a middle dot", async () => {
    rows = { ...rows, new_feedback: 2 };
    await render();
    const text = host.textContent!;
    expect(text).not.toContain("·");
    expect(text).toContain("2 rows have new feedback since this run.");
  });

  it("✓ on a value Claude worked out that wasn't published saves it as the expected value of the open ✕", async () => {
    await render();
    const card = cardOf("course-description", "BIOL110");
    const ok = card.querySelector<HTMLButtonElement>(".cb.ok")!;
    expect(ok.title).toBe("Correct (1): this is the right value. Saves it as BIOL110's expected Description");
    await act(async () => ok.click());
    await flush();
    expect(posts).toHaveLength(1);
    expect(posts[0].url).toBe("/api/catalogs/avc/annotations");
    expect(posts[0].body).toMatchObject({ type: "verdict", verdict: "wrong", author: "Jared Diener", supersedes: "an-biol-wrong",
      expected: { text: "A comprehensive introduction.", css_path: null },
      target: { kind: "match", rule_id: "course-description", occurrence_key: "p-BIOL110@html" } });
  });

  it("✓ on a value Claude published marks the current value correct", async () => {
    await render();
    const inf = host.querySelector("[data-testid=inferred] details")!;
    (inf as HTMLDetailsElement).open = true;
    await act(async () => cardOf("course-in-catalog", "GEOG222").querySelector<HTMLButtonElement>(".cb.ok")!.click());
    await flush();
    expect(posts[0].body).toMatchObject({ type: "verdict", verdict: "correct", supersedes: "an-geog",
      target: { rule_id: "course-in-catalog", occurrence_key: "p-GEOG222@html" } });
    expect(posts[0].body.expected).toBeUndefined();
    await flush();
    expect(cardOf("course-in-catalog", "GEOG222")).toBeTruthy();
  });

  it("a comment from the report is posted on the row and appended to its history", async () => {
    await render();
    const card = cardOf("course-credit-value-credit-unit-type", "ACCT199");
    await act(async () => card.querySelector<HTMLButtonElement>(".cb.talk")!.click());
    const input = card.querySelector<HTMLInputElement>(".expand.comment input.note")!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "Read it from the Units box");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => card.querySelector<HTMLButtonElement>(".expand .save")!.click());
    await flush();
    expect(posts[0].body).toMatchObject({ type: "comment", note: "Read it from the Units box",
      target: { rule_id: "course-credit-value-credit-unit-type" } });
    expect(histLines(cardOf("course-credit-value-credit-unit-type", "ACCT199")).slice(-1)[0])
      .toMatch(/^Jared Diener: “Read it from the Units box” .*after this run\.$/);
  });

  it("Open in Rules → and ✕ open the row in a new browser tab, pinned to the run's ruleset; ✕ with mark=wrong", async () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    await render();
    const card = cardOf("course-credit-value", "ACCT199");
    const rules = [...card.querySelectorAll<HTMLAnchorElement>(".xbtn")].find((a) => a.textContent === "Open in Rules →")!;
    expect(rules.target).toBe("_blank");
    expect(rules.getAttribute("href")).toBe("#/c/avc/rules/course-credit-value?row=ACCT199&by=anyone&ext=rs-0010");
    await act(async () => card.querySelector<HTMLButtonElement>(".cb.no")!.click());
    expect(open).toHaveBeenCalledWith("#/c/avc/rules/course-credit-value?row=ACCT199&by=anyone&ext=rs-0010&mark=wrong", "_blank", "noopener");
    expect(posts).toHaveLength(0);
  });

  it("builds the new-tab links itself when a row has none, with ext from the report", async () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    const bare = { ...ACCT_UNIT, links: null };
    await render({ ...REPORT, inferred: [], to_do: [], rules: [], also_changed: [{ ...REPORT.also_changed[0], rows: [bare] }] });
    const card = host.querySelector("[data-testid=row-card]")!;
    expect(card.querySelectorAll<HTMLAnchorElement>(".xbtn")[1].getAttribute("href"))
      .toBe("#/c/avc/rules/course-credit-value-credit-unit-type?row=ACCT199&by=anyone&ext=rs-0010");
    await act(async () => card.querySelector<HTMLButtonElement>(".cb.no")!.click());
    expect(open.mock.calls[0][0]).toBe("#/c/avc/rules/course-credit-value-credit-unit-type?row=ACCT199&by=anyone&ext=rs-0010&mark=wrong");
  });

  it("refetches the rows on open, when the window gets focus and when the page becomes visible", async () => {
    await render();
    expect(rowsFetches).toBe(1);
    rows = { ...rows, new_feedback: 1 };
    await act(async () => window.dispatchEvent(new Event("focus")));
    await flush();
    expect(rowsFetches).toBe(2);
    expect(host.querySelector("[data-testid=new-feedback]")!.textContent).toBe("1 row has new feedback since this run.");
    await act(async () => document.dispatchEvent(new Event("visibilitychange")));
    await flush();
    expect(rowsFetches).toBe(3);
  });

  it("offers Run again only when rows have new feedback, through the Run with Claude? dialog with the same rules", async () => {
    await render();
    const foot = () => host.querySelector("[data-testid=report-foot]")!;
    expect([...foot().querySelectorAll("button")].map((b) => b.textContent)).toEqual(["Past AI runs", "Revert v10", "View the prompt"]);
    rows = { ...rows, new_feedback: 2 };
    await act(async () => window.dispatchEvent(new Event("focus")));
    await flush();
    const again = [...foot().querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Run again")!;
    expect(again.className).toContain("primary");
    const asked: unknown[] = [];
    const on = (e: Event) => asked.push((e as CustomEvent).detail);
    window.addEventListener(OPEN_RUN_DIALOG, on);
    await act(async () => again.click());
    window.removeEventListener(OPEN_RUN_DIALOG, on);
    expect(asked).toEqual([{ rules: ["course-credit-value"] }]);
    expect(posts).toHaveLength(0);  // the dialog starts it, not this button
  });

  it("reverts only after the confirm (the app's own dialog, not the browser's), for anyone", async () => {
    const native = vi.spyOn(window, "confirm");
    await render();
    const revert = [...host.querySelectorAll<HTMLButtonElement>("[data-testid=report-foot] button")].find((b) => b.textContent === "Revert v10")!;
    await act(async () => revert.click());
    const ask = host.querySelector("[data-testid=revert-ask]")!;
    expect(ask.querySelector("h2")!.textContent).toBe("Revert v10?");
    expect(ask.querySelector(".ac-body p")!.textContent).toBe(
      "This publishes v11 with Credit Value and Credit Unit Type back to how they were in v9.");
    // Cancel: nothing posted, the dialog closes
    await act(async () => [...ask.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Cancel")!.click());
    expect(host.querySelector("[data-testid=revert-ask]")).toBeNull();
    expect(posts).toHaveLength(0);
    await act(async () => revert.click());
    await act(async () => host.querySelector<HTMLButtonElement>("[data-testid=revert-ask] .btn.primary")!.click());
    await flush();
    expect(posts).toEqual([{ url: "/api/catalogs/avc/rulesets/10/revert", body: { author: "Jared Diener" } }]);
    expect(host.querySelector("[data-testid=revert-ask]")).toBeNull();
    expect(native).not.toHaveBeenCalled();
  });

  it("has no Revert when the run published nothing, and says the ruleset is unchanged", async () => {
    const run = { ...RUN, state: "needs_you" as const, ruleset_after: 9, to_do_count: 1 };
    await render({ ...REPORT, revert: null, ending: "needs_you", outcome: "1 decision before Claude can publish Subject Webpage." }, run);
    expect([...host.querySelectorAll("[data-testid=report-foot] button")].map((b) => b.textContent)).toEqual(["Past AI runs", "View the prompt"]);
    const facts = host.querySelector("[data-testid=report-facts]")!;
    expect(facts.textContent).toContain("Rulesetv9, unchanged");
    expect(host.querySelector(".run-done a")).toBeNull();
  });

  it("shows the prompt Claude was given on View the prompt", async () => {
    await render();
    await act(async () => [...host.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "View the prompt")!.click());
    await flush();
    expect(host.querySelector(".runs-prompt")!.textContent).toBe("# The prompt");
  });
});

describe("Compare for a run that rebased or ended after another run's publish (e2e, 2026-11-05)", () => {
  it("uses the report's own pair: what the run built on to what it published", async () => {
    // started on v10, rebased on v11 (another run's), published v12; the run record says before 10, after 12
    const run = { ...RUN, ruleset_before: 10, ruleset_after: 12 };
    const report = { ...REPORT, ruleset: { started_on: 10, based_on: 11, published: [12], latest: 12, ext: "rs-0012",
                                           compare: { a: 11, b: 12 } } };
    await render(report, run);
    const a = host.querySelector(".run-done a")!;
    expect(a.getAttribute("href")).toBe("#/c/avc/compare?a=11&b=12");
    expect(a.textContent).toBe("Compare v11 → v12");
  });
  it("compareOf: the run record's base when it has one, else ruleset_before; nothing when nothing was published", () => {
    expect(compareOf({ ...RUN, ruleset_before: 10, ruleset_after: 12, ruleset_base: 11 })).toEqual({ a: 11, b: 12 });
    expect(compareOf({ ...RUN, ruleset_before: 10, ruleset_after: 11 })).toEqual({ a: 10, b: 11 });
    expect(compareOf({ ...RUN, ruleset_before: 10, ruleset_after: 10 })).toBeNull();
  });
});

describe("RunsPanel with reports", () => {
  it("renders a run's resolved report, and an older run's summary.md as before", async () => {
    await act(async () => root.render(<RunsPanel catalog="avc" initial={RUN.run_id} onClose={() => {}} />));
    await flush();
    expect(host.querySelector("[data-testid=run-report] .run-done-t")!.textContent).toBe("Claude published Credit Value in ruleset v10.");
    act(() => root.unmount());
    root = createRoot(host);
    await act(async () => root.render(<RunsPanel catalog="avc" initial="old-run" onClose={() => {}} />));
    await flush();
    expect(host.querySelector("[data-testid=run-detail] .runs-report h2")!.textContent).toBe("Decisions for Eric");
  });
});
