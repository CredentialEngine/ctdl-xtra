DO $$ BEGIN
 ALTER TABLE "datasets" DROP CONSTRAINT "datasets_catalogue_id_extraction_id_unique";
EXCEPTION
 WHEN OTHERS THEN
  IF SQLSTATE = '42704' THEN
    NULL;
  ELSE
    RAISE;
  END IF;
END $$;
--> statement-breakpoint
DO $$ BEGIN
 ALTER TABLE "model_api_calls" ADD COLUMN "dataset_id" integer;
EXCEPTION
 WHEN OTHERS THEN
  IF SQLSTATE = '42701' THEN
    NULL;
  ELSE
    RAISE;
  END IF;
END $$;
--> statement-breakpoint
DO $$ BEGIN
 ALTER TABLE "model_api_calls" ADD CONSTRAINT "model_api_calls_dataset_id_datasets_id_fk" FOREIGN KEY ("dataset_id") REFERENCES "public"."datasets"("id") ON DELETE cascade ON UPDATE no action;
EXCEPTION
 WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "model_api_calls_datasaet_idx" ON "model_api_calls" USING btree ("dataset_id");