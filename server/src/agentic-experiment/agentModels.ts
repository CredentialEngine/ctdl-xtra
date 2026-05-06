/** Anthropic models supported for the agent crawl (Claude Agent SDK `model` option). */
export enum AgentModel {
  Haiku = "haiku",
  Sonnet = "sonnet",
  Opus = "opus",
}

/** Per-model prompt snippets keyed by agent model; inserted into the crawl prompt. */
export type AgentModelPrompts = Partial<Record<AgentModel, string>>;

export function parseAgentModel(value?: string): AgentModel | undefined {
  const trimmed = value?.trim();
  if (!trimmed) {
    return undefined;
  }

  if (Object.values(AgentModel).includes(trimmed as AgentModel)) {
    return trimmed as AgentModel;
  }

  return undefined;
}

export function resolveAgentModelPrompt(
  agentModel: AgentModel | undefined,
  prompts?: AgentModelPrompts
) {
  if (!agentModel || !prompts) {
    return undefined;
  }

  const prompt = prompts[agentModel]?.trim();
  return prompt || undefined;
}

export function readOptionalAgentModelEnv(
  name = "AGENTIC_EXPERIMENT_AGENT_MODEL"
) {
  return parseAgentModel(process.env[name]);
}
