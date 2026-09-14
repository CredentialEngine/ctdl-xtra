import JobOutputModal from "@/components/app/jobs/JobOutputModal";
import { useJobWatcher } from "@/components/app/jobs/useJobWatcher";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";
import { useToast } from "@/components/ui/use-toast";
import { TimeElapsedText } from "@/useTimeElapsed";
import { cn, RecipeDetectionStatus, trpc } from "@/utils";
import {
  AGENTIC_RECIPE_STAGE_LABELS,
  agenticRecipeStageUiStates,
  latestAgenticRecipeStageFromLogs,
  parseAgenticRecipeStageLog,
  type AgenticRecipeStageUiState,
} from "@common/recipe";
import { anthropicModelLabel } from "@common/anthropicModels";
import {
  AGENTIC_RECIPE_STAGES,
  type AgenticRecipeStage,
} from "@common/types";
import {
  Check,
  ChevronsRight,
  LoaderIcon,
  RotateCcw,
  ScrollText,
} from "lucide-react";
import { useEffect, useState } from "react";

const STATUS_PREFIX = "<status>";
const STATUS_SUFFIX = "</status>";

const STAGE_STATE_STYLES: Record<
  AgenticRecipeStageUiState,
  { row: string; indicator: string; label: string }
> = {
  pending: {
    row: "text-gray-700",
    indicator: "bg-gray-700",
    label: "Pending",
  },
  in_progress: {
    row: "text-yellow-500",
    indicator: "text-yellow-500",
    label: "In progress",
  },
  done: {
    row: "text-green-600",
    indicator: "text-green-600",
    label: "Done",
  },
};

function StageIndicator({ state }: { state: AgenticRecipeStageUiState }) {
  const styles = STAGE_STATE_STYLES[state];
  if (state === "pending") {
    return (
      <span
        className={cn(
          "h-2.5 w-2.5 shrink-0 rounded-full",
          styles.indicator
        )}
        aria-hidden
      />
    );
  }
  if (state === "in_progress") {
    return (
      <ChevronsRight
        className={cn("h-4 w-4 shrink-0", styles.indicator)}
        aria-hidden
      />
    );
  }
  return (
    <Check
      className={cn("h-4 w-4 shrink-0", styles.indicator)}
      aria-hidden
    />
  );
}

function parseStatusLogMessage(line: string): string | null {
  if (!line.startsWith(STATUS_PREFIX)) {
    return null;
  }
  let message = line.slice(STATUS_PREFIX.length);
  if (message.endsWith(STATUS_SUFFIX)) {
    message = message.slice(0, -STATUS_SUFFIX.length);
  }
  message = message.trim();
  return message || null;
}

function renderRecipeJobLogLine(line: string) {
  const stage = parseAgenticRecipeStageLog(line);
  if (stage) {
    return (
      <>
        <em>Stage:</em> {AGENTIC_RECIPE_STAGE_LABELS[stage]}
      </>
    );
  }
  const statusMessage = parseStatusLogMessage(line);
  if (statusMessage) {
    return (
      <>
        <em>Status changed:</em> {statusMessage}
      </>
    );
  }
  return line;
}

function latestStatusFromLogs(logs: string[]): string | null {
  for (let i = logs.length - 1; i >= 0; i--) {
    const statusMessage = parseStatusLogMessage(logs[i]);
    if (statusMessage) {
      return statusMessage;
    }
  }
  return null;
}

function AgenticModelLabel({ model }: { model?: string | null }) {
  if (!model) {
    return null;
  }
  return (
    <p className="text-xs opacity-80">Model: {anthropicModelLabel(model)}</p>
  );
}

function AgenticStageList({
  logs,
  completed,
}: {
  logs: string[];
  completed: boolean;
}) {
  const current = latestAgenticRecipeStageFromLogs(logs);
  const states = agenticRecipeStageUiStates(current, { completed });

  return (
    <ol className="space-y-2">
      {AGENTIC_RECIPE_STAGES.map((stage: AgenticRecipeStage) => {
        const state = states[stage];
        const styles = STAGE_STATE_STYLES[state];
        return (
          <li
            key={stage}
            className={cn("flex items-center gap-2 text-sm", styles.row)}
          >
            <StageIndicator state={state} />
            <span>{AGENTIC_RECIPE_STAGE_LABELS[stage]}</span>
            <span className="sr-only">{styles.label}</span>
          </li>
        );
      })}
    </ol>
  );
}

