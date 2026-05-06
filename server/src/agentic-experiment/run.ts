/** This is PoC quality code and was not meant to be used in production as is. */

import "dotenv/config";
import { createReadStream } from "fs";
import { mkdir, writeFile } from "fs/promises";
import path from "path";
import { parse } from "fast-csv";
import type { CanUseTool } from "@anthropic-ai/claude-agent-sdk";
import {
  CatalogueType,
  ProviderModel,
  type TextInclusion,
} from "../../../common/types";
import type { SimplifiedMarkdown } from "../types";
import type { CsvExportItem } from "../csv";
import { createAgentMessageMonitor } from "./agentMessageLog";
import { colorize, errorStyled, logStyled, warnStyled } from "./agentLogColors";
import { shortToolName } from "./agentToolLog";
import {
  AgentModel,
  parseAgentModel,
  readOptionalAgentModelEnv,
  resolveAgentModelPrompt,
  type AgentModelPrompts,
} from "./agentModels";
import {
  bootstrapAgenticModuleEnv,
  buildClaudeAgentSdkEnv,
  formatAgenticApiRetryConfig,
  validateAgenticRuntime,
} from "./runtimeEnv";
import {
  createPageRegistryMcpServer,
  PageRegistry,
  REGISTER_PAGE_CONTENT_MCP_TOOL,
  type RegisteredPage,
} from "./pageRegistry";
import { BackgroundPageExtractor } from "./backgroundPageExtractor";
import {
  buildAgenticExtractionPagesDir,
  saveRegisteredPageContent,
} from "./pageContentStorage";

const DEFAULT_MAX_BUDGET_USD = 50;
const AGENTIC_EXTRACTIONS_DIR = path.join(__dirname, "extractions");

export interface AgenticContentPage {
  url: string;
  title: string | null;
  /** Empty after extraction; raw text is not retained in memory. */
  content: string;
}

export interface AgenticContentResult {
  sourceUrl: string;
  crawlSummary: {
    pagesVisited: number;
    strategy: string;
    limitations: string[];
  };
  pages: AgenticContentPage[];
}

export interface ResumeCheckpoint {
  lastSeenName: string;
  lastSeenUrl: string;
}

export interface AgenticExperimentOptions {
  targetUrl: string;
  catalogueType: CatalogueType;
  configName?: string;
  /** OpenAI model for post-crawl entity extraction. */
  modelOverride?: ProviderModel;
  /** Anthropic model for the agent crawl (SDK `model` option). Omit for SDK default. */
  agentModel?: AgentModel;
  /** Per-model prompt snippets keyed by agent model. */
  agentModelPrompts?: AgentModelPrompts;
  extraInstructions?: string;
  maxTurns?: number;
  maxBudgetUsd?: number;
  /** Claude Agent SDK session ID to resume. Requires resumeFile. */
  resumeSession?: string;
  /** CSV from a prior run; last row supplies resume checkpoint fields. */
  resumeFile?: string;
}

export type AgenticCatalogueRunOptions = Pick<
  AgenticExperimentOptions,
  "extraInstructions" | "configName" | "resumeSession" | "resumeFile"
>;

export interface AgenticExperimentResult {
  crawlResult: AgenticContentResult;
  extractionResults: AgenticExtractionDryRunResult;
  urlsPath: string;
  csvPath: string;
}

export type AgenticExtractionDryRunResult = Array<{
  url: string;
  entities: Array<{
    entity: Record<string, any>;
    textInclusion: TextInclusion<any>;
  }>;
  skipped?: boolean;
}>;

function usage() {
  console.error(
    [
      "Usage:",
      "  pnpm run agentic:experiment -- <catalogue-preset> [--resume-session=<id> --resume-file=<csv>]",
      "  pnpm run agentic:experiment -- <url> --catalogue-type <type> [--model <openai-model>] [--agent-model <anthropic-model>] [--resume-session=<id> --resume-file=<csv>] [extra prompt instructions]",
      "",
      "Example:",
      "  pnpm run agentic:experiment -- berkley",
      "  pnpm run agentic:experiment -- https://example.edu/catalog --catalogue-type COURSES --model gpt-5 --agent-model haiku \"Collect visible content from the catalogue page\"",
      "  pnpm run agentic:experiment -- antelope-course-competencies --resume-session=abc123 --resume-file=src/agentic-experiment/extractions/antelope-course-competencies-29-05-2026-17-39.csv",
      "",
      `Catalogue types: ${Object.values(CatalogueType).join(", ")}`,
      `Extraction models: ${Object.values(ProviderModel).join(", ")}`,
      `Agent models: SDK default, or ${Object.values(AgentModel).join(", ")}`,
    ].join("\n")
  );
}

