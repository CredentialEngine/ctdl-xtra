/**
 * Sample pages query for extractions. Uses raw SQL to ensure correct column
 * aliases (camelCase), data status filtering, and minimal data selection.
 * All filtering, aggregation, and sampling is done in the database.
 */
import { sql } from "drizzle-orm";
import { PageStatus } from "../../../common/types";
import db from ".";

export type SampleSortOption =
  | "random"
  | "most_expensive"
  | "most_data_items"
  | "least_data_items";

const VALID_STATUSES = new Set<string>(Object.values(PageStatus));
const VALID_SORT: SampleSortOption[] = [
  "random",
  "most_expensive",
  "most_data_items",
  "least_data_items",
];

export interface SamplePagesOptions {
  extractionId: number;
  sampleSizePercent: number;
  dataStatus: ("present" | "absent")[];
  statuses: PageStatus[];
  sortBy: SampleSortOption;
}

export interface SampledPageRow {
  id: number;
  extractionId: number;
  crawlStepId: number;
  url: string;
  status: string;
  createdAt: Date;
  dataItemCount: number;
  tokenSum: number;
}

/**
 * Fetches a sampled subset of crawl pages for an extraction.
 * 
 * ```markdown
 * **SQL Injection safety**: Numerical parameters are validated using Zod,
 * if calling this function from outside, make sure to validate the input.
 * ```
 */
export async function findSampledPagesForExtraction(
  opts: SamplePagesOptions
): Promise<SampledPageRow[]> {
  const statuses = (opts.statuses as string[]).filter((s) => VALID_STATUSES.has(s));
  if (statuses.length === 0) {
    return [];
  }

  const sortBy = VALID_SORT.includes(opts.sortBy) ? opts.sortBy : "random";

  const hasPresent = opts.dataStatus.includes("present");
  const hasAbsent = opts.dataStatus.includes("absent");
  const dataStatusFilter =
    (hasPresent && hasAbsent) || (!hasPresent && !hasAbsent)
      ? undefined
      : hasPresent && !hasAbsent
        ? "present"
        : "absent";

  const noDataStatusFilter = dataStatusFilter === undefined;
  const filterPresent = dataStatusFilter === "present";
  const filterAbsent = dataStatusFilter === "absent";

  const statusInClause = sql.join(
    statuses.map((s) => sql`${s}`),
    sql`, `
  );

  /* 
  SQL Injection safety:
  Interpolated parameters are safe to use with Drizzle `sql` function.
  From docs (https://orm.drizzle.team/docs/sql):
    Additionally, any dynamic parameters such as ${id} will be mapped to the $1 placeholder, 
    and the corresponding values will be moved to an array of values that are passed separately to the database. 
    This approach effectively prevents any potential SQL Injection vulnerabilities.
  */
  const result = await db.execute(sql`
    WITH latest_dataset AS (
      SELECT id FROM datasets
      WHERE extraction_id = ${opts.extractionId}
      ORDER BY created_at DESC
      LIMIT 1
    ),
    base AS (
      SELECT
        cp.id,
        cp.extraction_id AS "extractionId",
        cp.crawl_step_id AS "crawlStepId",
        cp.url,
        cp.status,
        cp.created_at AS "createdAt",
        COALESCE((
          SELECT COUNT(*)::integer
          FROM data_items di
          WHERE di.crawl_page_id = cp.id
            AND di.dataset_id = (SELECT id FROM latest_dataset)
        ), 0) AS "dataItemCount",
        COALESCE((
          SELECT SUM(mac.input_token_count + mac.output_token_count)::integer
          FROM model_api_calls mac
          WHERE mac.crawl_page_id = cp.id
        ), 0) AS "tokenSum"
      FROM crawl_pages cp
      WHERE cp.extraction_id = ${opts.extractionId}
        AND cp.status IN (${statusInClause})
        AND (
          ${noDataStatusFilter}
          OR (${filterPresent} AND COALESCE((
            SELECT COUNT(*)::integer FROM data_items di
            WHERE di.crawl_page_id = cp.id
              AND di.dataset_id = (SELECT id FROM latest_dataset)
          ), 0) > 0)
          OR (${filterAbsent} AND COALESCE((
            SELECT COUNT(*)::integer FROM data_items di
            WHERE di.crawl_page_id = cp.id
              AND di.dataset_id = (SELECT id FROM latest_dataset)
          ), 0) = 0)
        )
    ),
    with_total AS (
      SELECT *, COUNT(*) OVER () AS total FROM base
    ),
    numbered AS (
      SELECT *,
        ROW_NUMBER() OVER (
          ORDER BY
            CASE WHEN ${sortBy} = 'random' THEN random() END,
            CASE WHEN ${sortBy} = 'most_expensive' THEN "tokenSum" END DESC NULLS LAST,
            CASE WHEN ${sortBy} = 'most_data_items' THEN "dataItemCount" END DESC NULLS LAST,
            CASE WHEN ${sortBy} = 'least_data_items' THEN "dataItemCount" END ASC NULLS LAST
        ) AS rn
      FROM with_total
    ),
    limited AS (
      SELECT id, "extractionId", "crawlStepId", url, status, "createdAt",
             "dataItemCount", "tokenSum"
      FROM numbered
      WHERE total = 0 OR rn <= GREATEST(0, CEIL(total * ${opts.sampleSizePercent}::float / 100)::integer)
    )
    SELECT id, "extractionId", "crawlStepId", url, status, "createdAt",
           "dataItemCount", "tokenSum"
    FROM limited
    ORDER BY
      CASE WHEN ${sortBy} = 'random' THEN random() END,
      CASE WHEN ${sortBy} = 'most_expensive' THEN "tokenSum" END DESC NULLS LAST,
      CASE WHEN ${sortBy} = 'most_data_items' THEN "dataItemCount" END DESC NULLS LAST,
      CASE WHEN ${sortBy} = 'least_data_items' THEN "dataItemCount" END ASC NULLS LAST
  `);

  return (result.rows ?? []) as unknown as SampledPageRow[];
}
