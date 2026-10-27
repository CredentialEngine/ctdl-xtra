// The nine steps of the tour (spec §7.8), in order. Each lights one real area of the screen and, where it helps,
// does what the reader would do by hand (select a row and press ✗, open the comment, switch to HTML, go to the
// locator view, open "How this rule works", go to Compare). What a step does, it undoes when the reader leaves it.
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
    id: "rows",
    title: "One row per course, likeliest problems first",
    route: (c) => c.base,
    ready: onBase,
    targets: ["[data-tour=rows]"],
    read: () => ({ bar: text(".rows-bar") }),
    body: (f) => (
      <>
        <p>Each row is what the selected rule found for one course{f.bar ? <> ({String(f.bar).split(" · ")[0]})</> : null}.
          They're <b>sorted with the likeliest problems first</b>, so the rows worth checking are at the top.</p>
        <p>Rows that already have a verdict fade back, so the eye goes to the rows still waiting. Each shows its verdict
          and who gave it.</p>
        <p>Click a row, or press <kbd>Tab</kbd>, and its value is highlighted on the saved page at the right.</p>
      </>
    ),
    absent: () => <p>This rule has no rows.</p>,
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
    targets: [ROW, "[data-tour=page-pane]"],
    accents: ["[data-tour=row-controls]"],
    sides: ["below", "above", "left"],
    body: () => (
      <>
        <p><I name="correct" /> or <kbd>A</kbd>: the value is right.</p>
        <p><I name="wrong" /> or <kbd>W</kbd>: it's wrong. It has been pressed for you on this row: the row opens and
          asks you to <b>select the right text on the page →</b>. Drag across it on the saved page; the row then shows
          only that text, an optional note, and Save / Cancel.</p>
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
        <p>The speech bubble <I name="bubble" /> (<kbd>C</kbd>) has been clicked for you. It opens a short note for
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
    title: "How this rule works, and Improve this rule",
    route: (c) => c.base,
    ready: (c) => onBase(c) && !!q("[data-tour=how-it-works]"),
    arrive: () => {
      const d = q<HTMLDetailsElement>("[data-tour=how-it-works]");
      if (!d || d.open) return;
      d.open = true;
      return () => { d.open = false; };
    },
    targets: [".rule-head"],
    accents: ["[data-tour=improve-rule]"],
    sides: ["below", "right"],
    body: () => (
      <>
        <p><b>How this rule works</b>, opened for you, says in plain words what the rule finds, how, and why this version
          is better, then its selector, how many courses it filled, its version and what it depends on.</p>
        <p>When courses are wrong, <b>Improve this rule</b> <I name="spark" /> opens the <b>Prompt</b> tab with this rule
          selected. It turns your verdicts, selections and notes into a prompt for Claude Code, which changes the rule and
          publishes a new version.</p>
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
        <p>When everything a rule found is right, <b>Approve</b> it. A rule is rejected if even one course is wrong.</p>
        {c.blocked !== c.base && f.rule ? <p>“{String(f.rule)}” has been opened for you.</p> : null}
        {f.approved ? <p>This rule is already approved ({String(f.by ?? "").replace(/\s*·\s*Reopen$/, "")}).</p>
          : f.blocked ? <p>Here it's <b>greyed out</b>: some courses are still marked wrong or missing, and the reason
              is shown under the button. Approve stays greyed out until none is. Fix the rule with Improve this rule, or change those verdicts.</p>
          : <p>Nothing is marked wrong or missing here, so Approve can be pressed. The tour doesn't press it.</p>}
        <p>Once every rule is approved, the <b>Golden</b> tab can publish.</p>
      </>
    ),
    absent: () => <p>The rule hasn't loaded.</p>,
  },
];

