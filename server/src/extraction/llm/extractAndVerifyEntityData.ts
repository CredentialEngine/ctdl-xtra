import nlp from "compromise";

import { DefaultLlmPageOptions } from ".";
import { CatalogueType, TextInclusion } from "../../../../common/types";
import { SimplifiedMarkdown } from "../../types";
import { getCatalogueTypeDefinition } from "../catalogueTypes";
import { shouldChunk, splitChunks } from "../splitChunks";
import { extractEntityData } from "./extractEntityData";

export function preprocessText(text: string): string {
  return text
    .toLowerCase()
    .replace(/(?<!\!)\[([^\]]+)\]\([^)]*\)/g, "$1") // remove MD links
    .replace(/[^a-z0-9]/g, "");
}

export function stripNonAlphanumeric(text: string): string {
  return text.replace(/[^A-z0-9\.\-\s\;\\\,]/g, "");
}

async function reportTextInclusion(
  entity: Record<string, any>,
  preprocessedContent: string,
  sentences: string[],
  catalogueType: CatalogueType
): Promise<TextInclusion<any>> {
  const result: TextInclusion<any> = {} as TextInclusion<any>;
  const entityDef = getCatalogueTypeDefinition(catalogueType);

  for (const [key, value] of Object.entries(entity)) {
    if (value !== undefined && value !== null) {
      const preprocessedValue = preprocessText(String(value));
      const verifyFullPhrases = entityDef.verifyFullPhrases && entityDef.propertiesRequiredAsPhrases?.includes(key);
      const entitySentences = verifyFullPhrases && nlp(String(value)).sentences().out('array');
      
      result[key] = {
        full: preprocessedContent.includes(preprocessedValue),
      };

      if (verifyFullPhrases) {
        result[key].sentences = entitySentences.every((sentence: string) => sentences.includes(sentence));
      }
    }
  }

  return result;
}

const passesVerification = (
  textInclusion: TextInclusion<any>,
  catalogueType: CatalogueType
) => {
  const entityDef = getCatalogueTypeDefinition(catalogueType);

  const requiredFields = Object.entries(entityDef.properties || {})
    .filter(([_, prop]) => prop.required)
    .map(([key]) => key);

  const passes = requiredFields.every(
    (field) => !textInclusion[field] || textInclusion[field].full
  );
  const sentencesPass = entityDef.verifyFullPhrases 
  ?
    entityDef.propertiesRequiredAsPhrases?.every(
      (field) => textInclusion[field].sentences
    )
  : true;
  
  return passes && sentencesPass;
};

async function verifyAndRetryExtraction(
  entity: Record<string, any>,
  options: DefaultLlmPageOptions,
  preprocessedContent: string,
  sentences: string[],
  catalogueType: CatalogueType
) {
  let textInclusion = await reportTextInclusion(
    entity,
    preprocessedContent,
    sentences,
    catalogueType
  );
  let retryCount = 0;
  const MAX_RETRIES = 3;

  while (
    retryCount < MAX_RETRIES &&
    !passesVerification(textInclusion, catalogueType)
  ) {
    const { data: focusedEntityData } = await extractEntityData(
      options,
      catalogueType,
      entity
    );
    if (focusedEntityData?.length) {
      entity = focusedEntityData[0];
      textInclusion = await reportTextInclusion(
        entity,
        preprocessedContent,
        sentences,
        catalogueType
      );
    }
    retryCount++;
  }

  return { entity, textInclusion };
}

async function maybeChunkContent(
  options: DefaultLlmPageOptions
): Promise<DefaultLlmPageOptions[]> {
  if (options.catalogueType !== CatalogueType.COURSES) {
    return [options];
  }
  const willChunk = await shouldChunk(options);
  if (willChunk) {
    const chunks = await splitChunks(options);
    return chunks.map((chunk) => ({
      ...options,
      content: chunk as SimplifiedMarkdown,
    }));
  }
  return [options];
}

export async function extractAndVerifyEntityData(
  options: DefaultLlmPageOptions
) {
  const chunks = await maybeChunkContent(options);
  const catalogueType = options.catalogueType;
  const entityDef = catalogueType ? getCatalogueTypeDefinition(catalogueType!) : undefined;

  if (!catalogueType) {
    throw new Error("Catalogue type is required");
  }

  const results = [];
  for (const chunkOptions of chunks) {
    const { data: entitiesData } = await extractEntityData(chunkOptions, catalogueType);
    if (!entitiesData || entitiesData.length === 0) {
      console.log(`Couldn't find ${catalogueType} data from page ${chunkOptions.url}`);
      continue;
    }

    const preprocessedContent = preprocessText(chunkOptions.content);
    let sentences = entityDef?.verifyFullPhrases
      ? nlp(stripNonAlphanumeric(chunkOptions.content)).sentences().out('array')
      : [];

    for (const entity of entitiesData) {
      const verifiedExtraction = await verifyAndRetryExtraction(
        entity,
        chunkOptions,
        preprocessedContent,
        sentences,
        catalogueType
      );
      results.push(verifiedExtraction);
    }
  }

  return results;
}
