/** Completed agentic jobs are kept so recipe pages can still show the agentic card after refresh. */
export const AGENTIC_RECIPE_CONFIG_JOB_RETENTION_MS = 1000 * 60 * 60 * 48; // 48 hours

export const AGENTIC_RECIPE_CONFIG_JOB_RETENTION_HOURS =
  AGENTIC_RECIPE_CONFIG_JOB_RETENTION_MS / (1000 * 60 * 60);
