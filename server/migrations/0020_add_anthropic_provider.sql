DO $$ BEGIN ALTER TYPE "provider" ADD VALUE 'anthropic'; EXCEPTION WHEN duplicate_object THEN null; END $$;--> statement-breakpoint
DO $$ BEGIN ALTER TYPE "provider_model" ADD VALUE 'claude-haiku-4-5'; EXCEPTION WHEN duplicate_object THEN null; END $$;--> statement-breakpoint
DO $$ BEGIN ALTER TYPE "provider_model" ADD VALUE 'claude-sonnet-5'; EXCEPTION WHEN duplicate_object THEN null; END $$;--> statement-breakpoint
DO $$ BEGIN ALTER TYPE "provider_model" ADD VALUE 'claude-opus-5'; EXCEPTION WHEN duplicate_object THEN null; END $$;--> statement-breakpoint
DO $$ BEGIN ALTER TYPE "provider_model" ADD VALUE 'claude-fable-5-1'; EXCEPTION WHEN duplicate_object THEN null; END $$;
