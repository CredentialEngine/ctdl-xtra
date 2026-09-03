import { TextInclusion } from "../../../common/types";
import { getCatalogueTypeDefinition } from "./catalogueTypes";
import type { DefaultLlmPageOptions } from "./llm";
import { determinePresenceOfEntity } from "./llm/determinePresenceOfEntity";
import { extractAndVerifyEntityData } from "./llm/extractAndVerifyEntityData";

export interface ExtractedEntityResult {
  entity: Record<string, any>;
  textInclusion: TextInclusion<any>;
}

function flattenExtractedEntity(
  entity: Record<string, any>,
  textInclusion: TextInclusion<any>
): ExtractedEntityResult[] {
  if (Array.isArray(entity.items)) {
    return entity.items.map((item: Record<string, any>) => ({
      entity: item,
      textInclusion,
    }));
  }
  return [{ entity, textInclusion }];
}

/**
 * Presence check (when configured) plus extract-and-verify, flattening
 * `entity.items` the same way the extractData worker persists entries.
 */
export async function* runEntityExtraction(
  options: DefaultLlmPageOptions
): AsyncGenerator<ExtractedEntityResult> {
  const catalogueType = options.catalogueType;
  if (!catalogueType) {
    throw new Error("Catalogue type is required");
  }

  const entityDef = getCatalogueTypeDefinition(catalogueType);
  if (entityDef.presencePrompt) {
    const result = await determinePresenceOfEntity(options, entityDef);
    if (!result.present) {
      return;
    }
  }

  for await (const { entity, textInclusion } of extractAndVerifyEntityData(
    options
  )) {
    for (const entry of flattenExtractedEntity(entity, textInclusion)) {
      yield entry;
    }
  }
}