function readCliFlagValue(arg: string, flag: string) {
  if (arg.startsWith(`${flag}=`)) {
    return arg.slice(flag.length + 1);
  }

  return undefined;
}

export function parseResumeCliOptions(args: string[]) {
  let resumeSession: string | undefined;
  let resumeFile: string | undefined;
  const remaining: string[] = [];

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    const sessionValue = readCliFlagValue(arg, "--resume-session");

    if (sessionValue !== undefined) {
      resumeSession = sessionValue;
      continue;
    }

    if (arg === "--resume-session") {
      resumeSession = args[++i];
      continue;
    }

    const fileValue = readCliFlagValue(arg, "--resume-file");

    if (fileValue !== undefined) {
      resumeFile = fileValue;
      continue;
    }

    if (arg === "--resume-file") {
      resumeFile = args[++i];
      continue;
    }

    remaining.push(arg);
  }

  if (resumeSession && !resumeFile) {
    console.error("--resume-file is required when using --resume-session.");
    usage();
    process.exit(1);
  }

  return { resumeSession, resumeFile, remaining };
}

export async function readResumeCheckpointFromCsv(
  resumeFile: string
): Promise<ResumeCheckpoint> {
  const absolutePath = path.resolve(resumeFile);
  const rows: Record<string, string>[] = [];

  await new Promise<void>((resolve, reject) => {
    createReadStream(absolutePath)
      .pipe(parse({ headers: true }))
      .on("data", (row: Record<string, string>) => rows.push(row))
      .on("end", resolve)
      .on("error", reject);
  });

  if (!rows.length) {
    throw new Error(`Resume CSV has no data rows: ${absolutePath}`);
  }

  let lastSeenName: string | undefined;
  for (let i = rows.length - 1; i >= 0; i--) {
    const name = (rows[i]["ceasn:name"] ?? "").trim();
    if (name) {
      lastSeenName = name;
      break;
    }
  }

  const lastSeenUrl = (rows[rows.length - 1]["Page URL"] ?? "").trim();

  if (!lastSeenName) {
    throw new Error(
      `Resume CSV has no row with ceasn:name in ${absolutePath}`
    );
  }

  if (!lastSeenUrl) {
    throw new Error(
      `Resume CSV last row is missing Page URL in ${absolutePath}`
    );
  }

  return { lastSeenName, lastSeenUrl };
}

export function parseAgenticExperimentCliArgs(
  argv: string[]
):
  | AgenticExperimentOptions
  | ({
      cataloguePreset: string;
    } & AgenticCatalogueRunOptions) {
  const args = argv[0] === "--" ? argv.slice(1) : argv;
  const [targetUrl, ...rest] = args;

  if (!targetUrl || targetUrl === "--help" || targetUrl === "-h") {
    usage();
    process.exit(targetUrl ? 0 : 1);
  }

  const {
    resumeSession,
    resumeFile,
    remaining: restAfterResume,
  } = parseResumeCliOptions(rest);

  try {
    new URL(targetUrl);
  } catch {
    if (!targetUrl.startsWith("-")) {
      return {
        cataloguePreset: targetUrl,
        extraInstructions: restAfterResume.join(" ").trim() || undefined,
        resumeSession,
        resumeFile,
      };
    }

    console.error(`Invalid URL or catalogue preset: ${targetUrl}`);
    usage();
    process.exit(1);
  }

  let catalogueType: CatalogueType | undefined;
  let modelOverride: ProviderModel | undefined;
  let agentModel: AgentModel | undefined;
  const promptParts: string[] = [];

  for (let i = 0; i < restAfterResume.length; i++) {
    const arg = restAfterResume[i];

    if (arg === "--catalogue-type") {
      const value = rest[++i];
      if (!Object.values(CatalogueType).includes(value as CatalogueType)) {
        console.error(`Invalid catalogue type: ${value ?? ""}`);
        usage();
        process.exit(1);
      }
      catalogueType = value as CatalogueType;
      continue;
    }

    if (arg === "--model") {
      const value = rest[++i];
      if (!Object.values(ProviderModel).includes(value as ProviderModel)) {
        console.error(`Invalid model: ${value ?? ""}`);
        usage();
        process.exit(1);
      }
      modelOverride = value as ProviderModel;
      continue;
    }

    if (arg === "--agent-model") {
      const value = rest[++i];
      const parsed = parseAgentModel(value);
      if (!parsed) {
        console.error(`Invalid agent model: ${value ?? ""}`);
        usage();
        process.exit(1);
      }
      agentModel = parsed;
      continue;
    }

    promptParts.push(arg);
  }

  if (!catalogueType) {
    console.error("Missing required --catalogue-type option.");
    usage();
    process.exit(1);
  }

  return {
    targetUrl,
    catalogueType,
    configName: configNameFromUrl(targetUrl),
    modelOverride,
    agentModel: agentModel ?? readOptionalAgentModelEnv(),
    extraInstructions: promptParts.join(" ").trim() || undefined,
    resumeSession,
    resumeFile,
  };
}

