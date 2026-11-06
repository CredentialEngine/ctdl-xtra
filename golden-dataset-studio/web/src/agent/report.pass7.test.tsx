// The report tells the reader what to do (one-rule-runs spec pass 7, answers-pass6.md), on the real case: live run
// 20261106T012457Z-b970 on AVC, Subject Webpage (fixtures/, built from its files). Story first: the question and why,
// then the answers as buttons, then the evidence. An answer is confirmed in the app's dialog, posts one verdict per
// course, shows it is done with Undo and Run again. Each row card once, introduced in words; the rest of a set is a
// table; times are relative with the time zone in a tooltip; ✓ says what it does and offers Undo.
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { EventBrief } from "../api/types";
import { rowKeysBlocked } from "../rules/logic";
import { setIdentity } from "../shell/reviewer";
import type { AgentRun, ReportCourse, ReportRows, ResolvedReport } from "./api";
import OLD from "./fixtures/b970-before-pass7.resolved.json";
import NEW from "./fixtures/b970-pass7.resolved.json";
import RUN_JSON from "./fixtures/b970.run.json";
import { Report, undoEvent } from "./Report";
import { OPEN_RUN_DIALOG } from "./RunDialog";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const SW = "course-subject-webpage";
const RUN = { ...RUN_JSON, catalog_short: "avc", next_try_at: null, rulesets_published: [], also_changed: [] } as unknown as AgentRun;
const REPORT = NEW as unknown as ResolvedReport;
const BEFORE = OLD as unknown as ResolvedReport;
const YES = REPORT.to_do[0].options[0].do!.courses;
const ACCT = REPORT.to_do[0].options[1].do!.courses[0];

// the server's annotation log, as /rows reads it: each row's verdict and history, changed by every POST
type Row = ReportRows["rows"][number];
let log: Map<string, Row>;
let seq = 0;
const posts: { url: string; body: Record<string, unknown> }[] = [];
const respond = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
const byOcc = new Map<string, ReportCourse>([...YES, ACCT].map((c) => [c.occurrence_key!, c]));

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-11-06T01:37:45Z"));  // 12 minutes after the run ended
  posts.length = 0;
  seq = 0;
  log = new Map([...YES, ACCT].map((c) => [c.course, { rule: SW, course: c.course, occurrence_key: c.occurrence_key, page_stem: c.page_stem ?? undefined,
    state: c.state ?? null, verdict: c.current ?? null, history: c.current ? [{ ...c.current, after_run: false }] : [] }]));
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      const body = JSON.parse(String(init.body));
      posts.push({ url, body });
      const event = { ...body, annotation_id: `an-new-${++seq}`, at: new Date().toISOString(), note: body.note ?? null,
        expected: body.expected ?? null, verdict: body.verdict ?? null, target: { ...body.target } };
      const c = byOcc.get(body.target.occurrence_key)!;
      const r = log.get(c.course)!;
      const b = { ...event, type: "verdict", author: body.author, after_run: true, rule_version_seen: 1, value_seen: null } as EventBrief & { after_run: boolean };
      log.set(c.course, { ...r, verdict: b, state: b.verdict, history: [...r.history, b] });
      return respond(200, { event, rule: null, elapsed_ms: 1 });
    }
    if (url.endsWith("/rows")) return respond(200, { run_id: RUN.run_id, annotations_as_of: RUN.annotations_as_of, new_feedback: 0, rows: [...log.values()] });
    return respond(404, { detail: "no" });
  });
  setIdentity("Eric Riddoch", "engineer");
  location.hash = "#/c/avc/rules";
});

let host: HTMLDivElement, root: Root;
beforeEach(() => { host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers();
  document.querySelectorAll(".toast").forEach((t) => t.remove()); });
const flush = () => act(async () => { for (let i = 0; i < 40; i++) await Promise.resolve(); });

