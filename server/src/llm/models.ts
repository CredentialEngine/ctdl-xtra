import { providerForModel } from "../../../common/modelMetadata";
import { Provider, ProviderModel } from "../../../common/types";

export { providerForModel };

export const ANTHROPIC_MAX_TOKENS = 8192;

const NO_TOP_P = new Set<ProviderModel>([
  ProviderModel.Gpt5,
  ProviderModel.Gpt5Nano,
  ProviderModel.Gpt54,
  ProviderModel.Gpt54Mini,
  ProviderModel.Gpt54Nano,
  ProviderModel.Gpt6Astra,
  ProviderModel.Gpt61Sol,
  ProviderModel.Gpt6Luna,
]);

/** Luna: chat/completions tools require reasoning_effort none. */
const REASONING_EFFORT_NONE_FOR_TOOLS = new Set<ProviderModel>([
  ProviderModel.Gpt6Luna,
]);

export function openAiReasoningEffortNoneForTools(
  model: ProviderModel
): boolean {
  return REASONING_EFFORT_NONE_FOR_TOOLS.has(model);
}

/** Astra/Sol: chat/completions cannot combine tools with reasoning; use JSON schema output. */
const OPENAI_JSON_SCHEMA_FOR_TOOLS = new Set<ProviderModel>([
  ProviderModel.Gpt6Astra,
  ProviderModel.Gpt61Sol,
]);

export function openAiUsesJsonSchemaForTools(model: ProviderModel): boolean {
  return OPENAI_JSON_SCHEMA_FOR_TOOLS.has(model);
}

export function supportsTopP(model: ProviderModel): boolean {
  if (providerForModel(model) !== Provider.OpenAI) {
    return false;
  }
  return !NO_TOP_P.has(model);
}

export function stripsImages(model: ProviderModel): boolean {
  return model === ProviderModel.O3Mini;
}

/** Anthropic models that require structured JSON instead of forced tool_choice. */
const ANTHROPIC_JSON_SCHEMA_FOR_TOOLS = new Set<ProviderModel>([
  ProviderModel.ClaudeFable51,
  ProviderModel.ClaudeSonnet55,
  ProviderModel.ClaudeOpus55,
]);

export function usesForcedToolChoice(model: ProviderModel): boolean {
  return !ANTHROPIC_JSON_SCHEMA_FOR_TOOLS.has(model);
}
