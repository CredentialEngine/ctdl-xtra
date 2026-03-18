DO $$ BEGIN ALTER TYPE "provider_model" ADD VALUE 'gpt-5-nano'; EXCEPTION WHEN duplicate_object THEN null; END $$;--> statement-breakpoint
DO $$ BEGIN ALTER TYPE "provider_model" ADD VALUE 'gpt-5.4'; EXCEPTION WHEN duplicate_object THEN null; END $$;--> statement-breakpoint
DO $$ BEGIN ALTER TYPE "provider_model" ADD VALUE 'gpt-5.4-mini'; EXCEPTION WHEN duplicate_object THEN null; END $$;--> statement-breakpoint
DO $$ BEGIN ALTER TYPE "provider_model" ADD VALUE 'gpt-5.4-nano'; EXCEPTION WHEN duplicate_object THEN null; END $$;