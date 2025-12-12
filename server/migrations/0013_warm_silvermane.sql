CREATE TABLE IF NOT EXISTS "extractions_audit_log" (
	"id" serial PRIMARY KEY NOT NULL,
	"extraction_id" integer NOT NULL,
	"user_id" integer,
	"action" varchar(80) NOT NULL,
	"reason" varchar(180),
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
DO $$ BEGIN
 ALTER TABLE "extractions_audit_log" ADD CONSTRAINT "extractions_audit_log_extraction_id_extractions_id_fk" FOREIGN KEY ("extraction_id") REFERENCES "public"."extractions"("id") ON DELETE cascade ON UPDATE no action;
EXCEPTION
 WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
DO $$ BEGIN
 ALTER TABLE "extractions_audit_log" ADD CONSTRAINT "extractions_audit_log_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE cascade ON UPDATE no action;
EXCEPTION
 WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "extractions_audit_log_extraction_idx" ON "extractions_audit_log" USING btree ("extraction_id");--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "extractions_audit_log_user_idx" ON "extractions_audit_log" USING btree ("user_id");