export default function RecipeJobStatus({ recipeId }: { recipeId: number }) {
  const [jobOutputOpen, setJobOutputOpen] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const { toast } = useToast();
  const utils = trpc.useContext();
  const recipeQuery = trpc.recipes.detail.useQuery(
    { id: recipeId },
    {
      refetchInterval: (data) =>
        data?.status === RecipeDetectionStatus.SUCCESS ? false : 2000,
    }
  );
  const recipeStatus = recipeQuery.data?.status;
  const jobStatusQuery = trpc.recipes.configurationJobStatus.useQuery(
    { recipeId },
    {
      refetchInterval: (data) => {
        if (retrying && !data?.watchKey) {
          return 2000;
        }
        if (data?.watchKey) {
          return false;
        }
        if (
          recipeStatus === RecipeDetectionStatus.WAITING ||
          recipeStatus === RecipeDetectionStatus.IN_PROGRESS
        ) {
          return 2000;
        }
        return false;
      },
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
    }
  );
  const jobWatcher = useJobWatcher(jobStatusQuery.data?.watchKey ?? null);
  const reconfigureRecipe = trpc.recipes.reconfigure.useMutation();
  const reconfigureAgenticRecipe = trpc.recipes.reconfigureAgentic.useMutation();

  useEffect(() => {
    setRetrying(false);
  }, [recipeId]);

  const recipe = recipeQuery.data;
  const isAgenticJob = jobStatusQuery.data?.kind === "agentic";
  const isRetrying =
    retrying ||
    reconfigureRecipe.isLoading ||
    reconfigureAgenticRecipe.isLoading;
  const agenticModel =
    jobStatusQuery.data?.kind === "agentic"
      ? jobStatusQuery.data.model
      : undefined;
  if (!recipe || (recipe.status === RecipeDetectionStatus.SUCCESS && !isAgenticJob)) {
    return null;
  }

  const isAgenticComplete =
    isAgenticJob && recipe.status === RecipeDetectionStatus.SUCCESS;
  const showAgenticRunningCard =
    isAgenticJob &&
    (recipe.status !== RecipeDetectionStatus.ERROR || isRetrying);
  const showDetectPendingCard =
    !showAgenticRunningCard &&
    ((recipe.status === RecipeDetectionStatus.WAITING && !isAgenticJob) ||
      (isRetrying && !isAgenticJob));
  const showErrorCard =
    recipe.status === RecipeDetectionStatus.ERROR && !isRetrying;
  const showOutputButton =
    !isAgenticComplete || jobWatcher.logs.length > 0;
  const lastStatus = latestStatusFromLogs(jobWatcher.logs);
  const elapsedTickMs = jobWatcher.isTerminal ? 0 : 1000;
  const elapsed = (
    <TimeElapsedText
      startTimestamp={jobWatcher.startedAt}
      tickIntervalMs={elapsedTickMs}
    />
  );

  async function onReconfigure() {
    if (!recipe) {
      return;
    }
    const useAgentic = isAgenticJob;
    setRetrying(true);
    jobWatcher.resetLogs();
    try {
      if (useAgentic) {
        const result = await reconfigureAgenticRecipe.mutateAsync({
          id: recipe.id,
        });
        utils.recipes.configurationJobStatus.setData({ recipeId }, {
          kind: "agentic",
          state: "waiting",
          progress: null,
          model: agenticModel,
          ...result,
        });
      } else {
        const result = await reconfigureRecipe.mutateAsync({ id: recipe.id });
        utils.recipes.configurationJobStatus.setData({ recipeId }, {
          kind: "detect",
          state: "waiting",
          progress: null,
          ...result,
        });
      }
      await Promise.all([recipeQuery.refetch(), jobStatusQuery.refetch()]);
      setRetrying(false);
    } catch (err) {
      setRetrying(false);
      toast({
        title: useAgentic
          ? "Could not retry agentic configuration"
          : "Could not redetect configuration",
        description: (err as Error).message,
        variant: "destructive",
      });
    }
  }

  return (
    <>
      {showAgenticRunningCard ? (
        <div className="mt-4 grid gap-2 md:grid-cols-[1fr_250px] lg:grid-cols-2 lg:gap-4">
          <Card>
            <CardHeader>
              <CardDescription>Agentic Configuration</CardDescription>
              <AgenticModelLabel model={agenticModel} />
            </CardHeader>
            <CardContent className="text-sm space-y-3">
              {isAgenticComplete ? (
                <div className="flex items-center">
                  <Check className="mr-2 w-4 h-4" />
                  <span>Agent finished configuring this recipe.</span>
                </div>
              ) : (
                <div className="flex items-center">
                  <LoaderIcon className="animate-spin mr-2 w-4 h-4" />
                  <span>Agent is configuring this recipe…</span>
                </div>
              )}
              <AgenticStageList
                logs={jobWatcher.logs}
                completed={isAgenticComplete}
              />
              {lastStatus ? (
                <p
                  className="font-serif text-muted-foreground line-clamp-6 break-words"
                  title={lastStatus}
                >
                  {lastStatus}
                  {jobWatcher.startedAt ? <> · {elapsed}</> : null}
                </p>
              ) : jobWatcher.startedAt && !isAgenticComplete ? (
                <p className="text-muted-foreground">Running for {elapsed}</p>
              ) : null}
              {showOutputButton ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setJobOutputOpen(true)}
                >
                  <ScrollText className="w-4 h-4 mr-2" />
                  View output
                </Button>
              ) : null}
            </CardContent>
          </Card>
        </div>
      ) : null}
      {showDetectPendingCard ? (
        <div className="mt-4 grid gap-2 md:grid-cols-[1fr_250px] lg:grid-cols-2 lg:gap-4">
          <Card>
            <CardHeader>
              <CardDescription>Configuration Pending</CardDescription>
            </CardHeader>
            <CardContent className="text-sm">
              <p>
                Configuration detection hasn't started for this recipe. Please
                check back later.
              </p>
            </CardContent>
          </Card>
        </div>
      ) : null}
      {showErrorCard ? (
        <div className="mt-4 grid gap-2 md:grid-cols-[1fr_250px] lg:grid-cols-2 lg:gap-4">
          <Card>
            <CardHeader>
              <CardDescription>Configuration Error</CardDescription>
              {isAgenticJob ? (
                <AgenticModelLabel model={agenticModel} />
              ) : null}
            </CardHeader>
            <CardContent className="text-sm">
              <p className="text-red-800 font-semibold">
                {isAgenticJob
                  ? "The agentic configuration workflow failed for this recipe."
                  : "CTDL xTRA failed to detect a valid configuration for this recipe."}
              </p>
              {isAgenticJob ? (
                <div className="mt-4">
                  <AgenticStageList
                    logs={jobWatcher.logs}
                    completed={false}
                  />
                </div>
              ) : null}
              <p className="mt-4">You can adjust the URL, or try again.</p>
              <p className="mt-8">Failure reason:</p>
              <pre className="mt-2 text-xs overflow-x-auto">
                {recipe.detectionFailureReason}
              </pre>
              {jobWatcher.logs.length > 0 ? (
                <Button
                  type="button"
                  className="mt-4"
                  variant="outline"
                  size="sm"
                  onClick={() => setJobOutputOpen(true)}
                >
                  <ScrollText className="w-4 h-4 mr-2" />
                  View output
                </Button>
              ) : null}
              <Button
                type="button"
                className="mt-8"
                variant="outline"
                size="sm"
                onClick={onReconfigure}
                disabled={isRetrying}
              >
                {isRetrying ? (
                  <LoaderIcon className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <RotateCcw className="w-4 h-4 mr-2" />
                )}
                {isAgenticJob
                  ? "Retry agentic configuration"
                  : "Redetect configuration"}
              </Button>
            </CardContent>
          </Card>
        </div>
      ) : null}
      <JobOutputModal
        open={jobOutputOpen && showOutputButton}
        onOpenChange={setJobOutputOpen}
        logs={jobWatcher.logs}
        isRunning={!jobWatcher.isTerminal}
        renderLine={renderRecipeJobLogLine}
      />
    </>
  );
}
