import { ProviderModel } from "../../../common/types";

export const ModelPrices: Partial<
  Record<ProviderModel, { per1MInput: number; per1MOutput: number }>
> = {
  [ProviderModel.Gpt54]: {
    per1MInput: 2.5,
    per1MOutput: 15.0,
  },
  [ProviderModel.Gpt54Mini]: {
    per1MInput: 0.75,
    per1MOutput: 4.5,
  },
  [ProviderModel.Gpt54Nano]: {
    per1MInput: 0.2,
    per1MOutput: 1.25,
  },
  [ProviderModel.Gpt5]: {
    per1MInput: 1.25,
    per1MOutput: 10.0,
  },
  [ProviderModel.Gpt5Nano]: {
    per1MInput: 0.05,
    per1MOutput: 0.4,
  },
  [ProviderModel.Gpt4o]: {
    per1MInput: 2.5,
    per1MOutput: 10.0,
  },
  [ProviderModel.O3Mini]: {
    per1MInput: 1.1,
    per1MOutput: 4.4,
  },
  [ProviderModel.Gpt41]: {
    per1MInput: 2.0,
    per1MOutput: 8.0,
  },
  [ProviderModel.O4Mini]: {
    per1MInput: 1.1,
    per1MOutput: 4.4,
  },
  [ProviderModel.ClaudeHaiku45]: {
    per1MInput: 1.0,
    per1MOutput: 5.0,
  },
  [ProviderModel.ClaudeSonnet5]: {
    per1MInput: 2.0,
    per1MOutput: 10.0,
  },
  [ProviderModel.ClaudeOpus5]: {
    per1MInput: 5.0,
    per1MOutput: 25.0,
  },
  [ProviderModel.ClaudeFable51]: {
    per1MInput: 10.0,
    per1MOutput: 50.0,
  },
};

export function estimateCost(
  model: ProviderModel,
  inputTokens: number,
  outputTokens: number
) {
  const prices = ModelPrices[model];
  if (!prices) {
    throw new Error(`No pricing configured for model ${model}`);
  }
  const inputCost = (inputTokens / 1_000_000) * prices.per1MInput;
  const outputCost = (outputTokens / 1_000_000) * prices.per1MOutput;
  return inputCost + outputCost;
}
