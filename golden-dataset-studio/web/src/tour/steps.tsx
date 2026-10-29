// The steps of the tour (spec §7.8), in order. Each lights one real area of the screen and, where it helps,
// does what the reader would do by hand (select a row and press ✗, open the comment, switch to HTML, go to the
// locator view, open "How this rule works", go to Compare, go to Evals). What a step does, it undoes when the reader leaves it.
// The tour never saves anything: ✓, Save and Approve are never pressed.
import type { ReactNode } from "react";
import { Ico } from "../shell/icons";
import { fmtDate } from "../shell/ui";
import type { SessionStep, Side, TourCtx } from "./model";

export type Facts = Record<string, string | number | boolean | null>;
/** A selector, or a function finding the element(s) to light (their bounding box is lit as one area). */
export type Target = string | (() => Element | Element[] | null);

export interface Step extends SessionStep {
  id: string;
  title: string;
  targets: Target[];
  accents?: Target[];
  /** Where the card goes, when not beside the first target (e.g. over the rule list, to keep a row in sight). */
  anchor?: Target;
  sides?: Side[];
  /** Read from the screen what the card quotes (the real numbers, the real reason). */
  read?(ctx: TourCtx): Facts;
  body(f: Facts, ctx: TourCtx): ReactNode;
  /** Said instead when this catalog has nothing to show for the step. */
  absent(ctx: TourCtx): ReactNode;
}

// --- the screen ---------------------------------------------------------------------------------------------------
const q = <T extends Element = HTMLElement>(sel: string) => document.querySelector<T>(sel);
const qa = (sel: string) => [...document.querySelectorAll<HTMLElement>(sel)];
const click = (sel: string) => { const el = q(sel); el?.click(); return !!el; };
const text = (sel: string) => q(sel)?.textContent?.trim() || null;

/** The Rules tab is showing this rule (the route and the loaded rule head both say so). */
export function showing(ctx: TourCtx, ruleId: string | null): boolean {
  if (!ruleId || q(".rule-list .rule-item.on")?.getAttribute("data-rule") !== ruleId) return false;
  const want = ctx.headText[ruleId];
  return !want || (text(".rule-head h1") ?? "").includes(want);
}
const onBase = (ctx: TourCtx) => showing(ctx, ctx.ruleId);

const ROW = ".rows .row.on";

/** The heading over Jared's earlier verdicts and its first few rows. */
function verdictBlock(): Element[] | null {
  const h = qa(".cmp-layout h2").find((x) => /verdicts/i.test(x.textContent ?? ""));
  if (!h) return null;
  const rows = qa(".cmp-layout .crec.cv").slice(0, 4);
  return rows.length ? [h, ...rows] : [h, ...(h.nextElementSibling ? [h.nextElementSibling] : [])];
}

/** The rule's value highlighted on the saved page (inside the page pane's iframe), else the whole page pane. */
function pageValue(): Element[] | Element | null {
  const d = q<HTMLIFrameElement>(".gpp-body iframe")?.contentDocument;
  const marks = d ? [...d.querySelectorAll(".gds-box.gds-value")] : [];
  return marks.length ? marks : q("[data-tour=page-pane]");
}


/** Each group of the rule list (page rules, record locators, field rules). */
const group = (i: number) => () => qa(".rule-list .rule-group")[i] ?? null;

// --- small pieces of the cards ---------------------------------------------------------------------------------------
const I = ({ name }: { name: string }) => <span className="tour-ico"><Ico name={name} /></span>;
const plural = (n: number, one: string, many: string) => `${n.toLocaleString("en-US")} ${n === 1 ? one : many}`;