async function render(report = REPORT) {
  await act(async () => root.render(<Report catalog="avc" run={RUN} report={report} notes={[]} />));
  await flush();
}
const todo = () => host.querySelector<HTMLElement>("[data-testid=to-do]")!;
const buttons = (el: Element) => [...el.querySelectorAll<HTMLButtonElement>("button")];
const button = (el: Element, text: string) => buttons(el).find((b) => b.textContent === text)!;
const before = (a: Element, b: Element) => !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);

describe("A decision tells its story first (the live run)", () => {
  it("opens with the question and why, then the answers, then the evidence", async () => {
    await render();
    const t = todo();
    expect(t.querySelector("h3")!.textContent).toBe("Is Jared Diener's note on ACCT199 right for every course in this catalog?");
    const why = t.querySelector("[data-testid=to-do-why]")!;
    expect(why.textContent).toBe(REPORT.to_do[0].why);
    const answers = t.querySelector("[data-testid=answers]")!;
    expect(buttons(answers).map((b) => b.textContent)).toEqual(["Yes: mark the 13 courses Not on the page", "No: mark ACCT199 correct"]);
    expect(answers.textContent).toContain("Subject Webpage becomes empty. In Catalog reads the page's address. "
      + "In Catalog has no rule yet; the next run writes one. Then run again with Subject Webpage and In Catalog.");
    const leads = [...t.querySelectorAll("[data-testid=row-lead]")];
    expect(leads.map((p) => p.textContent)).toEqual(["Here is the row Jared Diener marked wrong:",
                                                     "Here is one of the 13 courses Jared Diener marked correct:"]);
    expect(before(why, answers) && before(answers, leads[0]) && before(leads[0], t.querySelector("[data-testid=row-card]")!)).toBe(true);
    // the buttons are the app's own
    expect(buttons(answers).every((b) => b.className === "btn")).toBe(true);
  });

  it("shows each row card once: the Subject Webpage section points back to ACCT199's card", async () => {
    await render();
    const cards = [...host.querySelectorAll<HTMLElement>("[data-testid=row-card]")].map((c) => c.dataset.course);
    expect(cards).toEqual(["ACCT199", "AERO199"]);
    const sec = host.querySelector("[data-testid=rule-section]")!;
    expect(sec.querySelector("[data-testid=shown-above]")!.textContent).toBe("Claude's comment is on ACCT199's row, shown above.");
  });

  it("lists the other 12 as a table, folded, with each course's title, value, mark and Open in Rules →", async () => {
    await render();
    const fold = todo().querySelector("details.run-fold")!;
    expect(fold.querySelector("summary")!.textContent).toBe("The other 12 courses Jared Diener marked correct");
    const rows = [...fold.querySelectorAll("[data-testid=course-table] tbody tr")];
    expect(rows).toHaveLength(12);
    expect([...rows[0].querySelectorAll("td")].map((td) => td.textContent)).toEqual([
      "AJ912", "AJ 912 - Intermediate Health and Fitness for First Responders II",
      "https://avc.elumenapp.com/catalog/2026-27/course/aj912", "Correct", "Open in Rules →"]);
    expect(rows[0].querySelector("a")!.getAttribute("href")).toBe(`#/c/avc/rules/${SW}?row=AJ912&by=anyone&ext=rs-0010`);
    expect(host.textContent).not.toMatch(/AERO199, AJ912/);
  });

  it("names people in full, and has no middle dot", async () => {
    await render();
    expect(host.textContent).not.toMatch(/Jared(?! Diener)/);
    expect(host.textContent).not.toContain("·");
  });
});