function sanitizeConfigName(name: string) {
  return (
    name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "") || "run"
  );
}

function formatExtractionTimestamp(date = new Date()) {
  const pad = (value: number) => String(value).padStart(2, "0");

  return [
    pad(date.getDate()),
    pad(date.getMonth() + 1),
    date.getFullYear(),
    pad(date.getHours()),
    pad(date.getMinutes()),
  ].join("-");
}

function configNameFromUrl(targetUrl: string) {
  try {
    const hostname = new URL(targetUrl).hostname.replace(/^www\./, "");
    return sanitizeConfigName(hostname.split(".")[0] ?? "custom");
  } catch {
    return "custom";
  }
}

export function buildAgenticExtractionBasename(
  configName: string,
  date = new Date()
) {
  return `${sanitizeConfigName(configName)}-${formatExtractionTimestamp(date)}`;
}

export function buildAgenticExtractionCsvPath(
  configName: string,
  date = new Date()
) {
  return path.join(
    AGENTIC_EXTRACTIONS_DIR,
    `${buildAgenticExtractionBasename(configName, date)}.csv`
  );
}

export function buildAgenticExtractionPartialCsvPath(csvPath: string) {
  return csvPath.replace(/\.csv$/i, "-partial.csv");
}

export function buildAgenticExtractionUrlsPath(
  configName: string,
  date = new Date()
) {
  return path.join(
    AGENTIC_EXTRACTIONS_DIR,
    `${buildAgenticExtractionBasename(configName, date)}.urls.txt`
  );
}

async function writeRegisteredUrlsFile(urlsPath: string, urls: string[]) {
  await writeFile(urlsPath, `${urls.join("\n")}\n`, "utf8");
}

async function writeExperimentCsv(options: {
  csvPath: string;
  extractionResults: AgenticExtractionDryRunResult;
  catalogueType: CatalogueType;
  sourceUrl: string;
}) {
  const csvItems = flattenExtractionResultsForCsv(options.extractionResults);
  const { writeBulkUploadCsvToPath } = await import("../csv");
  await writeBulkUploadCsvToPath(
    options.csvPath,
    csvItems,
    options.catalogueType,
    options.sourceUrl
  );
  return csvItems.length;
}

function installPartialCsvInterruptHandler(options: {
  partialCsvPath: string;
  catalogueType: CatalogueType;
  sourceUrl: string;
  getExtractionResults: () => AgenticExtractionDryRunResult;
}) {
  let handled = false;

  const handler = () => {
    if (handled) {
      process.exit(130);
      return;
    }

    handled = true;
    warnStyled("warn", "Interrupt received — writing partial CSV before exit…");

    void (async () => {
      try {
        const extractionResults = options.getExtractionResults();
        const rowCount = await writeExperimentCsv({
          csvPath: options.partialCsvPath,
          extractionResults,
          catalogueType: options.catalogueType,
          sourceUrl: options.sourceUrl,
        });
        logStyled(
          "success",
          `Wrote ${rowCount} row(s) to partial CSV at ${options.partialCsvPath}`
        );
      } catch (error) {
        errorStyled(
          "error",
          `Failed to write partial CSV: ${error instanceof Error ? error.message : String(error)}`
        );
      } finally {
        process.removeListener("SIGINT", handler);
        process.exit(130);
      }
    })();
  };

  process.on("SIGINT", handler);
  return () => {
    process.removeListener("SIGINT", handler);
  };
}

