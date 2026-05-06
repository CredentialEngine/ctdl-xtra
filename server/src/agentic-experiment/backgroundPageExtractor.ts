import type {
  CatalogueType,
  ProviderModel,
  TextInclusion,
} from "../../../common/types";
import { errorStyled, logStyled, warnStyled } from "./agentLogColors";
import type { PageRegistry, RegisteredPage } from "./pageRegistry";

type PageExtractionResult = {
  url: string;
  entities: Array<{
    entity: Record<string, any>;
    textInclusion: TextInclusion<any>;
  }>;
  skipped?: boolean;
};

export type ExtractRegisteredPageFn = (
  page: RegisteredPage,
  options: BackgroundPageExtractorOptions["extractionOptions"]
) => Promise<PageExtractionResult>;

export interface BackgroundPageExtractorOptions {
  pageRegistry: PageRegistry;
  extractionOptions: {
    catalogueType: CatalogueType;
    modelOverride?: ProviderModel;
  };
  extractPage: ExtractRegisteredPageFn;
}

function snapshotPage(page: RegisteredPage): RegisteredPage {
  return {
    url: page.url,
    title: page.title,
    content: page.content,
  };
}

export class BackgroundPageExtractor {
  private readonly results: PageExtractionResult[] = [];
  private readonly chainsByUrl = new Map<string, Promise<void>>();

  constructor(private readonly options: BackgroundPageExtractorOptions) {}

  /** Sync — schedules extraction without blocking the caller. */
  onPageRegistered(page: RegisteredPage) {
    const snapshot = snapshotPage(page);
    const previous = this.chainsByUrl.get(snapshot.url) ?? Promise.resolve();
    const next = previous
      .catch(() => {})
      .then(() => this.extractSnapshot(snapshot));

    this.chainsByUrl.set(snapshot.url, next);
  }

  private async extractSnapshot(snapshot: RegisteredPage) {
    try {
      const result = await this.options.extractPage(
        snapshot,
        this.options.extractionOptions
      );
      this.results.push(result);
      const entityCount = result.skipped ? 0 : result.entities.length;
      logStyled(
        result.skipped ? "warn" : "success",
        `Extracted ${snapshot.url} (${result.skipped ? "skipped" : `${entityCount} entity/entities`}), discarded page text.`
      );
    } catch (error) {
      errorStyled(
        "error",
        `Extraction failed for ${snapshot.url}: ${String(error)}`
      );
      this.results.push({ url: snapshot.url, entities: [] });
    } finally {
      this.options.pageRegistry.discardContent(snapshot.url);
    }
  }

  async waitForAll(): Promise<PageExtractionResult[]> {
    const chains = [...this.chainsByUrl.values()];
    if (chains.length) {
      logStyled(
        "meta",
        `Waiting for ${chains.length} background extraction chain(s) to finish…`
      );
      await Promise.allSettled(chains);
    }

    const pendingContent = this.options.pageRegistry
      .list()
      .filter((page) => page.content.trim()).length;
    if (pendingContent) {
      warnStyled(
        "warn",
        `${pendingContent} registered page(s) still have content in memory after extraction drain.`
      );
    }

    return [...this.results];
  }

  getCompletedResults(): PageExtractionResult[] {
    return [...this.results];
  }
}
