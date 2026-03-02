ALTER TABLE "extraction_logs" ADD COLUMN "crawl_page_id" integer;--> statement-breakpoint
DO $$ BEGIN
 ALTER TABLE "extraction_logs" ADD CONSTRAINT "extraction_logs_crawl_page_id_crawl_pages_id_fk" FOREIGN KEY ("crawl_page_id") REFERENCES "public"."crawl_pages"("id") ON DELETE cascade ON UPDATE no action;
EXCEPTION
 WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "extraction_logs_crawl_page_idx" ON "extraction_logs" USING btree ("crawl_page_id");