function readNumberEnv(name: string, fallback: number) {
  const value = process.env[name];

  if (!value) {
    return fallback;
  }

  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    throw new Error(`${name} must be a positive number when set.`);
  }

  return parsed;
}

function readOptionalPositiveNumberEnv(name: string) {
  const value = process.env[name]?.trim();

  if (!value) {
    return undefined;
  }

  if (value === "unlimited" || value === "none") {
    return undefined;
  }

  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    throw new Error(
      `${name} must be a positive number, "unlimited", or "none" when set.`
    );
  }

  return parsed;
}

function buildPrompt(
  targetUrl: string,
  extraInstructions: string,
  agentModel?: AgentModel,
  agentModelPrompts?: AgentModelPrompts,
  resumeCheckpoint?: ResumeCheckpoint
) {
  const modelSpecificPrompt = resolveAgentModelPrompt(
    agentModel,
    agentModelPrompts
  );

  const resumePrefix = resumeCheckpoint
    ? [
        "Resume previous instructions.",
        `The last thing we saw was "${resumeCheckpoint.lastSeenName}" from URL ${resumeCheckpoint.lastSeenUrl}.`,
        "Continue the crawl from there.\n",
      ].join("\n")
    : "";

  return [
    resumePrefix,
    "You are running an agentic web crawl using Puppeteer MCP.\n",
    `Start at: ${targetUrl}\n`,
    "\n",
    "Communication:\n",
    "- Explain in plain language what you are doing as you work (which section you are exploring, what page you opened, what you plan to do next).\n",
    "- Do not wrap your explanations in JSON or code blocks.\n",
    "\n",
    "Navigation:\n",
    "- Explore the page index of programs, courses, credentials, or other relevant sections.\n",
    "- Navigate deeper until you reach the detail pages that contain the target information.\n",
    "- After collecting each detail page, call registerPageContent before moving to the next one.\n",
    "- Do not use direct URL navigation as catalogues do not respect links, use clicks only.\n",
    "\n",
    "registerPageContent (xTRA tool) — use structured tool arguments only for this call:\n",
    "- url: canonical URL of the page\n",
    "- title: optional page title\n",
    "- content: full visible page text copied as-is; avoid nav sidebars, headers, and footers\n",
    "- Pass url, title, and content as separate tool fields. Do not put JSON inside the content field.\n",
    `\n${modelSpecificPrompt ?? ""}\n`,
    "\n",
    "Do not rewrite, summarize, classify, or restructure page content in registerPageContent.\n",
    "Do not log in, submit forms, bypass access controls, or leave the target site's domain.\n",
    "This is not an interactive chat; do not ask for clarification or respond to user input.\n",
    "Some catalogues may be very large, that is OK, just run as long as you can.\n",
    "\n",
    extraInstructions
      ? `Additional instructions: ${extraInstructions}\n`
      : "",
    "\n",
    "When finished, stop calling tools and give a brief plain-language summary of how the crawl went: pages collected, how you navigated, and any limitations.\n",
  ]
    .filter(Boolean)
    .join("\n");
}

function parseCrawlSummary(
  result: string | undefined,
  pagesRegistered: number
): AgenticContentResult["crawlSummary"] {
  if (!result?.trim()) {
    return {
      pagesVisited: pagesRegistered,
      strategy: "Registered pages via registerPageContent",
      limitations: [],
    };
  }

  const trimmed = result.trim();

  if (trimmed.startsWith("{")) {
    try {
      const parsed = JSON.parse(trimmed) as {
        crawlSummary?: {
          pagesVisited?: number;
          strategy?: string;
          limitations?: string[];
        };
        strategy?: string;
        limitations?: string[];
      };

      const summary = parsed.crawlSummary;

      return {
        pagesVisited: summary?.pagesVisited ?? pagesRegistered,
        strategy:
          summary?.strategy ??
          parsed.strategy ??
          "Registered pages via registerPageContent",
        limitations: summary?.limitations ?? parsed.limitations ?? [],
      };
    } catch {
      // Fall through to plain-language handling below.
    }
  }

  return {
    pagesVisited: pagesRegistered,
    strategy: trimmed,
    limitations: [],
  };
}

