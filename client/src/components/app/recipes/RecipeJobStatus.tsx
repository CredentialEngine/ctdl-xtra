import JobOutputModal from "@/components/app/jobs/JobOutputModal";
import {
  isTerminalJobState,
  useJobWatcher,
} from "@/components/app/jobs/useJobWatcher";
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
import { Fragment, useEffect, useState, type ReactNode } from "react";

const STATUS_PREFIX = "<status>";
const STATUS_SUFFIX = "</status>";
const TOOL_PREFIX = "<tool>";
const TOOL_SUFFIX = "</tool>";

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

function parseTaggedLogMessage(
  line: string,
  prefix: string,
  suffix: string
): string | null {
  if (!line.startsWith(prefix)) {
    return null;
  }
  let message = line.slice(prefix.length);
  if (message.endsWith(suffix)) {
    message = message.slice(0, -suffix.length);
  }
  message = message.trim();
  return message || null;
}

function parseStatusLogMessage(line: string): string | null {
  return parseTaggedLogMessage(line, STATUS_PREFIX, STATUS_SUFFIX);
}

function isStageOrStatusLog(line: string): boolean {
  return (
    parseAgenticRecipeStageLog(line) !== null ||
    parseStatusLogMessage(line) !== null
  );
}

function parseToolLogMessage(line: string): string | null {
  return parseTaggedLogMessage(line, TOOL_PREFIX, TOOL_SUFFIX);
}

function isSafeHttpUrl(href: string): boolean {
  try {
    const url = new URL(href);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

function renderInlineMarkdown(text: string, keyPrefix = "md"): ReactNode {
  const pattern = /\[([^\]]*)\]\(([^)]+)\)|`([^`]+)`|\*\*(.+?)\*\*/g;
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let matchIndex = 0;
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > lastIndex) {
      nodes.push(
        <Fragment key={`${keyPrefix}-t-${matchIndex}`}>
          {text.slice(lastIndex, index)}
        </Fragment>
      );
    }
    const key = `${keyPrefix}-${matchIndex}`;
    if (match[2] !== undefined) {
      const href = match[2];
      const label = match[1] ?? "";
      if (isSafeHttpUrl(href)) {
        nodes.push(
          <a
            key={key}
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="underline underline-offset-2 hover:opacity-80"
          >
            {renderInlineMarkdown(label, key)}
          </a>
        );
      } else {
        nodes.push(<Fragment key={key}>{match[0]}</Fragment>);
      }
    } else if (match[3] !== undefined) {
      nodes.push(
        <pre key={key} className="inline whitespace-pre-wrap font-mono">
          {match[3]}
        </pre>
      );
    } else {
      nodes.push(
        <strong key={key}>
          {renderInlineMarkdown(match[4] ?? "", key)}
        </strong>
      );
    }
    lastIndex = index + match[0].length;
    matchIndex += 1;
  }
  if (lastIndex < text.length) {
    nodes.push(
      <Fragment key={`${keyPrefix}-t-end`}>{text.slice(lastIndex)}</Fragment>
    );
  }
  return nodes;
}

function renderRecipeJobLogLine(line: string) {
  const stage = parseAgenticRecipeStageLog(line);
  if (stage) {
    return (
      <>
        <em className="text-yellow-800">Stage:</em>{" "}
        {AGENTIC_RECIPE_STAGE_LABELS[stage]}
      </>
    );
  }
  const statusMessage = parseStatusLogMessage(line);
  if (statusMessage) {
    return (
      <>
        <em className="text-green-800">Status changed:</em>{" "}
        {renderInlineMarkdown(statusMessage)}
      </>
    );
  }
  const toolMessage = parseToolLogMessage(line);
  if (toolMessage) {
    return (
      <>
        <em className="text-fuchsia-700">Tool:</em>{" "}
        {renderInlineMarkdown(toolMessage)}
      </>
    );
  }
  return renderInlineMarkdown(line);
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
  const [pollJob, setPollJob] = useState(false);
  const { toast } = useToast();
  const utils = trpc.useContext();
  const recipeQuery = trpc.recipes.detail.useQuery(
    { id: recipeId },
    {
      refetchInterval: (data) => {
        if (retrying) {
          return 2000;
        }
        if (
          data?.status === RecipeDetectionStatus.WAITING ||
          data?.status === RecipeDetectionStatus.IN_PROGRESS
        ) {
          return 2000;
        }
        return false;
      },
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
  const jobIsActive =
    !!jobStatusQuery.data?.state &&
    !isTerminalJobState(jobStatusQuery.data.state);
  const jobWatcher = useJobWatcher(jobStatusQuery.data?.watchKey ?? null, {
    poll: pollJob || jobIsActive,
  });
  const reconfigureRecipe = trpc.recipes.reconfigure.useMutation();
  const reconfigureAgenticRecipe = trpc.recipes.reconfigureAgentic.useMutation();

  useEffect(() => {
    setRetrying(false);
    setPollJob(false);
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
    setPollJob(true);
    jobWatcher.resetLogs();
    utils.recipes.detail.setData({ id: recipeId }, (current) =>
      current
        ? {
            ...current,
            status: RecipeDetectionStatus.WAITING,
            detectionFailureReason: null,
          }
        : current
    );
    try {
      if (useAgentic) {
        const result = await reconfigureAgenticRecipe.mutateAsync({
          id: recipe.id,
        });
        utils.recipes.configurationJobStatus.setData({ recipeId }, {
          kind: "agentic",
          state: "waiting",
          progress: null,
          model: agenticModel ?? "",
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
      jobWatcher.resumeWatching();
      await Promise.all([recipeQuery.refetch(), jobStatusQuery.refetch()]);
      setRetrying(false);
    } catch (err) {
      setPollJob(false);
      jobWatcher.resumeWatching();
      setRetrying(false);
      await Promise.all([recipeQuery.refetch(), jobStatusQuery.refetch()]);
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
                  {renderInlineMarkdown(lastStatus)}
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
        isStageOrStatusLine={isStageOrStatusLog}
      />
    </>
  );
}
