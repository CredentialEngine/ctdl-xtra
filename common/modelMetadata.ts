import { Provider, ProviderModel } from "./types";

export interface ModelMetadata {
  model: ProviderModel;
  label: string;
  releaseDate: string;
  provider: Provider;
  isCheapest?: boolean;
  isFlagship?: boolean;
  bestValue?: boolean;
  /** Provider-local hint shown in the extraction form (not a global badge). */
  hint?: string;
}

export const MODEL_METADATA: ModelMetadata[] = [
  {
    model: ProviderModel.Gpt5Nano,
    label: "GPT-5 Nano",
    releaseDate: "2024-05-31",
    provider: Provider.OpenAI,
    isCheapest: true,
  },
  {
    model: ProviderModel.Gpt54Nano,
    label: "GPT-5.4 Nano",
    releaseDate: "2025-03-01",
    provider: Provider.OpenAI,
  },
  {
    model: ProviderModel.Gpt54Mini,
    label: "GPT-5.4 Mini",
    releaseDate: "2025-03-01",
    provider: Provider.OpenAI,
    bestValue: true,
  },
  {
    model: ProviderModel.Gpt5,
    label: "GPT-5",
    releaseDate: "2025-01-15",
    provider: Provider.OpenAI,
  },
  {
    model: ProviderModel.Gpt54,
    label: "GPT-5.4",
    releaseDate: "2025-03-01",
    provider: Provider.OpenAI,
    isFlagship: true,
  },
  {
    model: ProviderModel.Gpt4o,
    label: "GPT-4o",
    releaseDate: "2024-04-01",
    provider: Provider.OpenAI,
  },
  {
    model: ProviderModel.Gpt41,
    label: "GPT-4.1",
    releaseDate: "2024-06-01",
    provider: Provider.OpenAI,
  },
  {
    model: ProviderModel.O3Mini,
    label: "O3 Mini",
    releaseDate: "2024-07-01",
    provider: Provider.OpenAI,
  },
  {
    model: ProviderModel.O4Mini,
    label: "O4 Mini",
    releaseDate: "2024-09-01",
    provider: Provider.OpenAI,
  },
  {
    model: ProviderModel.ClaudeHaiku45,
    label: "Claude Haiku 4.5",
    releaseDate: "2025-10-15",
    provider: Provider.Anthropic,
    hint: "fastest",
  },
  {
    model: ProviderModel.ClaudeSonnet5,
    label: "Claude Sonnet 5",
    releaseDate: "2026-05-01",
    provider: Provider.Anthropic,
  },
  {
    model: ProviderModel.ClaudeOpus5,
    label: "Claude Opus 5",
    releaseDate: "2026-05-01",
    provider: Provider.Anthropic,
  },
  {
    model: ProviderModel.ClaudeFable51,
    label: "Claude Fable 5.1",
    releaseDate: "2026-09-01",
    provider: Provider.Anthropic,
    hint: "newest",
  },
];

export const DEFAULT_EXTRACTION_MODEL: ProviderModel =
  MODEL_METADATA.find((m) => m.bestValue)?.model ?? ProviderModel.Gpt54Mini;

export function isProviderModel(value: unknown): value is ProviderModel {
  return (
    typeof value === "string" &&
    (Object.values(ProviderModel) as string[]).includes(value)
  );
}

export function coerceProviderModel(
  value: unknown,
  fallback: ProviderModel = DEFAULT_EXTRACTION_MODEL
): ProviderModel {
  return isProviderModel(value) ? value : fallback;
}

export function providerForModel(model: ProviderModel): Provider {
  return String(model).startsWith("claude-")
    ? Provider.Anthropic
    : Provider.OpenAI;
}

export const PROVIDER_LABELS: Record<Provider, string> = {
  [Provider.OpenAI]: "OpenAI",
  [Provider.Anthropic]: "Anthropic",
};

export function modelLabel(model: ProviderModel | string): string {
  return (
    MODEL_METADATA.find((m) => m.model === model)?.label ?? String(model)
  );
}

export function modelsForProvider(provider: Provider): ModelMetadata[] {
  return MODEL_METADATA.filter((m) => m.provider === provider);
}
