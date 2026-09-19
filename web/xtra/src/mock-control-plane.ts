import type {
    BenchmarkRun,
    CrawlRun,
    CrawlStrategy,
    PublishRun,
    Source,
    DiscoveredPage,
    GoldenSample,
    OrganizationRef,
    StrategyOption,
    BenchmarkStrategy,
    SourceStrategyAssignment,
} from "./domain";

/**
 * Temporary fixture data so the UI can be built independently of backend work.
 * Every consumer should eventually be replaced by the TODO calls noted in the pages.
 */
export const organizations: OrganizationRef[] = [
    { id: "org-credential-engine", name: "Credential Engine" },
    { id: "org-northstar", name: "Northstar Technical College" },
    { id: "org-riverview", name: "Riverview University" },
];

export const sources: Source[] = [
    {
        id: "source-northstar",
        organizationId: "org-northstar",
        organizationName: "Northstar Technical College",
        name: "Northstar Course Source",
        url: "https://source.northstar.example.edu",
        tags: ["higher-ed", "courses"],
        crawlStatus: "running",
        lastCrawlAt: "2026-09-16T18:12:00Z",
        lastCrawlPages: 1248,
        goldenSamples: 31,
        latestSuccessfulCrawlRunId: "crawl-northstar-004",
        lkgCrawlRunId: "crawl-northstar-003",
    },
    {
        id: "source-riverview",
        organizationId: "org-riverview",
        organizationName: "Riverview University",
        name: "Riverview Academic Source",
        url: "https://source.riverview.example.edu",
        tags: ["higher-ed", "pilot"],
        crawlStatus: "failed",
        lastCrawlAt: "2026-09-15T23:40:00Z",
        lastCrawlPages: 118,
        lastCrawlError: "Crawler stopped after repeated 429 responses.",
        goldenSamples: 0,
    },
    {
        id: "source-credential-engine",
        organizationId: "org-credential-engine",
        organizationName: "Credential Engine",
        name: "Credential Engine Public Resources",
        url: "https://credentialengine.org",
        tags: ["internal"],
        crawlStatus: "never",
        goldenSamples: 0,
    },
];

export const crawlStrategies: CrawlStrategy[] = [
    {
        id: "crawl-playwright",
        name: "Playwright",
        description: "Browser-driven crawl for JavaScript-heavy sites.",
        engine: "playwright",
        status: "active",
    },
    {
        id: "crawl-ai-agent",
        name: "AI agent",
        description:
            "Agent-guided crawl for sites requiring adaptive navigation.",
        engine: "ai-agent",
        status: "active",
    },
    {
        id: "crawl-http",
        name: "HTTP crawler",
        description: "Fast direct HTTP crawl for conventional sites.",
        engine: "http",
        status: "active",
    },
];

export const crawlRuns: CrawlRun[] = [
    {
        id: "crawl-northstar-005",
        sourceId: "source-northstar",
        sourceName: "Northstar Course Source",
        strategyId: "crawl-playwright",
        strategyName: "Playwright",
        status: "running",
        progressPercent: 63,
        startedAt: "2026-09-16T22:04:12Z",
        pagesCrawled: 811,
        pagesFailed: 2,
        discoveryStatus: "not_started",
    },
    {
        id: "crawl-northstar-004",
        sourceId: "source-northstar",
        sourceName: "Northstar Course Source",
        strategyId: "crawl-playwright",
        strategyName: "Playwright",
        status: "succeeded",
        progressPercent: 100,
        startedAt: "2026-09-16T18:08:12Z",
        finishedAt: "2026-09-16T18:12:00Z",
        pagesCrawled: 1248,
        pagesFailed: 3,
        durationSeconds: 228,
        cacheTimestamp: "2026-09-16T18:12:00Z",
        cachePath:
            "https://blob.example.net/http-source-northstar-example-edu/2026-09-16T18-12-00Z/",
        discoveryStatus: "succeeded",
        discoveryStartedAt: "2026-09-16T18:12:14Z",
        discoveryFinishedAt: "2026-09-16T18:13:09Z",
        pagesClassified: 1248,
        interestingPages: 492,
        ignoredPages: 756,
    },
    {
        id: "crawl-northstar-003",
        sourceId: "source-northstar",
        sourceName: "Northstar Course Source",
        strategyId: "crawl-ai-agent",
        strategyName: "AI agent",
        status: "succeeded",
        progressPercent: 100,
        startedAt: "2026-09-14T16:32:00Z",
        finishedAt: "2026-09-14T16:35:19Z",
        pagesCrawled: 1219,
        pagesFailed: 0,
        durationSeconds: 199,
        cacheTimestamp: "2026-09-14T16:35:19Z",
        cachePath:
            "https://blob.example.net/http-source-northstar-example-edu/2026-09-14T16-35-19Z/",
        discoveryStatus: "succeeded",
        discoveryStartedAt: "2026-09-14T16:35:30Z",
        discoveryFinishedAt: "2026-09-14T16:36:08Z",
        pagesClassified: 1219,
        interestingPages: 486,
        ignoredPages: 733,
    },
    {
        id: "crawl-northstar-002",
        sourceId: "source-northstar",
        sourceName: "Northstar Course Source",
        strategyId: "crawl-playwright",
        strategyName: "Playwright",
        status: "failed",
        progressPercent: 7,
        startedAt: "2026-09-12T19:02:00Z",
        finishedAt: "2026-09-12T19:02:41Z",
        pagesCrawled: 87,
        pagesFailed: 14,
        durationSeconds: 41,
        error: "Crawler stopped after repeated timeout responses.",
        discoveryStatus: "not_started",
    },
    {
        id: "crawl-riverview-002",
        sourceId: "source-riverview",
        sourceName: "Riverview Academic Source",
        strategyId: "crawl-http",
        strategyName: "HTTP crawler",
        status: "failed",
        progressPercent: 18,
        startedAt: "2026-09-15T23:38:00Z",
        finishedAt: "2026-09-15T23:40:00Z",
        pagesCrawled: 118,
        pagesFailed: 26,
        durationSeconds: 120,
        error: "Crawler stopped after repeated 429 responses.",
        discoveryStatus: "not_started",
    },
];

