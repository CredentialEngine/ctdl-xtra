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
]);

export function supportsTopP(model: ProviderModel): boolean {
  if (providerForModel(model) !== Provider.OpenAI) {
    return false;
  }
  return !NO_TOP_P.has(model);
}

export function stripsImages(model: ProviderModel): boolean {
  return model === ProviderModel.O3Mini;
}

/** Fable 5.1 rejects forced `tool_choice: { type: "tool" }`. */
export function usesForcedToolChoice(model: ProviderModel): boolean {
  return model !== ProviderModel.ClaudeFable51;
}
