import { resolveCname } from 'node:dns/promises';
import { URL } from 'node:url';

import { ApiProvider, RecipeConfiguration } from "@common/types";
import { BaseProbe, RecipeDecorateOptions } from "./base";

export class CourseDog extends BaseProbe {
  public async decorateRecipe(
    receipe: RecipeConfiguration,
    options: RecipeDecorateOptions
  ): Promise<RecipeConfiguration> {
    const url = new URL(options.pageUrl);
    const cnameHost = await resolveCname(url.hostname);
    const isCourseDogCname = cnameHost.some(entry => entry.includes("coursedog"));
    const hasCourseDogInPage = options.pageContent.includes('coursedog');

    const apiProvider = isCourseDogCname || hasCourseDogInPage
      ? ApiProvider.Coursedog
      : undefined;

    return { ...receipe, apiProvider };
  }
}
