import type { CatalogueType } from "../../../common/types";
import {
  AGENT_RECIPE_CONFIGURATION_JSON_SCHEMA,
  AGENT_RECIPE_STAGE_NAMES,
} from "./recipeConfigurationSchema";

const RECIPE_COMPATIBILITY_GUIDE = `
## Recipe compatibility (from xTRA recipe docs)

Recipes work when the catalogue exposes a **stable URL map**:
- You can copy an item link, paste it in a new tab, and reach that item.
- Index/category/detail pages follow repeating URL paths.
- Pagination changes the address bar using \`page_num\` (\`?page=2\`) or \`offset\` (\`?offset=20\`) patterns.
- Links are real href destinations, OR dynamic catalogue mode applies (click produces a new URL).

Recipes do **not** work when:
- The site is a SPA that never changes URL and clicks do not produce linkable addresses.
- Navigation uses non-link UI with no URL after click (not fixable with dynamic catalogue).
- Pagination uses patterns other than \`page_num\` or \`offset\` in a predictable URL template.

### Page types

Each recipe level has a \`pageType\` that tells xTRA what is on the page and what to do next. Levels are nested: a level's \`links\` child is the configuration for pages found at the next step.

#### \`DETAIL\`
- **What it is:** A page with full information for one catalogue item (one course, program, competency, or credential).
- **When to use:** The page shows a single item's name, description, credits, requirements, etc. It is the **deepest/final** level in the recipe.
- **Signals:** One primary item title, detailed fields, no list of other items to crawl.
- **Example:** \`/courses/ACCT-101\` showing "ACCT 101 – Financial Accounting" with full description.
- **Config:** No \`linkRegexp\` (nothing to follow). Must be the leaf of the nested \`links\` chain.

#### \`DETAIL_LINKS\`
- **What it is:** A listing page whose main purpose is linking to individual item detail pages.
- **What xTRA does:** Match links with \`linkRegexp\`, enqueue each matched URL, then apply the **next level** (\`links\`) on those pages — usually \`DETAIL\`.
- **When to use:** You see a list of items (course codes, program names, etc.) and each row/link goes to one item's detail page.
- **Signals:** Many links to items of the same kind; link text often includes identifiers (e.g. "ACCT 101 – Financial Accounting").
- **Example:** \`/courses/accounting\` listing links to \`/courses/ACCT-101\`, \`/courses/ACCT-102\`, etc.
- **Config:** \`linkRegexp\` **required**. Often paired with pagination if the list spans multiple pages.

#### \`CATEGORY_LINKS\`
- **What it is:** A hub page linking to **grouping** pages (departments, subjects, program areas) — not directly to item detail pages.
- **What xTRA does:** Match category URLs with \`linkRegexp\`, enqueue them, then apply the **next level** on each category page (often another \`CATEGORY_LINKS\`, \`DETAIL_LINKS\`, or eventually \`DETAIL\`).
- **When to use:** The site is organized in layers: index → departments/subjects → item lists → item details.
- **Signals:** Links named after groups ("Accounting", "Biology", "Undergraduate Programs") rather than individual items.
- **Example:** \`/courses\` linking to \`/courses/accounting\`, \`/courses/biology\` — not yet to individual courses.
- **Config:** \`linkRegexp\` **required**. Use when you need an intermediate level before \`DETAIL_LINKS\`.

#### Typical hierarchies
- **One level:** catalogue URL → \`DETAIL\` (all data on one page, no need to follow links and rarely used by users).
- **Two levels:** catalogue URL → \`DETAIL_LINKS\` → \`DETAIL\`. (This is the most common)
- **Three levels:** catalogue URL → \`CATEGORY_LINKS\` → \`DETAIL_LINKS\` → \`DETAIL\`.

#### Do not use for agentic recipe config
- \`API_REQUEST\` and \`EXPLORATORY\` — special/API flows; not for standard catalogue recipes.

### Pagination (when compatible)
- \`page_num\`: URL uses page numbers; template includes \`{page_num}\`.
- \`offset\`: URL uses offsets; template includes \`{offset}\`.
- Set \`startPage\` to \`0\` only for zero-based catalogues.

### Dynamic catalogue (last resort)
- Use only when links are empty, \`javascript:void(0)\`, or otherwise unlinkable.
- Requires \`clickSelector\` targeting the container of clickable items.
- Each click must change the URL within ~15s or extraction fails.

### Link RegExp
- Required for \`CATEGORY_LINKS\` and \`DETAIL_LINKS\`.
- JavaScript RegExp syntax; escape \`/\` as \`\\/\`.
- Should match target links but avoid nav/footer noise.
`.trim();

