# Scripted Pagination Design

Alternative design: [Agentic Page Navigation](./agentic-page-navigation.md)

## Goal

Some catalogues paginate results without changing URLs or rendering normal page links. Mt. Saint Antonio College is an example: the page list is driven by client-side scripting, so xTRA cannot construct paginated URLs and cannot discover later result pages by reading the initial HTML.

Add a manual recipe capability that tells xTRA how to click through those scripted pagination controls, wait for each page state to render, and index the links visible after each click.

Automatic detection is out of scope. Users must configure the selectors and limits needed for the recipe.

## High-Level Design

Add a new recipe-level option named `scriptedPagination` beside the existing `pagination`, `linkRegexp`, and `clickSelector` options.

`pagination` remains URL-pattern pagination. It creates new crawl pages from generated URLs.

`scriptedPagination` is browser-state pagination. It stays on the current crawl page, clicks configured pagination controls, and collects next-level links from each rendered state.

The feature should run inside `processLinks`, not `enqueuePages`, because scripted pagination does not produce page URLs to fetch. It produces the same kind of output as normal link discovery: URLs for the next recipe level.

Conceptually:

1. Fetch the current page normally.
2. If `scriptedPagination` is configured, open the page in Puppeteer.
3. Apply `pageSetup`.
4. Collect links from the initial page state.
5. Treat scripted pagination as an outer page-state traversal.
6. For each page state, run the configured link collector.
7. If the link collector is dynamic, let it click item links as an inner loop and then restore the current pagination state before the next item.
8. Move to the next pagination state by re-querying `pageButtonSelector`, choosing the next unvisited page control, clicking it, and waiting for the page state to settle.
9. De-duplicate and enqueue the resulting URLs through the existing `FETCH_LINKS` path.

The link collection strategy should be whichever the recipe already uses:

- Classic discovery: `linkRegexp` over simplified markdown.
- Dynamic discovery: `clickSelector` / `clickOptions`, for cases where the visible result items themselves require click simulation to reveal URLs.

## Proposed Recipe Shape

Add this optional field to `RecipeConfiguration`:

```ts
export interface ScriptedPaginationConfiguration {
  /**
   * Selector for clickable page controls.
   * This is evaluated against the whole document, so it can include hierarchy
   * when the recipe needs to scope controls to a specific page section.
   * Example: ".pagination button.page-link" or "#coursePagination li a".
   */
  pageButtonSelector: string;

  /**
   * Optional selector for page controls that should be ignored.
   * This lets recipes avoid current-page buttons, disabled previous/next
   * controls, ellipses, or non-page actions.
   */
  excludeSelector?: string;

  /** Maximum number of pagination controls xTRA may click. */
  limit?: number;

  /** Maximum time to wait for page controls, result changes, and link discovery. */
  waitMs?: number;

  /** Extra fixed delay after a click for sites that update after timers. */
  settleMs?: number;
}
```

Example recipe fragment:

```json
{
  "pageType": "DETAIL_LINKS",
  "linkRegexp": "course\\/[A-Za-z0-9-]+",
  "scriptedPagination": {
    "pageButtonSelector": ".pagination button.page-number",
    "excludeSelector": ".active, .disabled",
    "limit": 50,
    "waitMs": 30000,
    "settleMs": 500
  },
  "links": {
    "pageType": "DETAIL"
  }
}
```

`scriptedPagination` and URL `pagination` should be mutually exclusive at one recipe level. If both are present, validation should reject the recipe with a clear error.

## Runtime Behavior

### Classic Link Discovery

For recipes with `scriptedPagination` and `linkRegexp`:

1. Navigate to `crawlPage.url` with the existing proxy-aware Puppeteer setup.
2. Apply `pageSetup`.
3. For each page state, read either:
   - `contentSelector` subtree HTML when configured on the recipe level.
   - The full page HTML otherwise.
4. Convert the HTML to simplified markdown with `simplifiedMarkdown`.
5. Run `createUrlExtractor(new RegExp(linkRegexp, "g"))`.
6. Normalize and de-duplicate URLs.

This keeps the final output identical to the existing classic `processLinks` branch.

