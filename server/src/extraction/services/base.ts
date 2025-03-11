import { apiExtractorServices } from ".";
import { CourseStructuredData } from "../../../../common/types";
import { Recipe } from "../../data/recipes";

export function resolveExtractionService(
  recipe: Recipe
): VendorExtractionService {
  const provider = recipe.configuration?.apiProvider!;
  const service = apiExtractorServices[provider];

  if (!service) {
    const supportedProviders = Object.keys(apiExtractorServices).join(", ");
    throw new Error(
      `Unsupported API provider ${provider}. Supported providers: ${supportedProviders}.`
    );
  }

  return service;
}

export class VendorExtractionService {
  public async extractData(
    recipe: Recipe,
    onResultBatch: (results: CourseStructuredData[]) => Promise<boolean>
  ): Promise<void> {
    throw new Error(
      "Incorrect call on base class. Should call specialized type instead."
    );
  }
}