function logCrawlSummary(summary: AgenticContentResult["crawlSummary"]) {
  logStyled("crawlHeader", "Crawl summary:");
  console.log(
    `${colorize("crawlLabel", "  pagesVisited:")} ${colorize("crawlValue", String(summary.pagesVisited))}`
  );
  console.log(
    `${colorize("crawlLabel", "  strategy:")} ${colorize("crawlValue", summary.strategy)}`
  );
  if (summary.limitations.length) {
    console.log(colorize("crawlLabel", "  limitations:"));
    for (const limitation of summary.limitations) {
      console.log(colorize("limitation", `    - ${limitation}`));
    }
  }
}

function buildCrawlResult(
  sourceUrl: string,
  pages: RegisteredPage[],
  agentSummary: string | undefined,
  pagesRegistered: number,
  terminalFailure?: AgentCrawlTerminalState
): AgenticContentResult {
  let crawlSummary = parseCrawlSummary(agentSummary, pagesRegistered);

  if (terminalFailure && terminalFailure.subtype !== "success") {
    const limitation = terminalFailureMessage(terminalFailure.subtype);
    crawlSummary = {
      ...crawlSummary,
      limitations: [
        ...crawlSummary.limitations,
        limitation,
        ...terminalFailure.errors.filter(
          (error) =>
            !crawlSummary.limitations.includes(error) && error !== limitation
        ),
      ],
    };
  }

  return {
    sourceUrl,
    crawlSummary,
    pages,
  };
}

interface AgentCrawlTerminalState {
  subtype: string;
  agentResult?: string;
  errors: string[];
  numTurns?: number;
  totalCostUsd?: number;
  stopReason?: string | null;
  terminalReason?: string;
  sessionId?: string;
  isError?: boolean;
  apiErrorStatus?: number | null;
  permissionDenials?: Array<{
    tool_name: string;
    tool_use_id: string;
  }>;
}

function terminalFailureMessage(subtype: string) {
  switch (subtype) {
    case "error_max_turns":
      return "Crawl stopped after reaching the maximum turn limit; partial page collection was preserved.";
    case "error_max_budget_usd":
      return "Crawl stopped after reaching the maximum budget limit; partial page collection was preserved.";
    default:
      return `Crawl ended with status ${subtype}; partial page collection was preserved.`;
  }
}

function logAgentTerminalState(terminal: AgentCrawlTerminalState) {
  const detailParts = [
    `subtype=${terminal.subtype}`,
    terminal.stopReason != null ? `stop_reason=${terminal.stopReason}` : undefined,
    terminal.terminalReason ? `terminal_reason=${terminal.terminalReason}` : undefined,
    terminal.sessionId ? `session=${terminal.sessionId}` : undefined,
  ].filter(Boolean);

  logStyled("terminalHeader", `Agent result: ${detailParts.join(", ")}`);

  if (terminal.isError) {
    warnStyled("warn", "  Result flagged is_error=true.");
  }

  if (terminal.apiErrorStatus != null) {
    warnStyled("warn", `  API error status: HTTP ${terminal.apiErrorStatus}`);
  }

  if (terminal.permissionDenials?.length) {
    for (const denial of terminal.permissionDenials) {
      warnStyled(
        "error",
        `  Denied ${shortToolName(denial.tool_name)} (${denial.tool_use_id})`
      );
    }
  }

  if (terminal.subtype !== "success") {
    for (const error of terminal.errors) {
      warnStyled("error", `  ${error}`);
    }
  }

  if (terminal.agentResult?.trim()) {
    logStyled("terminalHeader", "--- Agent final result ---");
    console.log(colorize("finalSummary", terminal.agentResult));
  } else if (terminal.subtype === "success") {
    warnStyled(
      "warn",
      "Agent finished with success but returned no final summary text."
    );
  }

  if (terminal.numTurns !== undefined) {
    const cost =
      terminal.totalCostUsd !== undefined
        ? `, estimated cost $${terminal.totalCostUsd.toFixed(4)}`
        : "";
    logStyled("success", `Completed in ${terminal.numTurns} turns${cost}.`);
  }
}