### Dynamic Link Discovery

For recipes with `scriptedPagination` and `clickSelector`:

1. Navigate once to the root page.
2. Apply `pageSetup`.
3. Walk scripted pagination as the outer loop.
4. For each page state, find item clickables within `clickSelector`.
5. Click each item and capture URL changes using the same logic as `discoverDynamicLinks`.
6. Return to the same scripted pagination state before moving to the next item.
7. After all item clickables in the current page state are processed, move the outer loop to the next pagination state.

This likely requires extracting reusable internals from `dynamicLinkDiscovery.ts`, because the current `discoverDynamicLinks` helper assumes every click starts from the original URL and returns there after each item click.

The low-gap refactor is to split current logic into:

```ts
export async function collectDynamicLinksFromPage(options: {
  page: Page;
  rootUrl: string;
  selector?: string;
  clickOptions?: ClickDiscoveryOptions;
  pageSetup?: PageSetupConfig;
  expectedStateUrl?: string;
  restoreState: () => Promise<void>;
}): Promise<string[]>
```

`discoverDynamicLinks` can keep its public API and call this helper after navigation with a restore function that returns to the root page, preserving current behavior. Scripted pagination can call the same helper after each pagination click with a restore function that returns to the current pagination state.

The current dynamic implementation restores by checking whether `page.url()` differs from `rootUrl`, then trying `page.goBack(...)`, then falling back to `page.goto(rootUrl, ...)`. That is not enough for scripted pagination, because the correct state may be "root URL plus page 4 selected in client-side state." The refactor should make restoration caller-owned:

- Dynamic-only discovery restores to the root page, as it does today.
- Scripted pagination restores to the active pagination state.
- If browser back does not restore the active state, scripted pagination should navigate to `rootUrl`, apply `pageSetup`, and replay the pagination path needed to reach the active state again.

### Nested Traversal And Restore Model

Scripted pagination and dynamic link discovery must be composed as two nested algorithms:

- The outer loop owns pagination state. It starts at the initial page, collects links, then moves to the next scripted pagination state.
- The inner loop owns item clicks for the current pagination state. It clicks each visible item, captures any URL it reveals, and then restores the exact pagination state before clicking the next item.

The current dynamic link discovery implementation restores to `rootUrl`. That behavior is correct when there is no scripted pagination, but it is not enough when page 2, page 3, or page 4 are client-side states at the same URL. In scripted pagination mode, the dynamic collector should not decide how to recover the page. It should call a supplied `restoreState` callback after each item click.

`restoreState` should work in two phases:

1. Try the cheap recovery first: if `page.goBack()` returns to the expected URL and the active pagination state still matches, continue.
2. If browser history does not restore the expected state, navigate back to `rootUrl`, apply `pageSetup`, and replay the pagination path from the initial state to the last seen scripted page.

This replay path matters for catalogues whose pagination controls are not all available at once. Some only expose `Next` / `Previous`; others show a moving numeric window. The implementation cannot assume that page 10 is directly clickable from the initial page. It needs to walk the configured page controls one state at a time, re-querying `pageButtonSelector` after each state change.

Practically, every pagination state should keep:

- a state identity used for `visited` checks,
- a replayable path from the initial state,
- the active URL after settlement,
- enough information to find the next controls after the DOM re-renders.

## Implementation Notes

### Shared Types

Update `common/types.ts`.

Add `ScriptedPaginationConfiguration` and include it in `RecipeConfiguration`:

```ts
export interface RecipeConfiguration {
  pageType: PageType;
  linkRegexp?: string;
  clickSelector?: string;
  clickOptions?: ClickDiscoveryOptions;
  pagination?: PaginationConfiguration;
  scriptedPagination?: ScriptedPaginationConfiguration;
  links?: RecipeConfiguration;
  // ...
}
```

No database migration should be needed because recipe configuration is already stored as JSON.

### Validation

Update the recipe configuration schemas in:

- `server/src/routers/recipes.ts`
- `client/src/components/app/recipes/create.tsx`
- `client/src/components/app/recipes/edit.tsx`

The schema should:

