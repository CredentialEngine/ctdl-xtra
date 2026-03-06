#!/usr/bin/env node
/**
 * Manually run the completion stats update for an extraction.
 * Load server/.env first (run from server dir, or use -r dotenv/config).
 * No Redis or email.
 *
 * Usage:
 *   cd server && pnpm run run:update-completion [extractionId]
 *
 * Example:
 *   cd server && pnpm run run:update-completion 240
 */
(async () => {
  const { runUpdateExtractionCompletion } = await import(
    "../src/workers/updateExtractionCompletion.js"
  );

  const extractionId = parseInt(process.argv[2], 10);
  if (isNaN(extractionId) || extractionId < 1) {
    console.error(
      "Usage: pnpm run run:update-completion <extractionId>"
    );
    process.exit(1);
  }

  try {
    const result = await runUpdateExtractionCompletion(extractionId, null);
    console.log(JSON.stringify(result, null, 2));
  } catch (err) {
    console.error(err);
    process.exit(1);
  }
})();
