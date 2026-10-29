import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setIdentity } from "../shell/reviewer";
import type { CatalogDetail, RuleDetail, RulesResponse, RuleSummary } from "../api/types";
import { parseRoute } from "../shell/router";
import type { RowX, RowsX } from "./api";
import RulesTab from "./RulesTab";
import type { PagePaneProps } from "../pagepane/PagePane";

// The page pane is an iframe jsdom doesn't load: a stand-in keeps its latest props and shows its banner and legend.
const pane: { props: PagePaneProps | null } = { props: null };
vi.mock("../pagepane", async (orig) => ({
  ...(await orig<typeof import("../pagepane")>()),
  PagePane: (p: PagePaneProps) => { pane.props = p; return <div data-testid="pane">{p.banner}{p.legend}</div>; },
}));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const catalog = { catalog: "avc-x", short: "avc", name: "AVC", institution: "AVC", logo: null, crawl: "2026-10-12T20-59-13Z",
  crawl_started: "", pages: 1467, extraction: "rs-0002", ruleset_version: 2, extractions: [
    { extraction: "rs-0001", ruleset_version: 1, parent_extraction: null }, { extraction: "rs-0002", ruleset_version: 2, parent_extraction: "rs-0001" }], rulesets: [], authors: [],
  pane_css: "", root: "" } as CatalogDetail;

const summary = (o: Partial<RuleSummary>): RuleSummary => ({
  rule_id: "course-description", kind: "field", version: 2, title: "Description", subtitle: "ceterms:description",
  ctdl_property: "ceterms:description", property_label: "Description", locator: "locator-course-page", status: "in review",
  reviewed: 14, total: 1062, open_wrong: 0, open_missing: 0, questions: 0, approved_by: null, approved_at: null, comments: 0, ...o,
});

const rules: RulesResponse = { extraction: "rs-0002", ruleset_version: 2, groups: [
  { kind: "page", label: "Page rules", approved: 0, rules: [summary({ rule_id: "course-page", kind: "page", title: "Course pages", subtitle: "Which pages…", status: "needs work", open_wrong: 2 })] },
  { kind: "locator", label: "Record locators", approved: 0, rules: [] },
  { kind: "field", label: "Field rules", approved: 1, rules: [summary({}), summary({ rule_id: "course-language", title: "Language", status: "approved" })] },
] };

const detail = (o: Partial<RuleDetail> = {}): RuleDetail => ({
  ...summary({}), definition: { locator: "locator-course-page", selector: ".introtext" }, what: "The text under the title", how: "h", why: "",
  examples: [], depends_on: [], content_hash: "sha256:abcdef0123456789abcdef0123", published_by: "Claude", published_at: null,
  parent_version: 1, versions: [1, 2], fill: { rows: 1062, found: 1060 }, signal_counts: {}, settings: { content_root: "main" }, ...o,
});

const row = (i: number, o: Partial<RowX> = {}): RowX => ({
  key: `p${i}@html`, occurrence_key: `p${i}@html`, course_key: `GEOG${i}`, page_stem: `p${i}`, url: `https://x/p${i}`,
  page_title: `Page ${i}`, value: `Value ${i}`, status: "found", css_path: "html > body:nth-of-type(1)", char_start: 0, char_end: 5,
  occurrence_css_path: "html", context: `GEOG ${i} - Course`, state: null, verdict: null, reattached: false, comments: [],
  signal_count: 0, other_pages: [], group: `${i * 20}–${i * 20 + 19} words (percentile ${i * 33}–${i * 33 + 33})`, ...o,
});

const rows: RowsX = { rule_id: "course-description", extraction: "rs-0002", total: 3, offset: 0, missing: [], elapsed_ms: 1, focus_index: 1,
  spread: { by: "length: percentiles of the word count", groups: [0, 1, 2].map((i) => ({ label: `${i * 20}–${i * 20 + 19} words (percentile ${i * 33}–${i * 33 + 33})`, rows: 1 })) },
  rows: [
    row(0, { state: "fixed", verdict: { annotation_id: "an-old", type: "verdict", verdict: "wrong", author: "Jared", at: "t", note: "n",
             expected: null, rule_version_seen: 1, value_seen: "x" } }),
    row(1),
    row(2, { state: "correct", verdict: { annotation_id: "an-c", type: "verdict", verdict: "correct", author: "Seth", at: "t", note: null,
             expected: null, rule_version_seen: 2, value_seen: "Value 2" } }),
  ] };

