import { resolveCname } from "node:dns/promises";
import { URL } from "node:url";

import {
  ApiConfig,
  ApiProvider,
  PageType,
  RecipeConfiguration,
} from "@common/types";
import { BaseProbe, RecipeDecorateOptions } from "./base";

export class CourseDog extends BaseProbe {
  public async detectApiProviderRecipe(
    options: RecipeDecorateOptions
  ): Promise<RecipeConfiguration | undefined> {
    const url = new URL(options.pageUrl);
    const cnameHost = await resolveCname(url.hostname).catch(() => Promise.resolve([]));
    const isCourseDogCname = cnameHost.some((entry) =>
      entry.includes("coursedog")
    );
    const hasCourseDogInPage = options.pageContent.includes("coursedog");

    if (!isCourseDogCname && !hasCourseDogInPage) {
      // we didn't find any hints the page is using Coursedog
      return;
    }

    const courseDogConfig: Partial<ApiConfig[ApiProvider.Coursedog]> = {
      catalogIds: [],
    };
    const potentialSchoolIds = this.detectSchoolIds(options.pageContent);
    for (const school of potentialSchoolIds) {
      const catalogs: { id: string }[] | undefined =
        await this.fetchCatalogs(school);
      if (Array.isArray(catalogs)) {
        // @ts-ignore
        courseDogConfig.catalogIds = catalogs.map((entry) => entry.id);
        if (catalogs?.length > 0) {
          courseDogConfig.schoolId = school;
          break;
        }
      }
    }

    return {
      pageType: PageType.API_REQUEST,
      apiProvider: ApiProvider.Coursedog,
      apiConfig: courseDogConfig as ApiConfig[ApiProvider.Coursedog],
    };
  }

  detectSchoolIds(pageContent: string): string[] {
    const detectorExpressions = [
      /<meta.+name="og:url".+content=\"(.+)-catalog.coursedog.com.+>/,
      /school:\s?['|"](.[^\"]+)['|"]/,
    ];

    return detectorExpressions
      .map((pattern) => pageContent.match(pattern)?.at(1) || "")
      .filter(Boolean);
  }

  async fetchCatalogs(
    schooldId: string
  ): Promise<{ id: string }[] | undefined> {
    const url = `https://app.coursedog.com/api/v1/ca/${schooldId}/catalogs`;
    try {
      return (await fetch(url).then((response) => response.json())) as {
        id: string;
      }[];
    } catch (_) {}
  }
}