async function runAgentCrawl(options: {
  prompt: string;
  serverRoot: string;
  maxTurns?: number;
  maxBudgetUsd: number;
  agentModel?: AgentModel;
  resumeSession?: string;
  pageRegistry: PageRegistry;
  onPageRegistered?: (page: RegisteredPage) => void;
}): Promise<AgentCrawlTerminalState> {
  const { query } = await import("@anthropic-ai/claude-agent-sdk");
  let terminal: AgentCrawlTerminalState = {
    subtype: "unknown",
    errors: [],
  };

  const turnLimitLabel =
    options.maxTurns === undefined ? "unlimited" : String(options.maxTurns);
  const agentModelLabel = options.agentModel ?? "SDK default";
  logStyled(
    "meta",
    `Agent limits: maxTurns=${turnLimitLabel}, maxBudgetUsd=$${options.maxBudgetUsd.toFixed(2)}, agentModel=${agentModelLabel}`
  );
  if (options.resumeSession) {
    logStyled("meta", `Resuming Claude session ${options.resumeSession}`);
  }
  logStyled("meta", `SDK API retry: ${formatAgenticApiRetryConfig()}`);

  const messageMonitor = createAgentMessageMonitor();
  messageMonitor.start();

  try {
    for await (const message of query({
      prompt: options.prompt,
      options: {
        cwd: options.serverRoot,
        ...(options.maxTurns !== undefined
          ? { maxTurns: options.maxTurns }
          : {}),
        maxBudgetUsd: options.maxBudgetUsd,
        ...(options.agentModel ? { model: options.agentModel } : {}),
        ...(options.resumeSession ? { resume: options.resumeSession } : {}),
        includePartialMessages: true,
        env: buildClaudeAgentSdkEnv(),
        permissionMode: "dontAsk",
        settingSources: [],
        canUseTool,
        mcpServers: {
          puppeteer: {
            command: "npx",
            args: ["-y", "@modelcontextprotocol/server-puppeteer"],
            env: {
              PUPPETEER_LAUNCH_OPTIONS: JSON.stringify({
                headless: true,
                defaultViewport: {
                  width: 1194,
                  height: 834,
                  deviceScaleFactor: 2,
                  isMobile: true,
                  hasTouch: true,
                  isLandscape: true,
                },
                args: [
                  "--user-agent=Mozilla/5.0 (iPad; CPU OS 12_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.4 Mobile/15E148 Safari/604.1",
                ],
              }),
            },
          },
          xtra: createPageRegistryMcpServer(options.pageRegistry, {
            onRegistered: options.onPageRegistered,
          }),
        },
        allowedTools: [
          "ToolSearch",
          "mcp__puppeteer__*",
          REGISTER_PAGE_CONTENT_MCP_TOOL,
        ],
      },
    })) {
      messageMonitor.handleMessage(message);

      if (message.type === "result") {
        terminal = {
          subtype: message.subtype,
          agentResult:
            message.subtype === "success" ? message.result : undefined,
          errors: message.subtype === "success" ? [] : message.errors,
          numTurns: message.num_turns,
          totalCostUsd: message.total_cost_usd,
          stopReason: message.stop_reason,
          terminalReason: message.terminal_reason,
          sessionId: message.session_id,
          isError: message.is_error,
          apiErrorStatus:
            message.subtype === "success" ? message.api_error_status : undefined,
          permissionDenials:
            message.subtype === "success"
              ? message.permission_denials
              : undefined,
        };
        logAgentTerminalState(terminal);
      }
    }
  } catch (error) {
    terminal.errors.push(
      error instanceof Error ? error.message : String(error)
    );
    if (terminal.subtype === "unknown") {
      terminal.subtype = "error_during_execution";
    }
    errorStyled(
      "error",
      `Agent query ended unexpectedly: ${error instanceof Error ? error.message : String(error)}`
    );
  } finally {
    messageMonitor.stop();
  }

  return terminal;
}