export function agenticRecipeConfigurationPrompt(input: {
  url: string;
  catalogueType?: CatalogueType;
}): string {
  const catalogueContext = input.catalogueType
    ? `Catalogue type: ${input.catalogueType}.`
    : "Catalogue type: unknown.";

  const stageList = Object.entries(AGENT_RECIPE_STAGE_NAMES)
    .map(([num, name]) => `${num}. ${name}`)
    .join("\n");

  return `
You are configuring a CTDL xTRA crawl recipe for ${input.url}.
${catalogueContext}

Follow these stages in order:

${stageList}

## Reporting rules (required)

1. Call \`xtra_report_stage\` whenever you enter or re-enter a stage (including going back from stage 4 to stage 3).
2. Call \`xtra_report_progress\` before each major action to explain what you are about to do.
3. Use Puppeteer MCP tools (\`puppeteer_navigate\`, \`puppeteer_evaluate\`, etc.) to inspect pages.
4. Do not skip stages. If the catalogue is not recipe-compatible, stop after stage 1 with a clear explanation.

## Output style (required)

- Be very brief in all assistant text and in \`xtra_report_progress\` messages.
- State facts and next actions only; one short sentence when possible.
- Do not use interpersonal or chatty phrases (e.g. "Let me try", "Great!", "Let me help you", "I'll", "Sure", "Perfect").
- Prefer tools over prose; do not repeat information already sent via \`xtra_report_stage\` or \`xtra_report_progress\`.

## Stage 1 — ${AGENT_RECIPE_STAGE_NAMES[1]}

Using ${input.url}, determine whether this catalogue can be crawled with a recipe:

1. **Accessible:** page loads successfully (not blocked, not empty error page).
2. **Index of sub-pages:** the starting page lists or links to deeper catalogue pages (categories or items), OR is itself a detail page.
3. **Pagination:** if present, confirm it uses \`page_num\` or \`offset\` URL patterns compatible with recipe pagination. If pagination uses another mechanism (infinite scroll, POST-only, hash routing), note incompatibility.
4. **Link-based navigation:** confirm links are copyable/openable OR can be handled with dynamic catalogue (click changes URL). If navigation is a dynamic SPA with no linkable URLs, the catalogue is **not recipe-compatible** — explain why and stop.

## Stage 2 — ${AGENT_RECIPE_STAGE_NAMES[2]}

Explore the catalogue hierarchy:

1. Follow representative links from the index to see intermediate levels.
2. Identify where \`DETAIL\` pages live (deepest level with single-item content).
3. Map each level as \`CATEGORY_LINKS\`, \`DETAIL_LINKS\`, or \`DETAIL\` (see Page types above: category hubs vs item lists vs single-item pages).
4. Note whether dynamic catalogue or pagination is needed at any level.

## Stage 3 — ${AGENT_RECIPE_STAGE_NAMES[3]}

Write the full nested recipe configuration:

${RECIPE_COMPATIBILITY_GUIDE}

Submit configuration matching this JSON schema:

\`\`\`json
${JSON.stringify(AGENT_RECIPE_CONFIGURATION_JSON_SCHEMA, null, 2)}
\`\`\`

Guidelines:
- Deepest level must be \`DETAIL\`.
- Provide \`linkRegexp\` for every non-DETAIL level.
- Include \`pagination\` only when stage 1 confirmed compatible pagination.
- Include \`clickSelector\` / \`clickOptions\` only when dynamic catalogue is required.
- Set \`pageLoadWaitTime\` if content appears after load delay.

## Stage 4 — ${AGENT_RECIPE_STAGE_NAMES[4]}

Dry-run verification (do **not** enqueue pages):

1. For each non-DETAIL level, call \`xtra_verify_recipe_links\` with that level's URL, \`linkRegexp\`, and dynamic options.
2. Compare returned URLs to what you expect from browsing.
3. If results are wrong or empty, call \`xtra_report_stage\` with stage \`3\`, fix the configuration, and re-verify.
4. When link verification passes, sample DETAIL page URLs at random from the verified set (spread across the list; do not take the first consecutive links). Call \`xtra_test_extraction\` on each sampled URL, up to 10 times. This tool is limited to 10 calls for this recipe; further calls return an error that you tried too many times.
5. \`xtra_test_extraction\` returns \`extracted: true\` if any entries were generated, otherwise \`extracted: false\`. If a sample returns false, call \`xtra_report_stage\` with stage \`3\`, fix the configuration, and re-verify links. Remaining extraction attempts still count toward the 10-call limit.
6. When every level's links pass and sampled DETAIL pages extract successfully, call \`xtra_submit_recipe_configuration\` with the final configuration object and a brief summary.

Start now with stage 1: call \`xtra_report_stage\` with stage \`1\`, then \`xtra_report_progress\`, then navigate to ${input.url}.
`.trim();
}

export function inspectPagePrompt(input: { url: string }): string {
  return `Call puppeteer_navigate with url "${input.url}". Look at the first entry in the page and output what it is.`;
}

export function recipeConfigurationPrompt(input: {
  url: string;
  catalogueType?: CatalogueType;
}): string {
  return agenticRecipeConfigurationPrompt(input);
}
