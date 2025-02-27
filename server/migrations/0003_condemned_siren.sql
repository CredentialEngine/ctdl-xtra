ALTER TABLE "catalogues" DROP CONSTRAINT "catalogues_url_unique";--> statement-breakpoint
ALTER TABLE "catalogues" ADD CONSTRAINT "catalogues_url_catalogue_type_unique" UNIQUE("url","catalogue_type");