- Require `pageButtonSelector` when `scriptedPagination` exists.
- Limit `limit` to a safe maximum, matching the dynamic click limit maximum of `10000`.
- Limit `waitMs` to `60000`.
- Limit `settleMs` to a reasonable range, for example `0..10000`.
- Reject `pagination` and `scriptedPagination` on the same recipe level.
- Require either `linkRegexp` or `clickSelector` for non-`DETAIL` levels as today.

`edit.tsx` currently has a smaller recipe schema than create mode and does not include `clickSelector` / `clickOptions`. When implementing this feature, align edit and create schemas so existing dynamic configuration and new scripted pagination fields round-trip reliably.

### Client State Validation

Keep the zod schemas as submit/server guards, but do not rely on them as the primary user feedback for scripted pagination fields.

The recipe create form is currently configured with `mode: "onSubmit"` and `reValidateMode: "onSubmit"`, and the edit form uses the default submit-time validation behavior. That means schema-only validation is only surfaced after clicking save. The recipe editor already has state-driven UI through `form.watch(...)`, `useWatch(...)`, and explicit `setValue(...)` calls, so scripted pagination should follow that pattern for immediate feedback.

Add lightweight state validation in `RecipeLevel.tsx`:

```ts
type RecipeLevelValidation = {
  errors: Record<string, string>;
  warnings: string[];
};

function validateRecipeLevelState(config: FormRecipeConfiguration): RecipeLevelValidation {
  const errors: Record<string, string> = {};
  const warnings: string[] = [];

  if (!config.scriptedPagination) return { errors, warnings };

  if (!config.scriptedPagination.pageButtonSelector?.trim()) {
    errors["scriptedPagination.pageButtonSelector"] =
      "Page button selector is required when scripted pagination is enabled.";
  }

  if (config.pagination) {
    errors["scriptedPagination"] =
      "Use either URL pagination or scripted pagination, not both.";
  }

  if (!config.linkRegexp?.trim() && !config.clickSelector?.trim()) {
    errors["scriptedPagination"] =
      "Scripted pagination needs Link RegExp or Dynamic catalogue to collect links.";
  }

  return { errors, warnings };
}
```

Use the watched `config` value to compute this on every render:

```ts
const scriptedPaginationValidation = validateRecipeLevelState(config);
const scriptedPaginationError =
  scriptedPaginationValidation.errors["scriptedPagination"];
const pageButtonSelectorError =
  scriptedPaginationValidation.errors["scriptedPagination.pageButtonSelector"];
```

Display these messages directly below the scripted pagination section or field, using the same visual treatment as existing field descriptions/errors. This avoids waiting for `FormMessage` to populate from zod after save.

For invalid combinations that can be prevented at the UI layer, prefer state-driven disabling/clearing:

- If `scriptedPagination` is enabled, disable the URL `Pagination` checkbox or show a clear inline error if it is already enabled.
- If URL `pagination` is enabled, disable the `Scripted Pagination` checkbox or show the same conflict message.
- When enabling scripted pagination, initialize `pageButtonSelector` to an empty string and default `limit` to a conservative value.
- Do not auto-clear `pagination` or `scriptedPagination` without user action; that could silently discard recipe configuration.

The submit/save path should still keep the schema validation, because it protects JSON editing, imported templates, stale clients, and direct API calls. The state validation is a UX layer, not a replacement for server validation.

### Worker Flow

Update `server/src/workers/fetchPage.ts`.

Current order:

```ts
if (configuration.pagination && currentStep != Step.FETCH_PAGINATED) {
  return enqueuePages(configuration, datasetId, crawlPage, catalogueType, delayOptions);
}

// DETAIL pages extract, otherwise processLinks(...)
```

Keep this for URL pagination. Add scripted pagination inside `processLinks`:

```ts
if (configuration.scriptedPagination) {
  urls = await discoverScriptedPaginatedLinks({
    rootUrl: crawlPage.url,
    linkRegexp: configuration.linkRegexp,
    clickSelector: configuration.clickSelector,
    clickOptions: configuration.clickOptions,
    scriptedPagination: configuration.scriptedPagination,
    contentSelector: configuration.contentSelector,
    pageSetup: configuration.pageSetup,
    exactLinkPatternMatch: configuration.exactLinkPatternMatch,
  });
} else if (configuration.clickSelector) {
  // existing dynamic path
} else if (configuration.linkRegexp) {
  // existing classic path
}
```