describe("Answering from the report", () => {
  it("Yes: confirms in the app's dialog listing every course, posts one Not on the page per course, then shows Done, Undo and Run again", async () => {
    const native = vi.spyOn(window, "confirm");
    await render();
    await act(async () => button(todo(), "Yes: mark the 13 courses Not on the page").click());
    let ask = host.querySelector("[data-testid=answer-ask]")!;
    expect(ask.className).toBe("ac run-ask");
    expect(ask.querySelector("h2")!.textContent).toBe("Mark 13 courses Not on the page?");
    expect(ask.querySelector(".ac-body p")!.textContent).toBe("This records 13 verdicts on Subject Webpage, one per course, as Eric Riddoch. "
      + "Each replaces the course's current mark. You can undo it afterwards.");
    const listed = [...ask.querySelectorAll("[data-testid=answer-ask-courses] tbody tr")].map((tr) =>
      [...tr.querySelectorAll("td")].map((td) => td.textContent));
    expect(listed).toHaveLength(13);
    expect(listed[0]).toEqual(["AERO199", "AERO 199 - Work Experience Education", "Correct", "Not on the page"]);
    expect(ask.querySelector(".run-note")!.textContent).toBe("In Catalog has no rule yet; the next run writes one. Then run again with Subject Webpage and In Catalog.");
    // Cancel: nothing is posted
    await act(async () => button(ask, "Cancel").click());
    expect(host.querySelector("[data-testid=answer-ask]")).toBeNull();
    expect(posts).toHaveLength(0);

    await act(async () => button(todo(), "Yes: mark the 13 courses Not on the page").click());
    ask = host.querySelector("[data-testid=answer-ask]")!;
    await act(async () => button(ask, "Mark 13 courses Not on the page").click());
    await flush();
    expect(native).not.toHaveBeenCalled();
    expect(posts).toHaveLength(13);
    expect(posts.every((p) => p.url === "/api/catalogs/avc/annotations")).toBe(true);
    expect(posts[0].body).toEqual({ type: "verdict", author: "Eric Riddoch", verdict: "wrong", reasons: ["not_on_page"],
      supersedes: YES[0].current!.annotation_id,
      target: { kind: "match", rule_id: SW, occurrence_key: YES[0].occurrence_key, page_stem: YES[0].page_stem } });
    expect(posts.map((p) => p.body.supersedes)).toEqual(YES.map((c) => c.current!.annotation_id));

    const done = todo().querySelector("[data-testid=answer-done]")!;
    expect(done.textContent).toContain("Done: 13 courses marked Not on the page.");
    expect(todo().querySelector("[data-testid=answers]")).toBeNull();  // the other answer goes
    // the toast says what was recorded, with Undo
    const t = document.querySelector(".toast-act")!;
    expect(t.querySelector("span")!.textContent).toBe("Done: 13 courses marked Not on the page");
    expect(t.querySelector("button")!.textContent).toBe("Undo");
    // the table's marks are the new ones
    expect(todo().querySelector("[data-testid=course-table] tbody td:nth-child(4)")!.textContent).toBe("Not on the page");

    // Run again, with the answer's rules ticked
    const asked: unknown[] = [];
    const on = (e: Event) => asked.push((e as CustomEvent).detail);
    window.addEventListener(OPEN_RUN_DIALOG, on);
    await act(async () => button(done, "Run again").click());
    window.removeEventListener(OPEN_RUN_DIALOG, on);
    expect(asked).toEqual([{ rules: [SW, "course-in-catalog"] }]);
    expect(done.textContent).toContain("Then run again with Subject Webpage and In Catalog.");

    // Undo: one verdict per course that supersedes the mistaken one and restores Jared Diener's ✓
    await act(async () => button(done, "Undo").click());
    await flush();
    expect(posts).toHaveLength(26);
    expect(posts[13].body).toEqual({ type: "verdict", author: "Eric Riddoch", verdict: "correct", supersedes: "an-new-1",
      note: null, expected: null, target: posts[0].body.target });
    expect(todo().querySelector("[data-testid=answers]")).not.toBeNull();  // back to the question
  });

  it("No: marks ACCT199 correct, superseding Jared Diener's ✕; its toast's Undo restores the ✕", async () => {
    await render();
    await act(async () => button(todo(), "No: mark ACCT199 correct").click());
    const ask = host.querySelector("[data-testid=answer-ask]")!;
    expect(ask.querySelector("h2")!.textContent).toBe("Mark ACCT199 correct?");
    await act(async () => button(ask, "Mark ACCT199 correct").click());
    await flush();
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toMatchObject({ verdict: "correct", supersedes: "an-f69f1da3e976", target: { occurrence_key: ACCT.occurrence_key } });
    expect(todo().querySelector("[data-testid=answer-done]")!.textContent).toContain("Done: ACCT199 marked correct.");
    await act(async () => document.querySelector<HTMLButtonElement>(".toast-act button")!.click());
    await flush();
    expect(posts[1].body).toMatchObject({ verdict: "wrong", supersedes: "an-new-1", note: null, expected: null });
    expect(posts[1].body.reasons).toBeUndefined();
  });

  it("an answer whose courses are already so is shown as done", async () => {
    for (const c of YES) {
      const r = log.get(c.course)!;
      log.set(c.course, { ...r, state: "wrong", verdict: { ...c.current!, annotation_id: `an-x-${c.course}`, verdict: "wrong", reasons: ["not_on_page"] } });
    }
    await render();
    expect(todo().querySelector("[data-testid=answer-done]")!.textContent).toContain("Done: 13 courses marked Not on the page.");
    expect(buttons(todo().querySelector("[data-testid=answer-done]")!).map((b) => b.textContent)).toEqual(["Run again"]);  // no Undo: not posted here
  });

  it("undoEvent restores the earlier verdict, its note, expected value and reasons, superseding the mistaken one", () => {
    const target = { kind: "match" as const, rule_id: SW, occurrence_key: "o", page_stem: "p" };
    const prev = { ...ACCT.current!, note: "n", expected: { text: "x", css_path: null, char_start: null, char_end: null }, reasons: ["not_on_page"] };
    expect(undoEvent("Eric Riddoch", { rule: SW, course: "ACCT199", target, id: "an-mistake", prev })).toEqual({
      type: "verdict", author: "Eric Riddoch", target, verdict: "wrong", supersedes: "an-mistake", note: "n",
      expected: { text: "x", css_path: null, char_start: null, char_end: null }, reasons: ["not_on_page"] });
    expect(undoEvent("Eric Riddoch", { rule: SW, course: "ACCT199", target, id: "an-mistake", prev: null })).toBeNull();
  });
});

