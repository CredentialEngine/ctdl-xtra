import {
  AgenticRecipeStage,
  AGENTIC_RECIPE_STAGES,
  isAgenticRecipeStage,
} from "./types";

/** Completed agentic jobs are kept so recipe pages can still show the agentic card after refresh. */
export const AGENTIC_RECIPE_CONFIG_JOB_RETENTION_MS = 1000 * 60 * 60 * 48; // 48 hours

export const AGENTIC_RECIPE_CONFIG_JOB_RETENTION_HOURS =
  AGENTIC_RECIPE_CONFIG_JOB_RETENTION_MS / (1000 * 60 * 60);

export const AGENTIC_RECIPE_STAGE_LABELS: Record<AgenticRecipeStage, string> = {
  [AgenticRecipeStage.ASSESS_USABILITY]: "Assess catalogue usability",
  [AgenticRecipeStage.MAP_STRUCTURE]: "Map catalogue structure",
  [AgenticRecipeStage.WRITE_CONFIGURATION]: "Write recipe configuration",
  [AgenticRecipeStage.VERIFY_RECIPE]: "Verify recipe",
};

export type AgenticRecipeStageUiState = "pending" | "in_progress" | "done";

const STAGE_LOG_PREFIX = "<stage>";
const STAGE_LOG_SUFFIX = "</stage>";

export function agenticRecipeStageLog(stage: AgenticRecipeStage): string {
  return `${STAGE_LOG_PREFIX}${stage}${STAGE_LOG_SUFFIX}`;
}

export function parseAgenticRecipeStageLog(
  line: string
): AgenticRecipeStage | null {
  const trimmed = line.trim();
  if (
    !trimmed.startsWith(STAGE_LOG_PREFIX) ||
    !trimmed.endsWith(STAGE_LOG_SUFFIX)
  ) {
    return null;
  }
  const value = trimmed.slice(
    STAGE_LOG_PREFIX.length,
    trimmed.length - STAGE_LOG_SUFFIX.length
  );
  return isAgenticRecipeStage(value) ? value : null;
}

export function latestAgenticRecipeStageFromLogs(
  logs: string[]
): AgenticRecipeStage | null {
  for (let i = logs.length - 1; i >= 0; i--) {
    const stage = parseAgenticRecipeStageLog(logs[i]);
    if (stage) {
      return stage;
    }
  }
  return null;
}

export function agenticRecipeStageUiStates(
  current: AgenticRecipeStage | null,
  options?: { completed?: boolean }
): Record<AgenticRecipeStage, AgenticRecipeStageUiState> {
  const states = {} as Record<AgenticRecipeStage, AgenticRecipeStageUiState>;
  if (options?.completed) {
    for (const stage of AGENTIC_RECIPE_STAGES) {
      states[stage] = "done";
    }
    return states;
  }
  const currentIndex = current ? AGENTIC_RECIPE_STAGES.indexOf(current) : -1;
  for (let i = 0; i < AGENTIC_RECIPE_STAGES.length; i++) {
    const stage = AGENTIC_RECIPE_STAGES[i];
    if (currentIndex < 0) {
      states[stage] = "pending";
    } else if (i < currentIndex) {
      states[stage] = "done";
    } else if (i === currentIndex) {
      states[stage] = "in_progress";
    } else {
      states[stage] = "pending";
    }
  }
  return states;
}
