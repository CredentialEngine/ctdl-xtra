import { trpc } from "@/utils";
import { useEffect, useRef, useState } from "react";

const TERMINAL_JOB_STATES = new Set(["completed", "failed"]);

export function isTerminalJobState(state: string | undefined): boolean {
  return !!state && TERMINAL_JOB_STATES.has(state);
}

/**
 * Watches a job identified by `watchKey` (queue name and job id) using polling.
 *
 * @param watchKey Queue and job id, or null/undefined to stop watching.
 */
export function useJobWatcher(watchKey: string | null | undefined) {
  const utils = trpc.useContext();
  const [logs, setLogs] = useState<string[]>([]);
  const consumedUpdatedAt = useRef(0);

  useEffect(() => {
    setLogs([]);
    consumedUpdatedAt.current = 0;
  }, [watchKey]);

  const statusQuery = trpc.jobWatching.status.useQuery(
    { watchKey: watchKey ?? "" },
    {
      enabled: !!watchKey,
      refetchInterval: (data) =>
        isTerminalJobState(data?.state) ? false : 2000,
      retry: false,
    }
  );

  const isTerminal = isTerminalJobState(statusQuery.data?.state);

  const logsQuery = trpc.jobWatching.logs.useQuery(
    { watchKey: watchKey ?? "", startLineIndex: logs.length },
    {
      enabled: !!watchKey && !statusQuery.isError,
      refetchInterval: isTerminal || statusQuery.isError ? false : 2000,
      retry: false,
    }
  );

  useEffect(() => {
    if (!watchKey || !logsQuery.data) {
      return;
    }
    if (logsQuery.dataUpdatedAt === consumedUpdatedAt.current) {
      return;
    }
    consumedUpdatedAt.current = logsQuery.dataUpdatedAt;
    if (logsQuery.data.logs.length === 0) {
      return;
    }
    setLogs((prev) => [...prev, ...logsQuery.data.logs]);
  }, [watchKey, logsQuery.data, logsQuery.dataUpdatedAt]);

  const refetchLogs = logsQuery.refetch;
  useEffect(() => {
    if (!isTerminal || !watchKey) {
      return;
    }
    void refetchLogs();
  }, [isTerminal, watchKey, refetchLogs]);

  return {
    watchKey: watchKey ?? null,
    status: statusQuery.data ?? null,
    logs,
    logText: logs.join("\n"),
    isTerminal,
    startedAt: statusQuery.data?.startedAt ?? null,
    isError: statusQuery.isError || logsQuery.isError,
    resetLogs: () => {
      setLogs([]);
      consumedUpdatedAt.current = 0;
      if (!watchKey) {
        return;
      }
      void utils.jobWatching.logs.invalidate();
      void utils.jobWatching.status.invalidate({ watchKey });
    },
  };
}