describe("Obvious clicks", () => {
  it("✓ ✕ and comment say what they do on this row", async () => {
    await render();
    const card = host.querySelector("[data-testid=row-card][data-course=ACCT199]")!;
    expect(card.querySelector<HTMLButtonElement>(".cb.ok")!.title).toBe("Mark ACCT199's Subject Webpage correct");
    expect(card.querySelector<HTMLButtonElement>(".cb.no")!.title).toBe(
      "Mark ACCT199's Subject Webpage wrong: opens the row in the Rules tab, in a new browser tab, to select the right text");
    expect(card.querySelector<HTMLButtonElement>(".cb.talk")!.title).toBe("Comment on ACCT199's Subject Webpage");
  });

  it("an innocent click on a card posts nothing; ✓ posts, says what was recorded and offers Undo", async () => {
    await render();
    const card = host.querySelector<HTMLElement>("[data-testid=row-card][data-course=ACCT199]")!;
    await act(async () => { card.click(); card.querySelector<HTMLElement>(".valbox")!.click(); card.querySelector<HTMLElement>(".code")!.click(); });
    await flush();
    expect(posts).toHaveLength(0);
    await act(async () => card.querySelector<HTMLButtonElement>(".cb.ok")!.click());
    await flush();
    expect(posts[0].body).toMatchObject({ verdict: "correct", supersedes: "an-f69f1da3e976" });
    const t = document.querySelector(".toast-act")!;
    expect(t.querySelector("span")!.textContent).toBe("Marked ACCT199's Subject Webpage correct");
    await act(async () => t.querySelector("button")!.click());
    await flush();
    expect(posts[1].body).toMatchObject({ verdict: "wrong", supersedes: "an-new-1" });
    // a ✓ on a row already marked correct posts nothing
    const aero = host.querySelector<HTMLElement>("[data-testid=row-card][data-course=AERO199]")!;
    await act(async () => aero.querySelector<HTMLButtonElement>(".cb.ok")!.click());
    await flush();
    expect(posts).toHaveLength(2);
  });

  it("the Rules tab's keys don't act on its row while the report's drawer is open", () => {
    expect(rowKeysBlocked(document)).toBe(false);
    const d = document.createElement("aside");
    d.className = "run-watch";
    document.body.appendChild(d);
    expect(rowKeysBlocked(document)).toBe(true);
    d.remove();
  });
});

