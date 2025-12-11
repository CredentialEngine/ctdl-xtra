-- 1) Create institutions table
CREATE TABLE IF NOT EXISTS "institutions" (
  "id" serial PRIMARY KEY NOT NULL,
  "name" text NOT NULL,
  "domains" text[] NOT NULL,
  "created_at" timestamp DEFAULT now() NOT NULL,
  CONSTRAINT "institutions_name_unique" UNIQUE("name")
);
--> statement-breakpoint

-- 2) Add nullable institution_id to catalogues
ALTER TABLE "catalogues" ADD COLUMN IF NOT EXISTS "institution_id" integer;
--> statement-breakpoint

-- 3) Create institutions from catalogue URL domains
-- domain extraction: strip scheme, path, and leading www.
INSERT INTO "institutions" ("name", "domains")
SELECT DISTINCT domain AS name,
       ARRAY[domain] AS domains
FROM (
  SELECT
    NULLIF(
      lower(
        regexp_replace(
          regexp_replace(
            regexp_replace("url", '^https?://', ''),   -- remove scheme
            '/.*$', ''                                 -- remove path/query
          ),
          '^www\.', ''                                 -- strip leading www.
        )
      ),
      ''
    ) AS domain
  FROM "catalogues"
) AS t
WHERE domain IS NOT NULL;
--> statement-breakpoint

-- 4) Set institution_id on catalogues based on URL domain
UPDATE "catalogues" c
SET "institution_id" = i.id
FROM "institutions" i
WHERE lower(
        regexp_replace(
          regexp_replace(
            regexp_replace(c."url", '^https?://', ''),  -- remove scheme
            '/.*$', ''                                 -- remove path/query
          ),
          '^www\.', ''                                 -- strip leading www.
        )
      )
      = ANY(i.domains);
--> statement-breakpoint

-- (Optional safety check)
-- SELECT COUNT(*) FROM "catalogues" WHERE "institution_id" IS NULL;

-- 5) Add FK (nullable is fine at this point)
DO $$
BEGIN
  ALTER TABLE "catalogues"
    ADD CONSTRAINT "catalogues_institution_id_institutions_id_fk"
    FOREIGN KEY ("institution_id")
    REFERENCES "public"."institutions"("id")
    ON DELETE CASCADE
    ON UPDATE NO ACTION;
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;
--> statement-breakpoint

-- 6) Make institution_id NOT NULL once data is consistent
ALTER TABLE "catalogues"
  ALTER COLUMN "institution_id" SET NOT NULL;
