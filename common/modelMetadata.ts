import { ProviderModel } from "./types";

export interface ModelMetadata {
  model: ProviderModel;
  label: string;
  releaseDate: string;
  isCheapest?: boolean;
  isFlagship?: boolean;
  bestValue?: boolean;
}

export const MODEL_METADATA: ModelMetadata[] = [
  {
    model: ProviderModel.Gpt5Nano,
    label: "GPT-5 Nano",
    releaseDate: "2024-05-31",
    isCheapest: true,
  },
  {
    model: ProviderModel.Gpt54Nano,
    label: "GPT-5.4 Nano",
    releaseDate: "2025-03-01",
  },
  {
    model: ProviderModel.Gpt54Mini,
    label: "GPT-5.4 Mini",
    releaseDate: "2025-03-01",
    bestValue: true,
  },
  {
    model: ProviderModel.Gpt5,
    label: "GPT-5",
    releaseDate: "2025-01-15",
  },
  {
    model: ProviderModel.Gpt54,
    label: "GPT-5.4",
    releaseDate: "2025-03-01",
    isFlagship: true,
  },
  {
    model: ProviderModel.Gpt4o,
    label: "GPT-4o",
    releaseDate: "2024-04-01",
  },
  {
    model: ProviderModel.Gpt41,
    label: "GPT-4.1",
    releaseDate: "2024-06-01",
  },
  {
    model: ProviderModel.O3Mini,
    label: "O3 Mini",
    releaseDate: "2024-07-01",
  },
  {
    model: ProviderModel.O4Mini,
    label: "O4 Mini",
    releaseDate: "2024-09-01",
  },
];

export const DEFAULT_EXTRACTION_MODEL: ProviderModel =
  MODEL_METADATA.find((m) => m.bestValue)?.model ?? ProviderModel.Gpt54Mini;
