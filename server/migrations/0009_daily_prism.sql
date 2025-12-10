ALTER TABLE "recipes" ADD COLUMN "description" text;--> statement-breakpoint
ALTER TABLE "recipes" ADD COLUMN "name" text;--> statement-breakpoint
ALTER TABLE "recipes" ADD COLUMN "is_template" boolean DEFAULT false NOT NULL;--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "recipes_template_idx" ON "recipes" USING btree ("is_template","catalogue_id");
