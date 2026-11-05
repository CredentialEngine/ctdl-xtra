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
  rule_id: "course-description", kind: "property", version: 2, title: "Description", subtitle: "ceterms:description",
  ctdl_property: "ceterms:description", property_label: "Description", locator: "locator-course-page", status: "in review",
  reviewed: 14, total: 1062, open_wrong: 0, open_missing: 0, questions: 0, approved_by: null, approved_at: null, comments: 0, ...o,
});

const rules: RulesResponse = { extraction: "rs-0002", ruleset_version: 2, groups: [
  { id: "page", kind: "page", label: "Page rules", collapsed: false, approved: 0, rules: [summary({ rule_id: "course-page", kind: "page", title: "Course pages", subtitle: "Which pages…", status: "needs work", open_wrong: 2 })] },
  { id: "other", kind: "property", label: "Other properties", collapsed: false, approved: 1, rules: [summary({}), summary({ rule_id: "course-language", title: "Language", status: "approved" })] },
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

const sel = (text: string, at: number) => ({ text, css_path: `html > body > p:nth-of-type(${at})`, char_start: 0,
  char_end: text.length, prefix: "", suffix: "", doc_start: at * 100, doc_end: at * 100 + text.length });

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
    expect(last().get("order")).toBe("auto");  // Autostratify by default (sme-fixes §9), the drawer shut
    expect(container.querySelector("[data-testid=sample]")!.className).not.toContain("open");
    const mode = (name: string) => [...container.querySelectorAll<HTMLButtonElement>(".sm-modes button")].find((b) => b.textContent === name)!;
    await act(async () => { mode("Manual select").click(); await new Promise((r) => setTimeout(r, 0)); });
    const bar = container.querySelector<HTMLButtonElement>("[data-testid=sample-bars] .sm-bar")!;
    await act(async () => { bar.click(); await new Promise((r) => setTimeout(r, 0)); });
    expect(last().getAll("f")).toEqual(["length:0–9 chars"]);
    expect(container.querySelector(".sm-chip")!.textContent).toContain("0–9 chars");
    expect(container.querySelector(".row .sm-tag")!.textContent).toBe("Length 0–9 chars");
    await act(async () => { mode("Autostratify").click(); await new Promise((r) => setTimeout(r, 0)); });
    expect(last().get("order")).toBe("auto");
    expect(last().get("prior")).toBeNull();
    const prior = container.querySelector<HTMLInputElement>(".sm-prior input")!;
    expect(container.querySelector(".sm-prior")!.textContent).toContain("Reviewed in other properties first (2)");
    await act(async () => { prior.click(); await new Promise((r) => setTimeout(r, 0)); });
    expect(last().get("prior")).toBe("true");
    expect(container.querySelector<HTMLInputElement>(".sm-prior input")!.checked).toBe(true);
  });

  const people = { people: [{ name: "Jared Diener", role: "sme", values: 112 }, { name: "Cadence Calixto", role: "sme", values: 0 },
    { name: "Eric Riddoch", role: "engineer", values: 22 }], waiting: 22, experts: 112, engineers: 30 };
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
    expect(items()).toEqual(["Anyone", "Not annotated yet", "Subject matter experts · human-reviewed", "Any subject matter expert112 values", "Jared Diener112 values",
      "Cadence Calixtonone yet", "Engineers · waiting for an expert", "Any engineer30 values", "Any engineer · waiting for an expert22 values", "Eric Riddoch22 values"]);
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
    const quotes = () => [...container.querySelectorAll(".row.on [data-testid=capture]")].map((q) => q.textContent);
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
    expect(groups).toEqual(["Page rules0 of 1 approved", "Other properties1 of 2 approved"]);
    expect(container.querySelector("[data-rule=course-description]")?.textContent).toContain("14 / 1,062 reviewed");
    expect(container.querySelector("[data-tour=rule-list]")).not.toBeNull();
  });

  it("titles the rule with its CTDL term, collapses 'How this rule works', and enables Approve when nothing is wrong", async () => {
    await render();
    const term = container.querySelector<HTMLAnchorElement>(".rule-head a.term");
    expect(term?.textContent).toContain("ceterms:description");
    expect(term?.href).toBe("https://credreg.net/ctdl/terms/description");
    expect(container.querySelector(".rh-sub")?.textContent).toBe("course pages");
    expect(container.querySelector(".rule-head h1")?.textContent).toBe("Description");
    expect(container.querySelector<HTMLDetailsElement>("details.how")?.open).toBe(false);
    expect(container.querySelector<HTMLButtonElement>("button.approve")?.disabled).toBe(false);
    expect(container.querySelector("[data-tour=improve-rule]")).toBeNull();  // improving is one run for every rule, at the bottom of the list
  });

  it("asks before approving a property's rule: the silver dataset's columns now and after, then approves and publishes it", async () => {
    const fetchMock = vi.mocked(fetch);
    const base = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((url, init) => {
      if (String(url).includes("/golden/approve/course-description")) {
        return json({ publishes: true, rule_id: "course-description", property: "Description", column: "description",
                      golden: "ruleset-v3", ruleset_version: 3, creates: false, now: ["inLanguage"], after: ["description", "inLanguage"],
                      where: "/g/catalogs/avc/versions/ruleset-v3/", values: 1062, human: 31, rule: 1031,
                      path_shown: "ceterms:description", xtra_extracts: true });
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
    expect(dlg.querySelector("h2")?.textContent).toBe("Approve Description and publish its silver dataset?");
    expect(dlg.textContent).toContain("also called the rule-matched dataset");
    expect(dlg.textContent).toContain("doesn't change");
    expect([...dlg.querySelectorAll(".apx-cols tbody tr")].map((r) => r.textContent)).toEqual(
      ["NowinLanguage", "After approvingdescription, inLanguage"]);
    expect(dlg.querySelector(".apx-path")?.textContent).toContain("ceterms:description");
    expect(dlg.querySelector(".apx-count")?.textContent).toContain("1,062 values to the silver dataset");
    expect(dlg.querySelector(".apx-count")?.textContent).toContain("31 human-reviewed");
    expect(dlg.querySelector(".apx-xtra")).toBeNull();  // xtra extracts it: nothing to warn about
    expect(posted).toEqual([]);  // nothing approved yet
    const ok = [...dlg.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Approve rule and publish silver dataset")!;
    await act(async () => { ok.click(); });
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
    expect(posted).toEqual([expect.objectContaining({ type: "approve", target: { kind: "rule", rule_id: "course-description" } })]);
    expect(document.querySelector(".apx")).toBeNull();
    expect([...document.querySelectorAll(".toast")].pop()?.textContent).toBe("Approved and published description to the silver dataset ruleset v3");
  });

  it("selects the row from the route, fades rows with a verdict, writes history lines", async () => {
    await render();
    const r = container.querySelectorAll(".row[data-row-index]");
    expect(r).toHaveLength(3);
    expect(r[1].classList.contains("on")).toBe(true);
    expect(r[0].classList.contains("done")).toBe(false);  // fixed: needs a fresh look
    expect(r[2].classList.contains("done")).toBe(true);   // correct: fades back
    expect(r[0].textContent).toContain("Fixed: Jared marked the previous version wrong; this matches the text he selected.");
    expect(container.querySelector(".rows-bar")).toBeNull();   // no summary line above the rows
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
  it("says when xtra doesn't extract the property yet, in the approve dialog, with its path", async () => {
    const fetchMock = vi.mocked(fetch);
    const base = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((url, init) => (String(url).includes("/golden/approve/course-description")
      ? json({ publishes: true, rule_id: "course-description", property: "Description", column: "description", golden: "ruleset-v3",
               ruleset_version: 3, creates: false, now: [], after: ["description"], where: "/g/", values: 40, human: 1, rule: 39,
               path_shown: "ceterms:creditValue → schema:minValue", xtra_extracts: false })
      : base(url, init)));
    await render();
    await act(async () => { container.querySelector<HTMLButtonElement>("button.approve")!.click(); });
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
    const dlg = document.querySelector<HTMLElement>(".apx")!;
    expect(dlg.querySelector(".apx-xtra")!.textContent).toContain("xtra doesn't extract this property yet");
    expect(dlg.querySelector(".apx-path")!.textContent).toContain("ceterms:creditValue → schema:minValue");
  });

  // --- property rules with a child path, no rule yet, and list properties (property-rules spec §4.2–§4.6) ----------------
  function serve(d: RuleDetail, r: RowsX = rows) {
    const fetchMock = vi.mocked(fetch);
    const base = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((url, init) => {
      const u = String(url);
      if (u.includes("/rows")) return json(r);
      if (/\/rules\/[^/?]+$/.test(u)) return json(d);
      return base(u, init);
    });
  }

  it("shows a child's path with arrows, its leaf term linked, and what the rule reads", async () => {
    serve(detail({ rule_id: "creditUnitMinValue", title: "Credit Unit Min Value", property_label: "Credit Unit Min Value", subtitle: "part of Credit Value",
                    ctdl_property: "ceterms:creditValue>schema:minValue", path_shown: "ceterms:creditValue → schema:minValue",
                    parent_label: "Credit Value", input: "Credit Value's value" }));
    await render("#/c/avc/rules/creditUnitMinValue?row=GEOG1");
    expect(container.querySelector(".rule-head .rh-path")!.textContent).toBe("ceterms:creditValue → schema:minValue");
    const term = container.querySelector<HTMLAnchorElement>(".rule-head a.term")!;
    expect(term.textContent).toBe("schema:minValue");
    expect(term.href).toBe("https://credreg.net/ctdl/terms/minValue");
    expect(container.querySelector(".rh-sub")!.textContent).toBe("part of Credit Value · course pages");
    expect(container.querySelector(".rh-input")!.textContent).toBe("Input: Credit Value's value");
  });

  it("a property with no rule yet says so, shows what it is for, and Approve is off; a page the value shows is marked by hand", async () => {
    serve(detail({ no_rule: true, what: "Whether the course is non-credit", status: "in review" }), { ...rows, rows: [
      row(0, { status: "none", value: null, css_path: null, char_start: null, char_end: null }),
      row(1, { status: "none", value: null, css_path: null, char_start: null, char_end: null }), row(2)] });
    await render("#/c/avc/rules/course-description?row=GEOG1");
    expect(container.querySelector(".rh-norule")!.textContent).toContain("No rule yet");
    expect(container.querySelector<HTMLDetailsElement>("details.how")!.open).toBe(true);
    expect(container.querySelector(".wwh")!.textContent).toContain("Whether the course is non-credit");
    expect(container.querySelector<HTMLButtonElement>("button.approve")!.disabled).toBe(true);
    expect(container.querySelector(".row.on")!.textContent).toContain("no rule yet");
    expect(pane.props!.captureSelection).toBe(true);
    await act(async () => pane.props!.onSelection!({ text: "Yes", css_path: "html > p", char_start: 0, char_end: 3, prefix: "", suffix: "", doc_start: 1, doc_end: 4 }));
    await act(async () => container.querySelector<HTMLButtonElement>(".row.on .save")!.click());
    expect(posted[posted.length - 1]).toMatchObject({ type: "verdict", verdict: "wrong", expected: { text: "Yes", css_path: "html > p" },
      target: { kind: "match", rule_id: "course-description", occurrence_key: "p1@html" } });
  });

  const correct = { annotation_id: "an-i1", type: "verdict" as const, verdict: "correct" as const, author: "Seth", at: "t", note: null,
    expected: null, rule_version_seen: 2, value_seen: "Lab - 35" };
  const listRows = (extra: Partial<RowX> = {}): RowsX => ({ ...rows, rows: [row(0), row(1, { status: "found", value: "Lecture - 87.5\nLab - 35",
    css_path: null, char_start: null, char_end: null, missing_items: [],
    items: [
      { value_index: 0, value: "Lecture - 87.5", css_path: "html > p:nth-of-type(1)", char_start: 0, char_end: 14, state: null, verdict: null, human: false },
      { value_index: 1, value: "Lab - 35", css_path: "html > p:nth-of-type(1)", char_start: 20, char_end: 28, state: "correct", verdict: correct, human: false }],
    ...extra }), row(2)] });

  it("a list row shows one line per item, each with its own ✓ and ✕, and no ✓ or ✕ for the row", async () => {
    serve(detail({ list: true }), listRows());
    await render();
    const lines = [...container.querySelectorAll(".row.on [data-testid=item]")];
    expect(lines.map((l) => l.querySelector(".item-v")!.textContent)).toEqual(["Lecture - 87.5", "Lab - 35"]);
    expect(container.querySelector(".row.on .cb.ok")).toBeNull();
    expect(container.querySelector(".row.on .cb.no")).toBeNull();
    expect(container.querySelector(".row.on .cb.talk")).not.toBeNull();
    await act(async () => container.querySelector<HTMLButtonElement>("[aria-label='Correct Lecture - 87.5']")!.click());
    expect(posted[posted.length - 1]).toEqual({ type: "verdict", author: "Jared", verdict: "correct", supersedes: null,
      target: { kind: "match", rule_id: "course-description", occurrence_key: "p1@html", item: true, value_index: 0 } });
    expect(posted).toHaveLength(1);
    await act(async () => container.querySelector<HTMLButtonElement>("[aria-label='Correct Lab - 35']")!.click());
    expect(posted).toHaveLength(1);  // Lab - 35 is already correct: nothing new to save
    await act(async () => container.querySelector<HTMLButtonElement>("[aria-label='Wrong Lab - 35']")!.click());
    expect(posted[posted.length - 1]).toMatchObject({ verdict: "wrong", supersedes: "an-i1", target: { item: true, value_index: 1 } });
  });

  it("＋ Select a missing item on the page adds one the rule missed, listed under the row", async () => {
    serve(detail({ list: true }), listRows());
    await render();
    expect(pane.props!.captureSelection).toBe(false);  // a list's row: a selection isn't a whole-value answer
    await act(async () => container.querySelector<HTMLButtonElement>(".row.on .add-item")!.click());
    expect(pane.props!.captureSelection).toBe(true);
    await act(async () => pane.props!.onSelection!({ text: "Lab - 52.5", css_path: "html > p:nth-of-type(2)", char_start: 0, char_end: 9,
      prefix: "", suffix: "", doc_start: 200, doc_end: 209 }));
    expect(container.querySelector(".row.on .add-item-q")!.textContent).toContain("Lab - 52.5");
    await act(async () => container.querySelector<HTMLButtonElement>(".row.on .add-item-q .save")!.click());
    expect(posted[posted.length - 1]).toMatchObject({ type: "verdict", verdict: "missing",
      expected: { text: "Lab - 52.5", css_path: "html > p:nth-of-type(2)", char_start: 0, char_end: 9 },
      target: { kind: "match", rule_id: "course-description", occurrence_key: "p1@html", item: true } });
    expect(container.querySelector(".row.on .missing-items")!.textContent).toContain("Lab - 52.5");
  });

  // --- sme-fixes §1: the highlight bar ---------------------------------------------------------------------------
  const bar = (id: string, s: ReturnType<typeof sel>) => {
    const a = pane.props!.barActions?.find((x) => x.id === id);
    if (!a) throw new Error(`no ${id} on the highlight bar`);
    return act(async () => a.run(s));
  };

  it("a selection shows the highlight bar: the comment bubble, ✓ In answer, ✕ Not in answer, each with a tooltip", async () => {
    await render();
    expect(pane.props!.barActions!.map((a) => a.id)).toEqual(["comment", "in", "out"]);
    expect(pane.props!.barActions!.map((a) => a.label).slice(1)).toEqual(["✓ In answer", "✕ Not in answer"]);
    expect(typeof pane.props!.barActions![0].label).not.toBe("string");  // the app's bubble icon, not an emoji
    expect(pane.props!.captureFirst).toBe(false);
    expect(pane.props!.barActions!.every((a) => a.title.length > 30)).toBe(true);
    // a selection equal to the found value is never dropped: it is a piece like any other
    await bar("in", sel("Value 1", 1));
    expect([...container.querySelectorAll(".row.on [data-testid=capture]")].map((q) => q.textContent)).toEqual(["Value 1"]);
  });

  it("saves ✓ in and ✕ out segments with their polarity and draws them green and red dashed", async () => {
    await render();
    await bar("out", sel("LIMITATION ON ENROLLMENT", 1));
    expect(container.querySelector(".row.on .cb.no")!.className).toContain(" on");  // ✕ marks the row ✗
    expect(container.querySelector(".row.on .sel-pol")!.textContent).toBe("✕ not in answer");
    // the ✗ draft is open: a drag is a piece of the answer at once
    await act(async () => pane.props!.onSelection!(sel("Work Experience Education", 2)));
    expect(pane.props!.highlights.filter((h) => h.id.startsWith("capture-")).map((h) => [h.kind, h.text]))
      .toEqual([["excluded", "LIMITATION ON ENROLLMENT"], ["expected", "Work Experience Education"]]);
    await act(async () => container.querySelector<HTMLButtonElement>(".row.on .save")!.click());
    expect(posted[posted.length - 1]).toMatchObject({ type: "verdict", verdict: "wrong", expected: {
      text: "Work Experience Education", css_path: "html > body > p:nth-of-type(2)",
      segments: [{ text: "LIMITATION ON ENROLLMENT", polarity: "out" }, { text: "Work Experience Education", polarity: "in" }] } });
  });

  it("only ✕ pieces: the expected text is the value found without them; saved segments are drawn by polarity", async () => {
    const out = { annotation_id: "an-o", type: "verdict" as const, verdict: "wrong" as const, author: "Jared", at: "t", note: null,
      rule_version_seen: 2, value_seen: "x", expected: { text: "Body", css_path: "html > p", char_start: 0, char_end: 4, segments: [
        { text: "Head", css_path: "html > p", char_start: 0, char_end: 4, polarity: "out" as const },
        { text: "Body", css_path: "html > p:nth-of-type(2)", char_start: 0, char_end: 4 }] } };
    serve(detail(), { ...rows, rows: [row(0), row(1, { value: "Head\nBody", state: "wrong", verdict: out }), row(2)] });
    await render();
    expect(pane.props!.highlights.filter((h) => h.id.startsWith("expected-")).map((h) => h.kind)).toEqual(["excluded", "expected"]);
    await act(async () => container.querySelectorAll<HTMLElement>(".row")[1].click());
    await bar("out", sel("Head", 1));
    await act(async () => container.querySelector<HTMLButtonElement>(".row.on .save")!.click());
    expect(posted[posted.length - 1]).toMatchObject({ expected: { text: "Body", segments: [{ text: "Head", polarity: "out" }] } });
  });

  it("after ✗, a drag is kept as the answer at once (Jared, 2026-11-05); the bar still offers comment, ✓ and ✕", async () => {
    await render();
    await act(async () => container.querySelector<HTMLButtonElement>(".row.on .cb.no")!.click());
    expect(pane.props!.captureSelection && pane.props!.captureFirst).toBe(true);
    expect(pane.props!.barActions!.map((a) => a.id)).toEqual(["comment", "in", "out"]);
    await act(async () => pane.props!.onSelection!(sel("7", 1)));
    expect([...container.querySelectorAll(".row.on [data-testid=capture]")].map((q) => q.textContent)).toEqual(["7"]);
    await act(async () => container.querySelector<HTMLButtonElement>(".row.on .save")!.click());
    expect(posted[posted.length - 1]).toMatchObject({ type: "verdict", verdict: "wrong", expected: { text: "7" } });
  });

  it("✕ Not in answer on the bar after ✗ marks the piece just dragged as out", async () => {
    await render();
    await act(async () => container.querySelector<HTMLButtonElement>(".row.on .cb.no")!.click());
    await act(async () => pane.props!.onSelection!(sel("LIMITATION ON ENROLLMENT", 1)));
    await bar("out", sel("LIMITATION ON ENROLLMENT", 1));
    expect(pane.props!.highlights.filter((h) => h.id.startsWith("capture-")).map((h) => h.kind)).toEqual(["excluded"]);
  });

  it("a comment goes with either answer: bubble, then ✓, saves the ✗ with its answer and the comment pinned to the text", async () => {
    await render();
    const s = sel("Work Experience Education", 2);
    expect(pane.props!.barActions!.find((a) => a.id === "comment")!.keepOpen).toBe(true);  // then ✓ or ✕ on the same bar
    await bar("comment", s);
    await bar("in", s);
    expect(container.querySelector(".row.on [data-testid=anchor]")!.textContent).toBe("Work Experience Education");
    expect([...container.querySelectorAll(".row.on [data-testid=capture]")].map((q) => q.textContent)).toEqual(["Work Experience Education"]);
    const note = container.querySelector<HTMLInputElement>(".row.on .expand .note")!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(note, "Only this part");
      note.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => container.querySelector<HTMLButtonElement>(".row.on .save")!.click());
    expect(posted.slice(-2)).toMatchObject([
      { type: "verdict", verdict: "wrong", note: null, expected: { text: "Work Experience Education" } },
      { type: "comment", note: "Only this part", anchor: { text: "Work Experience Education" } }]);
  });

  it("after ✗ and a drag, the bubble pins a comment to that piece and ✕ marks it out: both are kept", async () => {
    await render();
    await act(async () => container.querySelector<HTMLButtonElement>(".row.on .cb.no")!.click());
    const s = sel("LIMITATION ON ENROLLMENT", 1);
    await act(async () => pane.props!.onSelection!(s));
    await bar("comment", s);
    await bar("out", s);
    expect(container.querySelector(".row.on .sel-pol:not(.pin)")!.textContent).toBe("✕ not in answer");
    expect(container.querySelector(".row.on [data-testid=anchor]")!.textContent).toBe("LIMITATION ON ENROLLMENT");
  });

  it("💬 opens the comment box anchored to the text; the comment is saved with its anchor and drawn as a numbered bubble", async () => {
    await render();
    await bar("comment", sel("This belongs in Entry Condition", 3));
    expect(container.querySelector(".row.on [data-testid=anchor]")!.textContent).toBe("This belongs in Entry Condition");
    expect(pane.props!.highlights.find((h) => h.kind === "note")).toMatchObject({ badge: 1, text: "This belongs in Entry Condition" });
    const note = container.querySelector<HTMLInputElement>(".row.on .expand .note")!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(note, "Not Description");
      note.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => container.querySelector<HTMLButtonElement>(".row.on .save")!.click());
    expect(posted[posted.length - 1]).toMatchObject({ type: "comment", note: "Not Description",
      anchor: { css_path: "html > body > p:nth-of-type(3)", char_start: 0, char_end: 31, text: "This belongs in Entry Condition" } });
  });

  // --- sme-fixes §2: deep links ------------------------------------------------------------------------------------
  it("selecting a row writes ?row= to the address bar, replacing the entry (no new history entry)", async () => {
    history.replaceState(null, "", "#/c/avc/rules/course-description?row=GEOG1");
    const replace = vi.spyOn(history, "replaceState");
    const push = vi.spyOn(history, "pushState");
    await render();
    await act(async () => container.querySelectorAll<HTMLElement>(".row")[2].click());
    expect(location.hash).toBe("#/c/avc/rules/course-description?row=p2%40html");
    await act(async () => { window.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", shiftKey: true })); });
    expect(location.hash).toBe("#/c/avc/rules/course-description?row=p1%40html");
    expect(replace).toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
    replace.mockRestore(); push.mockRestore();
  });

  // --- sme-fixes §9: defaults ------------------------------------------------------------------------------------
  it("'Annotated by' is Anyone by default; ?by= is written only when a person is picked", async () => {
    const last = annotated(null);
    await render("#/c/avc/rules/course-description");
    expect(last().get("by")).toBeNull();
    expect(container.querySelector(".ab-btn")!.textContent).toContain("Anyone");
    await act(async () => container.querySelector<HTMLButtonElement>(".ab-btn")!.click());
    const item = (t: string) => [...container.querySelectorAll<HTMLButtonElement>(".ab-pop .ab-item")].find((b) => b.textContent!.startsWith(t))!;
    await act(async () => item("Anyone").click());
    expect(location.hash).toBe("#/c/avc/rules/course-description");
  });

  // --- sme-fixes §3: course blocks ---------------------------------------------------------------------------------
  const loc = (o: Partial<RowX>, i: number, stem: string, n: number): RowX => row(i, { key: `${stem}@b${i}`, occurrence_key: `${stem}@b${i}`,
    page_stem: stem, page_title: "View - CurriQunet META", value: `INTD ${i} - Course ${i}`, page_courses: n, course_key: `INTD${i}`,
    css_path: `html > div:nth-of-type(${i + 1})`, ...o });
  const ccsf = (): RowsX => ({ ...rows, rule_id: "locator-course-page", total: 5, focus_index: null, rows: [
    loc({}, 0, "intd", 3), loc({}, 1, "intd", 3), loc({}, 2, "intd", 3),
    loc({ course_key: "SPAN1" }, 3, "span", 2), loc({ course_key: "SPAN2" }, 4, "span", 2)] });
  const locator = (repeat: string | null) => detail({ rule_id: "locator-course-page", kind: "locator", property_label: null,
    title: repeat ? `Course blocks: every ${repeat} on the page` : "Whole page is one course", subtitle: "s",
    definition: { page_rules: ["course-page"], repeat, repeat_filter: repeat ? { selector: ".course-title", regex: "\\d" } : null } });
  /** A locator's rows, and the overlay of the first page (its course boxes). */
  const serveLoc = (repeat: string | null, data: RowsX = ccsf()) => {
    serve(locator(repeat), data);
    const fetchMock = vi.mocked(fetch);
    const base = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((url, init) => (String(url).includes("/overlay") ? json({ marks: [], blocks: data.rows.slice(0, 3).map((r, n) => (
      { occurrence_key: r.occurrence_key, css_path: r.css_path, n: n + 1, course_key: r.course_key })) }) : base(url as string, init)));
  };
  const key = (k: string, shiftKey = false) => act(async () => { window.dispatchEvent(new KeyboardEvent("keydown", { key: k, shiftKey })); });

  it("a repeating locator has one row per page with its courses nested; Tab / Shift+Tab / Enter / Esc move between levels", async () => {
    serveLoc(".course-summary-wrapper");
    await render("#/c/ccsf/rules/locator-course-page");
    const heads = () => [...container.querySelectorAll("[data-testid=page-head]")].map((h) => h.querySelector(".ph-t")!.textContent);
    expect(heads()).toEqual(["INTD · View - CurriQunet META · 3 courses", "SPAN · View - CurriQunet META · 2 courses"]);
    expect(container.querySelector("h1")!.textContent).toBe("Course blocks: every .course-summary-wrapper on the page");
    expect(container.querySelector(".tech")!.textContent).toContain(".course-title inside it matches \\d");  // repeat_filter.selector
    const on = () => container.querySelector(".row.on")!;
    expect(on().getAttribute("data-testid")).toBe("page-head");  // starts on the first page row
    expect(container.querySelectorAll(".row.in-page").length).toBe(3);  // only the open page's courses are listed
    expect(container.querySelector(".add-course")!.textContent).toBe("+ Add a course this rule missed");
    expect(pane.props!.focusId).toBeNull();  // on a page row no course box is filled
    await key("Enter");
    expect(on().querySelector(".code")!.textContent).toBe("INTD0");
    expect(location.hash).toContain("row=intd%40b0");
    await key("Tab");
    expect(on().querySelector(".code")!.textContent).toBe("INTD1");
    await key("Escape");  // back up to the page row
    expect(on().getAttribute("data-testid")).toBe("page-head");
    expect(location.hash).toContain("row=intd");
    await key("Tab");  // at page level: the next page
    expect(on().textContent).toContain("SPAN");
    expect(container.querySelectorAll(".row.in-page").length).toBe(2);
    await key("Tab", true);
    expect(on().textContent).toContain("INTD");
    await key("Enter"); await key("Tab"); await key("Tab"); await key("Tab");  // after the last course: the next page row
    expect(on().getAttribute("data-testid")).toBe("page-head");
    expect(on().textContent).toContain("SPAN");
    await key("Enter"); await key("Tab", true);  // Shift+Tab on a page's first course: up to its page row
    expect(on().getAttribute("data-testid")).toBe("page-head");
  });

  it("✓ on a page row accepts all its courses; boxes turn green / red with their verdicts, only the current one filled", async () => {
    const wrong = { annotation_id: "an-w", type: "verdict" as const, verdict: "wrong" as const, author: "Jared", at: "t", note: null,
      expected: null, rule_version_seen: 2, value_seen: "x" };
    const data = ccsf();
    data.rows[1] = { ...data.rows[1], state: "wrong", verdict: wrong };
    serveLoc(".course-summary-wrapper", data);
    await render("#/c/ccsf/rules/locator-course-page");
    expect(pane.props!.highlights.filter((h) => h.kind === "block").map((h) => h.state)).toEqual([null, "bad", null]);
    await key("Enter");
    expect(pane.props!.focusId).toBe("intd@b0");  // the current course is the filled one
    await key("Escape");
    await act(async () => container.querySelector<HTMLButtonElement>("[data-testid=page-head] .cb.ok")!.click());
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
    expect(posted.map((e) => (e as { target: { occurrence_key: string } }).target.occurrence_key)).toEqual(["intd@b0", "intd@b1", "intd@b2"]);
    expect(posted.every((e) => (e as { verdict: string }).verdict === "correct")).toBe(true);
    expect(container.querySelector(".row.on")!.textContent).toContain("SPAN");  // on to the next page
  });

  it("a locator without repeat keeps one row per course", async () => {
    serveLoc(null);
    await render("#/c/avc/rules/locator-course-page");
    expect(container.querySelector("[data-testid=page-head]")).toBeNull();
    expect(container.querySelectorAll(".row[data-row-index]").length).toBe(5);
    expect(container.querySelector("h1")!.textContent).toBe("Whole page is one course");
  });

  it("the page pane outlines every item of the list on its page", async () => {
    serve(detail({ list: true }), listRows());
    await render();
    expect(pane.props!.highlights.filter((h) => h.id.startsWith("item-")).map((h) => [h.text, h.cssPath])).toEqual([
      ["Lecture - 87.5", "html > p:nth-of-type(1)"], ["Lab - 35", "html > p:nth-of-type(1)"]]);
  });
});
