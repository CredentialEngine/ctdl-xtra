ALTER TABLE "recipes" ADD COLUMN "robots_txt" jsonb;--> statement-breakpoint
ALTER TABLE "recipes" ADD COLUMN "acknowledged_skip_robots_txt" boolean;