export const STEPS: Step[] = [
  {
    id: "rules",
    title: "The rules, and how far each one has got",
    route: (c) => c.base,
    ready: onBase,
    targets: ["[data-tour=rule-list]"],
    accents: ["[data-tour=rule-status]", "[data-tour=reviewed-count]"],
    read: () => ({
      reviewed: text("[data-tour=reviewed-count]"),
      approved: qa(".rule-list .rule-item .ico[title='approved']").length,
      needs: qa(".rule-list .rule-item .ico[title='needs work']").length,
      review: qa(".rule-list .rule-item .ico[title='in review']").length,
    }),
    body: (f) => (
      <>
        <p>Every rule that reads this catalog, by kind: <b>page rules</b> find the course pages, <b>record locators</b> find
          each course on a page, and <b>field rules</b> read one field of each course.</p>
        <ul className="tour-legend">
          <li><Ico name="approved" /><span><b>Approved:</b> every course it found is right.</span></li>
          <li><Ico name="needs work" /><span><b>Needs work:</b> at least one course is marked wrong or missing.</span></li>
          <li><Ico name="in review" /><span><b>In review:</b> nothing wrong yet, not approved yet.</span></li>
        </ul>
        {f.reviewed && <p>“{f.reviewed}” counts the courses that have a verdict out of all the rule found.</p>}
        <p className="faint">Here: {Number(f.approved)} approved · {Number(f.needs)} need work · {Number(f.review)} in review.</p>
      </>
    ),
    absent: () => <p>The rule list hasn't loaded.</p>,
  },
  {
    id: "kinds",
    title: "Three kinds of rules, one after another",
    route: (c) => c.base,
    ready: (c) => onBase(c) && qa(".rule-list .rule-group").length > 0,
    targets: [group(0), group(1), group(2)],
    sides: ["right", "below"],
    read: () => {
      const g = qa(".rule-list .rule-group");
      const first = (i: number) => g[i]?.querySelector(".rule-item .nm")?.textContent?.trim() ?? null;
      const n = (i: number) => g[i]?.querySelectorAll(".rule-item").length ?? 0;
      return { page: first(0), pages: n(0), locator: first(1), locators: n(1), field: first(2), fields: n(2) };
    },
    body: (f) => (
      <>
        <p>A catalog is read in three steps, and each step has its own rules:</p>
        <ol className="tour-kinds">
          <li><b>Page rules</b> decide <b>which saved pages</b> hold courses: the catalog's course pages
            {f.page ? <> (e.g. “{String(f.page)}”)</> : null}. Their rows are pages.</li>
          <li><b>Record locators</b> find <b>where each course starts and ends</b> on those pages, whether a page holds
            one course or many{f.locator ? <> (e.g. “{String(f.locator)}”)</> : null}.
            Their rows are courses.</li>
          <li><b>Field rules</b> read <b>one field</b> (Description, Coded Notation, Name …) inside each course a locator
            found{f.field ? <> (e.g. “{String(f.field)}”)</> : null}. Their rows are that field's values.</li>
        </ol>
        <p>So a wrong page rule or locator affects every field after it. A <b>missing</b> course or page can only be
          added on a page rule or a locator; on a field rule an empty value is simply wrong.</p>
        <p className="faint">Here: {Number(f.pages)} page {Number(f.pages) === 1 ? "rule" : "rules"} · {Number(f.locators)} record{" "}
          {Number(f.locators) === 1 ? "locator" : "locators"} · {Number(f.fields)} field {Number(f.fields) === 1 ? "rule" : "rules"}.</p>
      </>
    ),
    absent: () => <p>The rule list hasn't loaded.</p>,
  },
  {
    id: "rows",
    title: "One row per course: discussed, then likeliest problems",
    route: (c) => c.base,
    ready: onBase,
    targets: ["[data-tour=rows]"],
    accents: ["[data-testid=sample] .sm-head"],
    read: () => ({ bar: text(".rows-bar") }),
    body: (f) => (
      <>
        <p>Each row is what the selected rule found for one course{f.bar ? <> ({String(f.bar).split(" · ")[0]})</> : null}.
          Rows a teammate commented on or was unsure about come <b>first</b>, until someone marks them correct. Then the{" "}
          <b>likeliest problems</b>, mixed with a spread sample, so you see every kind of value early.</p>
        <p>The <b>Sample</b> drawer above the rows changes that order: <b>Autostratify</b> goes through a few rows of each
          kind (by length, leading label, paragraphs …), rarest first; <b>Shuffle</b> is random; <b>Manual select</b>{" "}
          shows each kind as a bar chart to filter on.</p>
        <p>Rows that already have a verdict fade back, so the eye goes to the rows still waiting. Each shows its verdict
          and who gave it.</p>
        <p>Click a row, or press <kbd>Tab</kbd>, and its value is highlighted on the saved page at the right.</p>
      </>
    ),
    absent: () => <p>This rule has no rows.</p>,
  },
  {
    id: "annotated-by",
    title: "Annotated by: whose checks you're seeing",
    route: (c) => c.base,
    ready: (c) => onBase(c) && !!q(".sm-row"),
    targets: [".sm-row"],
    accents: ["[data-testid=annotated-by] .ab-btn"],
    sides: ["below", "right"],
    body: () => (
      <>
        <p><b>Annotated by</b> shows only the rows one person annotated (or any subject matter expert, any engineer, or{" "}
          <b>Not annotated yet</b>), and the switch beside
          it only ✓ correct, ✕ wrong or notes. The rule list then counts each rule's matching rows. The Records tab has the
          same dropdown.</p>
        <p>A subject matter expert's ✓ makes a value <b>human-reviewed</b>: it goes into the golden dataset at once, whether
          or not its rule is approved. An engineer's ✓ waits for an expert, who sees <b>Confirm</b> (<kbd>1</kbd>) on it.</p>
      </>
    ),
    absent: () => <p>The rule hasn't loaded.</p>,
  },
  {
    id: "verdict",
    title: "✓ correct, ✗ wrong: select the right text on the page",
    route: (c) => c.base,
    ready: (c) => onBase(c) && !!q(`${ROW} .cb.no`),
    arrive: () => {
      if (q(`${ROW} .expand.wrong`)) return;
      click(`${ROW} .cb.no`);
      return () => void click(`${ROW} .expand .btn.cancel`);
    },
    targets: [ROW, pageValue],
    accents: [`${ROW} .cb.no`, pageValue],
    // over the rule list: the row, its ✗ and the page beside it all stay in sight
    anchor: "[data-tour=rule-list]",
    sides: [],
    body: () => (
      <>
        <p><I name="correct" /> or <kbd>1</kbd>: the value is right.</p>
        <p><I name="wrong" /> or <kbd>2</kbd>: it's wrong. <b>✗ has been pressed for you</b> on this row (lit): the row
          opens and asks you to <b>select the right text on the page →</b>.</p>
        <p>On the saved page, the <b>lit area</b> is what the rule found. Drag across the text it <i>should</i> have
          found, usually in or next to it. The row then shows only your selection, an optional note, and Save / Cancel.</p>
        <p>An empty value works the same way: if the rule found nothing but the page has one, that's ✗ plus the right text.</p>
        <p className="faint">Nothing is saved during the tour.</p>
      </>
    ),
    absent: () => <p>This rule has no rows to mark.</p>,
  },
  {
    id: "comment",
    title: "A comment, or a question for the institution",
    route: (c) => c.base,
    ready: (c) => onBase(c) && !!q("[data-tour=comment-button]"),
    arrive: () => {
      if (q(`${ROW} .expand.comment`)) return;
      click("[data-tour=comment-button]");
      return () => void click(`${ROW} .expand .btn.cancel`);
    },
    targets: [ROW],
    accents: ["[data-tour=comment-button]", `${ROW} .chk-expert`],
    sides: ["below", "above", "right"],
    body: () => (
      <>
        <p>The speech bubble <I name="bubble" /> (<kbd>3</kbd>) has been clicked for you. It opens a short note for
          whoever fixes the rule.</p>
        <p>Tick <b>Question for the institution</b> <I name="inst" /> for things only the college can answer. Its question
          is kept out of the prompt's list of rule bugs.</p>
      </>
    ),
    absent: () => <p>This rule has no rows to comment on.</p>,
  },
  {
    id: "page",
    title: "The saved page",
    route: (c) => c.base,
    ready: (c) => onBase(c) && !!q("[data-tour=page-html-switch] button"),
    arrive: () => {
      const [page, html] = qa("[data-tour=page-html-switch] button");
      if (!html || html.classList.contains("on")) return;
      html.click();
      return () => page?.click();
    },
    targets: ["[data-tour=page-pane]"],
    accents: ["[data-tour=page-html-switch]", "[data-tour=open-live]"],
    sides: ["left", "below"],
    body: (_f, c) => (
      <>
        <p>The whole page as it was saved{c.crawl ? <> on {fmtDate(c.crawl)}</> : null}, in a browser-like frame with a tab
          per page in view. The selected row's value is <b>highlighted</b> and scrolled into view.</p>
        <p><b>Page | HTML</b>: the HTML view, switched on for you, shows the saved markup around the value with the same
          numbered highlight. It's for cases where the rendered page hides something.</p>
        <p><I name="ext" /> <b>Open live</b> opens the college's page as it is today, which may have changed since.</p>
      </>
    ),
    absent: () => <p>No saved page is showing for this row.</p>,
  },
  {
    id: "locator",
    title: "What a record locator found, and what it missed",
    route: (c) => c.locator,
    ready: (c) => showing(c, c.locatorId) && !!q("[data-tour=locator-legend]"),
    targets: ["[data-tour=page-pane]"],
    accents: ["[data-tour=locator-legend]", "[data-tour=add-missed]"],
    sides: ["left", "below"],
    read: () => ({ marks: qa(".gpp-body .gds-badge").length > 0, rule: text(".rule-head h1") }),
    body: (f) => (
      <>
        <p>This is a record locator's view{f.rule ? <> (“{String(f.rule)}”)</> : null}, opened for you. Its rows are the
          courses it found on each page.</p>
        <ul>
          <li>On the page, every course block it found is <b>outlined and numbered</b>.</li>
          <li>Text that looks like a course code but sits outside every outline is <b>marked</b> in another style: a course
            the rule may have missed. Pages with marked text come first.</li>
        </ul>
        <p><b>Add a course this rule missed</b> lets you select that course's block on the page. It's recorded as missing.</p>
      </>
    ),
    absent: () => <p>This catalog has no record locator, so there's no locator view to show.</p>,
  },
  {
    id: "improve",
    title: "How this rule works, and improving rules",
    route: (c) => c.base,
    ready: (c) => onBase(c) && !!q("[data-tour=how-it-works]"),
    arrive: () => {
      const d = q<HTMLDetailsElement>("[data-tour=how-it-works]");
      if (!d || d.open) return;
      d.open = true;
      return () => { d.open = false; };
    },
    targets: [".rule-head"],
    accents: [],
    sides: ["below", "right"],
    body: () => (
      <>
        <p><b>How this rule works</b>, opened for you, says in plain words what the rule finds, how, and why this version
          is better, then its selector, how many courses it filled, its version and what it depends on.</p>
        <p>When you've finished labeling for the session, <b>Improve all rules with Claude</b> <I name="spark" />, at the
          bottom of the rule list, hands every rule that needs work, with everyone's verdicts, selections and notes, to
          Claude on the Remote AI rule generator. It changes the rules and publishes a new version in a few minutes,
          while you watch its progress in the bar under the top bar. <b>Past AI runs</b>, in the footer, keeps each
          run's report.</p>
      </>
    ),
    absent: () => <p>The rule hasn't loaded.</p>,
  },
  {
    id: "compare",
    title: "Compare, after a new version",
    route: (c) => c.compare,
    ready: () => !!q(".cmp-layout .sumline, .cmp-layout .cmp-empty"),
    targets: [verdictBlock, ".cmp-layout .cmp-empty"],
    accents: [() => q(".cmp-layout .crec.cv .see") ?? q(".cmp-layout .see")],
    sides: ["below", "above", "left"],
    read: () => ({
      verdicts: qa(".cmp-layout .crec.cv").length,
      from: q<HTMLSelectElement>(".cmp-layout select[aria-label=from]")?.value ?? null,
      to: q<HTMLSelectElement>(".cmp-layout select[aria-label=to]")?.value ?? null,
      empty: text(".cmp-layout .cmp-empty"),
    }),
    body: (f) => (
      <>
        <p>Once Claude publishes a new version, <b>Compare</b> shows what changed between two ruleset versions
          {f.from && f.to ? <> (opened for you: v{String(f.from)} → v{String(f.to)})</> : null}.</p>
        {f.empty ? <p className="faint">{String(f.empty)}</p> : (
          <p><b>Jared's earlier verdicts come first</b>{f.verdicts ? <> ({plural(Number(f.verdicts), "record", "records")})</> : null}:
            the old value → the new one with a word diff, and whether it's now <b>fixed</b>, <b>still wrong</b> or
            <b> newly wrong</b>. Then the signals before → after, and a sample of other changed records.</p>
        )}
        <p><b>See on page →</b> opens the Rules tab with that record selected and highlighted on the saved page.</p>
      </>
    ),
    absent: () => (
      <>
        <p>This catalog has only one ruleset version so far, so there's nothing to compare yet.</p>
        <p>Once Claude publishes a new version of a rule, <b>Compare</b> shows Jared's earlier verdicts first (fixed, still
          wrong, newly wrong), and <b>See on page →</b> opens each record on the Rules tab.</p>
      </>
    ),
  },
  {
    id: "approve",
    title: "Approve",
    route: (c) => c.blocked,
    ready: (c) => showing(c, c.blockedId) && !!q("[data-tour=approve]"),
    arrive: () => {
      const tip = q(".tipwrap[data-tour=approve][data-tip]");
      if (!tip || tip.classList.contains("show")) return;
      tip.classList.add("show");
      return () => tip.classList.remove("show");
    },
    targets: ["[data-tour=approve]"],
    accents: ["[data-tour=approve] .btn"],
    sides: ["right", "below", "left"],
    read: () => ({
      approved: !!q("[data-tour=approve] .is-approved"),
      by: text("[data-tour=approve] .ab-who"),
      blocked: !!q(".tipwrap[data-tour=approve][data-tip]"),
      rule: text(".rule-head h1"),
    }),
    body: (f, c) => (
      <>
        <p>When everything a rule found is right, press <b>Approve rule</b>. A rule is rejected if even one course is wrong.</p>
        {c.blocked !== c.base && f.rule ? <p>“{String(f.rule)}” has been opened for you.</p> : null}
        {f.approved ? <p>This rule is already approved ({String(f.by ?? "").replace(/\s*·\s*Reopen$/, "")}).</p>
          : f.blocked ? <p>Here it's <b>greyed out</b>: some courses are still marked wrong or missing, and the reason
              is shown under the button. Approve stays greyed out until none is. Fix it with Improve all rules, or change those verdicts.</p>
          : <p>Nothing is marked wrong or missing here, so Approve can be pressed. The tour doesn't press it.</p>}
        <p><b>Approving a column's rule publishes it</b> into its ruleset's golden dataset, even while other fields are
          still being worked on. Approve asks once first, then scores xtra's latest extract output against it. The{" "}
          <b>Golden datasets</b> tab lists each version, its columns and how many values are human-reviewed and rule-matched.</p>
      </>
    ),
    absent: () => <p>The rule hasn't loaded.</p>,
  },
  {
    id: "evals",
    title: "Evals: how closely xtra matches the golden dataset",
    route: (c) => c.evals,
    ready: () => !!q(".evx-title"),
    targets: [".evx-title", ".evx-chartrow"],
    accents: [".evx-basis", () => q(".evx-rows .evx-row")],
    sides: ["below", "left"],
    body: () => (
      <>
        <p>Each bar is one of xtra's extract outputs, scored against the golden dataset: the share of values it got exactly
          right. Click a bar to see that output; a dashed one isn't scored yet and has a <b>Score</b> button.</p>
        <p><b>Scored against</b> switches between <b>Human-reviewed</b> values (only those an expert checked) and{" "}
          <b>Rule-matched</b> values (every value in a golden dataset version you pick: the ones the rules matched and the
          human-reviewed ones); the ⓘ beside it says the same.</p>
        <p>Click a row for the golden value and xtra's side by side with the differing words marked, and the saved page
          with both (scroll the panel for more of the page). <b>Split | Unified</b> at the top lays out every diff.{" "}
          <b>Save note</b> keeps a comment on the row; <b>The golden value is wrong…</b> marks it ✗.</p>
        <p className="faint">The home page's Catalogs table has the same score for every catalog (<b>xtra score</b>).</p>
      </>
    ),
    absent: () => <p>xtra hasn't written an extract output for this catalog yet, so there's nothing to score.</p>,
  },
];

