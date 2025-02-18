import { PaginationConfiguration, RecipeConfiguration } from "@common/types";

export interface RecipeDecorateOptions {
  pageUrl: string;
  pageContent: string;
  screenshot?: string;
  pageType: string;
  pagination?: PaginationConfiguration;
}

export class BaseProbe {
  constructor() {}

  public async decorateRecipe(
    configuration: RecipeConfiguration,
    options: RecipeDecorateOptions
  ): Promise<RecipeConfiguration> {
    return Promise.resolve(configuration);
  }
}

export class ProbeManager extends BaseProbe {
  constructor(private probes: BaseProbe[]) {
    super();
  }

/**
 * Applies a sequence of probe transformations to the given recipe configuration.
 * 
 * This method iterates through all the probes and sequentially applies their 
 * `decorateRecipe` method to the configuration. Each probe modifies the 
 * configuration based on its logic, and the result is passed to the next probe.
 * 
 * @param configuration - The initial recipe configuration to be modified.
 * @param options - Additional options for decorating the recipe.
 * @returns A Promise resolving to the final decorated recipe configuration.
 */
  public async decorateRecipe(
    configuration: RecipeConfiguration,
    options: RecipeDecorateOptions
  ): Promise<RecipeConfiguration> {
    const reducer = async (
      previousResult: Promise<RecipeConfiguration>,
      probe: BaseProbe
    ): Promise<RecipeConfiguration> => {
      return await probe.decorateRecipe(await previousResult, options);
    };
    return this.probes.reduce(reducer, Promise.resolve(configuration));
  }
}

export function registerProbes(probes: BaseProbe[]) {
  return new ProbeManager(probes);
}