DO $$ BEGIN ALTER TYPE "provider_model" ADD VALUE 'gpt-6-astra'; EXCEPTION WHEN duplicate_object THEN null; END $$;--> statement-breakpoint
DO $$ BEGIN ALTER TYPE "provider_model" ADD VALUE 'gpt-6.1-sol'; EXCEPTION WHEN duplicate_object THEN null; END $$;--> statement-breakpoint
DO $$ BEGIN ALTER TYPE "provider_model" ADD VALUE 'gpt-6-luna'; EXCEPTION WHEN duplicate_object THEN null; END $$;--> statement-breakpoint
DO $$ BEGIN ALTER TYPE "provider_model" ADD VALUE 'claude-haiku-5-5'; EXCEPTION WHEN duplicate_object THEN null; END $$;--> statement-breakpoint
DO $$ BEGIN ALTER TYPE "provider_model" ADD VALUE 'claude-sonnet-5-5'; EXCEPTION WHEN duplicate_object THEN null; END $$;--> statement-breakpoint
DO $$ BEGIN ALTER TYPE "provider_model" ADD VALUE 'claude-opus-5-5'; EXCEPTION WHEN duplicate_object THEN null; END $$;
