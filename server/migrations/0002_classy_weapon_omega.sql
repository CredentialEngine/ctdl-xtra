DO $$ BEGIN
 CREATE TYPE "public"."catalogue_type" AS ENUM('COURSES', 'LEARNING_PROGRAMS');
EXCEPTION
 WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
ALTER TABLE "catalogues" ADD COLUMN "catalogue_type" "catalogue_type" DEFAULT 'COURSES' NOT NULL;