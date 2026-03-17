ALTER TABLE "model_api_calls" ADD COLUMN "crawl_page_id" integer;--> statement-breakpoint
DO $$ BEGIN
 ALTER TABLE "model_api_calls" ADD CONSTRAINT "model_api_calls_crawl_page_id_crawl_pages_id_fk" FOREIGN KEY ("crawl_page_id") REFERENCES "public"."crawl_pages"("id") ON DELETE cascade ON UPDATE no action;
EXCEPTION
 WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "model_api_calls_crawl_page_idx" ON "model_api_calls" USING btree ("crawl_page_id");