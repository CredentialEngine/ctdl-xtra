import { Recipe } from "@/data/recipes";
import { CourseStructuredData } from "@common/types";
import { ApiProvider } from '@common/types';
import { CourseDogAPIService } from './coursedog';

export const apiExtractorServices = {
  [ApiProvider.Coursedog]: new CourseDogAPIService()
}

export function resolveExctractionService(recipe: Recipe): VendorExtractionService {
  const provider = recipe.configuration?.apiProvider!;
  const service = apiExtractorServices[provider];

  if (!service) {
    const supportedProviders = Object.keys(apiExtractorServices).join(', ');
    throw new Error(`Unsupported API provider ${provider}. Supported providers: ${supportedProviders}.`);
  }

  return service;
}

export class VendorExtractionService {
  public async extractData(recipe: Recipe): Promise<CourseStructuredData[]>  {
    return [];
  }
}
