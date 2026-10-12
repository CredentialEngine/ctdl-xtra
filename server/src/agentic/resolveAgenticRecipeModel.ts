import { coerceAnthropicModel } from "../../../common/modelMetadata";
import { SETTING_DEFAULTS } from "../constants";
import { findSetting } from "../data/settings";

/** Model id stored on an agentic recipe job, from the setting or the Sonnet default. */
export async function resolveAgenticRecipeModel(): Promise<string> {
  const setting = await findSetting<unknown>("AGENTIC_RECIPE_MODEL");
  return coerceAnthropicModel(
    setting?.value ?? SETTING_DEFAULTS.AGENTIC_RECIPE_MODEL
  );
}