After `urls` is populated, reuse the existing duplicate check, `createStepAndPages`, and `submitJobs` code unchanged.

### Extraction Helper

Add `server/src/extraction/scriptedPaginationDiscovery.ts`.

Suggested API:

```ts
export interface DiscoverScriptedPaginatedLinksOptions {
  rootUrl: string;
  linkRegexp?: string;
  clickSelector?: string;
  clickOptions?: ClickDiscoveryOptions;
  scriptedPagination: ScriptedPaginationConfiguration;
  contentSelector?: string;
  pageSetup?: PageSetupConfig;
  exactLinkPatternMatch?: boolean;
}

export async function discoverScriptedPaginatedLinks(
  options: DiscoverScriptedPaginatedLinksOptions
): Promise<string[]>
```

Use the same proxy rotation pattern as `discoverDynamicLinks`:

- `findProxies()`
- try direct first
- retry proxy-level failures and blocked `403` / `429` responses
- close the browser in `finally`

The helper can reuse `navigateWithProxy` from `dynamicLinkDiscovery.ts`. If needed, move common browser/proxy functions into a neutral module such as `server/src/extraction/browserNavigation.ts`.

Pseudo-flow:

```ts
type PaginationStep = {
  selector: string;
  index: number;
  label: string;
};

type PaginationState = {
  id: string;
  path: PaginationStep[];
};

const collectCurrentStateLinks = async () => {
  if (clickSelector) {
    return collectDynamicLinksFromPage({
      page,
      rootUrl,
      selector: clickSelector,
      clickOptions,
      pageSetup,
      expectedStateUrl: page.url(),
      restoreState: () => restorePaginationState(currentPaginationState),
    });
  }

  const html = contentSelector
    ? await page.$eval(contentSelector, el => el.outerHTML)
    : await page.content();

  const markdown = await simplifiedMarkdown(html);
  const extractor = createUrlExtractor(new RegExp(linkRegexp!, "g"));
  return extractor(rootUrl, markdown, exactLinkPatternMatch);
};
```

For pagination buttons:

```ts
await page.waitForSelector(pageButtonSelector, { timeout: waitMs });

const queue: PaginationState[] = [{ id: "initial", path: [] }];
const visited = new Set<string>();

while (queue.length) {
  currentPaginationState = queue.shift()!;
  await restorePaginationState(currentPaginationState);

  if (visited.has(currentPaginationState.id)) continue;
  visited.add(currentPaginationState.id);

  urls.push(...await collectCurrentStateLinks());

  const controls = await findScriptedPaginationControls(page, scriptedPagination);
  if (visited.size + controls.length > limit) {
    throw new Error(`Scripted pagination traversal exceeds limit ${limit}`);
  }

  for (const control of controls) {
    if (control.isCurrent || control.isDisabled || control.isPrevious) continue;
    queue.push({
      id: control.stateId,
      path: [...currentPaginationState.path, control.step],
    });
  }
}
```

Important details:

- Scripted pagination should not capture all controls once and click those stale handles. It should re-query `pageButtonSelector` in each page state, because pagination controls often re-render or expose different numeric windows as the user advances.
- Pagination traversal is the outer loop. Dynamic item clicks are an inner loop. The inner loop may navigate away from the current page state, so every item click must restore the active pagination state before the next item click.
- Store a replayable `path` for every pagination state. The path is the sequence of pagination button identities clicked from the root page state to reach the active state.
- `restorePaginationState(state)` should first try the cheapest route when the browser is still close to the desired state, but it must be able to fall back to `page.goto(rootUrl)`, `applyPageSetupSteps(...)`, and replay `state.path`.
- For catalogues that only expose `Next` / `Previous` buttons, users can set `pageButtonSelector` to the `Next` button. The traversal should repeatedly re-query and click the next available control until it is disabled, the page state stops changing, or `limit` is reached.
- For catalogues with numbered buttons that only show a moving range, the traversal still replays paths from the root and walks through intermediate page numbers as needed. It cannot assume page 10 is directly reachable from the initial DOM.

