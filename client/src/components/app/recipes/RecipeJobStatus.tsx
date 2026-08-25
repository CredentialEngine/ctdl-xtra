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
import { RecipeDetectionStatus, trpc } from "@/utils";
import { Check, LoaderIcon, RotateCcw, ScrollText } from "lucide-react";
import { useState } from "react";

const STATUS_PREFIX = "<status>";
const STATUS_SUFFIX = "</status>";

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

export default function RecipeJobStatus({ recipeId }: { recipeId: number }) {
  const [jobOutputOpen, setJobOutputOpen] = useState(false);
  const { toast } = useToast();
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

  const recipe = recipeQuery.data;
  const isAgenticJob = jobStatusQuery.data?.kind === "agentic";
  if (!recipe || (recipe.status === RecipeDetectionStatus.SUCCESS && !isAgenticJob)) {
    return null;
  }

  const isAgenticComplete =
    isAgenticJob && recipe.status === RecipeDetectionStatus.SUCCESS;
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
    try {
      if (isAgenticJob) {
        await reconfigureAgenticRecipe.mutateAsync({ id: recipe.id });
      } else {
        await reconfigureRecipe.mutateAsync({ id: recipe.id });
      }
      jobWatcher.resetLogs();
      await recipeQuery.refetch();
    } catch (err) {
      toast({
        title: isAgenticJob
          ? "Could not retry agentic configuration"
          : "Could not redetect configuration",
        description: (err as Error).message,
        variant: "destructive",
      });
    }
  }

  return (
    <>
      {isAgenticJob &&
      recipe.status !== RecipeDetectionStatus.ERROR ? (
        <div className="mt-4 grid gap-2 md:grid-cols-[1fr_250px] lg:grid-cols-2 lg:gap-4">
          <Card>
            <CardHeader>
              <CardDescription>Agentic Configuration</CardDescription>
            </CardHeader>
            <CardContent className="text-sm space-y-2">
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
              {lastStatus ? (
                <p className="font-serif text-muted-foreground">
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
      {recipe.status == RecipeDetectionStatus.WAITING && !isAgenticJob ? (
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
      {recipe.status == RecipeDetectionStatus.ERROR ? (
        <div className="mt-4 grid gap-2 md:grid-cols-[1fr_250px] lg:grid-cols-2 lg:gap-4">
          <Card>
            <CardHeader>
              <CardDescription>Configuration Error</CardDescription>
            </CardHeader>
            <CardContent className="text-sm">
              <p className="text-red-800 font-semibold">
                {isAgenticJob
                  ? "The agentic configuration workflow failed for this recipe."
                  : "CTDL xTRA failed to detect a valid configuration for this recipe."}
              </p>
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
                disabled={
                  reconfigureRecipe.isLoading ||
                  reconfigureAgenticRecipe.isLoading
                }
              >
                <RotateCcw className="w-4 h-4 mr-2" />
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