export const discoveredPages: DiscoveredPage[] = [
    {
        id: "page-101",
        sourceId: "source-northstar",
        crawlRunId: "crawl-northstar-003",
        url: "https://source.northstar.example.edu/courses/cs-101",
        title: "CS 101 — Introduction to Computing",
        labels: ["Course", "Learning Opportunity"],
        confidence: 0.98,
        isGolden: true,
        validationStatus: "validated",
    },
    {
        id: "page-102",
        sourceId: "source-northstar",
        crawlRunId: "crawl-northstar-003",
        url: "https://source.northstar.example.edu/programs/data-science",
        title: "Data Science Certificate",
        labels: ["Learning Opportunity", "Credential"],
        confidence: 0.94,
        isGolden: false,
        validationStatus: "ready_for_review",
    },
    {
        id: "page-103",
        sourceId: "source-northstar",
        crawlRunId: "crawl-northstar-003",
        url: "https://source.northstar.example.edu/outcomes/digital-literacy",
        title: "Digital Literacy Competencies",
        labels: ["Competency"],
        confidence: 0.91,
        isGolden: false,
        validationStatus: "not_run",
    },
    {
        id: "page-104",
        sourceId: "source-northstar",
        crawlRunId: "crawl-northstar-003",
        url: "https://source.northstar.example.edu/sitemap.xml",
        title: "Sitemap",
        labels: ["Ignore"],
        confidence: 0.99,
        isGolden: false,
        validationStatus: "not_run",
    },
];

// Discovery/classification is scoped to a specific crawl cache. The same URL can
// therefore have different labels between crawl runs when a site changes.
discoveredPages.push(
    {
        id: "page-201",
        crawlRunId: "crawl-northstar-004",
        sourceId: "source-northstar",
        url: "https://source.northstar.example.edu/courses/cs-101",
        title: "CS 101 — Introduction to Computing",
        labels: ["Course", "Learning Opportunity"],
        confidence: 0.98,
        isGolden: false,
        validationStatus: "not_run",
    },
    {
        id: "page-202",
        crawlRunId: "crawl-northstar-004",
        sourceId: "source-northstar",
        url: "https://source.northstar.example.edu/programs/data-science",
        title: "Data Science Certificate",
        labels: ["Learning Opportunity", "Credential"],
        confidence: 0.93,
        isGolden: false,
        validationStatus: "not_run",
    },
    {
        id: "page-203",
        crawlRunId: "crawl-northstar-004",
        sourceId: "source-northstar",
        url: "https://source.northstar.example.edu/outcomes/digital-literacy",
        title: "Digital Literacy Competencies",
        labels: ["Unclassified"],
        confidence: 0.42,
        isGolden: false,
        validationStatus: "not_run",
    },
    {
        id: "page-204",
        crawlRunId: "crawl-northstar-004",
        sourceId: "source-northstar",
        url: "https://source.northstar.example.edu/",
        title: "Northstar Technical College",
        labels: ["Ignore"],
        confidence: 0.99,
        isGolden: false,
        validationStatus: "not_run",
    },
    {
        id: "page-205",
        crawlRunId: "crawl-northstar-004",
        sourceId: "source-northstar",
        url: "https://source.northstar.example.edu/catalog",
        title: "Course Catalog",
        labels: ["Unclassified"],
        confidence: 0.51,
        isGolden: false,
        validationStatus: "not_run",
    },
);

