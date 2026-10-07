import { DEFAULT_EXTRACTION_MODEL } from "../../common/modelMetadata";

export const SETTING_DEFAULTS = {
  MAX_EXTRACTION_BUDGET: 50,
  PROXY_ENABLED: false,
  PROXY: [] as string[],
  OPENAI_API_KEY: "",
  ANTHROPIC_API_KEY: "",
  DEFAULT_EXTRACTION_MODEL,
};
