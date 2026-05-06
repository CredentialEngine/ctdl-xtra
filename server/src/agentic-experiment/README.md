# Agentic Experiment

Minimal Claude Agent SDK + Puppeteer MCP crawl experiment.

## Prerequisites

- Run commands from `server/`.
- Install dependencies with `pnpm install`.
- Set `ANTHROPIC_API_KEY` in `server/.env` or in your shell environment.

The runner registers the Puppeteer MCP server in code:

```ts
mcpServers: {
  puppeteer: {
    command: "npx",
    args: ["-y", "@modelcontextprotocol/server-puppeteer"],
    env: {
      PUPPETEER_LAUNCH_OPTIONS: "{\"headless\":true}",
    },
  },
}
```

## Usage

```bash
pnpm run agentic:experiment -- https://example.edu/catalog
```

Add extra prompt instructions after the URL:

```bash
pnpm run agentic:experiment -- https://example.edu/catalog "Focus on course names, descriptions, and detail page URLs"
```

## Optional Limits

- `AGENTIC_EXPERIMENT_MAX_BUDGET_USD` defaults to `10`. The agent stops with `error_max_budget_usd` when the client-side cost estimate reaches this cap.
- `AGENTIC_EXPERIMENT_MAX_TURNS` is unset by default (unlimited turns). Set a positive number, or `unlimited`/`none`, to override. When omitted, only the budget cap applies.
- `AGENTIC_EXPERIMENT_HEARTBEAT_SEC` defaults to `30`. Logs `[agent idle Ns — session still active]` when no SDK events arrive for that long (set `0` or `off` to disable).
- `AGENTIC_EXPERIMENT_MAX_API_RETRIES` defaults to `10`. Passed to the SDK subprocess as `CLAUDE_CODE_MAX_RETRIES`; transient API/network failures emit `api_retry` events and are retried automatically.
- `AGENTIC_EXPERIMENT_API_TIMEOUT_MS` defaults to `600000` (10 minutes per attempt). Passed as `API_TIMEOUT_MS`.
- `AGENTIC_EXPERIMENT_STREAM_WATCHDOG` defaults to `on`. When enabled, sets `CLAUDE_ENABLE_STREAM_WATCHDOG=1` so stalled response streams abort and enter the SDK retry path. Override idle threshold with `AGENTIC_EXPERIMENT_STREAM_IDLE_TIMEOUT_MS` (default `300000`).

## Activity monitoring

The runner enables SDK partial streaming (`includePartialMessages`) and logs several built-in progress signals:

- **Streaming text** — assistant prose appears token-by-token instead of only after each turn completes.
- **`[Using puppeteer:…]` / `done`** — tool call start/stop from stream events.
- **`[tool running … Ns]`** — `tool_progress` events while Puppeteer or xTRA tools execute.
- **`[agent] requesting model response...`** — `status` events while waiting on the API.
- **`[agent idle Ns]`** — local heartbeat when the SDK is silent longer than the heartbeat interval.
- **`[agent] API retry N/M`** — `api_retry` system events when the SDK retries a failed API call (network/HTTP errors).
- **`[tool finished]`** — user messages carrying tool results between turns.

See [Stream responses in real-time](https://code.claude.com/docs/en/agent-sdk/streaming-output) in the Agent SDK docs.

## MVP Constraints

- Only Puppeteer MCP tools are pre-approved.
- Non-Puppeteer tools are denied by `canUseTool`, except `ToolSearch` so Claude can discover the MCP tool names.
- Page text is registered via the xTRA `registerPageContent` tool (`url` / `title` / `content` tool fields). The agent explains its progress and final summary in plain language; only tool calls use structured arguments.
- Extraction runs in a background queue during the crawl so MCP tool calls return immediately.
