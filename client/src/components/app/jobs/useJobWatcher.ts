import { trpc } from "@/utils";
import { useEffect, useRef, useState } from "react";

const TERMINAL_JOB_STATES = new Set(["completed", "failed"]);

export function isTerminalJobState(state: string | undefined): boolean {
  return !!state && TERMINAL_JOB_STATES.has(state);
}

/**
 * Watches a job identified by `watchKey` (queue name and job id).
 *
 * Logs and status are fetched once when a key is present. Pass `poll: true`
 * to keep polling until the job reaches a terminal state.
 */
export function useJobWatcher(
  watchKey: string | null | undefined,
  options?: { poll?: boolean }
) {
  const poll = options?.poll ?? false;
  const utils = trpc.useContext();
  const [logs, setLogs] = useState<string[]>([]);
  const [suppressed, setSuppressed] = useState(false);
  const consumedUpdatedAt = useRef(0);
  const watching = !!watchKey && !suppressed;

  useEffect(() => {
    setLogs([]);
    consumedUpdatedAt.current = 0;
    setSuppressed(false);
  }, [watchKey]);

  useEffect(() => {
    if (!suppressed || !watchKey) {
      return;
    }
    void utils.jobWatching.logs.cancel();
    void utils.jobWatching.logs.reset();
    void utils.jobWatching.status.cancel();
    void utils.jobWatching.status.reset({ watchKey });
  }, [suppressed, watchKey]);

  const statusQuery = trpc.jobWatching.status.useQuery(
    { watchKey: watchKey ?? "" },
    {
      enabled: watching,
      refetchInterval: (data) =>
        poll && watching && !isTerminalJobState(data?.state) ? 2000 : false,
      refetchOnWindowFocus: poll,
      refetchOnReconnect: poll,
      retry: false,
    }
  );

  const isTerminal =
    !suppressed && isTerminalJobState(statusQuery.data?.state);

  const logsQuery = trpc.jobWatching.logs.useQuery(
    { watchKey: watchKey ?? "", startLineIndex: logs.length },
    {
      enabled: watching,
      refetchInterval:
        poll && watching && !isTerminal && !statusQuery.isError ? 2000 : false,
      refetchOnWindowFocus: poll,
      refetchOnReconnect: poll,
      retry: false,
    }
  );

  useEffect(() => {
    if (!watching || !logsQuery.data) {
      return;
    }
    if (logsQuery.dataUpdatedAt <= consumedUpdatedAt.current) {
      return;
    }
    consumedUpdatedAt.current = logsQuery.dataUpdatedAt;
    if (logsQuery.data.logs.length === 0) {
      return;
    }
    setLogs((prev) => [...prev, ...logsQuery.data.logs]);
  }, [watching, logsQuery.data, logsQuery.dataUpdatedAt]);

  const refetchLogs = logsQuery.refetch;
  useEffect(() => {
    if (!poll || !isTerminal || !watching) {
      return;
    }
    void refetchLogs();
  }, [poll, isTerminal, watching, refetchLogs]);

  return {
    watchKey: watchKey ?? null,
    status: suppressed ? null : statusQuery.data ?? null,
    logs,
    logText: logs.join("\n"),
    isTerminal,
    startedAt: suppressed ? null : statusQuery.data?.startedAt ?? null,
    isError: !suppressed && (statusQuery.isError || logsQuery.isError),
    resetLogs: () => {
      setLogs([]);
      consumedUpdatedAt.current = Date.now();
      setSuppressed(true);
      if (!watchKey) {
        return;
      }
      void utils.jobWatching.logs.cancel();
      void utils.jobWatching.status.cancel();
    },
    resumeWatching: () => {
      setSuppressed(false);
    },
  };
}