export function getEffectiveCrawlRunId(sourceId: string) {
    const source = sources.find((item) => item.id === sourceId);
    if (!source) return undefined;
    if (source.lkgCrawlRunId) return source.lkgCrawlRunId;
    return crawlRuns
        .filter(
            (run) => run.sourceId === sourceId && run.status === "succeeded",
        )
        .sort(
            (a, b) =>
                new Date(
                    b.cacheTimestamp ?? b.finishedAt ?? b.startedAt,
                ).getTime() -
                new Date(
                    a.cacheTimestamp ?? a.finishedAt ?? a.startedAt,
                ).getTime(),
        )[0]?.id;
}

export function getEffectiveDiscoveredPages(sourceId: string) {
    const crawlRunId = getEffectiveCrawlRunId(sourceId);
    if (!crawlRunId) return [];
    return discoveredPages.filter(
        (page) => page.sourceId === sourceId && page.crawlRunId === crawlRunId,
    );
}

export const goldenSamples: GoldenSample[] = [
    {
        id: "golden-101",
        sourceId: "source-northstar",
        crawlRunId: "crawl-northstar-003",
        pageId: "page-101",
        pageTitle: "CS 101 — Introduction to Computing",
        pageUrl: "https://source.northstar.example.edu/courses/cs-101",
        labels: ["Course", "Learning Opportunity"],
        promotedAt: "2026-09-12T20:15:00Z",
        stages: [
            {
                stage: "extract",
                status: "passed",
                durationMs: 780,
                actualSummary: "Course fields extracted",
                goldenSummary: "Course fields extracted",
            },
            {
                stage: "transform",
                status: "passed",
                durationMs: 120,
                actualSummary: "CTDL course payload",
                goldenSummary: "CTDL course payload",
            },
            {
                stage: "publish-ready",
                status: "passed",
                durationMs: 76,
                actualSummary: "Validated envelope",
                goldenSummary: "Validated envelope",
            },
        ],
    },
];

export const benchmarkRuns: BenchmarkRun[] = [
    {
        id: "bench-2026-09-16-01",
        sourceId: "source-northstar",
        sourceName: "Northstar Course Source",
        status: "completed",
        startedAt: "2026-09-16T18:30:00Z",
        finishedAt: "2026-09-16T18:31:42Z",
        strategyId: "strategy-northstar-course-v3",
        strategyName: "Course pipeline v3",
        samples: 31,
        passed: 30,
        failed: 1,
        stagePassRate: 98.9,
        durationSeconds: 102,
    },
    {
        id: "bench-2026-09-15-03",
        sourceId: "source-northstar",
        sourceName: "Northstar Course Source",
        status: "completed",
        startedAt: "2026-09-15T21:04:00Z",
        finishedAt: "2026-09-15T21:05:26Z",
        strategyId: "strategy-northstar-course-v2",
        strategyName: "Course pipeline v2",
        samples: 30,
        passed: 27,
        failed: 3,
        stagePassRate: 95.6,
        durationSeconds: 86,
    },
    {
        id: "bench-2026-09-16-02",
        sourceId: "source-northstar",
        sourceName: "Northstar Course Source",
        status: "running",
        startedAt: "2026-09-16T21:47:00Z",
        strategyId: "strategy-northstar-general",
        strategyName: "General structured pipeline",
        samples: 31,
        passed: 18,
        failed: 1,
        stagePassRate: 96.2,
        durationSeconds: 0,
    },
    {
        id: "bench-2026-09-14-01",
        sourceId: "source-northstar",
        sourceName: "Northstar Course Source",
        status: "failed",
        startedAt: "2026-09-14T19:12:00Z",
        finishedAt: "2026-09-14T19:12:18Z",
        strategyId: "strategy-northstar-course-v2",
        strategyName: "Course pipeline v2",
        samples: 30,
        passed: 0,
        failed: 0,
        stagePassRate: 0,
        durationSeconds: 18,
    },
];

export const extractStrategies: StrategyOption[] = [
    {
        id: "extract-default",
        name: "Default extractor",
        description: "General purpose structured extraction.",
    },
    {
        id: "extract-course",
        name: "Course-focused extractor",
        description: "Optimized for course and learning opportunity pages.",
    },
];

export const transformStrategies: StrategyOption[] = [
    {
        id: "transform-ctdl",
        name: "CTDL transform",
        description: "Maps extracted content into CTDL-shaped data.",
    },
    {
        id: "transform-strict",
        name: "Strict CTDL transform",
        description: "Applies stricter normalization and validation.",
    },
];

export const publishStrategies: StrategyOption[] = [
    {
        id: "publish-project",
        name: "Registry project envelope",
        description: "Builds the final project-ready publishing envelope.",
    },
    {
        id: "publish-dry-run",
        name: "Validation-only envelope",
        description: "Builds publish-ready records without sending them.",
    },
];

