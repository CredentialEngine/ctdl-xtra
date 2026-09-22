export type CrawlStatus =
    "never" | "queued" | "running" | "succeeded" | "failed";
export type DiscoverStatus =
    "not_started" | "queued" | "running" | "succeeded" | "failed";
export type BenchmarkRunStatus = "queued" | "running" | "completed" | "failed";
export type PublishRunStatus = "queued" | "running" | "succeeded" | "failed";

export type OrganizationRef = { id: string; name: string };

export type Source = {
    id: string;
    organizationId: string;
    organizationName: string;
    name: string;
    url: string;
    tags: string[];
    crawlStatus: CrawlStatus;
    lastCrawlAt?: string;
    lastCrawlPages?: number;
    lastCrawlError?: string;
    latestSuccessfulCrawlRunId?: string;
    lkgCrawlRunId?: string;
    goldenSamples: number;
};

export type CrawlStrategy = {
    id: string;
    name: string;
    description: string;
    engine: "playwright" | "ai-agent" | "http" | "custom";
    status: "active" | "archived";
};

export type CrawlRun = {
    id: string;
    sourceId: string;
    sourceName: string;
    strategyId: string;
    strategyName: string;
    status: Exclude<CrawlStatus, "never">;
    progressPercent: number;
    startedAt: string;
    finishedAt?: string;
    pagesCrawled: number;
    pagesFailed: number;
    durationSeconds?: number;
    cacheTimestamp?: string;
    cachePath?: string;
    error?: string;
    discoveryStatus: DiscoverStatus;
    discoveryStartedAt?: string;
    discoveryFinishedAt?: string;
    pagesClassified?: number;
    interestingPages?: number;
    ignoredPages?: number;
    discoveryError?: string;
};

export type DiscoveredPageLabel =
    | "Course"
    | "Learning Opportunity"
    | "Competency"
    | "Credential"
    | "Organization"
    | "Ignore"
    | "Unclassified";

export type DiscoveredPage = {
    id: string;
    sourceId: string;
    crawlRunId: string;
    url: string;
    title: string;
    labels: DiscoveredPageLabel[];
    confidence?: number;
    isGolden: boolean;
    validationStatus?:
        "not_run" | "ready_for_review" | "validated" | "rejected";
};

export type PipelineStage = "extract" | "transform" | "publish-ready";

export type StageArtifact = {
    stage: PipelineStage;
    status: "pending" | "running" | "passed" | "failed" | "review";
    durationMs?: number;
    actualSummary?: string;
    goldenSummary?: string;
};

export type GoldenSample = {
    id: string;
    sourceId: string;
    crawlRunId?: string;
    pageId: string;
    pageTitle: string;
    pageUrl: string;
    labels: DiscoveredPageLabel[];
    promotedAt?: string;
    stages: StageArtifact[];
};

export type StrategyOption = {
    id: string;
    name: string;
    description: string;
};

/** A benchmarkable ETL strategy is a versioned bundle of all three stage choices. */
export type BenchmarkStrategy = {
    id: string;
    name: string;
    description?: string;
    extractOptionId: string;
    transformOptionId: string;
    publishReadyOptionId: string;
    status: "draft" | "active" | "archived";
    createdAt: string;
    lastBenchmarkRunId?: string;
};

/** An admin-approved link that makes a global strategy available to Publishing for one Source. */
export type SourceStrategyAssignment = {
    sourceId: string;
    strategyId: string;
    promotedAt: string;
    promotedBy?: string;
};

export type BenchmarkRun = {
    id: string;
    sourceId: string;
    sourceName: string;
    strategyId: string;
    strategyName: string;
    status: BenchmarkRunStatus;
    startedAt: string;
    finishedAt?: string;
    samples: number;
    passed: number;
    failed: number;
    stagePassRate: number;
    durationSeconds?: number;
};

export type PublishRunStage = {
    stage: "extract" | "transform" | "publish-ready" | "publisher";
    status: "pending" | "running" | "succeeded" | "failed";
    completed: number;
    total: number;
};

export type PublishRun = {
    id: string;
    sourceId: string;
    sourceName: string;
    strategyId: string;
    strategyName: string;
    projectId: string;
    projectName: string;
    status: PublishRunStatus;
    progressPercent: number;
    startedAt: string;
    finishedAt?: string;
    totalPages: number;
    succeededPages: number;
    failedPages: number;
    publisherIterationId?: string;
    stages: PublishRunStage[];
    error?: string;
};