async function extractRegisteredPage(
  page: RegisteredPage,
  options: {
    catalogueType: CatalogueType;
    modelOverride?: ProviderModel;
  }
): Promise<AgenticExtractionDryRunResult[number]> {
  const { determinePresenceOfEntity } = await import(
    "../extraction/llm/determinePresenceOfEntity"
  );
  const { extractAndVerifyEntityData } = await import(
    "../extraction/llm/extractAndVerifyEntityData"
  );
  const { getCatalogueTypeDefinition } = await import("../extraction/catalogueTypes");

  const entityDef = getCatalogueTypeDefinition(options.catalogueType);
  const extractionOptions = {
    url: page.url,
    content: page.content as SimplifiedMarkdown,
    screenshot: "",
    catalogueType: options.catalogueType,
    modelOverride: options.modelOverride,
  };

  if (entityDef.presencePrompt) {
    const presence = await determinePresenceOfEntity(extractionOptions, entityDef);
    if (!presence.present) {
      return {
        url: page.url,
        entities: [],
        skipped: true,
      };
    }
  }

  const entities = [];
  for await (const entityResult of extractAndVerifyEntityData(extractionOptions)) {
    entities.push(entityResult);
  }

  return {
    url: page.url,
    entities,
  };
}

export function flattenExtractionResultsForCsv(
  extractionResults: AgenticExtractionDryRunResult
): CsvExportItem[] {
  const items: CsvExportItem[] = [];

  for (const pageResult of extractionResults) {
    if (pageResult.skipped) {
      continue;
    }

    for (const { entity, textInclusion } of pageResult.entities) {
      if (entity.items) {
        for (const structuredData of entity.items) {
          items.push({
            url: pageResult.url,
            structuredData,
            textInclusion,
          });
        }
      } else {
        items.push({
          url: pageResult.url,
          structuredData: entity,
          textInclusion,
        });
      }
    }
  }

  return items;
}

const canUseTool: CanUseTool = async (toolName) => {
  if (
    toolName === "ToolSearch" ||
    toolName.startsWith("mcp__puppeteer__") ||
    toolName === REGISTER_PAGE_CONTENT_MCP_TOOL
  ) {
    return { behavior: "allow" };
  }

  return {
    behavior: "deny",
    message: "This crawl only permits Puppeteer MCP tools and registerPageContent.",
  };
};

