CREATE TYPE "public"."role_type" AS ENUM('viewer', 'member', 'admin');--> statement-breakpoint
CREATE TABLE "memberships" (
	"org_id" integer NOT NULL,
	"user_id" integer NOT NULL,
	"role" "role_type" DEFAULT 'member'
);
--> statement-breakpoint
CREATE TABLE "orgs" (
	"id" serial PRIMARY KEY NOT NULL,
	"name" text DEFAULT 'null',
	"description" text DEFAULT 'null',
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "catalogues" ADD COLUMN "org_id" integer NOT NULL;--> statement-breakpoint
ALTER TABLE "settings" ADD COLUMN "org_id" integer NOT NULL;--> statement-breakpoint
ALTER TABLE "users" ADD COLUMN "is_staff" boolean DEFAULT false NOT NULL;--> statement-breakpoint
ALTER TABLE "memberships" ADD CONSTRAINT "memberships_org_id_orgs_id_fk" FOREIGN KEY ("org_id") REFERENCES "public"."orgs"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "memberships" ADD CONSTRAINT "memberships_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "catalogues" ADD CONSTRAINT "catalogues_org_id_orgs_id_fk" FOREIGN KEY ("org_id") REFERENCES "public"."orgs"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "settings" ADD CONSTRAINT "settings_org_id_orgs_id_fk" FOREIGN KEY ("org_id") REFERENCES "public"."orgs"("id") ON DELETE no action ON UPDATE no action;