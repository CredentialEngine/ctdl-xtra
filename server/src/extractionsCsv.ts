import { format } from "fast-csv";
import { Transform } from "stream";
import type { CompletionStats } from "../../common/types";
import db, { pool } from "./data";
import QueryStream from "pg-query-stream";
import { and, asc, eq, gte, lte, sql, SQL } from "drizzle-orm";
import { catalogues, dataItems, datasets, extractions, recipes } from "./data/schema";

function buildExtractionsQuery(dateFrom?: Date, dateTo?: Date) {
  const itemsCountByExtraction = db
    .select({
      extractionId: datasets.extractionId,
      itemsCount: sql<number>`COUNT(${dataItems.id})::int`.as("items_count"),
    })
    .from(dataItems)
    .innerJoin(datasets, eq(datasets.id, dataItems.datasetId))
    .groupBy(datasets.extractionId)
    .as("icc");

  const whereClauses: SQL[] = [];
  if (dateFrom) whereClauses.push(gte(extractions.createdAt, dateFrom));
  if (dateTo) whereClauses.push(lte(extractions.createdAt, dateTo));

  return db
    .select({
      id: extractions.id,
      status: extractions.status,
      completion_stats: extractions.completionStats,
      created_at: extractions.createdAt,
      catalogue_name: catalogues.name,
      catalogue_type: catalogues.catalogueType,
      items_count: sql<number>`COALESCE(${itemsCountByExtraction.itemsCount}, 0)::int`,
    })
    .from(extractions)
    .leftJoin(recipes, eq(recipes.id, extractions.recipeId))
    .leftJoin(catalogues, eq(catalogues.id, recipes.catalogueId))
    .leftJoin(itemsCountByExtraction, eq(itemsCountByExtraction.extractionId, extractions.id))
    .where(whereClauses.length ? and(...whereClauses) : undefined)
    .orderBy(asc(extractions.id));
}

type StreamRow = {
  id: number;
  status: string;
  completion_stats: CompletionStats | null;
  created_at: Date;
  catalogue_name: string | null;
  catalogue_type: string | null;
  items_count: number;
};

function streamRowToCsvRow(row: StreamRow): Record<string, string | number> {
  const completionStats = row.completion_stats;
  let totalDownloads = 0;
  let totalDownloadsAttempted = 0;
  let totalExtractionsPossible = 0;
  let totalExtractionsAttempted = 0;

  for (const step of completionStats?.steps || []) {
    totalDownloads += step.downloads.total;
    totalDownloadsAttempted += step.downloads.attempted;
    totalExtractionsPossible += step.downloads.succeeded;
    totalExtractionsAttempted += step.extractions.attempted;
  }

  const downloadsPct =
    totalDownloads > 0
      ? Math.floor((totalDownloadsAttempted / totalDownloads) * 100)
      : 0;
  const extractionsPct =
    totalExtractionsPossible > 0
      ? Math.floor((totalExtractionsAttempted / totalExtractionsPossible) * 100)
      : 0;

  const estimatedCost =
    completionStats?.costs?.estimatedCost != null
      ? completionStats.costs.estimatedCost
      : "";

  return {
    id: row.id,
    catalogue: row.catalogue_name ?? "",
    type: row.catalogue_type ?? "",
    status: row.status,
    downloads_pct: downloadsPct,
    extractions_pct: extractionsPct,
    items_count: row.items_count,
    estimated_cost: estimatedCost,
    created_at:
      row.created_at instanceof Date
        ? row.created_at.toISOString()
        : String(row.created_at),
  };
}

export function streamExtractionsCsv(dateFrom?: Date, dateTo?: Date) {
  const csvFormat = format({ headers: true });
  const { sql: rawSql, params } = buildExtractionsQuery(dateFrom, dateTo).toSQL();

  const rowTransform = new Transform({
    objectMode: true,
    transform(row: StreamRow, _encoding, callback) {
      try {
        callback(null, streamRowToCsvRow(row));
      } catch (err) {
        callback(err as Error);
      }
    },
  });

  pool.connect().then((client) => {
    const queryStream = new QueryStream(rawSql, params as unknown[]);
    const dbStream = client.query(queryStream);

    const releaseClient = () => {
      client.release();
    };

    dbStream.on("end", releaseClient);
    dbStream.on("error", (err) => {
      releaseClient();
      rowTransform.destroy(err);
    });

    dbStream.pipe(rowTransform).pipe(csvFormat);
  }).catch((err) => {
    rowTransform.destroy(err);
  });

  return csvFormat;
}
