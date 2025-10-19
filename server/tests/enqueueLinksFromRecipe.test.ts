require("dotenv").config();
import os from "os";
import {
  beforeAll,
  afterAll,
  beforeEach,
  describe,
  expect,
  test,
  vi,
} from "vitest";
import {
  CatalogueType,
  ExtractionStatus,
  PageType,
  Step,
} from "../../common/types";
import { promises as fs } from "fs";
import path from "path";

vi.mock("../src/data/extractions", () => {
  const createStepAndPages = vi.fn().mockImplementation(({ pages }: any) => {
    return {
      pages: pages.map((p: any, idx: number) => ({ id: idx + 1000, ...p })),
    };
  });
  return {
    createStepAndPages,
    findPageForJob: vi.fn().mockImplementation(async (_crawlPageId: number) => {
      return {
        id: 1,
        extractionId: 1,
        crawlStepId: 10,
        url: "https://example.com/",
        extraction: {
          id: 1,
          status: ExtractionStatus.WAITING,
          recipe: {
            acknowledgedSkipRobotsTxt: true,
            robotsTxt: undefined,
            catalogue: { catalogueType: CatalogueType.COURSES },
          },
        },
        crawlStep: {
          id: 10,
          step: Step.FETCH_ROOT,
          configuration: {
            pageType: PageType.CATEGORY_LINKS,
            linkRegexp: "\\/programs\\/coursesaz\\/[a-z0-9_]+\\/",
            links: { pageType: PageType.DETAIL },
          },
        },
      };
    }),
    findPageByUrl: vi.fn().mockResolvedValue(undefined),
    updateExtraction: vi.fn().mockResolvedValue(undefined),
    updatePage: vi.fn().mockResolvedValue(undefined),
  };
});

// Skip: We need to provide a database and using SQL does not work.
// More work is needed to setup an ephemeral database for tests with Postgres.
describe.skip("Recipe execution", () => {
  let tempDir =
    path.join(os.tmpdir(), "xtra-test-temp");

  beforeAll(async () => {
    process.env.ENCRYPTION_KEY =
      process.env.ENCRYPTION_KEY || "12345678901234567890123456789012"
    process.env.EXTRACTION_FILES_PATH = tempDir;
    await fs.mkdir(tempDir, { recursive: true });
  });

  afterAll(async () => {
    try {
      if (!tempDir.includes(os.tmpdir())) {
        throw new Error(`Temp directory ${tempDir} is not in OS temporary directory. Refusing to remove for safety.`);
      }
      await fs.rm(tempDir, { recursive: true, force: true });
    } catch {}
  });

  beforeEach(() => {
    vi.resetModules();
    vi.doMock("../src/workers", async () => {
      const actual = await vi.importActual<any>("../src/workers");
      return {
        ...actual,
        getRedisConnection: () => ({
          set: vi.fn().mockResolvedValue("OK"),
          pttl: vi.fn().mockResolvedValue(0),
        }),
      };
    });
  });

  test("should correctly enqueue pages for provided recipe", async () => {
    const extractionId = 1;
    const crawlStepId = 10;
    const pageId = 1;

    const { performJob } = await import("../src/workers/fetchPage");
    const { PageType } = await import("../../common/types");
    const configuration = {
      pageType: PageType.CATEGORY_LINKS,
      linkRegexp:
        "(https://cabrillo.elumenapp.com)/catalog/[d-]+/department(.+)",
      links: { pageType: PageType.DETAIL },
      pageLoadWaitTime: 1000,
    } as any;

    const crawlPage = {
      id: pageId,
      extractionId,
      crawlStepId: crawlStepId,
      url: "https://cabrillo.elumenapp.com/catalog/2025-2026/programs-and-courses",
      crawlStep: { step: Step.FETCH_ROOT, configuration },
      extraction: {
        id: 999,
        status: ExtractionStatus.IN_PROGRESS,
        recipe: {
          acknowledgedSkipRobotsTxt: true,
          catalogue: { catalogueType: CatalogueType.COURSES },
        },
      },
    } as any;

    const module = await import("../src/data/extractions");
    const createStepAndPages =
      module.createStepAndPages as unknown as ReturnType<typeof vi.fn>;

    const job: any = {
      data: { crawlPageId: pageId, extractionId: extractionId },
      opts: { jobId: `fetchPage.${pageId}` },
      updateProgress: vi.fn(),
    };

    await performJob(job, crawlPage, { delayInterval: 0, startWithDelay: 0 });

    expect((createStepAndPages as any).mock.calls.length).toBe(1);
    const arg = (createStepAndPages as any).mock.calls[0][0];
    expect(arg.pages).toHaveLength(135);
  }, 60_000);
});

describe("Dynamic link discovery and enqueueing", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  test(
    "should discover and enqueue links using click selector",
    async () => {
      // Mock workers to avoid real Redis usage when enqueueing
      vi.doMock("../src/workers", async () => {
        const actual = await vi.importActual<any>("../src/workers");
        return {
          ...actual,
          getRedisConnection: () => ({
            set: vi.fn().mockResolvedValue("OK"),
            pttl: vi.fn().mockResolvedValue(0),
          }),
          submitJobs: vi.fn().mockResolvedValue([]),
        };
      });

      const { performJob } = await import("../src/workers/fetchPage");
      const module = await import("../src/data/extractions");
      const createStepAndPages = module.createStepAndPages as unknown as ReturnType<typeof vi.fn>;

      const extractionId = 1;
      const crawlStepId = 10;
      const pageId = 1;

      const configuration = {
        pageType: PageType.CATEGORY_LINKS,
        clickSelector: "#body-list-2950 > div",
        links: { pageType: PageType.DETAIL },
      } as any;

      const crawlPage = {
        id: pageId,
        extractionId,
        crawlStepId,
        url: "https://rccd.curriqunet.com/catalog/alias/nc-catalog/iq/2743/2950",
        crawlStep: { step: Step.FETCH_ROOT, configuration },
        extraction: {
          id: 999,
          status: ExtractionStatus.IN_PROGRESS,
          recipe: {
            acknowledgedSkipRobotsTxt: true,
            catalogue: { catalogueType: CatalogueType.COURSES },
            pageLoadWaitTime: 10000,
          },
        },
      } as any;

      const job: any = {
        data: { crawlPageId: pageId, extractionId },
        opts: { jobId: `fetchPage.${pageId}` },
        updateProgress: vi.fn(),
      };

      await performJob(job, crawlPage, { delayInterval: 0, startWithDelay: 0 });

      expect((createStepAndPages as any).mock.calls.length).toBe(1);
      const arg = (createStepAndPages as any).mock.calls[0][0];
      expect(Array.isArray(arg.pages)).toBe(true);
      expect(arg.pages.length).toBeGreaterThan(0);
      // Ensure discovered URLs look valid
      for (const p of arg.pages) {
        expect(typeof p.url).toBe("string");
        expect(p.url).toContain("rccd.curriqunet.com");
      }
    },
    600_000 // 10 minutes
  );
});

