ALTER TABLE "data_items" ADD COLUMN "uuid" uuid;--> statement-breakpoint
ALTER TABLE "data_items" ADD CONSTRAINT "data_items_uuid_unique" UNIQUE("uuid");