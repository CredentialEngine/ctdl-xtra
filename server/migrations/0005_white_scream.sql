ALTER TABLE "crawl_pages" RENAME COLUMN "data_type" TO "page_type";--> statement-breakpoint
DROP INDEX IF EXISTS "crawl_pages_data_type_idx";--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "crawl_pages_data_type_idx" ON "crawl_pages" USING btree ("page_type");