### Waiting Strategy

Use recipe-configurable waits, with conservative defaults:

- `waitMs`: default `30000`
- `settleMs`: default `300`
- wait for network idle when possible
- wait for network idle and the configured `settleMs` after each click

For pages that do not trigger network activity, `settleMs` is the practical fallback.

The first implementation does not need automatic "content changed" detection. If the configured wait is too short, the recipe should be adjusted manually.

### Pagination State Identity

The implementation needs a stable-enough identity for each visited page state so it can avoid loops and restore dynamic item clicks to the right state.

Use a layered identity:

1. Prefer an active/current pagination control, such as `aria-current`, `.active`, `[aria-selected="true"]`, or a disabled numeric control.
2. Fall back to the clicked control label plus its index among matching controls.
3. Include a lightweight fingerprint of the link collection scope after settle, such as the first few matched links or normalized text from `contentSelector`.

This identity is not intended to be a public recipe field. It is internal traversal bookkeeping. If a state cannot be distinguished from a previously visited state after clicking a control, treat it as already visited and stop following that branch.

### UI

Update `client/src/components/app/recipes/RecipeLevel.tsx`.

Add a new expandable section under existing `Dynamic catalogue` and before URL `Pagination`:

- Label: `Scripted Pagination`
- `pageButtonSelector`
- `excludeSelector`
- `limit`
- `waitMs`
- `settleMs`

Recommended help text:

> Use this when pagination changes the visible results without changing the page URL. xTRA will click each configured page control and collect links from the results shown after each click.

Keep the existing `Pagination` section for URL pagination and label it more explicitly as `URL Pagination` once this feature is added.

### Documentation

Update `doc/recipe-options-guide.md` after implementation.

Add a new user-facing section between `Dynamic Catalogue` and `Pagination` explaining:

- Scripted pagination is for page controls that update visible results without changing the URL.
- Users must provide CSS selectors.
- Classic link extraction uses the existing `contentSelector` when one is configured; otherwise it scans the whole page.
- It can be combined with classic `Link RegExp` or `Dynamic catalogue`.
- URL pagination and scripted pagination should not both be enabled for the same level.

## Edge Cases

- Current-page controls: users should exclude them via `excludeSelector`; otherwise xTRA may click the current page and collect duplicate links.
- Previous/next buttons: users can either exclude them or include only numeric page buttons with `pageButtonSelector`.
- Pagination controls that are re-rendered after each click: re-resolve controls from stable selectors before every click.
- Result rows that require scrolling: reuse the existing `scrollAndSettle` behavior where possible, or add a scoped scroll to `contentSelector` when configured.
- Duplicate links across pages: keep the existing `Set` de-duplication before enqueueing pages.
- Sites that virtualize results: users may need `settleMs` and a specific `contentSelector`.
- Dynamic item links inside a scripted page state: use the refactored dynamic click collector and restore the current pagination state after each item click.

## Testing Plan

Add focused tests around the new helper and worker routing:

- Unit test validation rejects both `pagination` and `scriptedPagination`.
- Unit test scripted pagination classic mode extracts links from initial and clicked states.
- Unit test `excludeSelector` filters active/disabled controls.
- Unit test limit errors before clicking too many controls.
- Worker test verifies `processLinks` enqueues `FETCH_LINKS` pages from `discoverScriptedPaginatedLinks`.

For Puppeteer behavior, prefer a small fixture page served locally in vitest rather than a live college site.

## Recommended Implementation Sequence

1. Add shared types and zod schemas.
2. Extract reusable dynamic-link internals from `dynamicLinkDiscovery.ts` without changing current behavior.
3. Add `scriptedPaginationDiscovery.ts` for classic mode first.
4. Wire `processLinks`.
5. Add dynamic mode support using the extracted collector.
6. Add UI fields in `RecipeLevel.tsx`.
7. Add tests.
8. Update `recipe-options-guide.md`.

