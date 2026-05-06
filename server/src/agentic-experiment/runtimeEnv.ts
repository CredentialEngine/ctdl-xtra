const DEFAULT_MAX_API_RETRIES = 10;
const DEFAULT_API_TIMEOUT_MS = 600_000;
const DEFAULT_STREAM_IDLE_TIMEOUT_MS = 300_000;

function readOptionalNonNegativeNumberEnv(name: string, fallback: number) {
  const value = process.env[name]?.trim();

  if (!value) {
    return fallback;
  }

  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) {
    throw new Error(`${name} must be a non-negative number when set.`);
  }

  return parsed;
}

function readOptionalBooleanEnv(name: string, fallback: boolean) {
  const value = process.env[name]?.trim();

  if (!value) {
    return fallback;
  }

  if (value === "off" || value === "0" || value === "false") {
    return false;
  }

  if (value === "on" || value === "1" || value === "true") {
    return true;
  }

  throw new Error(
    `${name} must be "on", "off", "true", "false", "1", or "0" when set.`
  );
}

/** Max Anthropic API retries inside the Claude Code subprocess (SDK `api_retry`). */
export function readAgenticMaxApiRetries() {
  return readOptionalNonNegativeNumberEnv(
    "AGENTIC_EXPERIMENT_MAX_API_RETRIES",
    DEFAULT_MAX_API_RETRIES
  );
}

export function readAgenticApiTimeoutMs() {
  return readOptionalNonNegativeNumberEnv(
    "AGENTIC_EXPERIMENT_API_TIMEOUT_MS",
    DEFAULT_API_TIMEOUT_MS
  );
}

export function readAgenticStreamIdleTimeoutMs() {
  return readOptionalNonNegativeNumberEnv(
    "AGENTIC_EXPERIMENT_STREAM_IDLE_TIMEOUT_MS",
    DEFAULT_STREAM_IDLE_TIMEOUT_MS
  );
}

export function readAgenticStreamWatchdogEnabled() {
  return readOptionalBooleanEnv(
    "AGENTIC_EXPERIMENT_STREAM_WATCHDOG",
    true
  );
}

/**
 * Environment for the Claude Agent SDK subprocess. Spreads `process.env` so
 * PATH and keys remain available, then sets retry/timeout knobs the CLI reads.
 */
export function buildClaudeAgentSdkEnv(): Record<string, string | undefined> {
  const env: Record<string, string | undefined> = {
    ...process.env,
    CLAUDE_CODE_MAX_RETRIES: String(readAgenticMaxApiRetries()),
    API_TIMEOUT_MS: String(readAgenticApiTimeoutMs()),
    CLAUDE_AGENT_SDK_CLIENT_APP: "ctdl-xtra-agentic-experiment",
  };

  if (readAgenticStreamWatchdogEnabled()) {
    env.CLAUDE_ENABLE_STREAM_WATCHDOG = "1";
    env.CLAUDE_STREAM_IDLE_TIMEOUT_MS = String(
      readAgenticStreamIdleTimeoutMs()
    );
  }

  return env;
}

export function formatAgenticApiRetryConfig() {
  return [
    `maxApiRetries=${readAgenticMaxApiRetries()}`,
    `apiTimeoutMs=${readAgenticApiTimeoutMs()}`,
    `streamWatchdog=${readAgenticStreamWatchdogEnabled() ? "on" : "off"}`,
  ].join(", ");
}

export function validateAgenticRuntime() {
  if (!process.env.ANTHROPIC_API_KEY?.trim()) {
    throw new Error("ANTHROPIC_API_KEY is required for the agentic crawl.");
  }

  if (!process.env.OPENAI_API_KEY?.trim()) {
    throw new Error(
      "OPENAI_API_KEY is required for the post-crawl extraction step."
    );
  }
}

/**
 * Shared extraction modules import the data layer at load time. The agentic
 * experiment does not use the database, but those imports still require these
 * env vars to be present. Placeholders are set only when missing.
 */
export function bootstrapAgenticModuleEnv() {
  validateAgenticRuntime();

  if (!process.env.DATABASE_URL?.trim()) {
    process.env.DATABASE_URL = "postgresql://127.0.0.1:1/agentic-unused";
  }

  if (!process.env.ENCRYPTION_KEY?.trim()) {
    process.env.ENCRYPTION_KEY = "00000000000000000000000000000000";
  }
}
