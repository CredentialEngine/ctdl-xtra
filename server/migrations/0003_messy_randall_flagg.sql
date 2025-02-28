DO $$ BEGIN
 CREATE TYPE "public"."catalogue_type" AS ENUM('COURSES', 'LEARNING_PROGRAMS', 'COMPETENCIES');
EXCEPTION
 WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
BEGIN;
ALTER TYPE "page_type" ADD VALUE 'DETAIL';--> statement-breakpoint
ALTER TYPE "page_type" ADD VALUE 'CATEGORY_LINKS';--> statement-breakpoint
ALTER TYPE "page_type" ADD VALUE 'DETAIL_LINKS';--> statement-breakpoint
COMMIT;
ALTER TABLE "crawl_pages" RENAME COLUMN "data_type" TO "page_type";--> statement-breakpoint
ALTER TABLE "catalogues" DROP CONSTRAINT "catalogues_url_unique";--> statement-breakpoint
DROP INDEX IF EXISTS "crawl_pages_data_type_idx";--> statement-breakpoint
ALTER TABLE "catalogues" ADD COLUMN "catalogue_type" "catalogue_type" DEFAULT 'COURSES' NOT NULL;--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "crawl_pages_data_type_idx" ON "crawl_pages" USING btree ("page_type");--> statement-breakpoint
ALTER TABLE "catalogues" ADD CONSTRAINT "catalogues_url_catalogue_type_unique" UNIQUE("url","catalogue_type");
