import type {
  SDKAPIRetryMessage,
  SDKMessage,
} from "@anthropic-ai/claude-agent-sdk";
import {
  AgentActivityMonitor,
  readHeartbeatIntervalSec,
} from "./agentActivityMonitor";
import { colorize, errorStyled, logStyled, warnStyled } from "./agentLogColors";
import { AgentStreamPrinter } from "./agentStreamPrinter";
import { formatToolUseForLog, shortToolName } from "./agentToolLog";
import {
  extractToolResultsFromUserMessage,
  formatToolResultLabel,
  ToolCallTracker,
} from "./agentToolResultLog";

function isMcpServerHealthy(status: string) {
  return /connect(ed)?/i.test(status);
}

function printSystemInitMessage(
  message: Extract<SDKMessage, { type: "system"; subtype: "init" }>
) {
  const mcpServers = message.mcp_servers
    .map((server) => `${server.name}:${server.status}`)
    .join(", ");

  logStyled("init", "Claude SDK initialized");
  console.log(colorize("initDetail", `  session: ${message.session_id}`));
  console.log(colorize("initDetail", `  cwd: ${message.cwd}`));
  console.log(colorize("initDetail", `  model: ${message.model}`));
  console.log(
    colorize("initDetail", `  MCP servers: ${mcpServers || "none"}`)
  );

  for (const server of message.mcp_servers) {
    if (!isMcpServerHealthy(server.status)) {
      warnStyled(
        "error",
        `  MCP server ${server.name} failed to connect: ${server.status}`
      );
    }
  }
}

function isApiRetryMessage(
  message: SDKMessage
): message is SDKAPIRetryMessage {
  return message.type === "system" && message.subtype === "api_retry";
}

function printApiRetryMessage(message: SDKAPIRetryMessage) {
  const status =
    message.error_status != null
      ? `HTTP ${message.error_status}`
      : "connection error";
  warnStyled(
    "warn",
    `[agent] API retry ${message.attempt}/${message.max_retries} in ${message.retry_delay_ms}ms (${status}, ${message.error})`
  );
}

function printAgentStatusMessage(
  message: Extract<SDKMessage, { type: "system"; subtype: "status" }>
) {
  if (message.status === "requesting") {
    logStyled("status", "[agent] requesting model response...");
    return;
  }

  if (message.status === "compacting") {
    logStyled("status", "[agent] compacting conversation context...");
  }
}

function printAgentSystemMessage(message: SDKMessage) {
  if (message.type !== "system") {
    return;
  }

  switch (message.subtype) {
    case "init":
      printSystemInitMessage(message);
      return;
    case "status":
      printAgentStatusMessage(message);
      return;
    case "permission_denied":
      warnStyled(
        "error",
        `[agent] denied ${shortToolName(message.tool_name)}: ${message.message}`
      );
      return;
    case "notification":
      logStyled("notify", `[agent] ${message.text}`);
      return;
    case "task_progress":
      logStyled(
        "task",
        `[agent task ${message.task_id}] ${message.description}` +
          (message.last_tool_name
            ? ` (last tool: ${shortToolName(message.last_tool_name)})`
            : "")
      );
      return;
    case "mirror_error":
      errorStyled(
        "error",
        `[agent] transcript mirror error: ${message.error}`
      );
      return;
    default:
      return;
  }
}

function printToolProgressMessage(
  message: Extract<SDKMessage, { type: "tool_progress" }>,
  tracker: ToolCallTracker
) {
  tracker.remember(message.tool_use_id, message.tool_name);
  const elapsed = Math.floor(message.elapsed_time_seconds);
  logStyled(
    "toolProgress",
    `[tool running ${shortToolName(message.tool_name)} ${elapsed}s]`
  );
}

function printUserMessage(
  message: Extract<SDKMessage, { type: "user" }>,
  tracker: ToolCallTracker
) {
  if (message.tool_use_result === undefined) {
    return;
  }

  const results = extractToolResultsFromUserMessage(message, tracker);
  const errors = results.filter((entry) => entry.isError);
  const successes = results.filter((entry) => !entry.isError);

  if (errors.length) {
    for (const entry of errors) {
      const label = formatToolResultLabel(entry);
      const detail = entry.text ? `: ${entry.text}` : "";
      warnStyled("toolError", `${label}${detail}`);
    }
  }

  if (successes.length) {
    logStyled("toolFinished", "[tool finished]");
    for (const entry of successes) {
      if (!entry.text || !entry.toolName?.startsWith("mcp__puppeteer__")) {
        continue;
      }

      logStyled(
        "toolPuppeteer",
        `  ${formatToolResultLabel(entry)}${entry.text ? `: ${entry.text}` : ""}`
      );
    }
  } else if (!errors.length) {
    logStyled("toolFinished", "[tool finished]");
  }
}

function printAssistantMessage(
  message: Extract<SDKMessage, { type: "assistant" }>,
  tracker: ToolCallTracker,
  options?: { skipText?: boolean }
) {
  if (message.error) {
    warnStyled("error", `[agent] assistant turn error: ${message.error}`);
  }

  for (const block of message.message.content) {
    if (block.type === "text") {
      if (options?.skipText) {
        continue;
      }

      const text = block.text.trim();
      if (text) {
        process.stdout.write(`${colorize("prose", text)}\n`);
      }
      continue;
    }

    if (block.type === "tool_use") {
      tracker.remember(block.id, block.name);
      const input =
        block.input && typeof block.input === "object"
          ? (block.input as Record<string, unknown>)
          : {};
      process.stdout.write(`${formatToolUseForLog(block.name, input)}\n`);
    }
  }
}

function printToolUseSummaryMessage(
  message: Extract<SDKMessage, { type: "tool_use_summary" }>
) {
  logStyled("meta", `[tool summary] ${message.summary}`);
}

function handleAgentSdkMessage(
  message: SDKMessage,
  activityMonitor: AgentActivityMonitor,
  streamPrinter: AgentStreamPrinter,
  tracker: ToolCallTracker
) {
  if (isApiRetryMessage(message)) {
    printApiRetryMessage(message);
    activityMonitor.touch();
    return;
  }

  activityMonitor.touch();

  if (message.type === "stream_event") {
    streamPrinter.handleStreamEvent(message, tracker);
    return;
  }

  if (message.type === "system") {
    printAgentSystemMessage(message);
    return;
  }

  if (message.type === "tool_progress") {
    printToolProgressMessage(message, tracker);
    return;
  }

  if (message.type === "user") {
    printUserMessage(message, tracker);
    return;
  }

  if (message.type === "assistant") {
    streamPrinter.finishTurn();
    printAssistantMessage(message, tracker, { skipText: true });
    return;
  }

  if (message.type === "tool_use_summary") {
    printToolUseSummaryMessage(message);
    return;
  }

  if (message.type === "result") {
    streamPrinter.finishTurn();
  }
}

export function createAgentMessageMonitor(options?: {
  heartbeatIntervalSec?: number;
}) {
  const activityMonitor = new AgentActivityMonitor(
    options?.heartbeatIntervalSec ?? readHeartbeatIntervalSec()
  );
  const streamPrinter = new AgentStreamPrinter();
  const tracker = new ToolCallTracker();

  return {
    start() {
      activityMonitor.start();
    },
    stop() {
      activityMonitor.stop();
    },
    handleMessage(message: SDKMessage) {
      handleAgentSdkMessage(message, activityMonitor, streamPrinter, tracker);
    },
  };
}
