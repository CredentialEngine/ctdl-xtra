# Agentic Page Navigation Design

Alternative design to: [Scripted Pagination](./scripted-pagination-design.md)

## Table Of Contents

- [Goal](#goal)
- [When This Fits](#when-this-fits)
- [Tool Landscape](#tool-landscape)
  - [Claude Agent SDK With Puppeteer Tools](#claude-agent-sdk-with-puppeteer-tools)
  - [Playwright MCP](#playwright-mcp)
  - [Claude Code With Chrome](#claude-code-with-chrome)
  - [OpenAI Codex](#openai-codex)
  - [Raw Computer Use](#raw-computer-use)
- [Recommended Direction](#recommended-direction)
- [Proposed Recipe Shape](#proposed-recipe-shape)
- [Runtime Architecture](#runtime-architecture)
  - [Runner Boundary](#runner-boundary)
  - [Worker Placement](#worker-placement)
- [Agent Contract](#agent-contract)
- [Validation And Guardrails](#validation-and-guardrails)
- [Observability](#observability)
- [Comparison With Scripted Pagination](#comparison-with-scripted-pagination)
- [Barebones De-Risking Project](#barebones-de-risking-project)
- [Implementation Plan](#implementation-plan)
- [Open Questions](#open-questions)
- [Recommendation](#recommendation)

## Goal

Some catalogues hide the URLs xTRA needs behind browser state: client-side
pagination, filters, search forms, tabs, infinite scroll, or result cards that
only reveal detail URLs after interaction. The scripted pagination design solves
one version of this by adding user-configured selectors and a deterministic
Puppeteer traversal.

This design proposes a more agentic alternative: give a browser-capable agent a
catalogue start URL and extraction intent, let it decide which controls to click
or fields to fill, and let xTRA programmatically collect the next-level URLs from
the resulting browser states.

The agent does not replace extraction or URL extraction. It only guides
navigation. xTRA remains the system of record for recipes, crawl pages, datasets,
retries, budget controls, audit logs, URL validation, and item extraction.

## When This Fits

Use agentic navigation when the user can describe the discovery goal more easily
than they can provide stable selectors:

- The site mixes pagination, filters, tabs, accordions, and search forms.
- Pagination state is not addressable by URL and selector configuration would be
  brittle.
- The correct navigation path depends on page semantics, such as "open each
  program category, then collect all course links".
- The task is expected to run for minutes and can tolerate higher per-run cost in
  exchange for less recipe authoring.

Do not use it as the default fetch path. Deterministic URL pagination, classic
`linkRegexp`, dynamic `clickSelector`, and the scripted pagination design should
remain cheaper and more predictable for sites that fit them.

## Tool Landscape

The best product shape is not to shell out to a consumer coding agent directly.
Use an embeddable agent runtime with browser tools, then keep Claude Code,
Codex, and similar tools as implementation options.

### Claude Agent SDK With Puppeteer Tools

[Claude Agent SDK](https://code.claude.com/docs/en/sdk/) exposes the same agent
loop and context-management model as Claude Code through TypeScript and Python.
For xTRA, the preferred integration is to give the SDK a small set of
Puppeteer-backed tools instead of introducing a separate browser automation
dependency.

This is the strongest fit for xTRA because it is programmable, can run in our
worker infrastructure, supports long-running sessions, and can be constrained to
a small tool set while reusing the Chrome/Puppeteer stack already present in the
server.

Useful properties:

- TypeScript SDK available for direct server integration.
- Browser actions can be backed by existing `rebrowser-puppeteer`,
  `puppeteer-extra`, stealth, proxy, and page setup helpers.
- The same headless Chrome instance can be owned by xTRA while the agent receives
  snapshots and returns action decisions.
- Agent sessions can stream progress and preserve context.
- Tool permissions can be limited to `snapshot`, `choose action`, and possibly
  read-only browser observations. xTRA code executes clicks, fills, waits, and
  URL collection.

Risks:

- Requires a small adapter that turns Puppeteer page state into an LLM-friendly
  snapshot with stable refs.
- Requires careful timeout, token, and domain controls.
- The model may still click irrelevant paths unless the prompt and result schema
  are strict.

### Playwright MCP

[Playwright MCP](https://playwright.dev/mcp/introduction) is still useful as a
reference design. It gives agents browser actions through accessibility snapshots
rather than raw screenshots or DOM dumps.

It should not be the default implementation if we want to avoid another browser
dependency. The useful idea to borrow is the snapshot/ref/action protocol:
produce a compact structured page snapshot, let the agent choose a referenced
control, and have trusted code execute that action.

### Claude Code With Chrome

[Claude Code Chrome integration](https://docs.anthropic.com/en/docs/claude-code/chrome)
can browse, click, fill forms, inspect pages, and extract data from visible
Chrome or Edge sessions. It is useful for prototyping prompts and manually
debugging difficult catalogues.

It is not the preferred production runner because it is an interactive developer
tool, depends on a browser extension, shares local browser login state, and may
pause for manual intervention on login pages or CAPTCHAs.

### OpenAI Codex

[Codex](https://platform.openai.com/docs/codex) can run long-horizon tasks in
background cloud environments, and its computer-use mode can operate applications
by seeing, clicking, and typing. OpenAI's long-horizon examples show agent runs
on the order of many hours, so a minutes-long catalogue navigation task is within
the intended operating envelope.

Codex is valuable as an external delegated agent or experimentation surface, but
it is less directly shaped like a server-side URL discovery component. If xTRA
uses Codex, prefer an explicit adapter that submits a bounded task and receives a
structured artifact, not a free-form PR or code-editing workflow.

Risks:

- Cloud environments need explicit public internet access and egress policy.
- Computer-use style browser control is harder to make deterministic than
  structured Puppeteer snapshots with stable refs.
- Product integration depends on which Codex surfaces expose stable automation
  APIs for the target deployment.

### Raw Computer Use

Anthropic Computer Use and OpenAI Computer Use can control a browser visually.
They are useful fallback tools for visually complex sites, but they should not be
the first production choice for URL discovery. Snapshot-based browser tools are
cheaper, easier to audit, and less sensitive to layout changes.

## Recommended Direction

Implement an internal `agenticNavigation` recipe mode backed first by Claude
Agent SDK plus a Puppeteer-controlled headless Chrome runner.

The agent should emit structured navigation decisions, not modify recipes,
enqueue jobs, or become the source of truth for URLs. xTRA should retrieve URLs
from the browser state with deterministic code, then validate each accepted URL
before it enters the normal `FETCH_LINKS` path.

Conceptually:

1. Fetch the current crawl page normally.
2. If `agenticNavigation` is configured, start an agent navigation job.
3. Give the agent the root URL, same-origin constraints, discovery goal, limits,
   and URL acceptance rules.
4. Let the agent choose the next relevant interaction from each browser snapshot.
5. After each settled state, collect matching URLs programmatically from anchors,
   the current URL, and configured extraction scopes.
6. Stop when no new relevant navigation decisions remain or a limit is reached.
7. Validate, normalize, de-duplicate, and enqueue URLs through the existing
   `processLinks` flow.

This keeps the behavioral contract close to existing link discovery:

```ts
const urls = await discoverAgenticNavigationLinks({
  rootUrl: crawlPage.url,
  configuration: configuration.agenticNavigation,
  linkRegexp: configuration.linkRegexp,
  contentSelector: configuration.contentSelector,
  pageType: configuration.links?.pageType,
});
```

After programmatic URL collection populates `urls`, reuse existing duplicate
checks, `createStepAndPages`, and `submitJobs`.

## Proposed Recipe Shape

Add an optional recipe-level field beside `pagination`, `scriptedPagination`,
`linkRegexp`, and `clickSelector`:

```ts
export interface AgenticNavigationConfiguration {
  /**
   * Natural-language instruction for the browser agent.
   * Example: "Open every page of the course catalogue and collect course detail URLs."
   */
  goal: string;

  /**
   * Optional additional hints that help the agent avoid irrelevant paths.
   * These are not hard selectors; they are semantic guidance.
   */
  hints?: string[];

  /** Maximum browser actions the agent may take. */
  maxActions?: number;

  /** Maximum wall-clock runtime for this navigation task. */
  timeoutMs?: number;

  /** Maximum accepted URLs collected by the runner. */
  maxUrls?: number;

  /**
   * Restrict accepted URLs to the root origin by default.
   * The first implementation should keep this true unless a catalogue requires
   * known cross-origin detail pages.
   */
  sameOriginOnly?: boolean;

  /**
   * Optional URL pattern used as a hard post-validation filter.
   * If omitted, fall back to the level's linkRegexp when present.
   */
  acceptUrlRegexp?: string;

  /**
   * Optional text that should be present near accepted links or on clicked
   * result cards. This is a hint for agent judgement, not a hard parser.
   */
  targetDescription?: string;
}
```

Example recipe fragment:

```json
{
  "pageType": "DETAIL_LINKS",
  "linkRegexp": "/courses/[A-Za-z0-9-]+",
  "agenticNavigation": {
    "goal": "Use the catalogue UI to visit every result page and collect all course detail URLs.",
    "hints": [
      "The page list may update without changing the URL.",
      "Ignore login, apply, request information, and contact links."
    ],
    "maxActions": 250,
    "timeoutMs": 600000,
    "maxUrls": 5000,
    "sameOriginOnly": true
  },
  "links": {
    "pageType": "DETAIL"
  }
}
```

`agenticNavigation`, URL `pagination`, and `scriptedPagination` should be
mutually exclusive at one recipe level. Agentic navigation can still use
`linkRegexp` as an acceptance filter.

## Runtime Architecture

Add a new helper:

```ts
export interface DiscoverAgenticNavigationLinksOptions {
  rootUrl: string;
  configuration: AgenticNavigationConfiguration;
  linkRegexp?: string;
  contentSelector?: string;
  pageType?: PageType;
}

export interface AgenticNavigationResult {
  urls: string[];
  stopReason: "complete" | "limit" | "timeout" | "blocked" | "error";
  actionsUsed: number;
  evidence: AgenticNavigationEvidence[];
}

export async function discoverAgenticNavigationLinks(
  options: DiscoverAgenticNavigationLinksOptions
): Promise<AgenticNavigationResult>
```

The helper owns provider selection, prompt construction, timeouts, retries,
browser actions, and programmatic URL collection. `processLinks` should only
call it and handle accepted URLs.

### Runner Boundary

Introduce an adapter interface so the recipe model is not tied to one vendor:

```ts
export interface BrowserNavigationAgent {
  chooseNextAction(input: AgenticNavigationInput): Promise<AgenticNavigationAction>;
}
```

Initial implementation:

- `ClaudePuppeteerNavigationAgent`
- TypeScript Claude Agent SDK
- a Puppeteer `Browser` / `Page` owned by xTRA, launched with the same options as
  existing dynamic discovery where possible
- a lightweight snapshot builder that maps visible interactive elements to stable
  refs for the current turn
- allowed agent behavior limited to reading the snapshot and returning the next
  action to take; the xTRA runner executes the action and extracts URLs
  programmatically from the same page

Possible later adapters:

- `CodexNavigationAgent` for cloud/background delegated tasks
- `OpenAIComputerUseNavigationAgent` for visual fallback
- `LocalPuppeteerScriptedAgent` for a smaller non-LLM baseline

The agent SDK does not need direct ownership of Chrome. The safer design is:

1. xTRA launches Chrome through Puppeteer.
2. xTRA builds a compact page snapshot from that `Page`.
3. The agent SDK receives the snapshot, goal, prior actions, and collected URL
   summary.
4. The agent returns one structured action.
5. xTRA executes that action through Puppeteer and collects URLs.

If we later want the agent to call tools directly, expose a tiny local MCP server
or SDK tool wrapper whose implementations close over the same Puppeteer page.
Those tools should still be xTRA-owned operations such as `getSnapshot`,
`clickRef`, `fillRef`, `pressKey`, and `finish`, not general browser or shell
access.

### Worker Placement

Run agentic navigation inside `processLinks`, the same place the scripted
pagination design proposes. It produces next-level links, not page content.

However, minutes-long agent runs should have their own operational limits:

- Increase BullMQ job timeout for `FetchPage` jobs that use
  `agenticNavigation`, or split discovery into a dedicated queue such as
  `extractions.discoverLinks`.
- Store incremental progress in job progress updates so the UI can show the
  current agent action, URL count, and stop reason.
- Respect extraction cancellation before starting the agent and between streamed
  tool events.

Splitting into a dedicated queue is cleaner if agentic navigation becomes common,
because it allows lower concurrency and separate budget controls without slowing
ordinary fetch jobs.

## Agent Contract

The prompt should make the task narrow and auditable:

- You are choosing navigation actions only.
- Stay within the allowed domain unless explicitly instructed otherwise.
- Prefer controls likely to reveal links that match the accepted URL pattern.
- Explore pagination, tabs, filters, and result sections that are relevant to the
  stated target.
- Do not sign in, submit lead forms, download files, or change persistent site
  state.
- Stop when no new relevant URLs are found, or when limits are reached.
- Return only the structured action schema.

Each agent turn should return JSON matching a schema like:

```ts
export type AgenticNavigationAction =
  | {
      type: "click";
      ref: string;
      reason: string;
    }
  | {
      type: "fill";
      ref: string;
      value: string;
      reason: string;
    }
  | {
      type: "press";
      key: "Enter" | "Tab" | "Escape";
      reason: string;
    }
  | {
      type: "done";
      reason: string;
    };
```

The runner, not the agent, executes the returned action and collects URLs after
the page settles:

```ts
export interface AgenticNavigationEvidence {
  url: string;
  sourcePageUrl: string;
  source: "anchor" | "current-url" | "network" | "script";
  linkText?: string;
  actionReason?: string;
}

export interface AgenticNavigationFinalAnswer {
  urls: string[];
  evidence: AgenticNavigationEvidence[];
  stopReason: "complete" | "limit" | "timeout" | "blocked" | "error";
  notes?: string;
}
```

xTRA should parse the action schema and discard any prose outside it. The final
URL result is assembled by xTRA from observed browser states, not copied from the
agent's final response.

## Validation And Guardrails

Never let the agent bypass deterministic gates. After each settled browser state:

1. Normalize every collected URL relative to `rootUrl`.
2. Drop invalid URLs and unsupported protocols.
3. Enforce same-origin unless the recipe explicitly allows configured origins.
4. Apply `acceptUrlRegexp` or `linkRegexp` as a hard filter.
5. De-duplicate URLs.
6. Cap the accepted URL count at `maxUrls`.
7. Optionally issue `HEAD` or cheap `GET` checks for a sample before enqueueing.

During the run:

- Enforce `timeoutMs`, `maxActions`, `maxUrls`, token budget, and model spend.
- Block destructive browser actions such as file upload, form submission beyond
  search fields, payment, account changes, and downloads.
- Keep domain allowlists explicit.
- Record each accepted URL with evidence so users can debug false positives.

## Observability

Agentic navigation will fail in softer ways than deterministic scripts, so the
run needs first-class traces.

Persist or log:

- agent provider and model,
- root URL and recipe level,
- prompt version,
- action count,
- pages visited,
- accepted URLs,
- rejected URL samples with rejection reason,
- stop reason,
- screenshots or Chrome DevTools Protocol traces for failed/blocked runs when
  allowed.

The UI should expose a concise summary on the extraction step:

- `Found 312 URLs using agentic navigation`
- `Stopped after 184 browser actions: complete`
- `Rejected 27 URLs that did not match /courses/...`

For failed runs, show the agent's blocked/error reason and the last visited URL.

## Comparison With Scripted Pagination

| Aspect | Scripted Pagination | Agentic Navigation |
| --- | --- | --- |
| Configuration | CSS selectors and waits | Natural-language goal, limits, URL filters |
| Determinism | High | Medium |
| Setup effort | Higher for complex sites | Lower for complex sites |
| Runtime cost | Low to medium | Medium to high |
| Auditability | Straightforward logs | Needs action/evidence trace |
| Best case | Known pagination controls | Mixed or unknown navigation patterns |
| Failure mode | Selector stale or wait too short | Agent misses paths or explores irrelevant UI |

The two designs should coexist. Scripted pagination is better when a site has a
single known control pattern. Agentic navigation is better when the site requires
semantic exploration that would otherwise turn into a custom mini crawler.

## Barebones De-Risking Project

Before wiring this into recipe execution, build a small standalone project that
tests the riskiest assumption: can an agent reliably choose useful browser
interactions while deterministic code remains responsible for URL retrieval?

The prototype should not use the agent to return URLs. Instead, the loop should
look like this:

1. Open a start URL in Puppeteer using the same headless Chrome setup xTRA uses
   for dynamic link discovery.
2. Capture an accessibility snapshot and a compact list of already collected
   URLs.
3. Ask the agent which single action to take next based on the recipe goal.
4. Execute that action with Puppeteer on the same page.
5. Wait for the page to settle.
6. Programmatically collect URLs from the resulting state.
7. Apply same-origin, regexp, and de-duplication filters.
8. Repeat until the agent returns `done` or limits are reached.

The prototype can live outside the production worker path, for example under
`server/scripts/agentic-navigation-poc.ts` or a temporary `experiments/`
directory. It should take a JSON input file rather than depending on database
state:

```json
{
  "rootUrl": "https://example.edu/catalog/courses",
  "goal": "Find every course detail URL in the catalogue.",
  "acceptUrlRegexp": "/courses/[A-Za-z0-9-]+",
  "sameOriginOnly": true,
  "maxActions": 100,
  "maxUrls": 1000
}
```

The output should be a local JSON artifact:

```json
{
  "urls": ["https://example.edu/catalog/courses/abc-101"],
  "actions": [
    {
      "type": "click",
      "label": "Next",
      "reason": "The next page of results should reveal more course links."
    }
  ],
  "rejectedUrls": [
    {
      "url": "https://example.edu/apply",
      "reason": "Does not match acceptUrlRegexp."
    }
  ],
  "stopReason": "complete"
}
```

This creates a useful boundary:

- Agent-owned: interpreting page state and choosing the next click, fill, key
  press, or `done`.
- Code-owned: browser execution, waits, URL extraction, URL normalization,
  acceptance filters, de-duplication, budgets, and final result shape.

Programmatic URL retrieval should start simple:

- collect anchors from `document.links`,
- optionally scope collection to `contentSelector`,
- include the current page URL after navigations,
- optionally inspect same-origin network responses for document URLs,
- run `linkRegexp` or `acceptUrlRegexp` as the hard acceptance gate.

Success criteria for the prototype:

- It finds URLs on at least one fixture with URL-less pagination.
- It avoids obvious decoy links such as apply, login, contact, and social links.
- Re-running the same input produces similar accepted URL sets.
- Every accepted URL can be traced to the browser state and action after which it
  was observed.
- The agent can stop without being asked to enumerate URLs itself.

If the prototype works, promote the loop into
`agenticNavigationDiscovery.ts`. If it fails, the failure mode will still be
informative: poor action selection can be addressed with better prompts or
snapshot summaries without rewriting URL extraction.

## Implementation Plan

1. Build the barebones de-risking project as a standalone script with JSON input
   and JSON output.
2. Validate the action-only agent loop against local fixtures and one real
   catalogue page.
3. Promote the proven loop into `agenticNavigationDiscovery.ts`, keeping URL
   collection programmatic.
4. Add `AgenticNavigationConfiguration` to shared recipe types and validation.
5. Add server/client validation that rejects `pagination`,
   `scriptedPagination`, and `agenticNavigation` on the same recipe level.
6. Implement `ClaudePuppeteerNavigationAgent` behind a provider interface.
7. Wire `processLinks` to call agentic navigation before dynamic and classic
   discovery branches when configured.
8. Add progress updates and logs for actions, URL count, and stop reason.
9. Add recipe UI fields for goal, hints, limits, and URL filter.
10. Add fixture-based tests with a local page containing URL-less pagination,
   tabs, and decoy links.

Once the prototype result quality is acceptable, wire accepted URLs into the
existing `FETCH_LINKS` enqueue path.

## Open Questions

- Should agentic navigation run inline in `FetchPage`, or should link discovery
  get a separate queue with lower concurrency?
- Which provider should be the default for deployed xTRA instances?
- How much of the browser trace can be stored without creating privacy or
  storage concerns?
- Do recipes need an explicit `allowedOrigins` field, or is same-origin plus
  `acceptUrlRegexp` enough for the first version?
- Should users review discovered URLs before xTRA enqueues detail extraction, or
  should review be optional for high-confidence runs?

## Recommendation

Build the first version as an experimental recipe option using Claude Agent SDK
plus an xTRA-owned Puppeteer/headless Chrome runner. Keep the agent contract
narrow: choose the next navigation action. Keep browser execution, URL
discovery, evidence, validation, database state, and extraction queueing in xTRA
code.

This gives xTRA a path for catalogues that do not fit scripted selectors while
preserving the deterministic extraction pipeline after URL discovery.