let posted: unknown[] = [];
let container: HTMLDivElement;
let root: Root;

function json(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
}

beforeEach(() => {
  setIdentity("Jared", "sme");
  posted = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const u = String(url);
    if (init?.method === "POST") {
      const ev = JSON.parse(String(init.body));
      posted.push(ev);
      return json({ event: { ...ev, annotation_id: "an-new", at: "now", note: ev.note ?? null, expected: ev.expected ?? null,
                             verdict: ev.verdict ?? null, target: { ...ev.target, rule_version_seen: 2 } },
                    rule: summary({ reviewed: 15 }), elapsed_ms: 1 });
    }
    if (u.endsWith("/rules")) return json(rules);
    if (u.includes("/rows")) return json(rows);
    if (/\/rules\/[^/?]+$/.test(u)) return json(detail());
    return json({});
  }));
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

async function render(hash = "#/c/avc/rules/course-description?row=GEOG1") {
  await act(async () => {
    root.render(<RulesTab catalog={catalog} route={parseRoute(hash)} reload={() => {}} />);
  });
  await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
}

describe("RulesTab", () => {
  it("discusses a whole rule in the sidebar, and posts comments with their topic", async () => {
    let talk = { ruleset: [] as unknown[], rules: {} as Record<string, unknown[]> };
    const fetchMock = vi.mocked(fetch);
    const base = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((url, init) => {
      if (String(url).endsWith("/discussion")) return json(talk);
      if (init?.method === "POST") {
        const ev = JSON.parse(String(init.body));
        const item = { annotation_id: "an-t", author: ev.author, at: "2026-10-27T10:00:00Z", note: ev.note, topic: ev.topic,
                       rule_id: ev.target.rule_id, rule_version_seen: ev.target.rule_id ? 2 : null, ruleset_version_seen: 3 };
        talk = ev.target.kind === "ruleset" ? { ...talk, ruleset: [...talk.ruleset, item] }
          : { ...talk, rules: { ...talk.rules, [ev.target.rule_id]: [item] } };
      }
      return base(url as string, init);
    });
    await render();
    expect(container.querySelector("[data-testid=ruleset-talk]")).toBeNull();  // the ruleset's box is gone
    const pick = container.querySelector<HTMLSelectElement>("[data-testid=ruleset-pick] select")!;
    expect([...pick.options].map((o) => o.textContent)).toEqual(["v2 (latest)", "v1"]);
    expect(pick.value).toBe("rs-0002");
    const type = async (box: Element, text: string) => {
      const ta = box.querySelector<HTMLTextAreaElement>(".talk-input")!;
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
      await act(async () => { setter.call(ta, text); ta.dispatchEvent(new Event("input", { bubbles: true })); });
      await act(async () => { box.querySelector<HTMLButtonElement>(".talk-actions .btn")!.click(); await new Promise((r) => setTimeout(r, 0)); });
    };
    const btn = container.querySelector<HTMLButtonElement>("[data-rule=course-description] .rule-talk-btn")!;
    expect(btn.textContent).toBe("Discuss");
    await act(async () => btn.click());
    const thread = container.querySelector("[data-testid=rule-talk]")!;
    await act(async () => thread.querySelector<HTMLInputElement>(".talk-q input")!.click());
    await type(thread, "Do we need this rule at all?");
    expect(posted[posted.length - 1]).toMatchObject({ topic: "question-rule", target: { kind: "rule", rule_id: "course-description" } });
    expect(container.querySelector("[data-rule=course-description] .rule-talk-btn")!.textContent).toBe("1");
  });

  it("closes the Sample drawer when the reader moves to another row", async () => {
    const fetchMock = vi.mocked(fetch);
    const base = fetchMock.getMockImplementation()!;
    const sample = { order: "review", seed: 0, total: 3, listed: 3, cross: [], cells: [], tag_dims: [], histograms: [] };
    fetchMock.mockImplementation((url, init) => (String(url).includes("/rows") ? json({ ...rows, sample }) : base(url as string, init)));
    await render();
    await act(async () => container.querySelector<HTMLButtonElement>("[data-testid=sample] .sm-tog")!.click());
    expect(container.querySelector("[data-testid=sample]")!.className).toContain("open");
    await act(async () => container.querySelectorAll<HTMLElement>(".row")[2].click());
    expect(container.querySelector("[data-testid=sample]")!.className).not.toContain("open");
  });

  it("shows the selected row's whole value, paragraphs kept, and links to the course on the Records tab", async () => {
    const long = "Advisory: Completion of DA 125.\n\n" + "A long description that goes on. ".repeat(20);
    const fetchMock = vi.mocked(fetch);
    const base = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((url, init) => (String(url).includes("/rows")
      ? json({ ...rows, rows: rows.rows.map((r, i) => (i === 1 ? { ...r, value: long } : r)) }) : base(url as string, init)));
    await render();
    const full = container.querySelector<HTMLElement>(".row.on [data-testid=row-full-value]")!;
    expect(full.textContent).toBe(long);                              // not cut, the line breaks kept for pre-line
    expect(container.querySelectorAll("[data-testid=row-full-value]").length).toBe(1);  // only the selected row
    const link = container.querySelector<HTMLAnchorElement>(".row.on .row-links .xbtn")!;
    expect(link.textContent).toBe("Open in Records →");
    expect(link.getAttribute("href")).toBe("#/c/avc/records/GEOG1?prop=Description&occ=p1%40html");
  });

  it("sends the Sample drawer's order and filters to /rows and shows the rows' strata tags", async () => {
    const sample = { order: "review", seed: 0, total: 3, listed: 3, cross: [], cells: [], tag_dims: [], elsewhere: 2, histograms: [
      { id: "length", label: "Length", help: "", uniform: false, spread: 0.9,
        buckets: [{ id: "0–9 chars", count: 2, on: false }, { id: "10–19 chars", count: 1, on: false }] }] };
    const fetchMock = vi.mocked(fetch);
    const base = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((url, init) => (String(url).includes("/rows")
      ? json({ ...rows, sample, rows: rows.rows.map((r) => ({ ...r, tags: [{ dim: "length", label: "Length", bucket: "0–9 chars" }] })) })
      : base(url as string, init)));
    await render();
    const last = () => new URLSearchParams(fetchMock.mock.calls.map((c) => String(c[0])).filter((u) => u.includes("/rows")).pop()!.split("?")[1]);
    expect(last().get("order")).toBe("review");
    const mode = (name: string) => [...container.querySelectorAll<HTMLButtonElement>(".sm-modes button")].find((b) => b.textContent === name)!;
    await act(async () => { mode("Manual select").click(); await new Promise((r) => setTimeout(r, 0)); });
    const bar = container.querySelector<HTMLButtonElement>("[data-testid=sample-bars] .sm-bar")!;
    await act(async () => { bar.click(); await new Promise((r) => setTimeout(r, 0)); });
    expect(last().getAll("f")).toEqual(["length:0–9 chars"]);
    expect(container.querySelector(".rows-bar")!.textContent).toContain("filtered by strata");
    expect(container.querySelector(".row .sm-tag")!.textContent).toBe("Length 0–9 chars");
    await act(async () => { mode("Autostratify").click(); await new Promise((r) => setTimeout(r, 0)); });
    expect(last().get("order")).toBe("auto");
    expect(last().get("prior")).toBeNull();
    const prior = container.querySelector<HTMLInputElement>(".sm-prior input")!;
    expect(container.querySelector(".sm-prior")!.textContent).toContain("Reviewed in other fields first (2)");
    await act(async () => { prior.click(); await new Promise((r) => setTimeout(r, 0)); });
    expect(last().get("prior")).toBe("true");
    expect(container.querySelector(".rows-bar")!.textContent).toContain("reviewed in other fields first");
  });

  const people = { people: [{ name: "Jared Diener", role: "sme", values: 112 }, { name: "Cadence Calixto", role: "sme", values: 0 },
    { name: "Eric Riddoch", role: "engineer", values: 22 }], waiting: 22 };
  const check = { annotation_id: "an-eric", type: "verdict" as const, verdict: "correct" as const, author: "Eric Riddoch",
    at: "2026-10-21T10:00:00Z", note: null, expected: null, rule_version_seen: 2, value_seen: "Value 1" };
  function annotated(counts: Record<string, number> | null) {
    const fetchMock = vi.mocked(fetch);
    const base = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((url, init) => {
      const u = String(url);
      if (u.includes("/annotators")) return json({ ...people, rules: counts });
      if (u.includes("/rows")) return json({ ...rows, rows: rows.rows.map((r, i) => (i === 1
        ? { ...r, state: "correct", verdict: check, engineer_checked: true, human_reviewed: false, checked: check } : r)) });
      return base(u, init);
    });
    return () => new URLSearchParams(fetchMock.mock.calls.map((c) => String(c[0])).filter((u) => u.includes("/rows")).pop()!.split("?")[1]);
  }

  it("filters every rule's rows by Annotated by, counts them in the rule list, and lets an expert confirm an engineer's check", async () => {
    const last = annotated({ "course-description": 17, "course-language": 0, "course-page": 0 });
    await render("#/c/avc/rules/course-description?row=GEOG1&by=waiting&v=correct");
    expect(last().get("by")).toBe("waiting");
    expect(last().get("verdict")).toBe("correct");
    expect(container.querySelector(".ab-btn")!.textContent).toContain("Any engineer · waiting for an expert");
    expect(container.querySelector("[data-rule=course-description] .rev")!.textContent).toBe("17");
    expect(container.querySelector("[data-rule=course-language]")!.className).toContain("dim");
    expect(container.querySelector("[data-testid=waiting-note]")!.textContent).toContain("22 values an engineer checked are waiting for an expert");
    expect(container.querySelector("[data-testid=waiting-note] .btn")!.textContent).toBe("Clear filter");
    expect(container.querySelector(".row.on [data-testid=review-line]")!.textContent)
      .toBe("✓ engineer-checkedEric Riddochengineer· 21 Oct · waiting for an expert");
    expect(container.querySelector(".row.on .byline")).toBeNull();  // the review line names who
    expect(container.querySelector(".row.on .cb.confirm")!.textContent).toBe("Confirm");
    await act(async () => { window.dispatchEvent(new KeyboardEvent("keydown", { key: "1" })); });
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
    expect(posted).toEqual([{ type: "verdict", author: "Jared", verdict: "correct", supersedes: "an-eric",
      target: { kind: "match", rule_id: "course-description", occurrence_key: "p1@html", page_stem: "p1" } }]);
    const line = container.querySelectorAll("[data-row-index]")[1].querySelector("[data-testid=review-line]")!;
    expect(line.textContent).toBe("✓ human-reviewed · publishedJaredconfirmed Eric Riddoch's check· just now");
    // the dropdown: people grouped by role with their values, searchable; picking one keeps it in the URL
    await act(async () => container.querySelector<HTMLButtonElement>(".ab-btn")!.click());
    const items = () => [...container.querySelectorAll(".ab-pop .ab-item, .ab-pop .ab-h")].map((x) => x.textContent);
    expect(items()).toEqual(["Anyone", "Not annotated yet", "Subject matter experts · human-reviewed", "Jared Diener112 values",
      "Cadence Calixtonone yet", "Engineers · waiting for an expert", "Any engineer · waiting for an expert22 values", "Eric Riddoch22 values"]);
    const q = container.querySelector<HTMLInputElement>(".ab-q")!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(q, "jar");
      q.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(items()).toEqual(["Subject matter experts · human-reviewed", "Jared Diener112 values", "Engineers · waiting for an expert"]);
    await act(async () => container.querySelector<HTMLButtonElement>(".ab-pop .ab-item")!.click());
    expect(location.hash).toBe("#/c/avc/rules/course-description?by=Jared+Diener&v=correct");
  });

  it("shows an engineer the check waiting, without Confirm or the experts' note", async () => {
    setIdentity("Eric Riddoch", "engineer");
    annotated(null);
    await render();
    expect(container.querySelector("[data-rule=course-description]")!.textContent).toContain("14 / 1,062 reviewed");
    expect(container.querySelector(".row.on [data-testid=review-line]")!.textContent).toContain("waiting for an expert");
    expect(container.querySelector(".row.on .cb.confirm")).toBeNull();
    expect(container.querySelector("[data-testid=waiting-note]")).toBeNull();
  });

  it("marks the right value by selecting it on the page, without pressing ✗ first, in one piece or several", async () => {
    await render();
    const p = () => pane.props!;
    expect(container.querySelector("[data-testid=answer-hint]")!.textContent).toBe("Wrong? Drag across the right text to mark it.");
    expect(p().captureSelection).toBe(true);
    const sel = (text: string, at: number) => ({ text, css_path: `html > body > p:nth-of-type(${at})`, char_start: 0,
      char_end: text.length, prefix: "", suffix: "", doc_start: at * 100, doc_end: at * 100 + text.length });
    const quotes = () => [...container.querySelectorAll(".row.on [data-testid=capture]")].map((q) => q.textContent);
    await act(async () => p().onSelection!(sel("Value 1", 1)));  // the value found itself: nothing to fix
    expect(quotes()).toEqual([]);
    await act(async () => p().onSelection!(sel("Second part", 3)));
    expect(container.querySelector(".row.on .cb.no")!.className).toContain(" on");
    await act(async () => p().onSelection!(sel("First part", 2)));  // another drag adds a piece, kept in page order
    expect(quotes()).toEqual(["First part", "Second part"]);
    expect(p().highlights.filter((h) => h.removable).map((h) => h.text)).toEqual(["First part", "Second part"]);
    expect(container.querySelector("[data-testid=pane]")!.textContent).toContain("Your answer is outlined (2 pieces)");
    await act(async () => p().onSelection!(sel("Second part, fixed", 3)));  // a drag over a piece replaces it
    expect(quotes()).toEqual(["First part", "Second part, fixed"]);
    await act(async () => p().onRemove!("capture-0"));  // × on the page
    expect(quotes()).toEqual(["Second part, fixed"]);
    await act(async () => p().onSelection!(sel("Stray", 4)));
    await act(async () => container.querySelector<HTMLButtonElement>(".row.on [aria-label='Remove piece 2']")!.click());  // × in the row
    expect(quotes()).toEqual(["Second part, fixed"]);
    await act(async () => p().onSelection!(sel("First part", 2)));
    await act(async () => container.querySelector<HTMLButtonElement>(".row.on .save")!.click());
    expect(posted[posted.length - 1]).toMatchObject({ type: "verdict", verdict: "wrong", expected: {
      text: "First part\nSecond part, fixed", css_path: "html > body > p:nth-of-type(2)",
      segments: [{ text: "First part" }, { text: "Second part, fixed", css_path: "html > body > p:nth-of-type(3)" }] } });
  });

  it("shows rules by kind with status icons and reviewed counts", async () => {
    await render();
    const groups = [...container.querySelectorAll(".group-h")].map((g) => g.textContent);
    expect(groups).toEqual(["Page rules0 of 1 approved", "Record locators0 of 0 approved", "Field rules1 of 2 approved"]);
    expect(container.querySelector("[data-rule=course-description]")?.textContent).toContain("14 / 1,062 reviewed");
    expect(container.querySelector("[data-tour=rule-list]")).not.toBeNull();
  });

  it("titles the rule with its CTDL term, collapses 'How this rule works', and enables Approve when nothing is wrong", async () => {
    await render();
    const term = container.querySelector<HTMLAnchorElement>(".rule-head a.term");
    expect(term?.textContent).toContain("ceterms:description");
    expect(term?.href).toBe("https://credreg.net/ctdl/terms/description");
    expect(container.querySelector(".rh-sub")?.textContent).toBe("Description · course pages");
    expect(container.querySelector<HTMLDetailsElement>("details.how")?.open).toBe(false);
    expect(container.querySelector<HTMLButtonElement>("button.approve")?.disabled).toBe(false);
    expect(container.querySelector("[data-tour=improve-rule]")).toBeNull();  // improving is one run for every rule, at the bottom of the list
  });

  it("asks before approving a column's rule: the golden dataset's columns now and after, then approves and publishes", async () => {
    const fetchMock = vi.mocked(fetch);
    const base = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((url, init) => {
      if (String(url).includes("/golden/approve/course-description")) {
        return json({ publishes: true, rule_id: "course-description", property: "Description", column: "description",
                      golden: "ruleset-v3", ruleset_version: 3, creates: false, now: ["inLanguage"], after: ["description", "inLanguage"],
                      where: "/g/catalogs/avc/versions/ruleset-v3/", values: 1062, human: 31, rule: 1031 });
      }
      if (init?.method === "POST") {
        posted.push(JSON.parse(String(init.body)));
        return json({ event: { annotation_id: "ap-1", type: "approve", author: "Jared", at: "now", target: { kind: "rule", rule_id: "course-description" } },
                      rule: summary({ status: "approved", approved_by: "Jared" }), elapsed_ms: 1,
                      published: { written: true, publication: "ruleset-v3", created: false, column: "description",
                                   columns: ["description", "inLanguage"], files: 1062 }, score: null });
      }
      return base(url, init);
    });
    await render();
    await act(async () => { container.querySelector<HTMLButtonElement>("button.approve")!.click(); });
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
    const dlg = document.querySelector<HTMLElement>(".apx")!;
    expect(dlg.querySelector("h2")?.textContent).toBe("Approve description and publish it?");
    expect([...dlg.querySelectorAll(".apx-cols tbody tr")].map((r) => r.textContent)).toEqual(
      ["NowinLanguage", "After approvingdescription, inLanguage"]);
    expect(dlg.querySelector(".apx-count")?.textContent).toContain("1,062 description values: 31 human-reviewed, 1,031 labelled by the rule.");
    expect(posted).toEqual([]);  // nothing approved yet
    const ok = [...dlg.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Approve and publish")!;
    await act(async () => { ok.click(); });
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
    expect(posted).toEqual([expect.objectContaining({ type: "approve", target: { kind: "rule", rule_id: "course-description" } })]);
    expect(document.querySelector(".apx")).toBeNull();
    expect([...document.querySelectorAll(".toast")].pop()?.textContent).toBe("Approved and published description in ruleset v3");
  });

  it("selects the row from the route, fades rows with a verdict, writes history lines", async () => {
    await render();
    const r = container.querySelectorAll(".row[data-row-index]");
    expect(r).toHaveLength(3);
    expect(r[1].classList.contains("on")).toBe(true);
    expect(r[0].classList.contains("done")).toBe(false);  // fixed: needs a fresh look
    expect(r[2].classList.contains("done")).toBe(true);   // correct: fades back
    expect(r[0].textContent).toContain("Fixed: Jared marked the previous version wrong; this matches the text he selected.");
    expect(container.querySelector(".rows-bar")?.textContent).toBe("3 courses · discussed first, then the likeliest problems, with every 5th row from a spread sample by length (3 groups)");
    expect(container.querySelector(".row .grp, .row .sm-tag")).toBeNull(); // no strata labels unless filtered or autostratified
  });

  it("✗ opens the inline expansion; Esc cancels; A records correct and moves on", async () => {
    await render();
    const on = () => container.querySelector(".row.on")!;
    await act(async () => { on().querySelector<HTMLButtonElement>(".cb.no")!.click(); });
    expect(on().querySelector(".expand.wrong")?.textContent).toContain("Select the right text on the page →");
    await act(async () => { window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })); });
    expect(on().querySelector(".expand")).toBeNull();
    await act(async () => { window.dispatchEvent(new KeyboardEvent("keydown", { key: "a" })); });
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
    expect(posted).toEqual([{ type: "verdict", author: "Jared", verdict: "correct", supersedes: null,
      target: { kind: "match", rule_id: "course-description", occurrence_key: "p1@html", page_stem: "p1" } }]);
    expect(container.querySelector(".row.on")?.getAttribute("data-row-index")).toBe("2");
    expect(container.querySelectorAll(".row[data-row-index]")[1].classList.contains("done")).toBe(true);
    expect(container.querySelector("[data-rule=course-description]")?.textContent).toContain("15 / 1,062 reviewed");
  });

  it("changing a verdict supersedes the previous one; the comment bubble posts a question when ticked", async () => {
    await render();
    const on = () => container.querySelector(".row.on")!;
    await act(async () => { container.querySelector<HTMLButtonElement>('[data-row-index="0"] .cb.talk')!.click(); });
    expect(on().getAttribute("data-row-index")).toBe("0");
    const input = on().querySelector<HTMLInputElement>(".expand.comment .note")!;
    const box = on().querySelector<HTMLInputElement>(".chk-expert input")!;
    await act(async () => {
      const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
      set.call(input, "Ask the college");
      input.dispatchEvent(new Event("input", { bubbles: true }));
      box.click();
    });
    await act(async () => { on().querySelector<HTMLButtonElement>(".save")!.click(); });
    expect(posted[0]).toMatchObject({ type: "verdict", verdict: "question", note: "Ask the college", supersedes: "an-old" });
  });

  it("greys out Approve with the reason while a course is wrong", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      const u = String(url);
      if (u.endsWith("/rules")) return json(rules);
      if (u.includes("/rows")) return json({ ...rows, rows: [row(0, { state: "wrong" })] });
      if (/\/rules\/[^/?]+$/.test(u)) return json(detail({ status: "needs work", open_wrong: 3 }));
      return json({});
    }));
    await render();
    const btn = container.querySelector<HTMLButtonElement>("button.approve")!;
    expect(btn.disabled).toBe(true);
    expect(btn.closest(".tipwrap")?.getAttribute("data-tip")).toMatch(/^Can't approve yet: 3 courses are marked wrong or missing/);
  });
});
