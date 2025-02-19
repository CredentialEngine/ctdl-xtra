import { PaginationConfiguration, RecipeConfiguration } from "@common/types";

export interface RecipeDecorateOptions {
  pageUrl: string;
  pageContent: string;
  screenshot?: string;
  pageType?: string;
  pagination?: PaginationConfiguration;
}

export class BaseProbe {
  constructor() {}

  public async detectApiProviderRecipe(
    options: RecipeDecorateOptions
  ): Promise<RecipeConfiguration | undefined> {
    return undefined;
  }
}

export class ProbeManager extends BaseProbe {
  constructor(private probes: BaseProbe[]) {
    super();
  }


  public async detectApiProviderRecipe(
    options: RecipeDecorateOptions
  ): Promise<RecipeConfiguration | undefined> {
    for (const probe of this.probes) {
      const recipe = await probe.detectApiProviderRecipe(options)
      if (recipe) {
        return recipe;
      }
    }
  }
}

export function registerProbes(probes: BaseProbe[]) {
  return new ProbeManager(probes);
}