export const benchmarkStrategies: BenchmarkStrategy[] = [
    {
        id: "strategy-northstar-course-v3",
        name: "Course pipeline v3",
        description:
            "Current candidate strategy for course and learning-opportunity pages.",
        extractOptionId: "extract-course",
        transformOptionId: "transform-strict",
        publishReadyOptionId: "publish-project",
        status: "active",
        createdAt: "2026-09-10T17:10:00Z",
        lastBenchmarkRunId: "bench-2026-09-16-01",
    },
    {
        id: "strategy-northstar-course-v2",
        name: "Course pipeline v2",
        description:
            "Previous extractor with the standard CTDL transformation.",
        extractOptionId: "extract-course",
        transformOptionId: "transform-ctdl",
        publishReadyOptionId: "publish-project",
        status: "active",
        createdAt: "2026-09-08T16:30:00Z",
        lastBenchmarkRunId: "bench-2026-09-15-03",
    },
    {
        id: "strategy-northstar-general",
        name: "General structured pipeline",
        description: "Baseline strategy using the general-purpose extractor.",
        extractOptionId: "extract-default",
        transformOptionId: "transform-ctdl",
        publishReadyOptionId: "publish-project",
        status: "active",
        createdAt: "2026-09-06T20:00:00Z",
    },
];

export const sourceStrategyAssignments: SourceStrategyAssignment[] = [
    {
        sourceId: "source-northstar",
        strategyId: "strategy-northstar-course-v3",
        promotedAt: "2026-09-16T19:05:00Z",
        promotedBy: "admin@example.org",
    },
];

export const publishRuns: PublishRun[] = [
    {
        id: "publish-2026-09-16-03",
        sourceId: "source-northstar",
        sourceName: "Northstar Course Source",
        strategyId: "strategy-northstar-course-v3",
        strategyName: "Course pipeline v3",
        projectId: "project-registry-101",
        projectName: "Northstar Registry Project",
        status: "running",
        progressPercent: 71,
        startedAt: "2026-09-16T22:20:00Z",
        totalPages: 486,
        succeededPages: 332,
        failedPages: 3,
        stages: [
            {
                stage: "extract",
                status: "succeeded",
                completed: 486,
                total: 486,
            },
            {
                stage: "transform",
                status: "succeeded",
                completed: 486,
                total: 486,
            },
            {
                stage: "publish-ready",
                status: "running",
                completed: 352,
                total: 486,
            },
            {
                stage: "publisher",
                status: "running",
                completed: 332,
                total: 486,
            },
        ],
    },
    {
        id: "publish-2026-09-15-01",
        sourceId: "source-northstar",
        sourceName: "Northstar Course Source",
        strategyId: "strategy-northstar-course-v3",
        strategyName: "Course pipeline v3",
        projectId: "project-registry-101",
        projectName: "Northstar Registry Project",
        status: "succeeded",
        progressPercent: 100,
        startedAt: "2026-09-15T19:00:00Z",
        finishedAt: "2026-09-15T19:11:42Z",
        totalPages: 472,
        succeededPages: 472,
        failedPages: 0,
        publisherIterationId: "iteration-2481",
        stages: [
            {
                stage: "extract",
                status: "succeeded",
                completed: 472,
                total: 472,
            },
            {
                stage: "transform",
                status: "succeeded",
                completed: 472,
                total: 472,
            },
            {
                stage: "publish-ready",
                status: "succeeded",
                completed: 472,
                total: 472,
            },
            {
                stage: "publisher",
                status: "succeeded",
                completed: 472,
                total: 472,
            },
        ],
    },
    {
        id: "publish-2026-09-14-02",
        sourceId: "source-northstar",
        sourceName: "Northstar Course Source",
        strategyId: "strategy-northstar-course-v2",
        strategyName: "Course pipeline v2",
        projectId: "project-registry-101",
        projectName: "Northstar Registry Project",
        status: "failed",
        progressPercent: 44,
        startedAt: "2026-09-14T18:10:00Z",
        finishedAt: "2026-09-14T18:15:20Z",
        totalPages: 470,
        succeededPages: 190,
        failedPages: 17,
        error: "Publisher endpoint rejected a batch after validation failures.",
        stages: [
            {
                stage: "extract",
                status: "succeeded",
                completed: 470,
                total: 470,
            },
            {
                stage: "transform",
                status: "succeeded",
                completed: 470,
                total: 470,
            },
            {
                stage: "publish-ready",
                status: "succeeded",
                completed: 470,
                total: 470,
            },
            {
                stage: "publisher",
                status: "failed",
                completed: 190,
                total: 470,
            },
        ],
    },
];