describe("Times", () => {
  it("are relative, with the full date and time zone in a tooltip", async () => {
    await render();
    const dt = [...host.querySelectorAll("[data-testid=report-facts] dt")].find((d) => d.textContent === "Started")!;
    const started = dt.nextElementSibling!.querySelector("time")!;
    expect(dt.nextElementSibling!.textContent).toBe("12 minutes ago by Eric Riddoch");
    expect(started.textContent).toBe("12 minutes ago");
    expect(started.getAttribute("title")).toMatch(/^Nov \d, 2026, \d{1,2}:24 [AP]M (GMT|UTC|[A-Z]{2,5})/);
    // a verdict made after the run, on the row's history line
    await act(async () => host.querySelector<HTMLButtonElement>("[data-testid=row-card][data-course=ACCT199] .cb.ok")!.click());
    await flush();
    const lines = [...host.querySelectorAll("[data-testid=row-card][data-course=ACCT199] .hist.stacked > span")].map((s) => s.textContent);
    expect(lines[lines.length - 1]).toBe("Eric Riddoch marked it correct just now, after this run.");
    expect(host.textContent).not.toMatch(/\d{1,2}:\d\d ?[AP]M/);  // no bare clock time anywhere
  });
});

describe("A report from before pass 7 (the live file as it was written)", () => {
  it("still renders: the answers as sentences before the evidence, a table for the set, one card per row", async () => {
    await render(BEFORE);
    const t = todo();
    expect(t.querySelector("h3")!.textContent).toBe(BEFORE.to_do[0].ask);
    expect([...t.querySelectorAll(".report-option b")].map((b) => b.textContent)).toEqual(["If yes,", "If no,"]);
    expect(before(t.querySelector(".report-option")!, t.querySelector("[data-testid=row-card]")!)).toBe(true);
    expect(t.querySelectorAll("[data-testid=course-table] tbody tr")).toHaveLength(12);
    expect([...host.querySelectorAll("[data-testid=row-card]")].map((c) => (c as HTMLElement).dataset.course)).toEqual(["ACCT199", "AERO199"]);
    expect([...t.querySelectorAll("[data-testid=row-lead]")].map((p) => p.textContent)).toEqual([
      "Here is the row Jared Diener marked wrong:", "Here is one of the 13 courses marked correct:"]);
  });
});

describe("History from the CLI's resolved report", () => {
  it("shows the card's history before …/rows answers (items with `kind`, contract §3.3)", async () => {
    vi.stubGlobal("fetch", () => new Promise(() => {}));  // /rows never answers
    await render(BEFORE);
    const lines = [...host.querySelectorAll("[data-testid=row-card][data-course=ACCT199] .hist.stacked > span")].map((s) => s.textContent);
    expect(lines[0]).toBe("Jared Diener: “When the resource is in a catalog, use the property ceterms:inCatalog instead of ceterms:subjectWebpage.”");
    expect(lines[1]).toMatch(/^Claude \(v10, AI run Nov [56]\): The value is still the page's address/);  // the date in the browser's zone
    expect(lines).toHaveLength(2);
  });
});
