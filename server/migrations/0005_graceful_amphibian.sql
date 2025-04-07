ALTER TYPE "provider_model" ADD VALUE 'o3-mini';--> statement-breakpoint
ALTER TABLE "crawl_pages" DROP CONSTRAINT "crawl_pages_extraction_id_url_unique";--> statement-breakpoint
ALTER TABLE "crawl_pages" ADD COLUMN "step" "step";--> statement-breakpoint
UPDATE crawl_pages
SET step = crawl_steps.step
FROM crawl_steps
WHERE crawl_pages.crawl_step_id = crawl_steps.id;--> statement-breakpoint
ALTER TABLE "crawl_pages" ALTER COLUMN "step" SET NOT NULL;--> statement-breakpoint
ALTER TABLE "crawl_pages" ADD CONSTRAINT "crawl_pages_extraction_id_url_step_unique" UNIQUE("extraction_id","url","step");