export async function runAgenticExperiment(
  options: AgenticExperimentOptions
): Promise<AgenticExperimentResult> {
  const serverRoot = path.resolve(__dirname, "../..");
  const maxTurns =
    options.maxTurns ?? readOptionalPositiveNumberEnv("AGENTIC_EXPERIMENT_MAX_TURNS");
  const maxBudgetUsd =
    options.maxBudgetUsd ??
    readNumberEnv("AGENTIC_EXPERIMENT_MAX_BUDGET_USD", DEFAULT_MAX_BUDGET_USD);
  const runStartedAt = new Date();
  const outputConfigName =
    options.configName ?? configNameFromUrl(options.targetUrl);
  const urlsPath = buildAgenticExtractionUrlsPath(outputConfigName, runStartedAt);
  const csvPath = buildAgenticExtractionCsvPath(outputConfigName, runStartedAt);
  const partialCsvPath = buildAgenticExtractionPartialCsvPath(csvPath);
  const pagesDir = buildAgenticExtractionPagesDir(csvPath);
  validateAgenticRuntime();
  bootstrapAgenticModuleEnv();
  await mkdir(AGENTIC_EXTRACTIONS_DIR, { recursive: true });
  const pageRegistry = new PageRegistry();
  const extractionOptions = {
    catalogueType: options.catalogueType,
    modelOverride: options.modelOverride,
  };
  const backgroundExtractor = new BackgroundPageExtractor({
    pageRegistry,
    extractionOptions,
    extractPage: extractRegisteredPage,
  });

  const removePartialCsvInterruptHandler = installPartialCsvInterruptHandler({
    partialCsvPath,
    catalogueType: options.catalogueType,
    sourceUrl: options.targetUrl,
    getExtractionResults: () => backgroundExtractor.getCompletedResults(),
  });

  try {
    const onPageRegistered = (page: RegisteredPage) => {
      logStyled("success", `Registered ${page.url} via registerPageContent.`);
      saveRegisteredPageContent({ extractionDir: pagesDir, page });
      backgroundExtractor.onPageRegistered(page);
    };

    const agentModel = options.agentModel ?? readOptionalAgentModelEnv();
    const resumeCheckpoint =
      options.resumeSession && options.resumeFile
        ? await readResumeCheckpointFromCsv(options.resumeFile)
        : undefined;

    if (resumeCheckpoint) {
      logStyled(
        "meta",
        `Resume checkpoint: "${resumeCheckpoint.lastSeenName}" at ${resumeCheckpoint.lastSeenUrl}`
      );
    }

    const terminal = await runAgentCrawl({
      prompt: buildPrompt(
        options.targetUrl,
        options.extraInstructions ?? "",
        agentModel,
        options.agentModelPrompts,
        resumeCheckpoint
      ),
      serverRoot,
      maxTurns,
      maxBudgetUsd,
      agentModel,
      resumeSession: options.resumeSession,
      pageRegistry,
      onPageRegistered,
    });

    const registeredPageCount = pageRegistry.count();

    if (registeredPageCount === 0) {
      logCrawlSummary(
        parseCrawlSummary(terminal.agentResult, registeredPageCount)
      );
      process.exitCode = 1;
      throw new Error(
        terminal.subtype === "success"
          ? "Agent did not register any pages via registerPageContent."
          : `Agent failed (${terminal.subtype}) without registering any pages.`
      );
    }

    const registeredUrls = pageRegistry.list().map((page) => page.url);
    await writeRegisteredUrlsFile(urlsPath, registeredUrls);
    logStyled(
      "success",
      `Wrote ${registeredUrls.length} registered URL(s) to ${urlsPath}`
    );

    const extractionResults = await backgroundExtractor.waitForAll();

    if (terminal.subtype !== "success" || !terminal.agentResult?.trim()) {
      warnStyled(
        "warn",
        `Continuing with ${registeredPageCount} registered page(s) after ${terminal.subtype}.`
      );
    }

    const crawlResult = buildCrawlResult(
      options.targetUrl,
      pageRegistry.list(),
      terminal.agentResult,
      registeredPageCount,
      terminal.subtype !== "success" ? terminal : undefined
    );
    logCrawlSummary(crawlResult.crawlSummary);
    logStyled(
      "success",
      `Registered ${crawlResult.pages.length} page(s) via registerPageContent.`
    );
    logStyled(
      "meta",
      `Extracted ${extractionResults.length} page(s); raw page text discarded from memory.`
    );

    const rowCount = await writeExperimentCsv({
      csvPath,
      extractionResults,
      catalogueType: options.catalogueType,
      sourceUrl: crawlResult.sourceUrl || options.targetUrl,
    });
    logStyled(
      "success",
      `Wrote ${rowCount} row(s) to bulk upload CSV at ${csvPath}`
    );

    return {
      crawlResult,
      extractionResults,
      urlsPath,
      csvPath,
    };
  } finally {
    removePartialCsvInterruptHandler();
  }
}

async function runCataloguePreset(
  cataloguePreset: string,
  options: AgenticCatalogueRunOptions = {}
) {
  const modulePath = path.join(__dirname, "catalogues", `${cataloguePreset}.ts`);
  const preset = await import(modulePath);
  if (typeof preset.default !== "function") {
    throw new Error(
      `Catalogue preset ${cataloguePreset} must export a default run function.`
    );
  }

  return preset.default({
    extraInstructions: options.extraInstructions,
    configName: cataloguePreset,
    resumeSession: options.resumeSession,
    resumeFile: options.resumeFile,
  });
}

async function main() {
  const parsedArgs = parseAgenticExperimentCliArgs(process.argv.slice(2));

  if ("cataloguePreset" in parsedArgs) {
    await runCataloguePreset(parsedArgs.cataloguePreset, parsedArgs);
    return;
  }

  await runAgenticExperiment(parsedArgs);
}

if (require.main === module) {
  main().catch((err) => {
    console.error(err);
    process.exitCode = 1;
  });
}
