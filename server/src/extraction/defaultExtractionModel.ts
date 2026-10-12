import { coerceProviderModel } from "../../../common/modelMetadata";
import { ProviderModel } from "../../../common/types";
import { SETTING_DEFAULTS } from "../constants";
import { findSetting } from "../data/settings";

export async function resolveExtractionModel(
  model?: ProviderModel
): Promise<ProviderModel> {
  if (model) {
    return model;
  }
  const setting = await findSetting<unknown>("DEFAULT_EXTRACTION_MODEL");
  return coerceProviderModel(
    setting?.value ?? SETTING_DEFAULTS.DEFAULT_EXTRACTION_MODEL
  );
}
